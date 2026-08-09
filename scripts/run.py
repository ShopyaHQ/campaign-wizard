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
    st = {
        "run": {"run_id": rid, "spec_version": spec_v, "charter_version": chart_v,
                "created_at": now()},
        "identity": {
            "campaign_id": {"value": None, "status": None, "confirmed_by_owner": False,
                            "externally_referenced": False, "first_external_reference": None},
            "display_name": None},
        "workflow": {"state": "NEW", "entered_at": now(),
                     "history": [{"from": None, "to": "NEW", "at": now(),
                                  "transition_type": "forward",
                                  "pinned_spec_version": spec_v,
                                  "pinned_charter_version": chart_v,
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
    atomic_write(state_path(a.run), s)
    print("migrated run %s: spec %s->%s, charter %s->%s"
          % (a.run, frm_spec, to_spec, frm_chart, to_chart))
    print("  by %s: %s" % (a.by, a.note or "(no note)"))


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

    p = sub.add_parser("new");  p.add_argument("--note"); p.set_defaults(f=cmd_new)
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
