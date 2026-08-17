#!/usr/bin/env python3
"""run.py — the minimum run-management interface.

    python3 scripts/run.py new [--note ...]
    python3 scripts/run.py list
    python3 scripts/run.py status            --run <run_id>
    python3 scripts/run.py record-decision   --run <run_id> --id <decision_id> --by <who>
                                             [--value-json '{...}'] [--note ...]
    python3 scripts/run.py register-artifact --run <run_id> --key <key> --path <path>
    python3 scripts/run.py set               --run <run_id> --path <p> (--value X | --value-json J)
    python3 scripts/run.py review-inputs     --run <run_id>
    python3 scripts/run.py validate          --run <run_id> [--to <STATE>]
    python3 scripts/run.py transition        --run <run_id> --to <STATE>

WHY THIS EXISTS
The state file is never hand-edited. Every mutation goes through this interface, and every
requested transition SHELLS OUT to scripts/validate_state.py as a real subprocess whose exit
code is honoured. An agent operating this interface cannot fabricate a passing transition:
the canonical state is only replaced after the external validator exits 0.

ATOMIC TRANSITION
  1. build the proposed state in memory
  2. write it to <run_dir>/.state.proposed.yaml
  3. run validate_state.py against the PROPOSED file with --to <target>
  4. on exit 0: stamp the new state and os.replace() it over state.yaml
  5. on non-zero: print the validator's own output, delete the proposal, leave state.yaml
     byte-identical, and exit non-zero
"""
import argparse, copy, datetime, glob, hashlib, json, os, shutil, subprocess, sys, tempfile
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # sibling scripts (receipt_ingest…)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RUNS = os.environ.get("SHOPYA_CAMPAIGN_RUNS", os.path.join(ROOT, "campaigns"))
SCHEMA = os.path.join(ROOT, "schemas", "workflow_state.schema.yaml")
CHARTER = os.path.join(ROOT, "SHOPYA_CAMPAIGN_CHARTER.yaml")
VALIDATOR = os.path.join(HERE, "validate_state.py")

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
QUARANTINE = "_to_delete"     # never a run, never an artifact source
DRAFTS = "_drafts"            # unnamed runs live here until campaign_id is locked (promote)


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ulid():
    ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
    t = "".join(CROCKFORD[(ms >> (5 * i)) & 31] for i in range(9, -1, -1))
    rb = int.from_bytes(os.urandom(10), "big")
    r = "".join(CROCKFORD[(rb >> (5 * i)) & 31] for i in range(15, -1, -1))
    return t + r


def load(p):
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def atomic_write(path, doc):
    """Write via a same-directory temp file + os.replace. Never a partial state.yaml."""
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".state.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(doc, f, sort_keys=False, default_flow_style=False, allow_unicode=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def run_dir(run_id):
    """Resolve a run directory across the supported layouts (NAMING_CONVENTIONS.md):
       campaigns/<campaign_id>/runs/<run_id>   named, post-promotion
       campaigns/_drafts/<run_id>              unnamed, pre-promotion
       campaigns/<run_id>                      legacy flat layout
    """
    cands = [os.path.join(RUNS, run_id), os.path.join(RUNS, DRAFTS, run_id)]
    cands += sorted(glob.glob(os.path.join(RUNS, "*", "runs", run_id)))
    for c in cands:
        rel = os.path.relpath(c, RUNS)
        if QUARANTINE in rel.split(os.sep):
            continue
        if os.path.isdir(c):
            return c
    return os.path.join(RUNS, DRAFTS, run_id)


def all_run_dirs():
    """Every run directory across all layouts, quarantine excluded."""
    out = []
    if not os.path.isdir(RUNS):
        return out
    for r in sorted(os.listdir(RUNS)):
        if r == QUARANTINE:
            continue
        base = os.path.join(RUNS, r)
        if not os.path.isdir(base):
            continue
        if r == DRAFTS:
            out += [os.path.join(base, x) for x in sorted(os.listdir(base))]
        elif os.path.isdir(os.path.join(base, "runs")):
            rb = os.path.join(base, "runs")
            out += [os.path.join(rb, x) for x in sorted(os.listdir(rb))]
        else:
            out.append(base)
    return [d for d in out if os.path.exists(os.path.join(d, "state.yaml"))]


def state_path(run_id):
    return os.path.join(run_dir(run_id), "state.yaml")


def require_run(run_id):
    p = state_path(run_id)
    if not os.path.exists(p):
        sys.exit("FATAL: no state file for run %r (%s)" % (run_id, p))
    return load(p)


def call_validator(sp, to=None, as_json=False, run_dir=None):
    cmd = [sys.executable, VALIDATOR, "--state", sp, "--schema", SCHEMA,
           "--charter", CHARTER, "--runs-dir", RUNS]
    if run_dir:
        cmd += ["--run-dir", run_dir]
    if to:
        cmd += ["--to", to]
    if as_json:
        cmd += ["--json"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


# ─────────────────────────────── commands ───────────────────────────────

def cmd_new(a):
    schema = load(SCHEMA)
    charter = load(CHARTER)
    rid = "cmp_" + ulid()
    d = os.path.join(RUNS, DRAFTS, rid)   # unnamed at NEW; promoted when campaign_id locks
    os.makedirs(d, exist_ok=False)
    spec_v = schema["schema"]["version"]
    chart_v = charter["charter"]["version"]
    # run_mode is a run-level identity, set ONCE here and immutable. Normal /new-campaign
    # is production; --diagnostic creates a sanctioned below-Foundation diagnostic run.
    run_mode = "diagnostic" if getattr(a, "diagnostic", False) else "production"
    st = {
        "run": {"run_id": rid, "spec_version": spec_v, "charter_version": chart_v,
                "run_mode": run_mode, "created_at": now()},
        "identity": {
            "campaign_id": {"value": None, "status": None, "confirmed_by_owner": False,
                            "externally_referenced": False, "first_external_reference": None},
            "display_name": None},
        "workflow": {"state": "NEW", "entered_at": now(),
                     "history": [{"from": None, "to": "NEW", "at": now(),
                                  "transition_type": "forward",
                                  "pinned_spec_version": spec_v,
                                  "pinned_charter_version": chart_v,
                                  "pinned_run_mode": run_mode,
                                  "decision_ref": None}]},
        "owner_decisions": {},
        "artifacts": {},
        "invalidated": [],
        "execution_tracking": {"activation_architecture_status": "not_started",
                               "seam6_execution_status": "not_started",
                               "external_handoffs_status": "not_started",
                               "external_handoffs_implemented": "unknown"},
        "capability_claims": [],
        "validation_attempts": [],
        "collection_freeze": {"snapshot": [], "exceptions": []},
        "abandonment": None,
    }
    if a.note:
        st["run"]["note"] = a.note
    atomic_write(state_path(rid), st)
    rc, out, err = call_validator(state_path(rid))
    print(out or err)
    print("run_id        %s" % rid)
    print("run_mode      %s   (immutable)" % run_mode)
    print("spec_version  %s   (pinned)" % spec_v)
    print("charter_ver   %s   (pinned, status %s)" % (chart_v, charter["charter"]["status"]))
    print("state file    %s" % os.path.relpath(state_path(rid), ROOT))
    sys.exit(rc)


def cmd_list(a):
    rows = []
    for d in all_run_dirs():
        s = load(os.path.join(d, "state.yaml"))
        rows.append((s.get("run", {}).get("run_id") or os.path.basename(d),
                     s.get("workflow", {}).get("state"),
                     (s.get("identity", {}).get("campaign_id") or {}).get("value") or "-"))
    if not rows:
        print("no runs"); return
    print("%-34s %-22s %s" % ("RUN_ID", "STATE", "CAMPAIGN_ID"))
    for r in rows:
        print("%-34s %-22s %s" % r)


def cmd_status(a):
    s = require_run(a.run)
    schema = load(SCHEMA)
    cur = s["workflow"]["state"]
    print("run          %s" % s["run"]["run_id"])
    print("state        %s   (since %s)" % (cur, s["workflow"]["entered_at"]))
    print("versions     spec %s | charter %s" % (s["run"]["spec_version"], s["run"]["charter_version"]))
    cid = s["identity"]["campaign_id"]
    print("campaign_id  %s [%s] confirmed=%s external=%s" % (
        cid.get("value"), cid.get("status"), cid.get("confirmed_by_owner"),
        cid.get("externally_referenced")))
    print("display_name %s" % s["identity"].get("display_name"))
    arts = s.get("artifacts") or {}
    print("artifacts    %d" % len(arts))
    for k, v in arts.items():
        print("   %-20s %-9s %s" % (k, v.get("status", "current"), v.get("path")))
    ds = s.get("owner_decisions") or {}
    print("decisions    %d" % len(ds))
    for k, v in ds.items():
        print("   %-24s %s by %s" % (k, v.get("decided"), v.get("decided_by")))
    va = s.get("validation_attempts") or []
    if va:
        print("validation   %d attempt(s), last=%s" % (len(va), va[-1].get("result")))
    nxt = sorted({t["to"] for t in schema["transitions"]
                  if t.get("from") == cur
                  or (t.get("from") == "ANY_PRE_LIVE" and cur in (t.get("expands_to") or []))})
    print("next states  %s" % (", ".join(nxt) or "none (terminal)"))


# Owner-decision ledger is BINARY (governance_003, owner 2026-08-09): a judgment is either a
# provisional agent recommendation or a genuinely explicit owner confirmation. Engine
# fulfillment, validator passes and material exceptions are NOT owner decisions and live in
# their own structures (product truth / validation_attempts / exception artifacts).
DECISION_STATUSES = ("provisional_recommendation", "owner_confirmed")


def cmd_record_decision(a):
    s = require_run(a.run)
    status = a.status
    # governance_003: product_owner is valid ONLY on an owner_confirmed entry. An agent
    # recommendation or engine fulfillment must never be stamped as an owner decision.
    if a.by == "product_owner" and status != "owner_confirmed":
        sys.exit("REFUSED (decision_status_misstamped): decided_by product_owner requires "
                 "--status owner_confirmed, got %r. Record agent proposals as "
                 "provisional_recommendation, engine output as fulfilled." % status)
    val = json.loads(a.value_json) if a.value_json else None
    # decided is true ONLY for a genuine owner confirmation; every other status is not a decision.
    rec = {"status": status, "decided": status == "owner_confirmed",
           "decided_by": a.by, "decided_at": now()}
    if val is not None:
        rec["value"] = val
    if a.note:
        rec["note"] = a.note
    s.setdefault("owner_decisions", {})[a.id] = rec
    # A1 (2026-08-10): a decision invalidated by a reopen becomes gate-worthy again ONLY by
    # being genuinely re-recorded. An owner_confirmed re-record clears the invalidation; any
    # other status leaves it invalidated (a provisional recommendation cannot resurrect it).
    if status == "owner_confirmed" and a.id in (s.get("invalidated") or []):
        s["invalidated"].remove(a.id)
        print("  cleared invalidation of %r (re-recorded by owner)" % a.id)
    atomic_write(state_path(a.run), s)
    print("recorded %s %r by %s at %s" % (status, a.id, a.by, rec["decided_at"]))
    if val is not None:
        print("  value: %s" % json.dumps(val))


def cmd_register_artifact(a):
    s = require_run(a.run)
    p = a.path if os.path.isabs(a.path) else os.path.join(ROOT, a.path)
    if not os.path.exists(p):
        sys.exit("FATAL: artifact path does not exist: %s" % p)
    if (os.path.sep + QUARANTINE + os.path.sep) in (os.path.abspath(p) + os.path.sep):
        sys.exit("FATAL: %s/ is quarantined. Files there are pending deletion and can never\n"
                 "       satisfy an artifact prerequisite: %s" % (QUARANTINE, p))
    rd = os.path.abspath(run_dir(a.run))
    ap = os.path.abspath(p)
    # Convention (NAMING_CONVENTIONS.md): paths inside the run are stored RUN-ROOT-relative
    # so promotion/moves never invalidate references; anything else stays repo-relative.
    rel = os.path.relpath(ap, rd) if (ap + os.sep).startswith(rd + os.sep) else os.path.relpath(ap, ROOT)
    sha = hashlib.sha256(open(p, "rb").read()).hexdigest()
    s.setdefault("artifacts", {})[a.key] = {
        "path": rel, "written_at": now(), "sha256": sha, "status": "current",
        "superseded_by": None, "superseded_at": None, "supersession_reason": None}
    atomic_write(state_path(a.run), s)
    print("registered artifact %-20s %s" % (a.key, rel))
    print("  sha256 %s" % sha)


def _artifact_rel(run_id, p):
    rd, ap = os.path.abspath(run_dir(run_id)), os.path.abspath(p)
    return os.path.relpath(ap, rd) if (ap + os.sep).startswith(rd + os.sep) \
        else os.path.relpath(ap, ROOT)


# ═══════════════════════════════════════════════════════════════════
# STRUCTURED FRONT HALF (spec 1.8.0) — register-object + typed hash-bound approvals.
# The structured objects are AUTHORITY; register-object BUILDS + canonically HASHES them (never
# hand-authored bytes), writes an IMMUTABLE revision file, registers it as an artifact, stamps the
# structured_objects spine, and on a MATERIAL change deterministically invalidates the downstream
# front-half approvals per the schema dependency_graph. State mutation stays here; the object logic
# lives in front_half.py.
# ═══════════════════════════════════════════════════════════════════
FRONT_HALF_KINDS = ("research_brief", "research_ledger", "campaign_directions", "campaign_spec")


def _dependency_graph():
    return (load(SCHEMA).get("state_file") or {}).get("dependency_graph") or {}


def cmd_register_object(a):
    """Author + register a structured front-half object revision (task §3/§5/§7/§18).

    Reads a JSON/YAML payload, BUILDS the canonical object (validating structure + charter rules and
    stamping section/composite/per-item hashes), writes it as an IMMUTABLE revision file
    <kind>.r<NNN>.yaml under the run, registers it as the artifact <kind>, and updates the
    structured_objects spine. A revision is write-once: registering a materially different object
    under the same id mints a NEW revision and (per dependency_graph) invalidates the downstream
    front-half approvals so a stale approval can never gate a changed object (task §19)."""
    import front_half as fh
    s = require_run(a.run)
    kind = a.kind
    if kind not in FRONT_HALF_KINDS:
        sys.exit("FATAL: --kind must be one of %s" % (FRONT_HALF_KINDS,))
    raw = a.payload if os.path.isabs(a.payload) else os.path.join(ROOT, a.payload)
    if not os.path.exists(raw):
        sys.exit("FATAL: payload not found: %s" % raw)
    with open(raw, encoding="utf-8") as f:
        payload = json.load(f) if raw.endswith(".json") else yaml.safe_load(f)

    # optional cross-object binding material (ledger for direction evidence-ref resolution).
    try:
        if kind == "research_brief":
            obj = fh.build_research_brief(payload)
        elif kind == "research_ledger":
            obj = fh.build_research_ledger(payload)
        elif kind == "campaign_directions":
            ledger = _load_current_object(s, a.run, "research_ledger")
            obj = fh.build_campaign_directions(payload, ledger=ledger)
        else:
            obj = fh.build_campaign_spec_revision(payload)
    except fh.FrontHalfError as e:
        sys.exit("REFUSED — %s is not a valid %s: %s" % (raw, kind, e))

    spine_prev = (s.get("structured_objects") or {}).get(kind) or {}
    prev_hash = spine_prev.get("canonical_hash")
    prev_section_hashes = spine_prev.get("section_hashes") or {}

    # write the IMMUTABLE revision file (never overwrite an existing revision of the same id).
    rev = obj["revision"]
    rd = run_dir(a.run)
    os.makedirs(rd, exist_ok=True)
    rev_path = os.path.join(rd, "%s.%s.yaml" % (kind, rev))
    if os.path.exists(rev_path):
        existing = yaml.safe_load(open(rev_path, encoding="utf-8")) or {}
        if existing.get("canonical_hash") != obj["canonical_hash"]:
            sys.exit("REFUSED (campaign_spec_revision_mutated): %s already exists with a different "
                     "hash — a revision is write-once; mint a NEW revision label instead" % rev_path)
    with open(rev_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(obj, f, sort_keys=False, default_flow_style=False, allow_unicode=True)

    # register the artifact (points at the current revision file) with sha over the bytes.
    rel = _artifact_rel(a.run, rev_path)
    sha = hashlib.sha256(open(rev_path, "rb").read()).hexdigest()
    s.setdefault("artifacts", {})[kind] = {
        "path": rel, "written_at": now(), "sha256": sha, "status": "current",
        "superseded_by": None, "superseded_at": None, "supersession_reason": None}

    # stamp the spine + keep a write-once revision ledger (for campaign_spec_revision_immutable).
    spine = fh.spine_for_object(obj, kind)
    revisions = list(spine_prev.get("revisions") or [])
    rec = {"campaign_spec_id" if kind == "campaign_spec" else "object_id": spine["object_id"],
           "revision": rev, "canonical_hash": obj["canonical_hash"]}
    if kind == "campaign_spec":
        rec["composite_hash"] = obj["composite_hash"]
    if not any(r.get("revision") == rev and r.get("canonical_hash") == obj["canonical_hash"]
               for r in revisions):
        revisions.append(rec)
    spine["revisions"] = revisions
    s.setdefault("structured_objects", {})[kind] = spine

    # DETERMINISTIC dependency invalidation (task §19). Compute which sections/objects materially
    # changed and invalidate the downstream front-half approvals via the schema dependency_graph.
    changed_nodes = _changed_nodes(kind, prev_hash, obj, prev_section_hashes)
    invalidated = _invalidate_downstream(s, changed_nodes)

    atomic_write(state_path(a.run), s)
    print("registered %s %s/%s" % (kind, spine["object_id"], rev))
    print("  canonical_hash %s" % obj["canonical_hash"])
    if kind == "campaign_spec":
        print("  composite_hash %s" % obj["composite_hash"])
        for sec in fh.CS_SECTIONS:
            print("    %-22s %s" % (sec, obj["section_hashes"][sec][:16]))
    if invalidated:
        print("  invalidated stale downstream approvals: %s" % sorted(invalidated))


def _load_current_object(s, run_id, kind):
    """Load the current registered structured object's bytes, or None."""
    rec = (s.get("artifacts") or {}).get(kind)
    if not rec or rec.get("status", "current") != "current":
        return None
    p = rec["path"]
    full = p if os.path.isabs(p) else os.path.join(run_dir(run_id), p)
    if not os.path.exists(full):
        full = os.path.join(ROOT, p)
    if not os.path.exists(full):
        return None
    return yaml.safe_load(open(full, encoding="utf-8"))


def _changed_nodes(kind, prev_hash, obj, prev_section_hashes):
    """Return the dependency-graph nodes that materially changed by this registration."""
    if kind != "campaign_spec":
        node = {"research_brief": "research_brief", "research_ledger": "research_ledger",
                "campaign_directions": "campaign_directions"}[kind]
        # a changed brief/ledger/directions is a change at that node (nothing changed if same hash).
        return set() if prev_hash == obj["canonical_hash"] else {node}
    # campaign_spec: a change is per-SECTION so an independent leaf (e.g. a content headline) does
    # NOT invalidate an unrelated upstream approval (task §19).
    changed = set()
    for sec, h in obj["section_hashes"].items():
        if prev_section_hashes.get(sec) != h:
            changed.add("campaign_spec." + sec)
    return changed


def _invalidate_downstream(s, changed_nodes):
    """Mark every downstream front-half approval invalidated (state.invalidated). Deterministic."""
    import front_half as fh
    dg = _dependency_graph()
    to_invalidate = set()
    for node in changed_nodes:
        to_invalidate |= fh.downstream_approvals_for_change(dg, node)
    inval = s.setdefault("invalidated", [])
    newly = []
    decisions = s.get("owner_decisions") or {}
    for did in to_invalidate:
        # only invalidate an approval that actually exists (was recorded) and isn't already stale.
        if did in decisions and did not in inval:
            inval.append(did)
            newly.append(did)
    return newly


def cmd_select_direction(a):
    """Record the owner's EXACT direction selection (task §8) — a typed decision binding the chosen
    direction_id + its per-direction hash from the current campaign_directions. This is the vNext
    form of opportunity_selected; the validator refuses a selection that names no current direction."""
    import front_half as fh  # noqa: F401 (parity; hash already on the object)
    s = require_run(a.run)
    dirs_obj = _load_current_object(s, a.run, "campaign_directions")
    if not dirs_obj:
        sys.exit("FATAL: no current campaign_directions registered — register-object it first")
    match = next((d for d in (dirs_obj.get("directions") or [])
                  if d.get("direction_id") == a.direction_id), None)
    if match is None:
        sys.exit("FATAL: direction %r is not in the current campaign_directions" % a.direction_id)
    if a.by == "product_owner" and a.status != "owner_confirmed":
        sys.exit("REFUSED (decision_status_misstamped): product_owner requires --status owner_confirmed")
    value = {"directions_id": dirs_obj.get("directions_id"),
             "revision": dirs_obj.get("revision"),
             "direction_id": a.direction_id,
             "direction_hash": match.get("direction_hash")}
    rec = {"status": a.status, "decided": a.status == "owner_confirmed", "decided_by": a.by,
           "decided_at": now(), "value": value}
    if a.note:
        rec["note"] = a.note
    s.setdefault("owner_decisions", {})["direction_selected_v2"] = rec
    if a.status == "owner_confirmed" and "direction_selected_v2" in (s.get("invalidated") or []):
        s["invalidated"].remove("direction_selected_v2")
    atomic_write(state_path(a.run), s)
    print("recorded direction_selected_v2 -> %s (hash %s) by %s"
          % (a.direction_id, (match.get("direction_hash") or "")[:16], a.by))


def cmd_approve_object(a):
    """Record a typed, hash-bound front-half owner approval (task §4/§11/§20/§21).

    Binds the EXACT current object/section/composite so an approval can never silently authorize a
    different revision. Modes:
      --binding object     : binds {object_id, revision, canonical_hash}          (kickoff_approved)
      --binding section    : binds {object_id, revision, section, section_hash}   (premise/verticals)
      --binding composite  : binds {object_id, revision, composite_hash} over --sections
                             (architecture_approved: 3 sections; campaign_spec_approved: all 8)
    """
    import front_half as fh
    s = require_run(a.run)
    if a.by == "product_owner" and a.status != "owner_confirmed":
        sys.exit("REFUSED (decision_status_misstamped): product_owner requires --status owner_confirmed")
    obj = _load_current_object(s, a.run, a.kind)
    spine = (s.get("structured_objects") or {}).get(a.kind) or {}
    if not obj or not spine:
        sys.exit("FATAL: no current %s registered — register-object it first" % a.kind)
    if a.binding == "object":
        value = {"object_id": spine["object_id"], "revision": spine["revision"],
                 "canonical_hash": spine["canonical_hash"]}
    elif a.binding == "section":
        sh = (spine.get("section_hashes") or {}).get(a.section)
        if not sh:
            sys.exit("FATAL: campaign_spec has no section_hash for %r" % a.section)
        value = {"object_id": spine["object_id"], "revision": spine["revision"],
                 "section": a.section, "section_hash": sh}
    else:  # composite
        sections = [x.strip() for x in (a.sections or "").split(",") if x.strip()]
        if not sections:
            sys.exit("FATAL: --sections is required for a composite binding")
        sh = spine.get("section_hashes") or {}
        missing = [x for x in sections if not sh.get(x)]
        if missing:
            sys.exit("FATAL: missing section hashes for %s" % missing)
        value = {"object_id": spine["object_id"], "revision": spine["revision"],
                 "composite_hash": fh.composite_hash(sh, sections)}
    rec = {"status": a.status, "decided": a.status == "owner_confirmed", "decided_by": a.by,
           "decided_at": now(), "value": value}
    if a.note:
        rec["note"] = a.note
    s.setdefault("owner_decisions", {})[a.id] = rec
    if a.status == "owner_confirmed" and a.id in (s.get("invalidated") or []):
        s["invalidated"].remove(a.id)
        print("  cleared invalidation of %r (re-recorded by owner on the current object)" % a.id)
    atomic_write(state_path(a.run), s)
    print("recorded %s %r by %s (binds %s)" % (a.status, a.id, a.by, a.binding))
    print("  value: %s" % json.dumps(value))


def cmd_reopen(a):
    """Prepare a reopen edge so a subsequent `transition --to <to>` validates.

    Reopen obligations (check_reopen) are: the named artifacts superseded WITH a reason, the
    reopen owner-decision recorded (owner_confirmed) with its required value fields + reason,
    and every `invalidates` target present in state.invalidated. Before F5 there was no writer
    for `invalidated`, so both non-trivial reopen edges were un-executable through the sanctioned
    interface (forcing a hand-edit of state.yaml). This command performs those writes atomically;
    it does NOT transition — run `transition --to <to>` after, so the validator still gates it.
    """
    s = require_run(a.run)
    schema = load(SCHEMA)
    frm = s.get("workflow", {}).get("state")
    t = next((x for x in schema["transitions"]
              if x.get("from") == frm and x.get("to") == a.to
              and x.get("transition_type") == "reopen"), None)
    if not t:
        sys.exit("FATAL: no reopen edge %s -> %s in the schema" % (frm, a.to))
    did = t["owner_decision"]
    # 1) supersede the named artifacts (idempotent) with the reopen reason.
    for key in t.get("supersedes_artifacts") or []:
        rec = (s.get("artifacts") or {}).get(key)
        if rec and rec.get("status") != "superseded":
            rec["status"] = "superseded"; rec["superseded_by"] = None
            rec["superseded_at"] = now(); rec["supersession_reason"] = a.reason
    # 2) record every invalidates target in state.invalidated.
    inval = s.setdefault("invalidated", [])
    for target in t.get("invalidates") or []:
        if target not in inval:
            inval.append(target)
    # 2b) A1 (2026-08-10): the invalidation is ATOMIC with the reopen preparation — stale
    # execution-dependent proof must not survive as live proof. Driven by the edge's declared
    # invalidates list; these fields are stamped ONLY here and in cmd_migrate.
    if "validation_attempts" in (t.get("invalidates") or []):
        for att in s.get("validation_attempts") or []:
            if att.get("result") == "passed" and not att.get("invalidated_at"):
                att["invalidated_at"] = now()
                att["invalidated_by_decision"] = did
    if "verification" in (t.get("invalidates") or []) and s.get("verification"):
        v = s["verification"]
        if not v.get("invalidated_at"):
            v["invalidated_at"] = now()
            v["invalidated_by_decision"] = did
    if a.to == "SEAM6_READY":
        # execution returns to regenerate-and-revalidate; 'validated' may not survive a reopen
        et = s.setdefault("execution_tracking", {})
        if et.get("seam6_execution_status") in ("validated", "executed"):
            et["seam6_execution_status"] = "ready"
    # 3) record the reopen owner decision (owner_confirmed; required value fields + reason).
    value = json.loads(a.value_json) if a.value_json else {}
    value.setdefault("reason", a.reason)
    missing = [f for f in (t.get("decision_value_required_fields") or []) if not value.get(f)]
    if missing:
        sys.exit("FATAL: reopen decision %r requires value fields %s — pass them via --value-json"
                 % (did, missing))
    if a.by == "product_owner":
        pass  # allowed: reopen is an explicit owner decision
    s.setdefault("owner_decisions", {})[did] = {
        "status": "owner_confirmed", "decided": True, "decided_by": a.by,
        "decided_at": now(), "value": value, "note": a.reason}
    atomic_write(state_path(a.run), s)
    print("reopen prepared %s -> %s: superseded %s; invalidated %s; decision %r recorded"
          % (frm, a.to, t.get("supersedes_artifacts") or [], t.get("invalidates") or [], did))
    print("  now run:  python3 scripts/run.py transition --run %s --to %s" % (a.run, a.to))


def cmd_verify_live(a):
    """Record the COMPUTED live-verification the LIVE gate consumes. This is the only writer of
    `verification` (which is not settable), the F2-equivalent for go-live: an agent cannot enter
    LIVE by asserting post_cache_verified=true. The record is bound to the registered products_csv
    by build_sha256. For an automated probe the result is gathered; when the sandbox cannot reach
    the live product a human-observed result may be ingested with explicit provenance (--observed-by),
    never a generic boolean.
    """
    s = require_run(a.run)
    registered = ((s.get("artifacts") or {}).get("products_csv") or {}).get("sha256")
    if not registered:
        sys.exit("FATAL: no registered products_csv to bind verification to — run "
                 "validate-execution first")
    if a.method == "human_observation" and not a.observed_by:
        sys.exit("FATAL: --method human_observation requires --observed-by <who>")
    passed = a.result == "pass"
    s["verification"] = {
        "post_cache_verified": passed,
        "reprobe_at": a.reprobe_at or now(),
        "executed_build": a.executed_build,
        "build_sha256": registered,           # bound to the build that was actually executed
        "rail_ids": [x for x in (a.rail_ids or "").split(",") if x],
        "method": a.method,
        "observed_by": a.observed_by or "",
        "evidence": a.evidence or "",
        "result": a.result,
    }
    et = s.setdefault("execution_tracking", {})
    et["executed_build"] = a.executed_build
    atomic_write(state_path(a.run), s)
    print("verify-live: recorded %s (%s) for build %s, bound to products_csv %s"
          % (a.result, a.method, a.executed_build, registered[:12]))
    if not passed:
        print("  result=fail — LIVE will refuse until a passing verification is recorded")


def cmd_migrate(a):
    """Model B (current-canon + explicit migration): bring a run's pinned spec/charter
    versions up to the on-disk canon and record why. The validator evaluates current canon
    always; an un-migrated run whose pins differ is refused (run_canon_version_mismatch)
    until this records the bump. Creating-versions remain in workflow.history as provenance."""
    s = require_run(a.run)
    schema = load(SCHEMA); charter = load(CHARTER)
    to_spec = schema["schema"]["version"]
    to_chart = charter["charter"]["version"]
    run = s.setdefault("run", {})
    frm_spec, frm_chart = run.get("spec_version"), run.get("charter_version")
    if (frm_spec, frm_chart) == (to_spec, to_chart):
        print("already at canon: spec %s / charter %s — no migration needed" % (to_spec, to_chart))
        return
    rec = {"from_spec_version": frm_spec, "to_spec_version": to_spec,
           "from_charter_version": frm_chart, "to_charter_version": to_chart,
           "at": now(), "by": a.by, "note": a.note or ""}
    run.setdefault("migration", []).append(rec)
    run["spec_version"] = to_spec
    run["charter_version"] = to_chart

    # A2 (2026-08-10): migration may NOT leave traversed canon-dependent/hash-bound proof that
    # would fail the current canon. Deterministic invalidation, not historical replay:
    # a passing validation attempt is current-canon-valid only if it is a production build
    # hash-bound to the CURRENTLY registered products_csv. Anything else is stamped invalid,
    # the 'validated' execution status is downgraded, and the stale execution artifacts are
    # superseded (never deleted). The validator's stale_execution_proof invariant enforces the
    # same rule, so a hand-edited state cannot dodge this.
    csv_rec = (s.get("artifacts") or {}).get("products_csv") or {}
    csv_sha = csv_rec.get("sha256")
    invalidated_n = 0
    live_valid = False
    for att in s.get("validation_attempts") or []:
        if att.get("result") != "passed" or att.get("invalidated_at"):
            continue
        bound = (att.get("production") is True and att.get("output_sha256")
                 and att.get("output_sha256") == csv_sha
                 and not att.get("allow_stale_used") and not att.get("legacy_replay_used"))
        if bound and csv_rec.get("status", "current") == "current":
            live_valid = True
        else:
            att["invalidated_at"] = now()
            att["invalidated_by_decision"] = "canon_migration"
            invalidated_n += 1
    et = s.setdefault("execution_tracking", {})
    if invalidated_n and not live_valid:
        if et.get("seam6_execution_status") == "validated":
            et["seam6_execution_status"] = "ready"
        for key in ("products_csv", "execution_manifest"):
            arec = (s.get("artifacts") or {}).get(key)
            if arec and arec.get("status", "current") == "current":
                arec["status"] = "superseded"
                arec["superseded_by"] = None
                arec["superseded_at"] = now()
                arec["supersession_reason"] = ("canon migration %s/%s -> %s/%s: bound proof "
                                               "invalid under current canon; regenerate via "
                                               "validate-execution"
                                               % (frm_spec, frm_chart, to_spec, to_chart))
        rec["proof_invalidated"] = {
            "validation_attempts_stamped": invalidated_n,
            "seam6_execution_status": et.get("seam6_execution_status"),
            "superseded": [k for k in ("products_csv", "execution_manifest")
                           if ((s.get("artifacts") or {}).get(k) or {}).get("status") == "superseded"],
        }

    atomic_write(state_path(a.run), s)
    print("migrated run %s: spec %s->%s, charter %s->%s"
          % (a.run, frm_spec, to_spec, frm_chart, to_chart))
    print("  by %s: %s" % (a.by, a.note or "(no note)"))
    if invalidated_n:
        print("  OBLIGATION: %d passing validation attempt(s) carried no current-canon proof "
              "and were stamped invalidated" % invalidated_n)
        if not live_valid:
            print("  OBLIGATION: no live proof remains — seam6_execution_status downgraded to "
                  "%r; stale execution artifacts superseded; run validate-execution to "
                  "regenerate" % et.get("seam6_execution_status"))
            # prd.md §16.5: a run whose workflow.state is post-validation may not rest on
            # invalidated proof. Migration does not silently transition state (state changes go
            # through the sanctioned reopen edge); it flags that the run is now incoherent and
            # will be REFUSED by the validator until reopened out of the post-validation state.
            wf_state = (s.get("workflow") or {}).get("state")
            if wf_state in ("VALIDATED", "CAMPAIGN_APPROVED"):
                print("  OBLIGATION: workflow.state is still %r with no live proof — the run "
                      "will now be REFUSED (stale_execution_proof) until it is reopened via "
                      "`run.py reopen --to SEAM6_READY` and regenerated. Migration does not "
                      "move the workflow state on its own." % wf_state)


def cmd_validate_execution(a):
    """Run the v2 execution builder as a REAL subprocess and record the result.

    This is the ONLY writer of validation_attempts and of the products_csv artifact.
    An agent cannot fabricate a passing validation: the pass is computed from the
    builder's exit code, and the attempt is bound by output_sha256 to the exact CSV
    the builder wrote (which is registered here in the same operation). The VALIDATED
    gate later requires that binding to hold.
    """
    s = require_run(a.run)
    # PRODUCTION validation path: stale or legacy truth can NEVER produce a launch-ready
    # attempt. --allow-stale / --legacy-replay are diagnostic-only and are run against the raw
    # builder directly, which never touches validation_attempts. There is therefore no path
    # from stale/legacy truth to a VALIDATED-satisfying attempt.
    builder = os.path.join(HERE, "build_execution_csv.py")
    out = a.out if os.path.isabs(a.out) else os.path.join(run_dir(a.run), a.out)
    cmd = [sys.executable, builder, "--campaign", a.campaign, "--campaign-name",
           a.campaign_name, "--build", a.build, "--judgment", a.judgment,
           "--out", out]
    if a.engine:
        cmd += ["--engine", a.engine]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    passed = proc.returncode == 0
    attempt = {"attempted_at": now(), "result": "passed" if passed else "failed",
               "builder_argv": cmd[1:], "allow_stale_used": False, "legacy_replay_used": False,
               "production": passed,  # only a clean, non-stale, non-legacy build is production
               "builder_stdout_tail": (proc.stdout or "")[-2000:],
               "output_sha256": None, "failures": []}
    if passed and os.path.exists(out):
        sha = hashlib.sha256(open(out, "rb").read()).hexdigest()
        attempt["output_sha256"] = sha
        s.setdefault("artifacts", {})["products_csv"] = {
            "path": _artifact_rel(a.run, out), "written_at": now(), "sha256": sha,
            "status": "current", "superseded_by": None, "superseded_at": None,
            "supersession_reason": None}
    else:
        attempt["failures"] = [{"builder_exit": proc.returncode,
                                "stderr_tail": (proc.stderr or "")[-1000:]}]
    s.setdefault("validation_attempts", []).append(attempt)
    atomic_write(state_path(a.run), s)
    print("validate-execution: %s (builder exit %d)"
          % ("PASSED" if passed else "FAILED", proc.returncode))
    if passed:
        print("  products_csv registered, sha256 %s" % attempt["output_sha256"])
    else:
        print(proc.stdout[-1500:] if proc.stdout else "")
        print(proc.stderr[-500:] if proc.stderr else "")
        sys.exit(1)


# ─────────────────── receipt ingestion + execution package (this unit) ───────────────────
def _run_store(run_id):
    """Per-run Wizard-side fulfillment store (receipt ingestions + material exceptions).
    Under the run directory so it travels with promotion; never in the Engine tree."""
    return os.path.join(run_dir(run_id), "fulfillment")


def _package_dir(run_id):
    return os.path.join(run_dir(run_id), "execution", "package")


def cmd_ingest_receipt(a):
    """THE sanctioned Wizard receipt-ingestion path (task §3). Given ONLY artifact refs + the
    exact Wizard-generated Request v2 this receipt must fulfil, the Wizard independently verifies
    the receipt, binds it to the request, verifies the bound Truth Export v2 snapshot and
    recomputes the eligible sellable SET, distinguishes satisfied vs shortfall (opening a Material
    Exception for a shortfall), and records an immutable ingestion. No hand-authored facts."""
    import receipt_ingest as ri
    require_run(a.run)
    s = require_run(a.run)
    run_mode = (s.get("run") or {}).get("run_mode") or "production"
    campaign_id = ((s.get("identity") or {}).get("campaign_id") or {}).get("value")
    run_ref = (s.get("run") or {}).get("run_id")
    store = _run_store(a.run)
    try:
        res = ri.ingest_receipt(
            a.receipt, a.request,
            snapshot_dir=a.snapshot_dir, store_dir=store,
            fulfillment_exception_path=a.fulfillment_exception,
            expected_run_mode=run_mode,
            expected_campaign_id=campaign_id if not a.no_campaign_check else None,
            expected_run_ref=run_ref if not a.no_run_check else None,
            generated_at=now())
    except ri.ReceiptIngestError as e:
        sys.exit("REFUSED — receipt ingestion: %s" % e)
    print("ingested receipt %s" % res["receipt_id"])
    print("  request        %s" % res["request_id"])
    print("  category       %s  run_mode %s" % (res["category_id"], res["run_mode"]))
    print("  terminal       %s" % res["terminal_status"])
    print("  required/achieved  %s / %s   (independently recomputed %s)"
          % (res["required_depth"], res["achieved_depth"], res["recomputed_depth"]))
    print("  eligible set   %d verified sellable products" % len(res["eligible_sellable_set"]))
    if res["terminal_status"] == "satisfied":
        print("  SATISFIED — verified eligible set is the trusted material for assembly")
    else:
        print("  SHORTFALL — opened Material Exception %s (status open) — BLOCKS assembly"
              % res.get("material_exception_id"))
        print("  no automatic widening/substitution: owner resolution required (run.py "
              "resolve-material-exception)")


def cmd_resolve_material_exception(a):
    """Record an owner JUDGMENT on an open Material Exception (open -> resolved; task §0 Issue B).
    DECISION RECORD ONLY: it does NOT unblock assembly, waive render_003, or make a shortfall
    Request satisfy package completeness. The factual section is never rewritten; no silent
    auto-resolution. Completeness still requires a genuine satisfied Receipt for the request."""
    import receipt_ingest as ri
    require_run(a.run)
    if a.by != "product_owner":
        sys.exit("REFUSED: a Material Exception resolution is an owner judgment — --by product_owner")
    resolution = json.loads(a.value_json) if a.value_json else {"note": a.note or ""}
    resolution.setdefault("resolved_by", a.by)
    try:
        rec = ri.resolve_material_exception(_run_store(a.run), a.id, resolution, generated_at=now())
    except ri.ReceiptIngestError as e:
        sys.exit("REFUSED: %s" % e)
    print("resolved material exception %s -> %s (owner judgment recorded)"
          % (a.id, rec.get("status")))
    print("  NOTE: this does NOT unblock package assembly. The expected Request still needs a "
          "satisfied Receipt — resolving the exception does not waive the material requirement "
          "(render_003) or transmute the Engine result.")


def _load_architecture_or_exit(a):
    import execution_package as ep
    try:
        return ep.load_architecture(a.architecture)
    except (ep.PackageError, FileNotFoundError, ValueError) as e:
        sys.exit("REFUSED — architecture: %s" % e)


def _build_master_csv(a, out_csv):
    """Build A (Master CSV) via the sanctioned v2 builder as a REAL subprocess. Product facts are
    hydrated from Engine truth; the Wizard authors judgment only. Returns (ok, sha256, stdout)."""
    builder = os.path.join(HERE, "build_execution_csv.py")
    cmd = [sys.executable, builder, "--campaign", a.campaign, "--campaign-name",
           a.campaign_name, "--build", a.build, "--judgment", a.judgment, "--out", out_csv]
    if a.engine:
        cmd += ["--engine", a.engine]
    if getattr(a, "truth", None):
        cmd += ["--truth", a.truth]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not os.path.exists(out_csv):
        return False, None, (proc.stdout or "") + (proc.stderr or "")
    return True, hashlib.sha256(open(out_csv, "rb").read()).hexdigest(), proc.stdout


def cmd_build_package(a):
    """STAGE the COMPLETE A–G human execution components (task §0 Issue A, step 1). A (Master CSV)
    is built via the v2 builder (Engine truth hydration); B–E, G are produced by execution_package
    from the campaign architecture + accepted receipt ingestions. It writes NO Execution Manifest
    and makes NO validity claim — F is emitted ONLY by validate-package, AFTER validation passes.
    Does not transition. Refuses if there is nothing to stage (no ingestions)."""
    import execution_package as ep
    import receipt_ingest as ri
    s = require_run(a.run)
    run_ref = (s.get("run") or {}).get("run_id")  # noqa: F841 (kept for parity/log symmetry)
    arch = _load_architecture_or_exit(a)

    store = _run_store(a.run)
    ingestions = ri.load_ingestions(store)
    material = ri.load_material_exceptions(store)
    if not ingestions:
        sys.exit("REFUSED: no accepted receipt ingestions under %s — ingest receipts first "
                 "(run.py ingest-receipt)" % store)
    fview = ep.build_fulfillment_view(ingestions, material)

    pkg_dir = _package_dir(a.run)
    os.makedirs(pkg_dir, exist_ok=True)
    out_csv = os.path.join(pkg_dir, "A_master.csv")
    ok, csv_sha, blob = _build_master_csv(a, out_csv)
    if not ok:
        print(blob[-1500:])
        sys.exit("REFUSED — Master CSV (A) build failed; the complete package cannot stage")

    try:
        staged = ep.stage_components(arch, fview, out_dir=pkg_dir, master_csv_path=out_csv,
                                     master_csv_sha256=csv_sha)
    except ep.PackageError as e:
        sys.exit("REFUSED — staging: %s" % e)
    print("staged A–G components under %s (no manifest yet — validate-package emits F)"
          % os.path.relpath(pkg_dir, ROOT))
    for comp in ("A", "B", "C", "D", "E", "G"):
        print("  %s  sha %s" % (comp, staged["shas"][comp][:16]))
    print("  next: run.py validate-package (validates A–G, THEN emits + registers F)")


def cmd_validate_package(a):
    """VALIDATE the COMPLETE A–G package, THEN emit + register the immutable F Execution Manifest
    over the ALREADY-VALIDATED component set, and record a package-validating attempt bound to it
    (task §0 Issue A, steps 2–5). Frozen order — no self-attestation:

        stage A–G (build-package)  ->  VALIDATE A–G + deps + completeness + coherence
                                   ->  emit F from the COMPLETED validation result
                                   ->  register F  ->  record execution_package_validated bound F.

    A manifest is NEVER emitted over an unvalidated/incoherent package, and validation NEVER
    consults a manifest field to decide the package is valid. The sanctioned writer of a
    package-validating validation_attempts entry + the products_csv/execution_manifest artifacts."""
    import execution_package as ep
    import receipt_ingest as ri
    s = require_run(a.run)
    run_mode = (s.get("run") or {}).get("run_mode") or "production"
    campaign_id = ((s.get("identity") or {}).get("campaign_id") or {}).get("value")
    run_ref = (s.get("run") or {}).get("run_id")
    arch = _load_architecture_or_exit(a)
    store = _run_store(a.run)
    fview = ep.build_fulfillment_view(ri.load_ingestions(store), ri.load_material_exceptions(store))
    pkg_dir = _package_dir(a.run)

    # ---- step 2a: rebuild A (real subprocess) and re-stage B–G deterministically. Staging is a
    #      pure function of architecture + fview; re-staging here means validate-package does not
    #      trust whatever build-package happened to leave on disk. ----
    out_csv = os.path.join(pkg_dir, "A_master.csv")
    failures = []
    ok_csv, csv_sha, blob = _build_master_csv(a, out_csv)
    if not ok_csv:
        failures.append({"predicate": "master_csv_builds", "detail": (blob or "")[-500:]})
    if failures:
        _record_failed_package_attempt(s, a.run, failures, blob)
        return
    try:
        staged = ep.stage_components(arch, fview, out_dir=pkg_dir, master_csv_path=out_csv,
                                     master_csv_sha256=csv_sha)
    except ep.PackageError as e:
        _record_failed_package_attempt(s, a.run, [{"predicate": "staging", "detail": str(e)}], blob)
        return

    # ---- step 2b: AUTHORITATIVE validation of the staged package (consults no manifest) ----
    result = ep.validate_package(arch, fview, pkg_dir, staged, run_mode)
    if not result["ok"]:
        failures = [{"predicate": "validate_package", "detail": p} for p in result["problems"]]
        _record_failed_package_attempt(s, a.run, failures, blob)
        return

    # ---- steps 3–4: emit F over the VALIDATED set (validation recorded FROM the result) + register
    arch_sha = hashlib.sha256(open(a.architecture, "rb").read()).hexdigest()
    try:
        emitted = ep.emit_manifest(
            arch, fview, out_dir=pkg_dir, staged=staged, campaign_id=campaign_id,
            run_id=run_ref, run_mode=run_mode, validation_result=result,
            package_revision=a.revision,
            architecture_ref=os.path.relpath(a.architecture, run_dir(a.run))
            if os.path.abspath(a.architecture).startswith(os.path.abspath(run_dir(a.run)))
            else a.architecture,
            architecture_sha256=arch_sha, generated_at=now())
    except ep.PackageError as e:
        _record_failed_package_attempt(s, a.run,
                                       [{"predicate": "emit_manifest", "detail": str(e)}], blob)
        return

    manifest = emitted["manifest"]
    manifest_file_sha = hashlib.sha256(open(emitted["manifest_path"], "rb").read()).hexdigest()

    # ---- step 5: register F + record the package-validated attempt bound to the exact manifest ----
    s = require_run(a.run)
    s.setdefault("artifacts", {})["execution_manifest"] = {
        "path": _artifact_rel(a.run, emitted["manifest_path"]), "written_at": now(),
        "sha256": manifest_file_sha, "status": "current",
        "superseded_by": None, "superseded_at": None, "supersession_reason": None}
    s.setdefault("artifacts", {})["products_csv"] = {
        "path": _artifact_rel(a.run, out_csv), "written_at": now(), "sha256": csv_sha,
        "status": "current", "superseded_by": None, "superseded_at": None,
        "supersession_reason": None}
    attempt = {"attempted_at": now(), "result": "passed",
               "allow_stale_used": False, "legacy_replay_used": False,
               "production": run_mode == "production",
               "package_validated": True,
               "package_manifest_sha256": manifest_file_sha,
               "output_sha256": csv_sha,
               "manifest_id": manifest["manifest_id"],
               "validated_checks": result["checks"],
               "builder_stdout_tail": (blob or "")[-1500:],
               "failures": []}
    s.setdefault("validation_attempts", []).append(attempt)
    et = s.setdefault("execution_tracking", {})
    et["seam6_execution_status"] = "validated"
    atomic_write(state_path(a.run), s)
    print("validate-package: PASSED — COMPLETE A–G package validated, THEN F emitted over it")
    print("  products_csv sha         %s" % csv_sha)
    print("  emitted execution_manifest %s (sha %s)"
          % (manifest["manifest_id"], manifest_file_sha[:16]))
    print("  seam6_execution_status -> validated")


def _record_failed_package_attempt(s, run_id, failures, blob):
    """Record a FAILED package validation attempt (no products_csv/manifest registered, status not
    advanced). A failed validation never emits a manifest — the frozen order forbids it."""
    s = require_run(run_id)
    attempt = {"attempted_at": now(), "result": "failed",
               "allow_stale_used": False, "legacy_replay_used": False, "production": False,
               "package_validated": False, "package_manifest_sha256": None, "output_sha256": None,
               "builder_stdout_tail": (blob or "")[-1500:], "failures": failures}
    s.setdefault("validation_attempts", []).append(attempt)
    atomic_write(state_path(run_id), s)
    print("validate-package: FAILED — %d issue(s) (no manifest emitted):" % len(failures))
    for f in failures:
        print("  [%s] %s" % (f["predicate"], f["detail"]))
    sys.exit(1)


def cmd_approve_package(a):
    """Record the owner EXECUTION-PACKAGE approval bound to the EXACT current Execution Manifest
    (task §23). "Approve this exact validated human execution package for implementation." The
    approval decision.value binds manifest_id + manifest_sha256; the CAMPAIGN_APPROVED gate refuses
    an approval that does not match the current manifest. Owner-only, owner_confirmed."""
    if a.by != "product_owner":
        sys.exit("REFUSED: execution-package approval is an owner judgment — --by product_owner")
    s = require_run(a.run)
    rec = (s.get("artifacts") or {}).get("execution_manifest")
    if not rec or rec.get("status", "current") != "current":
        sys.exit("REFUSED: no current execution_manifest to approve — build/validate the package first")
    mpath = artifact_path(a.run, rec)
    manifest = json.load(open(mpath, encoding="utf-8"))
    value = {"manifest_id": manifest.get("manifest_id"),
             "manifest_sha256": rec.get("sha256"),
             "meaning": "approve this exact validated human execution package for implementation"}
    if a.note:
        value["note"] = a.note
    decision = {"status": "owner_confirmed", "decided": True, "decided_by": a.by,
                "decided_at": now(), "value": value, "note": a.note or ""}
    s.setdefault("owner_decisions", {})["execution_package_approved"] = decision
    if "execution_package_approved" in (s.get("invalidated") or []):
        s["invalidated"].remove("execution_package_approved")
        print("  cleared prior invalidation of execution_package_approved (re-recorded by owner)")
    atomic_write(state_path(a.run), s)
    print("recorded execution-package approval by %s" % a.by)
    print("  manifest_id  %s" % value["manifest_id"])
    print("  manifest_sha %s" % value["manifest_sha256"])


def cmd_promote(a):
    """Controlled lifecycle operation (NAMING_CONVENTIONS.md): move a run whose campaign_id
    is owner-confirmed into campaigns/<campaign_id>/runs/<run_id>, rewrite legacy artifact
    paths to run-root-relative, and maintain campaigns/<campaign_id>/campaign.yaml."""
    s = require_run(a.run)
    old_dir = os.path.abspath(run_dir(a.run))
    ident = (s.get("identity") or {}).get("campaign_id") or {}
    cid = ident.get("value")
    if not cid:
        sys.exit("FATAL: campaign_id is not set — promotion requires a locked campaign_id")
    if ident.get("status") != "confirmed":
        sys.exit("FATAL: campaign_id status is %r, not 'confirmed'" % ident.get("status"))
    new_parent = os.path.join(RUNS, cid, "runs")
    new_dir = os.path.abspath(os.path.join(new_parent, a.run))
    if old_dir == new_dir:
        print("already promoted: %s" % os.path.relpath(new_dir, ROOT)); return
    if os.path.exists(new_dir):
        sys.exit("FATAL: target already exists: %s" % new_dir)
    orig = copy.deepcopy(s)
    os.makedirs(new_parent, exist_ok=True)
    os.rename(old_dir, new_dir)
    legacy_prefix = os.path.join("campaigns", a.run) + os.sep
    rewritten = 0
    for key, rec in (s.get("artifacts") or {}).items():
        pth = rec.get("path") or ""
        if pth.startswith(legacy_prefix):
            rec["path"] = pth[len(legacy_prefix):]
            rewritten += 1
    atomic_write(os.path.join(new_dir, "state.yaml"), s)
    rc, out, err = call_validator(os.path.join(new_dir, "state.yaml"), run_dir=new_dir)
    if rc != 0:
        atomic_write(os.path.join(new_dir, "state.yaml"), orig)
        os.rename(new_dir, old_dir)
        print(out or err)
        sys.exit("PROMOTION ROLLED BACK — validator refused the promoted state; nothing changed.")
    cy_path = os.path.join(RUNS, cid, "campaign.yaml")
    cy = load(cy_path) if os.path.exists(cy_path) else {
        "campaign_id": cid, "display_name": None,
        "created_at": (s.get("run") or {}).get("created_at"), "runs": []}
    cy["display_name"] = (s.get("identity") or {}).get("display_name")
    cy["current_run_id"] = a.run
    cy["status"] = ((s.get("workflow") or {}).get("state") or "").lower()
    if not any(r.get("run_id") == a.run for r in (cy.get("runs") or [])):
        cy.setdefault("runs", []).append({"run_id": a.run, "purpose": a.purpose})
    atomic_write(cy_path, cy)
    print(out or err)
    print("PROMOTED  %s -> %s" % (os.path.relpath(old_dir, ROOT), os.path.relpath(new_dir, ROOT)))
    print("  %d artifact path(s) rewritten run-root-relative; campaign.yaml updated" % rewritten)


def cmd_supersede_artifact(a):
    """Mark a registered artifact superseded (fields exist in the artifact record schema;
    this is the controlled write path for them — the state file is never hand-edited)."""
    s = require_run(a.run)
    rec = (s.get("artifacts") or {}).get(a.key)
    if not rec:
        sys.exit("FATAL: no artifact %r registered" % a.key)
    if rec.get("status") == "superseded":
        print("already superseded: %s" % a.key); return
    rec["status"] = "superseded"
    rec["superseded_by"] = a.by_key
    rec["superseded_at"] = now()
    rec["supersession_reason"] = a.reason
    atomic_write(state_path(a.run), s)
    print("superseded artifact %-24s -> %s" % (a.key, a.by_key))


def _coerce(raw):
    """'true'/'false' -> bool, integers -> int, 'null' -> None, else the string."""
    low = raw.strip().lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "none", "~"):
        return None
    try:
        return int(raw)
    except ValueError:
        return raw


def cmd_set(a):
    """Controlled write of an operational state field.

    The whitelist lives in the schema (settable_paths), not here — run.py re-implements
    nothing. Anything outside it is refused, so the 'state is never hand-edited' rule is
    enforceable rather than aspirational.
    """
    schema = load(SCHEMA)
    allowed = schema.get("settable_paths") or {}
    spec = allowed.get(a.path)
    if spec is None:
        print("REFUSED: %r is not a settable path.\n" % a.path)
        print("Settable paths (schemas/workflow_state.schema.yaml -> settable_paths):")
        for k in allowed:
            print("   %s" % k)
        ns = (schema.get("not_settable") or {}).get("note", "")
        if ns:
            print("\nNot settable: %s" % " ".join(ns.split()))
        sys.exit(2)

    if (a.value is None) == (a.value_json is None):
        sys.exit("FATAL: supply exactly one of --value or --value-json")
    val = json.loads(a.value_json) if a.value_json is not None else _coerce(a.value)

    if spec.get("type") == "enum" and val not in (spec.get("values") or []):
        sys.exit("REFUSED: %r is not one of %s" % (val, spec.get("values")))
    if spec.get("type") == "boolean" and not isinstance(val, bool):
        sys.exit("REFUSED: %s expects a boolean" % a.path)
    if spec.get("type") == "list" and not isinstance(val, list):
        sys.exit("REFUSED: %s expects a list (use --value-json)" % a.path)
    if spec.get("type") == "mapping" and not isinstance(val, dict):
        sys.exit("REFUSED: %s expects a mapping (use --value-json)" % a.path)

    s = require_run(a.run)
    segs = a.path.split(".")
    node = s
    for seg in segs[:-1]:
        if not isinstance(node.get(seg), dict):
            node[seg] = {}
        node = node[seg]
    before = node.get(segs[-1], "<absent>")
    node[segs[-1]] = val
    atomic_write(state_path(a.run), s)
    print("set %s" % a.path)
    print("  before: %r" % (before,))
    print("  after:  %r" % (val,))


def cmd_unregister_artifact(a):
    s = require_run(a.run)
    if a.key not in (s.get("artifacts") or {}):
        sys.exit("FATAL: no artifact registered under key %r" % a.key)
    s["artifacts"].pop(a.key)
    atomic_write(state_path(a.run), s)
    print("unregistered artifact %r" % a.key)


CONFIRM = {
    "direct":       "no",
    "normalized":   "no",
    "inferred":     "no - labelled inference",
    "proposed":     "YES - agent recommendation, unconfirmed",
    "not_supplied": "no - the owner did not supply this",
}


def _row(label, said, normalized, interp, status, extra=None):
    print(label)
    print("  Owner said:          %s" % (said if said not in (None, "") else "nothing"))
    print("  Normalized:          %s" % (normalized if normalized not in (None, "") else "unset"))
    print("  Inferred/proposed:   %s" % (interp if interp not in (None, "") else "none"))
    print("  Needs confirmation:  %s" % CONFIRM.get(status, status))
    if extra:
        print("  %s" % extra)
    print()
    return status == "proposed"


def artifact_path(run_id, rec):
    """Resolve a registered artifact path: absolute as-is; else run-root-relative first
    (current convention), repo-root-relative second (legacy). Mirrors the validator."""
    pth = rec["path"]
    if os.path.isabs(pth):
        return pth
    rr = os.path.join(run_dir(run_id), pth)
    return rr if os.path.exists(rr) else os.path.join(ROOT, pth)


def cmd_review_inputs(a):
    """Review only. Creates no decision and transitions nothing."""
    s = require_run(a.run)
    rec = (s.get("artifacts") or {}).get("frame")
    if not rec or rec.get("status", "current") != "current":
        sys.exit("FATAL: no current frame artifact registered for this run.")
    p = artifact_path(a.run, rec)
    fr = load(p)
    oi, tm = fr.get("owner_inputs") or {}, fr.get("timing") or {}
    ob, av = fr.get("objective") or {}, fr.get("avoidance") or {}
    sc, ms = fr.get("scope") or {}, fr.get("measurement") or {}
    pending = []

    print("=== STAGE 0 INPUT REVIEW - %s ===" % s["run"]["run_id"])
    print("review only: no decision is created and no transition is requested\n")

    d, op = oi.get("requested_launch") or {}, tm.get("operational_interpretation") or {}
    pending.append(_row("Requested launch", d.get("raw"), d.get("normalized_date"),
                        ("%s; actual launch TBD" % op.get("value")) if op.get("value") else None,
                        op.get("interpretation_status", d.get("interpretation_status"))))

    d = oi.get("planning_horizon") or {}
    pending.append(_row("Planning horizon", d.get("raw"),
                        "minimum %s, maximum %s weeks" % (d.get("minimum_weeks"), d.get("maximum_weeks")),
                        "campaign end: none inferred", d.get("interpretation_status")))

    d = tm.get("desired_campaign_end") or {}
    pending.append(_row("Desired campaign end", None, d.get("value"), None, d.get("interpretation_status")))

    d = tm.get("earliest_actual_campaign_launch") or {}
    pending.append(_row("Earliest actual launch", None, d.get("value"), None, d.get("interpretation_status")))

    d = oi.get("objective") or {}
    nz = d.get("normalized") or {}
    pending.append(_row("Objective", d.get("raw"),
                        "%s among %s" % (nz.get("desired_behavior"), nz.get("audience")),
                        "event mapping: %s" % ob.get("event_mapping"),
                        d.get("interpretation_status"),
                        extra="Counterfactual lift:  not claimed"))

    d = oi.get("starting_territory") or {}
    pending.append(_row("Starting territory", d.get("raw"), d.get("normalized"), None,
                        d.get("interpretation_status")))

    d, add = oi.get("exclusions") or {}, (av.get("additional_restrictions") or {})
    pending.append(_row("Restrictions", "; ".join(d.get("raw") or []),
                        "; ".join(av.get("prohibited_campaign_frames") or []),
                        "added restrictions: %s" % ("none" if not add.get("value") else add.get("value")),
                        d.get("interpretation_status"),
                        extra="Scope:                bars ADOPTION in campaign expression; "
                              "research may still describe these frames"))

    d = sc.get("market") or {}
    pending.append(_row("Market", None, d.get("value"), d.get("basis"), d.get("interpretation_status")))

    pending.append(_row("Seams", None,
                        "available: %s" % (sc.get("seams_available_for_consideration") or []),
                        "selected: %s" % (sc.get("selected_seams") or "none - selection is a later owner act"),
                        (sc.get("derivation") or {}).get("interpretation_status")))

    d = ms.get("proxy") or {}
    pending.append(_row("Measurement proxy", None, d.get("value"),
                        "retrieval %s / baseline %s / causal lift measurable: %s"
                        % (ms.get("retrieval_status"), ms.get("baseline_available"),
                           ms.get("causal_incrementality_measurable")),
                        d.get("interpretation_status")))

    n = sum(1 for x in pending if x)
    print("-" * 68)
    print(("%d value(s) need confirmation." % n) if n else "Nothing needs confirmation.")


def cmd_validate(a):
    rc, out, err = call_validator(state_path(a.run), a.to, a.json)
    sys.stdout.write(out)
    sys.stderr.write(err)
    sys.exit(rc)


def cmd_transition(a):
    sp = state_path(a.run)
    s = require_run(a.run)
    frm = s["workflow"]["state"]
    proposed = copy.deepcopy(s)                       # 1. proposed state, in memory
    # The proposal is held OUTSIDE the repository. Some mounted filesystems forbid unlink, so a
    # proposal written into the run directory could never be cleaned up; and a stray proposal
    # inside campaigns/ is indistinguishable from a real artifact.
    scratch = tempfile.mkdtemp(prefix="shopya_proposal_")
    prop_path = os.path.join(scratch, "state.proposed.yaml")
    with open(prop_path, "w", encoding="utf-8") as f: # 2. temp file
        yaml.safe_dump(proposed, f, sort_keys=False, default_flow_style=False, allow_unicode=True)
    try:
        # 3. EXTERNAL validator, real subprocess. --run-dir keeps the run from looking like a
        #    sibling of itself while its proposal lives elsewhere.
        rc, out, err = call_validator(prop_path, a.to, run_dir=run_dir(a.run))
        sys.stdout.write(out)
        sys.stderr.write(err)
        if rc != 0:                                    # 5. failure: canonical state untouched
            print("\nstate.yaml UNCHANGED — still %s. Nothing was written." % frm)
            sys.exit(rc)
        proposed["workflow"]["state"] = a.to           # 4. success: stamp and commit
        proposed["workflow"]["entered_at"] = now()
        schema = load(SCHEMA)
        t = next((x for x in schema["transitions"]
                  if x.get("to") == a.to and (x.get("from") == frm or
                     (x.get("from") == "ANY_PRE_LIVE" and frm in (x.get("expands_to") or [])))), {})
        proposed["workflow"]["history"].append({
            "from": frm, "to": a.to, "at": now(),
            "transition_type": t.get("transition_type"),
            "decision_ref": t.get("owner_decision"),
            "campaign_id_at_transition": (proposed["identity"]["campaign_id"] or {}).get("value"),
        })
        atomic_write(sp, proposed)
        print("\nCOMMITTED  %s -> %s  (%s)" % (frm, a.to, t.get("transition_type")))
    finally:
        # Best effort. Cleanup failure must never turn a committed transition into a crash.
        shutil.rmtree(scratch, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description="Campaign run interface.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("new");  p.add_argument("--note")
    p.add_argument("--diagnostic", action="store_true",
                   help="create a sanctioned diagnostic run (default: production); immutable")
    p.set_defaults(f=cmd_new)
    p = sub.add_parser("list"); p.set_defaults(f=cmd_list)
    p = sub.add_parser("status"); p.add_argument("--run", required=True); p.set_defaults(f=cmd_status)

    p = sub.add_parser("record-decision")
    p.add_argument("--run", required=True); p.add_argument("--id", required=True)
    p.add_argument("--by", required=True)
    p.add_argument("--status", required=True, choices=DECISION_STATUSES,
                   help="governance_003: owner_confirmed is the only status that gates a "
                        "transition and the only one on which --by may be product_owner")
    p.add_argument("--value-json"); p.add_argument("--note")
    p.set_defaults(f=cmd_record_decision)

    p = sub.add_parser("supersede-artifact")
    p.add_argument("--run", required=True); p.add_argument("--key", required=True)
    p.add_argument("--by-key", required=True); p.add_argument("--reason", required=True)
    p.set_defaults(f=cmd_supersede_artifact)

    p = sub.add_parser("validate-execution",
                       help="run the v2 builder and record a hash-bound validation attempt "
                            "(the ONLY writer of validation_attempts + products_csv)")
    p.add_argument("--run", required=True)
    p.add_argument("--campaign", required=True); p.add_argument("--campaign-name", required=True)
    p.add_argument("--build", required=True); p.add_argument("--judgment", required=True)
    p.add_argument("--out", default="execution/execution.csv")
    p.add_argument("--engine")
    # NOTE: no --allow-stale / --legacy-replay here by design. Diagnostic/legacy builds use the
    # raw build_execution_csv.py directly; they can never produce a launch-ready validation.
    p.set_defaults(f=cmd_validate_execution)

    p = sub.add_parser("ingest-receipt",
                       help="ingest ONE immutable Engine Curation Receipt v1: independently "
                            "verify + bind to the exact Wizard Request v2 + recompute the eligible "
                            "SET + open a Material Exception on shortfall (the sanctioned path)")
    p.add_argument("--run", required=True)
    p.add_argument("--receipt", required=True, help="path to the Curation Receipt v1 artifact")
    p.add_argument("--request", required=True,
                   help="path to the exact Wizard-generated Request v2 this receipt must fulfil")
    p.add_argument("--snapshot-dir", help="dir holding <export_id>.jsonl Truth Export v2 snapshots "
                                          "(when the receipt's immutable_ref is not reachable)")
    p.add_argument("--fulfillment-exception",
                   help="path to the matching Fulfillment Exception v1 (required for a shortfall)")
    p.add_argument("--no-campaign-check", action="store_true",
                   help="skip campaign_id association check (diagnostic/cross-repo fixtures)")
    p.add_argument("--no-run-check", action="store_true",
                   help="skip run_ref association check (diagnostic/cross-repo fixtures)")
    p.set_defaults(f=cmd_ingest_receipt)

    p = sub.add_parser("resolve-material-exception",
                       help="record an owner resolution on an open Material Exception (open -> "
                            "resolved) — owner judgment record ONLY; does NOT unblock assembly "
                            "or waive the material requirement")
    p.add_argument("--run", required=True); p.add_argument("--id", required=True)
    p.add_argument("--by", required=True); p.add_argument("--value-json"); p.add_argument("--note")
    p.set_defaults(f=cmd_resolve_material_exception)

    for name, fn, helptext in (
        ("build-package", cmd_build_package,
         "assemble the COMPLETE A–G execution package + immutable F manifest and register it"),
        ("validate-package", cmd_validate_package,
         "validate the COMPLETE A–G package, bind the manifest, record a hash-bound attempt")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--run", required=True)
        p.add_argument("--architecture", required=True,
                       help="campaign architecture JSON (judgment: collections/rails/content)")
        p.add_argument("--campaign", required=True); p.add_argument("--campaign-name", required=True)
        p.add_argument("--build", required=True); p.add_argument("--judgment", required=True)
        p.add_argument("--engine")
        p.add_argument("--truth", help="engine truth export / v2 snapshot for A (Master CSV) "
                                       "hydration; default <engine>/exports/current_truth.jsonl")
        p.add_argument("--revision", type=int, default=1)
        p.set_defaults(f=fn)

    # ── STRUCTURED FRONT HALF (spec 1.8.0) ──
    p = sub.add_parser("register-object",
                       help="build + register an IMMUTABLE structured front-half object revision "
                            "(research_brief|research_ledger|campaign_directions|campaign_spec)")
    p.add_argument("--run", required=True)
    p.add_argument("--kind", required=True, choices=list(FRONT_HALF_KINDS))
    p.add_argument("--payload", required=True, help="JSON/YAML object payload")
    p.set_defaults(f=cmd_register_object)

    p = sub.add_parser("select-direction",
                       help="record the owner's EXACT direction selection, hash-bound (task §8)")
    p.add_argument("--run", required=True); p.add_argument("--direction-id", required=True)
    p.add_argument("--by", required=True)
    p.add_argument("--status", default="owner_confirmed",
                   choices=["provisional_recommendation", "owner_confirmed"])
    p.add_argument("--note")
    p.set_defaults(f=cmd_select_direction)

    p = sub.add_parser("approve-object",
                       help="record a typed, hash-bound front-half approval (kickoff/premise/"
                            "verticals/architecture/final campaign_spec) (task §4/§11/§20/§21)")
    p.add_argument("--run", required=True); p.add_argument("--id", required=True)
    p.add_argument("--kind", required=True, choices=list(FRONT_HALF_KINDS))
    p.add_argument("--binding", required=True, choices=["object", "section", "composite"])
    p.add_argument("--section", help="section name for --binding section")
    p.add_argument("--sections", help="comma-separated sections for --binding composite")
    p.add_argument("--by", required=True)
    p.add_argument("--status", default="owner_confirmed",
                   choices=["provisional_recommendation", "owner_confirmed"])
    p.add_argument("--note")
    p.set_defaults(f=cmd_approve_object)

    p = sub.add_parser("approve-package",
                       help="record the owner execution-package approval bound to the EXACT "
                            "current Execution Manifest (task §23)")
    p.add_argument("--run", required=True); p.add_argument("--by", required=True)
    p.add_argument("--note")
    p.set_defaults(f=cmd_approve_package)

    p = sub.add_parser("verify-live",
                       help="record the computed live-verification the LIVE gate consumes "
                            "(the only writer of `verification`; binds to the executed build)")
    p.add_argument("--run", required=True); p.add_argument("--executed-build", required=True)
    p.add_argument("--result", required=True, choices=["pass", "fail"])
    p.add_argument("--method", required=True, choices=["automated_probe", "human_observation"])
    p.add_argument("--reprobe-at"); p.add_argument("--rail-ids")
    p.add_argument("--observed-by"); p.add_argument("--evidence")
    p.set_defaults(f=cmd_verify_live)

    p = sub.add_parser("reopen",
                       help="prepare a reopen edge (supersede artifacts, write invalidated, "
                            "record the reopen decision) so a following transition validates")
    p.add_argument("--run", required=True); p.add_argument("--to", required=True)
    p.add_argument("--by", required=True); p.add_argument("--reason", required=True)
    p.add_argument("--value-json")
    p.set_defaults(f=cmd_reopen)

    p = sub.add_parser("migrate",
                       help="Model B: bump this run's pinned spec/charter versions to the "
                            "current on-disk canon and record the migration (required before "
                            "a stale-pinned run can transition)")
    p.add_argument("--run", required=True)
    p.add_argument("--by", required=True)
    p.add_argument("--note")
    p.set_defaults(f=cmd_migrate)

    p = sub.add_parser("promote")
    p.add_argument("--run", required=True)
    p.add_argument("--purpose", default="original")
    p.set_defaults(f=cmd_promote)

    p = sub.add_parser("register-artifact")
    p.add_argument("--run", required=True); p.add_argument("--key", required=True)
    p.add_argument("--path", required=True); p.set_defaults(f=cmd_register_artifact)

    p = sub.add_parser("set")
    p.add_argument("--run", required=True); p.add_argument("--path", required=True)
    p.add_argument("--value"); p.add_argument("--value-json")
    p.set_defaults(f=cmd_set)

    p = sub.add_parser("review-inputs")
    p.add_argument("--run", required=True); p.set_defaults(f=cmd_review_inputs)

    p = sub.add_parser("unregister-artifact")
    p.add_argument("--run", required=True); p.add_argument("--key", required=True)
    p.set_defaults(f=cmd_unregister_artifact)

    p = sub.add_parser("validate")
    p.add_argument("--run", required=True); p.add_argument("--to"); p.add_argument("--json", action="store_true")
    p.set_defaults(f=cmd_validate)

    p = sub.add_parser("transition")
    p.add_argument("--run", required=True); p.add_argument("--to", required=True)
    p.set_defaults(f=cmd_transition)

    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
