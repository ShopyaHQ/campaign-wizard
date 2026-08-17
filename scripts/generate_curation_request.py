#!/usr/bin/env python3
"""generate_curation_request.py — the ONE sanctioned deterministic Curation Request v2
generator (Wizard side).

Future Wizard orchestration must never hand-build request JSON. This reads the current run,
inherits its immutable run_mode, takes the selected canonical category + depth, and emits an
immutable, canonically-hashed Request v2 (contract_version 2.0.0) that Engine validates and
normalizes without prose guessing.

    python3 scripts/generate_curation_request.py --run <cmp_ULID> \
        --category-id w.coats --required-depth 50 [--out <path>] \
        [--price-usd-min N] [--price-usd-max N] \
        [--merchant-allow a,b] [--merchant-deny c,d] \
        [--advisory-json '{"inclusion_logic":"..."}'] \
        [--required-prose "must be hand-finished"]     # -> generation REFUSES (unstructured required)

Determinism: identical inputs -> identical canonical bytes -> identical request_hash. The
canonical form is json.dumps(payload, sort_keys=True, separators=(',',':'), ensure_ascii=False)
over the whole artifact EXCEPT integrity.request_hash — the SAME algorithm Engine's
tools/request_v2.py implements (no cross-repo import; the algorithm is the contract).

SPEC-REF MODES (task §22/§23):
  * vNext production: `--from-spec` binds spec_ref to the EXACT approved campaign_spec
    (kind='campaign_spec', ref=<cs_id>, version=<revision>, hash=<composite_hash>). Only a CURRENT,
    non-stale campaign_spec_approved owner decision authorizes generation; category_id + required_depth
    are read from the approved spec's collection_selections. This is the ONLY sanctioned production
    path once a campaign_spec exists.
  * compatibility / historical fixtures: without --from-spec, spec_ref binds to the current run
    (kind='run', hash=null) — retained for pre-campaign_spec / historical fixtures ONLY (the honest
    null-hash path). It must NOT be used for a new vNext production flow that has a campaign_spec.

Request v2 SEMANTICS (contract 2.0.0, canonical hashing) are UNCHANGED — only the spec_ref input
adapter differs. The canonical bytes / request_hash algorithm still matches Engine exactly.
"""
import argparse
import hashlib
import json
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.environ.get("SHOPYA_CAMPAIGN_RUNS", os.path.join(ROOT, "campaigns"))
CONTRACT_VERSION = "2.0.0"
FLOOR = 50   # render_003 hard floor (mirrors Engine)

# Structured eligibility keys the Engine kernel can enforce (mirrors Engine ELIGIBILITY_MACHINE_KEYS).
ELIGIBILITY_MACHINE_KEYS = {"category_id", "price_usd_min", "price_usd_max",
                            "merchant_allow", "merchant_deny"}
# Advisory (non-enforced, judgment/context) keys allowed under `advisory`.
ADVISORY_KEYS = {"inclusion_logic", "exclusion_logic", "merchant_preferences",
                 "price_expectations", "assortment_characteristics", "ideal_examples",
                 "avoid_terms", "campaign_context"}


# ---- canonical hashing: MUST match Engine tools/request_v2.py exactly ----
def canonical_bytes(artifact):
    payload = {k: v for k, v in artifact.items() if k != "integrity"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def request_hash(artifact):
    return hashlib.sha256(canonical_bytes(artifact)).hexdigest()


def stamp_hash(artifact):
    a = dict(artifact)
    a["integrity"] = {"request_hash": request_hash(artifact)}
    return a


def _find_run(run_id):
    for base in (os.path.join(RUNS, "_drafts"), RUNS):
        p = os.path.join(base, run_id, "state.yaml")
        if os.path.exists(p):
            return yaml.safe_load(open(p, encoding="utf-8"))
    # scan (runs may be promoted to named dirs)
    for d in os.listdir(RUNS) if os.path.isdir(RUNS) else []:
        p = os.path.join(RUNS, d, "state.yaml")
        if os.path.exists(p):
            s = yaml.safe_load(open(p, encoding="utf-8")) or {}
            if (s.get("run") or {}).get("run_id") == run_id:
                return s
    return None


def build_request(run_state, category_id, required_depth, eligibility=None,
                  advisory=None, required_prose=None, request_id=None, spec_ref=None):
    """Build (and hash) a v2 request from run judgment. Returns (artifact, errors).

    spec_ref: when supplied (vNext production, task §22), it is the EXACT approved-campaign_spec
    binding {kind:'campaign_spec', ref, version, hash}; otherwise the compatibility run binding
    {kind:'run', ref:<run_id>, version:null, hash:null}. Request v2 SEMANTICS are unchanged either
    way — spec_ref is just an input field the canonical hash already spans.

    A REQUIRED prose constraint that cannot be structured makes generation REFUSE — the
    request is never emitted with a silently-dropped required constraint (§8)."""
    errors = []
    run = run_state.get("run") or {}
    ident = (run_state.get("identity") or {}).get("campaign_id") or {}
    run_mode = run.get("run_mode")
    if run_mode not in ("production", "diagnostic"):
        errors.append("run has no valid run_mode (is it a pre-1.7.0 run?) — cannot inherit authority")
    if required_prose:
        errors.append("required prose constraint(s) %s cannot be deterministically enforced — "
                      "generation REFUSES (never silently dropped)"
                      % (required_prose if isinstance(required_prose, list) else [required_prose]))
    if not isinstance(required_depth, int) or required_depth < FLOOR:
        errors.append("required_depth must be an int >= %d" % FLOOR)

    elig = {"category_id": category_id}
    for k, v in (eligibility or {}).items():
        if k not in ELIGIBILITY_MACHINE_KEYS:
            errors.append("eligibility key %r is not machine-evaluable" % k)
        elif v is not None:
            elig[k] = v
    adv = {k: v for k, v in (advisory or {}).items() if k in ADVISORY_KEYS and v is not None}
    bad_adv = set((advisory or {}).keys()) - ADVISORY_KEYS
    if bad_adv:
        errors.append("advisory carries non-advisory key(s) %s" % sorted(bad_adv))

    if errors:
        return None, errors

    # deterministic request_id: derived from run + category + depth + mode (stable, opaque).
    rid = request_id or ("rq_" + hashlib.sha256(
        ("%s|%s|%s|%s" % (run.get("run_id"), category_id, required_depth, run_mode))
        .encode("utf-8")).hexdigest()[:26])

    # spec_ref: the exact approved campaign_spec binding for a vNext production flow, or the
    # honest compatibility run binding (kind='run', hash=null) for historical/pre-spec fixtures.
    sref = spec_ref or {"kind": "run", "ref": run.get("run_id"), "version": None, "hash": None}

    artifact = {
        "contract_version": CONTRACT_VERSION,
        "request_id": rid,
        "campaign_id": ident.get("value") or "unnamed",
        "run_ref": run.get("run_id"),
        "run_mode": run_mode,
        "spec_ref": sref,
        "category_id": category_id,
        "required_depth": required_depth,
        "eligibility": elig,
        "advisory": adv,
    }
    return stamp_hash(artifact), []


# ---------------------------------------------------------------------------
# vNext: derive request inputs from the EXACT approved campaign_spec (task §22/§23)
# ---------------------------------------------------------------------------
def approved_spec_binding(run_state):
    """Return (spec_ref, spec_doc, errors). A production Request may be generated from a campaign_spec
    ONLY when the run holds a CURRENT, non-stale campaign_spec_approved owner decision whose bound
    composite_hash equals the current campaign_spec spine composite_hash — the exact 'build this'
    authority (task §21/§23). Otherwise it returns errors; a stale/unapproved spec never generates."""
    errors = []
    spine = ((run_state.get("structured_objects") or {}).get("campaign_spec")) or {}
    dec = ((run_state.get("owner_decisions") or {}).get("campaign_spec_approved")) or {}
    inval = run_state.get("invalidated") or []
    if not spine:
        errors.append("no campaign_spec is registered — cannot generate a spec-bound Request")
        return None, None, errors
    if dec.get("status") != "owner_confirmed" or dec.get("decided") is not True:
        errors.append("no owner-confirmed campaign_spec_approved decision — the exact final "
                      "'build this' approval is required before production Request generation "
                      "(task §21/§23)")
    if "campaign_spec_approved" in inval:
        errors.append("campaign_spec_approved was invalidated (a dependency change/reopen) and "
                      "cannot authorize generation until re-recorded on the current spec")
    val = dec.get("value") or {}
    composite = spine.get("composite_hash")
    if val.get("composite_hash") != composite or val.get("revision") != spine.get("revision") \
            or val.get("object_id") != spine.get("object_id"):
        errors.append("campaign_spec_approved binds %r/%r/%r but the current spec is %r/%r/%r — a "
                      "stale approval cannot authorize a different revision"
                      % (val.get("object_id"), val.get("revision"), val.get("composite_hash"),
                         spine.get("object_id"), spine.get("revision"), composite))
    if errors:
        return None, None, errors
    spec_ref = {"kind": "campaign_spec", "ref": spine.get("object_id"),
                "version": spine.get("revision"), "hash": composite}
    return spec_ref, spine, errors


def selections_from_spec(spec_doc_sections):
    """Yield (category_id, requested_depth) for each durable collection_selection requiring
    fulfillment. Reads the approved spec's collection_selections section (task §22)."""
    out = []
    sel = ((spec_doc_sections or {}).get("collection_selections") or {}).get("selections") or []
    for c in sel:
        out.append((c.get("category_id"), c.get("requested_depth")))
    return out


def _csv(s):
    return [x.strip() for x in s.split(",") if x.strip()] if s else None


def main():
    ap = argparse.ArgumentParser(description="Deterministic Curation Request v2 generator")
    ap.add_argument("--run", required=True)
    ap.add_argument("--from-spec", action="store_true",
                    help="vNext production: derive category/depth + spec_ref from the EXACT approved "
                         "campaign_spec (requires a current campaign_spec_approved decision). Emits "
                         "ONE request per durable collection_selection unless --category-id narrows it.")
    ap.add_argument("--category-id", help="required WITHOUT --from-spec; with --from-spec, narrows "
                                          "generation to one selected category")
    ap.add_argument("--required-depth", type=int,
                    help="required WITHOUT --from-spec; with --from-spec, read from the spec")
    ap.add_argument("--price-usd-min", type=float)
    ap.add_argument("--price-usd-max", type=float)
    ap.add_argument("--merchant-allow")
    ap.add_argument("--merchant-deny")
    ap.add_argument("--advisory-json")
    ap.add_argument("--required-prose", action="append")
    ap.add_argument("--out")
    a = ap.parse_args()

    run_state = _find_run(a.run)
    if run_state is None:
        sys.exit("FATAL: no run %r found under campaigns/" % a.run)
    elig = {"price_usd_min": a.price_usd_min, "price_usd_max": a.price_usd_max,
            "merchant_allow": _csv(a.merchant_allow), "merchant_deny": _csv(a.merchant_deny)}
    advisory = json.loads(a.advisory_json) if a.advisory_json else None

    if a.from_spec:
        spec_ref, spine, errors = approved_spec_binding(run_state)
        if errors:
            print("REFUSED — cannot generate a spec-bound Request v2 (no current 'build this' "
                  "authority):")
            for e in errors:
                print("  ERROR: " + e)
            sys.exit(2)
        spec_doc = _find_spec_doc(a.run, spine)
        sections = (spec_doc or {}).get("sections") or {}
        pairs = selections_from_spec(sections)
        if a.category_id:
            pairs = [(c, d) for (c, d) in pairs if c == a.category_id]
            if not pairs:
                sys.exit("FATAL: --category-id %r is not a selected collection in the approved spec"
                         % a.category_id)
        arts, all_err = [], []
        for cat, depth in pairs:
            art, errs = build_request(run_state, cat, depth, eligibility=elig, advisory=advisory,
                                      required_prose=a.required_prose, spec_ref=spec_ref)
            if errs:
                all_err += ["%s: %s" % (cat, e) for e in errs]
            else:
                arts.append(art)
        if all_err:
            print("REFUSED — cannot generate a valid Request v2:")
            for e in all_err:
                print("  ERROR: " + e)
            sys.exit(2)
        base = a.out or os.path.join(os.path.dirname(_run_state_path(a.run)), "requests")
        os.makedirs(base if not base.endswith(".json") else os.path.dirname(base), exist_ok=True)
        for art in arts:
            out = (a.out if (a.out and len(arts) == 1) else
                   os.path.join(base, "request_%s.json" % art["category_id"].replace(".", "_")))
            with open(out, "w", encoding="utf-8") as f:
                json.dump(art, f, ensure_ascii=False, indent=2)
            print("generated Request v2 (spec-bound): %s" % out)
            print("  request_id  %s" % art["request_id"])
            print("  spec_ref    %s/%s hash=%s" % (spec_ref["ref"], spec_ref["version"],
                                                   (spec_ref["hash"] or "")[:16]))
            print("  category    %s  depth>=%d" % (art["category_id"], art["required_depth"]))
            print("  request_hash %s" % art["integrity"]["request_hash"])
        return

    if not a.category_id or a.required_depth is None:
        sys.exit("FATAL: --category-id and --required-depth are required without --from-spec")
    art, errors = build_request(run_state, a.category_id, a.required_depth,
                                eligibility=elig, advisory=advisory,
                                required_prose=a.required_prose)
    if errors:
        print("REFUSED — cannot generate a valid Request v2:")
        for e in errors:
            print("  ERROR: " + e)
        sys.exit(2)
    out = a.out or os.path.join(RUNS, "_drafts", a.run, "curation_request_v2.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(art, f, ensure_ascii=False, indent=2)
    print("generated Request v2: %s" % out)
    print("  request_id  %s" % art["request_id"])
    print("  run_mode    %s (inherited, immutable)" % art["run_mode"])
    print("  category    %s  depth>=%d" % (art["category_id"], art["required_depth"]))
    print("  request_hash %s" % art["integrity"]["request_hash"])


def _run_state_path(run_id):
    for base in (os.path.join(RUNS, "_drafts"), RUNS):
        p = os.path.join(base, run_id, "state.yaml")
        if os.path.exists(p):
            return p
    for d in os.listdir(RUNS) if os.path.isdir(RUNS) else []:
        p = os.path.join(RUNS, d, "runs", run_id, "state.yaml")
        if os.path.exists(p):
            return p
        p = os.path.join(RUNS, d, "state.yaml")
        if os.path.exists(p):
            s = yaml.safe_load(open(p, encoding="utf-8")) or {}
            if (s.get("run") or {}).get("run_id") == run_id:
                return p
    return os.path.join(RUNS, "_drafts", run_id, "state.yaml")


def _find_spec_doc(run_id, spine):
    """Load the approved campaign_spec revision bytes via its registered artifact path."""
    sp = _run_state_path(run_id)
    rundir = os.path.dirname(sp)
    key = spine.get("artifact_key") or "campaign_spec"
    state = yaml.safe_load(open(sp, encoding="utf-8")) or {}
    rec = (state.get("artifacts") or {}).get(key) or {}
    p = rec.get("path")
    if not p:
        return None
    full = p if os.path.isabs(p) else os.path.join(rundir, p)
    if not os.path.exists(full):
        full = os.path.join(ROOT, p)
    return yaml.safe_load(open(full, encoding="utf-8")) if os.path.exists(full) else None


if __name__ == "__main__":
    main()
