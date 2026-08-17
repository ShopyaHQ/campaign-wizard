#!/usr/bin/env python3
"""test_merchandising_flow.py — post-fulfillment merchandising automation (closeout §12).

Proves the browser owner-flow generates the execution package MECHANICALLY: no owner-supplied truth
export, no curated product rows. The Wizard loads the receipt-bound Truth Export automatically,
invokes the merchandising worker over the BOUNDED eligible set, validates + registers the
execution_selection, materializes the judgment rows, and builds → validates → emits F.

Adversarial: worker chooses noneligible UID / wrong-category / product-fact mutation / duplicate →
refused; worker failure → safe retry; no F from invalid selections.

Deterministic + network-free (fake worker + existing Engine fixtures). Run directly.
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

PASS, FAIL = [], []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %s %s%s" % ("PASS " if cond else "FAIL ", name, "" if cond else "  << " + str(detail)))


def _fulfilled_run(cc, wk, fx, xf, tmp, cats):
    """A run driven to satisfied fulfillment for `cats` (front half via fake spec worker)."""
    import test_back_half_flow as bh
    rid = bh._front_half_to_build(cc, wk, fx, cats)
    cc.generate_requests(rid)
    s = cc._rt().require_run(rid)
    my_run = s["run"]["run_id"]
    my_camp = (s["identity"]["campaign_id"] or {}).get("value") or "xrepo-2026"
    e = xf.EngineEnv()
    for cat in cats:
        out, req, rec = e.satisfied(category=cat, depth=55, required=50,
                                    run_id=my_run, campaign_id=my_camp)
        rp = os.path.join(tmp, "req_%s.json" % cat.replace(".", "_"))
        json.dump(req, open(rp, "w"))
        cc.ingest_receipt(rid, out["receipt_path"], rp, snapshot_dir=e.snaps,
                          no_run_check=True, no_campaign_check=True)
    return rid, e


def main():
    tmp = tempfile.mkdtemp(prefix="merch_")
    runs = os.path.join(tmp, "campaigns")
    os.makedirs(os.path.join(runs, "_drafts"))
    os.environ["SHOPYA_CAMPAIGN_RUNS"] = runs
    for m in ("run", "checkpoint_core", "front_half", "worker"):
        sys.modules.pop(m, None)
    import checkpoint_core as cc
    import worker as wk
    import front_half_fixture as fx
    import cross_repo_fixture as xf
    try:
        # ── automatic truth-export binding (task §2) ──
        rid, e = _fulfilled_run(cc, wk, fx, xf, tmp, ["w.coats"])
        s = cc._rt().require_run(rid)
        import receipt_ingest as ri
        ing = ri.load_ingestions(cc._run_store(rid))[0]
        ok("bound Truth Export snapshot persisted automatically at ingestion",
           cc.bound_snapshot_path(rid, ing["truth_export_id"]) is not None)

        # ── MECHANICAL package generation: NO judgment / truth / product inputs ──
        res = cc.generate_execution_package(rid, worker=wk.FakeWorker())
        ok("generate_execution_package builds + validates + emits F with NO owner inputs",
           res.get("validated") and res.get("manifest_id"), res)
        sel = cc._current_object_bytes(cc._rt().require_run(rid), cc._rt().run_dir, rid,
                                       "execution_selection")
        ok("an immutable execution_selection artifact was registered (Wizard merchandising judgment)",
           sel is not None and sel.get("canonical_hash") and sel.get("selections"))
        # selection references Engine facts by UID; carries NO product facts
        pick = sel["selections"][0]["picks"][0]
        ok("selection references sellable identity by UID, authors no product facts",
           "sellable_product_uid" in pick and not (set(pick) & {"price", "price_usd", "url",
                                                                 "product_name", "stock_status"}))
        # pins/order generated mechanically (12 rail positions per collection)
        railpos = sorted(p["rail_position"] for p in sel["selections"][0]["picks"] if p["is_rail_item"])
        ok("pins/order generated mechanically (rail positions 1..12)",
           railpos == list(range(1, 13)), railpos)
        # owner-friendly review has selected/pinned counts
        pkg = cc.execution_package_view(rid)
        ok("execution review shows selected + pinned product counts (no product-row form)",
           pkg["summary"]["collections"][0]["selected"] > 0
           and any(r["pinned"] for r in pkg["summary"]["rails"]))
        # approve the exact manifest (unchanged)
        av = cc.approve_package(rid, by="product_owner")
        ok("exact-manifest approval unchanged (owner approves the built package)", av["approved"])
        e.close()

        # ── SELECTION AUTHORITY adversarial (task §5) ──
        rid2, e2 = _fulfilled_run(cc, wk, fx, xf, tmp, ["w.coats"])
        ctx = cc._merchandising_worker_input(rid2)
        good_uid = ctx["requests"][0]["eligible"][0]

        def sel_payload(picks, cat="w.coats"):
            return {"execution_selection_id": "es_x", "revision": "r001",
                    "selections": [{"category_id": cat, "picks": picks}]}

        cases = [
            ("noneligible UID", sel_payload([{"sellable_product_uid": "sp:not:eligible",
                                              "collection_position": 1, "is_rail_item": False}]),
             ("selection_not_eligible", "selection_absent_from_truth")),
            ("wrong category", sel_payload([], cat="w.boots"), ("selection_wrong_category",)),
            ("product-fact mutation", sel_payload([{"sellable_product_uid": good_uid, "price_usd": 9.99,
                                                    "collection_position": 1, "is_rail_item": False}]),
             ("selection_authors_product_truth",)),
            ("duplicate identity", sel_payload([
                {"sellable_product_uid": good_uid, "collection_position": 1, "is_rail_item": False},
                {"sellable_product_uid": good_uid, "collection_position": 2, "is_rail_item": False}]),
             ("selection_duplicate",)),
        ]
        for label, payload, codes in cases:
            try:
                cc.build_execution_selection(rid2, payload)
                ok("selection refused: %s" % label, False, "should have refused")
            except cc.CheckpointError as ex:
                ok("selection refused: %s" % label, ex.code in codes, ex.code)

        # invalid selection cannot advance to a package (no F emitted)
        try:
            cc.generate_execution_package(rid2, worker=wk.FakeWorker(produce_invalid=True))
            ok("no package built from invalid selections", False, "should have refused")
        except cc.CheckpointError as ex:
            s2 = cc._rt().require_run(rid2)
            ok("no F manifest emitted from invalid selections",
               "execution_manifest" not in (s2.get("artifacts") or {}), ex.code)

        # ── worker FAILURE → safe retry ──
        rid3, e3 = _fulfilled_run(cc, wk, fx, xf, tmp, ["w.coats"])
        try:
            cc.generate_execution_package(rid3, worker=wk.FakeWorker(fail_on="post_fulfillment_merchandising"))
            ok("merchandising failure surfaces", False, "should fail")
        except cc.CheckpointError as ex:
            ok("merchandising worker failure is a clean, retryable error",
               ex.code == "merchandising_failed", ex.code)
        r = cc.generate_execution_package(rid3, worker=wk.FakeWorker())   # retry good worker
        ok("retry with a working worker succeeds (safe retry)", r.get("validated"))
        e2.close(); e3.close()

        print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
        sys.exit(1 if FAIL else 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("SHOPYA_CAMPAIGN_RUNS", None)


if __name__ == "__main__":
    main()
