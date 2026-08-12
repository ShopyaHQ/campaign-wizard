#!/usr/bin/env python3
"""Cross-repo contract tests: real Wizard-generated Request v2 artifacts are accepted and
interpreted identically by CollectionCuration (the Engine). Proves the coordinated
Request v2 + run_mode contract end to end.

    python3 tests/test_cross_repo_request_v2.py

Engine is located via the sibling path, isolated to ONE constant here (§15) — override with
$SHOPYA_ENGINE_ROOT.
"""
import os
import sys
import json
import tempfile
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

# --- transport: one isolated Engine-root resolution (no scattered ../ assumptions) ---
ENGINE_ROOT = os.environ.get("SHOPYA_ENGINE_ROOT") or os.path.join(
    os.path.dirname(ROOT), "shopya-collection-curation")
sys.path.insert(0, os.path.join(ENGINE_ROOT, "tools"))

import generate_curation_request as wiz  # noqa: E402
import request_v2 as engine  # noqa: E402
from validate_curation_request import normalize_request_v2  # noqa: E402

PASS, FAIL = [], []
READY = {"ready": True, "roster_working_profiles": 200, "required": 200}
UNREADY = {"ready": False, "roster_working_profiles": 166, "required": 200}


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %s  %s%s" % ("PASS" if cond else "FAIL", name,
                          ("  <- " + detail) if detail and not cond else ""))


def run_state(run_mode="production", run_id="cmp_01KZCD765E6NNW2TZR1AFHQMWG",
              campaign_id="almost-fall-2026"):
    return {"run": {"run_id": run_id, "run_mode": run_mode, "spec_version": "1.7.0"},
            "identity": {"campaign_id": {"value": campaign_id}}}


def main():
    # =====================================================================
    # PRODUCTION happy path — generate -> Engine validates -> normalized -> depth
    # =====================================================================
    art, errs = wiz.build_request(run_state("production"), "w.coats", 50,
                                  eligibility={"price_usd_max": 800})
    ok("Wizard generates a production v2 request", art is not None and not errs)
    ok("cross-repo HASH equality (wizard hash == engine hash)",
       wiz.request_hash(art) == engine.request_hash(art)
       and art["integrity"]["request_hash"] == engine.request_hash(art))
    ok("Engine accepts the Wizard artifact (production + ready)",
       normalize_request_v2(art, info=READY)["accepted"])
    res = normalize_request_v2(art, info=READY)
    ok("Engine returns a normalized eligibility spec",
       res["spec"] and res["spec"]["category_id"] == "w.coats"
       and res["spec"].get("price_usd_max") == 800)
    # kernel consumes the spec -> expected depth
    from eligibility import eligible_products  # noqa: E402
    from taxonomy_membership import sellable_membership_view, make_membership  # noqa: E402
    from sellable_identity import compute_sellable_uids  # noqa: E402
    from taxonomy import load_taxonomy  # noqa: E402
    rows = [{"product_uid": "b:coat:blk", "brand": "B", "product_name": "Coat",
             "url": "https://b.com/products/coat", "url_class": "pdp",
             "stock_status": "in_stock", "confidence": "confirmed_live", "price_usd": 100.0}]
    ev = [make_membership("b:coat:blk", "w.coats", "m", "e", "2026-08-12", "2026-08-12",
                          taxonomy=load_taxonomy())]
    sv = sellable_membership_view(ev, compute_sellable_uids(rows))
    ok("Engine eligibility fixture produces expected depth from the Wizard request",
       eligible_products(res["spec"], rows, sv)["eligible_depth"] == 1)

    # =====================================================================
    # PRODUCTION Foundation failure — Engine refuses, no acknowledgment bypass
    # =====================================================================
    ok("production request REFUSED below Foundation Readiness",
       not normalize_request_v2(art, info=UNREADY)["accepted"])

    # =====================================================================
    # DIAGNOSTIC — inherits diagnostic; Engine recognizes distinct authority
    # =====================================================================
    dart, _ = wiz.build_request(run_state("diagnostic"), "w.coats", 50)
    ok("diagnostic run yields a diagnostic v2 request", dart["run_mode"] == "diagnostic")
    dres = normalize_request_v2(dart, info=UNREADY)
    ok("Engine validates diagnostic below Foundation and marks it diagnostic",
       dres["accepted"] and dres["diagnostic"] is True)
    ok("Engine does NOT treat diagnostic as production",
       normalize_request_v2(art, info=UNREADY)["accepted"] is False
       and dres["diagnostic"] is True)

    # =====================================================================
    # TAMPERED MODE — a request cannot self-promote diagnostic -> production
    # =====================================================================
    tampered = dict(dart); tampered["run_mode"] = "production"   # tamper without re-hashing
    ok("tampering run_mode breaks the hash", not engine.verify_hash(tampered))
    ok("Engine refuses a tampered-mode request (self-promotion blocked)",
       not normalize_request_v2(tampered, info=READY)["accepted"])

    # =====================================================================
    # v1 PRODUCTION vs HISTORICAL READ (Request v2 §4/§5)
    # =====================================================================
    v1 = {"contract_version": "1.0.0", "campaign_id": "c", "run_ref": "cmp_x",
          "category_id": "w.coats", "required_depth": 50,
          "inclusion_logic": "wool", "exclusion_logic": "no casual"}
    tmp = tempfile.mkdtemp()
    f = os.path.join(tmp, "v1.json"); json.dump(v1, open(f, "w"))
    import subprocess
    VCLI = os.path.join(ENGINE_ROOT, "tools", "validate_curation_request.py")

    def _cli(*extra):
        return subprocess.run([sys.executable, VCLI, f, *extra],
                              capture_output=True, text=True)

    r = _cli()
    ok("v1 request REFUSED for new production (never new production)",
       r.returncode == 2 and "LEGACY" in (r.stdout + r.stderr))
    # historical structural read: works BELOW today's Foundation Readiness (roster is 166<200
    # in this repo state), and confers NO production authority.
    r = _cli("--allow-legacy-v1")
    ok("v1 historical read WORKS below current Foundation Readiness (structural, non-production)",
       r.returncode == 0 and "NON-PRODUCTION" in r.stdout
       and "no Foundation gate applied" in r.stdout)
    ok("v1 historical read confers no production authority (explicitly non-production)",
       "NON-PRODUCTION" in r.stdout and "READABLE (legacy v1" in r.stdout)
    # a legacy flag can never create production authority: no ACCEPTED-production wording.
    ok("legacy flag never yields production acceptance",
       "ACCEPTED (v2)" not in r.stdout)
    shutil.rmtree(tmp)

    # =====================================================================
    # PRODUCT-FACT LEAK — refused
    # =====================================================================
    leak = dict(art); leak["price_usd"] = 100; leak = engine.stamp_hash(leak)
    ok("a request carrying a forbidden product fact is refused",
       not normalize_request_v2(leak, info=READY)["accepted"])

    # =====================================================================
    # UNSUPPORTED PROSE-ONLY REQUIRED CONSTRAINT — generation refuses
    # =====================================================================
    none_art, errs = wiz.build_request(run_state("production"), "w.coats", 50,
                                       required_prose=["must be hand-finished"])
    ok("generation REFUSES a required prose constraint (never silently dropped)",
       none_art is None and errs)

    # =====================================================================
    # TAXONOMY — invalid category refused
    # =====================================================================
    badcat, _ = wiz.build_request(run_state("production"), "w.not-a-node", 50)
    ok("Engine refuses a non-canonical category from a generated request",
       not normalize_request_v2(badcat, info=READY)["accepted"])

    # =====================================================================
    # DETERMINISM — identical inputs -> identical bytes/hash
    # =====================================================================
    a1, _ = wiz.build_request(run_state("production"), "w.coats", 50,
                              eligibility={"price_usd_max": 800})
    a2, _ = wiz.build_request(run_state("production"), "w.coats", 50,
                              eligibility={"price_usd_max": 800})
    ok("deterministic generation: identical inputs -> identical request_hash",
       a1["integrity"]["request_hash"] == a2["integrity"]["request_hash"])

    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        for f in FAIL:
            print("  FAILED: %s" % f)
        sys.exit(1)


if __name__ == "__main__":
    main()
