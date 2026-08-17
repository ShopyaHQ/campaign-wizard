#!/usr/bin/env python3
"""smoke_real_merchandising.py — real Claude worker through the post_fulfillment_merchandising work
type (closeout §13). NOT in the automated suite (needs the live Claude CLI). Disposable controlled
fixture; NO live sourcing, NO Almost Fall.

Drives a run to satisfied fulfillment (controlled Engine fixture), then invokes the REAL Claude
merchandising worker: it must return valid bounded selections from the supplied eligible set (only
eligible UIDs, no product facts), which the Wizard validates + registers, then builds/validates/emits F.

Run:  python3 tests/smoke_real_merchandising.py
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "tests"))


def main():
    import worker as wk
    if not wk.claude_cli_available():
        print("SKIP: claude CLI not available — cannot run the real merchandising smoke.")
        sys.exit(2)

    tmp = tempfile.mkdtemp(prefix="smoke_merch_")
    runs = os.path.join(tmp, "campaigns")
    os.makedirs(os.path.join(runs, "_drafts"))
    os.environ["SHOPYA_CAMPAIGN_RUNS"] = runs
    os.environ["SHOPYA_WIZARD_WORKER_CMD"] = "%s %s" % (
        sys.executable, os.path.join(ROOT, "console", "workers", "claude_worker.py"))
    for m in ("run", "checkpoint_core", "front_half", "worker"):
        sys.modules.pop(m, None)
    import checkpoint_core as cc
    import worker as wk
    import front_half_fixture as fx
    import cross_repo_fixture as xf
    import test_back_half_flow as bh
    fails = []
    try:
        CATS = ["w.coats"]
        # front half via the deterministic spec worker (fast); fulfillment via controlled Engine
        rid = bh._front_half_to_build(cc, wk, fx, CATS, )
        cc.generate_requests(rid)
        s = cc._rt().require_run(rid)
        my_run, my_camp = s["run"]["run_id"], (s["identity"]["campaign_id"] or {}).get("value") or "xrepo-2026"
        e = xf.EngineEnv()
        for cat in CATS:
            out, req, rec = e.satisfied(category=cat, depth=55, required=50,
                                        run_id=my_run, campaign_id=my_camp)
            rp = os.path.join(tmp, "req.json"); json.dump(req, open(rp, "w"))
            cc.ingest_receipt(rid, out["receipt_path"], rp, snapshot_dir=e.snaps,
                              no_run_check=True, no_campaign_check=True)
        print("fulfillment complete; invoking the REAL Claude merchandising worker…")

        # REAL worker (SHOPYA_WIZARD_WORKER_CMD → claude_worker.py) — no explicit worker passed
        res = cc.generate_execution_package(rid)
        sel = cc._current_object_bytes(cc._rt().require_run(rid), cc._rt().run_dir, rid,
                                       "execution_selection")
        picks = (sel or {}).get("selections", [{}])[0].get("picks", [])
        print("execution_selection picks:", len(picks),
              "| provenance:", (sel or {}).get("worker_provenance"))
        if not res.get("validated"):
            fails.append("package did not validate")
        if not picks:
            fails.append("no picks produced")
        # every pick is from the eligible set (the Wizard already validated; re-assert here)
        import receipt_ingest as ri
        ing = ri.load_ingestions(cc._run_store(rid))[0]
        elig = set(ing["eligible_sellable_set"])
        if not all(p.get("sellable_product_uid") in elig for p in picks):
            fails.append("a pick was outside the eligible set")
        # no product facts authored
        if any(set(p) & {"price", "price_usd", "url", "product_name", "stock_status"} for p in picks):
            fails.append("a pick carried product facts")
        e.close()

        print()
        if fails:
            print("REAL MERCHANDISING SMOKE FAILED:")
            for f in fails:
                print("  -", f)
            sys.exit(1)
        print("REAL MERCHANDISING SMOKE PASSED: live Claude merchandised the fulfilled eligible "
              "products into valid bounded selections → validated → F manifest %s."
              % res.get("manifest_id"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        for k in ("SHOPYA_CAMPAIGN_RUNS", "SHOPYA_WIZARD_WORKER_CMD"):
            os.environ.pop(k, None)


if __name__ == "__main__":
    main()
