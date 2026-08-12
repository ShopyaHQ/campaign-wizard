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

CURRENT-vs-TARGET honesty (§5/§12): the approved structured campaign_spec object does not
exist yet, so spec_ref binds to the current run (kind='run', hash=null). When campaign_spec
lands, only this input adapter changes — Request v2 semantics do not.
"""
import argparse
import hashlib
import json
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(ROOT, "campaigns")
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
                  advisory=None, required_prose=None, request_id=None):
    """Build (and hash) a v2 request from run judgment. Returns (artifact, errors).

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

    artifact = {
        "contract_version": CONTRACT_VERSION,
        "request_id": rid,
        "campaign_id": ident.get("value") or "unnamed",
        "run_ref": run.get("run_id"),
        "run_mode": run_mode,
        "spec_ref": {"kind": "run", "ref": run.get("run_id"), "version": None, "hash": None},
        "category_id": category_id,
        "required_depth": required_depth,
        "eligibility": elig,
        "advisory": adv,
    }
    return stamp_hash(artifact), []


def _csv(s):
    return [x.strip() for x in s.split(",") if x.strip()] if s else None


def main():
    ap = argparse.ArgumentParser(description="Deterministic Curation Request v2 generator")
    ap.add_argument("--run", required=True)
    ap.add_argument("--category-id", required=True)
    ap.add_argument("--required-depth", type=int, required=True)
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


if __name__ == "__main__":
    main()
