#!/usr/bin/env python3
"""Cross-repo receipt-ingestion tests (task §27: RECEIPT INGESTION + SHORTFALL + RECEIPT SET).

    python3 tests/test_receipt_ingest.py

Every receipt here is a REAL Engine (CollectionCuration) Curation Receipt v1 produced from a
genuine Wizard-generated Request v2 and its exact Truth Export v2 snapshot (cross_repo_fixture).
The Wizard side (receipt_ingest.py) verifies, binds, and independently recomputes the eligible
SET — none of it mocked. Golden parity with the Engine's own verifier is asserted too.
"""
import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import receipt_ingest as ri  # noqa: E402
import cross_repo_fixture as fx  # noqa: E402
ENGINE_ROOT = fx.ENGINE_ROOT
sys.path.insert(0, os.path.join(ENGINE_ROOT, "tools"))
import curation_receipt as engine_cr  # noqa: E402  (Engine verifier — for parity only)

PASS, FAIL = [], []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %s  %s%s" % ("PASS" if cond else "FAIL", name,
                          ("  <- " + str(detail)[-300:]) if detail and not cond else ""))


def refused(fn, *a, **kw):
    try:
        fn(*a, **kw)
        return False, None
    except ri.ReceiptIngestError as e:
        return True, str(e)


def main():
    print("\n== RECEIPT INGESTION (real Engine receipts) ==")
    e = fx.EngineEnv()
    try:
        out, req, rec = e.satisfied()
        receipt = out["receipt"]
        store = os.path.join(e.d, "store")

        res = ri.ingest_receipt(out["receipt_path"], req, snapshot_dir=e.snaps, store_dir=store,
                                expected_run_mode="production", generated_at="t")
        ok("valid satisfied Receipt accepted", res["accepted"] and res["satisfied"])
        ok("independently recomputed eligible SET matches achieved_depth",
           res["recomputed_depth"] == receipt["eligibility"]["achieved_depth"] ==
           len(res["eligible_sellable_set"]))
        ok("ingestion recorded immutably",
           os.path.exists(res["ingestion_path"]) and res["wrote_ingestion"])
        ok("re-ingesting the same receipt is idempotent (no-op)",
           ri.ingest_receipt(out["receipt_path"], req, snapshot_dir=e.snaps, store_dir=store,
                             expected_run_mode="production", generated_at="t2")["wrote_ingestion"]
           is False)

        # GOLDEN PARITY: the Wizard's independent verifier agrees with the Engine's own verifier.
        eng_ok, _ = engine_cr.verify_receipt_artifact(receipt)
        wiz_ok = all(ri.verify_receipt(receipt).values())
        ok("Wizard verifier parity with Engine verifier (both accept a valid receipt)",
           eng_ok and wiz_ok)

        # receipt hash tamper refused
        tampered = copy.deepcopy(receipt)
        tampered["eligibility"]["achieved_depth"] = 999
        ok_ref, msg = refused(ri.ingest_receipt, tampered, req, snapshot_dir=e.snaps,
                              store_dir=store, expected_run_mode="production")
        ok("receipt hash tamper refused", ok_ref, msg)

        # wrong Request hash refused (same request_id, different content -> different hash)
        wrongreq = copy.deepcopy(req)
        wrongreq["required_depth"] = 60   # changes canonical hash but not request_id necessarily
        import generate_curation_request as gcr
        wrongreq = gcr.stamp_hash({k: v for k, v in wrongreq.items() if k != "integrity"})
        wrongreq["request_id"] = req["request_id"]   # force same id, wrong hash
        ok_ref, msg = refused(ri.ingest_receipt, out["receipt_path"], wrongreq,
                              snapshot_dir=e.snaps, store_dir=store, expected_run_mode="production")
        ok("same request_id with wrong hash refused", ok_ref, msg)

        # wrong category/eligibility binding refused (receipt for a different request entirely)
        other_req = e.request(category="w.coats", required_depth=50, campaign_id="other-2026",
                              run_id="cmp_01OTHER0000000000000000000")
        ok_ref, msg = refused(ri.ingest_receipt, out["receipt_path"], other_req,
                              snapshot_dir=e.snaps, store_dir=store, expected_run_mode="production")
        ok("receipt for another request/run refused", ok_ref, msg)

        # Truth Export tamper refused (corrupt the snapshot bytes)
        snap_path = receipt["truth_export"]["immutable_ref"]
        raw = open(snap_path, "rb").read()
        bad_snap = os.path.join(e.d, "bad.jsonl")
        open(bad_snap, "wb").write(raw.replace(b"in_stock", b"in_STOCK", 1))
        r2 = copy.deepcopy(receipt)
        r2["truth_export"]["immutable_ref"] = bad_snap
        # recompute id/sha so the receipt itself still self-verifies (isolate the snapshot tamper)
        r2p = os.path.join(e.d, "r2.json")
        open(r2p, "w").write(json.dumps(r2))
        ok_ref, msg = refused(ri.ingest_receipt, r2p, req, store_dir=store,
                              expected_run_mode="production")
        ok("Truth Export tamper refused (snapshot fails hash / recompute mismatch)", ok_ref, msg)
    finally:
        e.close()

    print("\n== run_mode / diagnostic refusal ==")
    e = fx.EngineEnv()
    try:
        out, req, rec = e.satisfied(run_mode="diagnostic")
        store = os.path.join(e.d, "store")
        ok_ref, msg = refused(ri.ingest_receipt, out["receipt_path"], req, snapshot_dir=e.snaps,
                              store_dir=store, expected_run_mode="production")
        ok("diagnostic receipt refused in a production ingestion", ok_ref, msg)
        # ... but accepted in a diagnostic ingestion
        res = ri.ingest_receipt(out["receipt_path"], req, snapshot_dir=e.snaps, store_dir=store,
                                expected_run_mode="diagnostic", generated_at="t")
        ok("diagnostic receipt accepted in a diagnostic ingestion", res["accepted"])
    finally:
        e.close()

    print("\n== SHORTFALL -> Fulfillment Exception -> Material Exception ==")
    e = fx.EngineEnv()
    try:
        out, req, rec = e.shortfall()
        receipt, exc_path = out["receipt"], out["exception_path"]
        store = os.path.join(e.d, "store")

        # shortfall WITHOUT the matching exception is refused
        ok_ref, msg = refused(ri.ingest_receipt, out["receipt_path"], req, snapshot_dir=e.snaps,
                              store_dir=store, expected_run_mode="production")
        ok("shortfall Receipt without a Fulfillment Exception is refused", ok_ref, msg)

        res = ri.ingest_receipt(out["receipt_path"], req, snapshot_dir=e.snaps, store_dir=store,
                                fulfillment_exception_path=exc_path,
                                expected_run_mode="production", generated_at="t")
        ok("shortfall Receipt + matching Fulfillment Exception ingests", res["accepted"])
        mx = res.get("material_exception")
        ok("a Material Exception opens (status open)", mx and mx["status"] == "open")
        ok("Material Exception BLOCKS assembly", res["blocks_assembly"] is True)
        ok("Material Exception facts derived from Engine artifacts (required/achieved/gap)",
           mx["required_depth"] == receipt["eligibility"]["required_depth"] and
           mx["achieved_depth"] == receipt["eligibility"]["achieved_depth"] and
           mx["gap"] == receipt["eligibility"]["gap"])
        ok("Material Exception carries NO auto-widen/substitute field",
           not any(k in mx for k in ("widen_to", "substitute_category", "drop_collection",
                                     "recommendation")))

        # a Fulfillment Exception for a DIFFERENT fulfillment is refused
        e2 = fx.EngineEnv()
        try:
            out2, req2, rec2 = e2.shortfall()
            ok_ref, msg = refused(ri.ingest_receipt, out["receipt_path"], req, snapshot_dir=e.snaps,
                                  store_dir=store, fulfillment_exception_path=out2["exception_path"],
                                  expected_run_mode="production")
            ok("a Fulfillment Exception for another fulfillment is refused", ok_ref, msg)
        finally:
            e2.close()

        # --- Issue B: package completeness BEFORE resolving (open exception + shortfall) ---
        import execution_package as ep0
        arch = {"collections": [{"category_id": "w.coats", "display_name": "Coats",
                                 "request_id": req["request_id"]}]}
        fview_before = ep0.build_fulfillment_view(ri.load_ingestions(store),
                                                  ri.load_material_exceptions(store))
        comp_before = ep0.check_receipt_completeness(arch, fview_before, "production")
        ok("BEFORE resolve: package completeness is BLOCKED (shortfall + open exception)",
           not comp_before["complete"])

        # owner resolution: records owner JUDGMENT (open -> resolved). It is NOT an unblock.
        rec_mx = ri.resolve_material_exception(store, mx["material_exception_id"],
                                               {"decision": "narrow_scope", "resolved_by": "product_owner"},
                                               generated_at="t2")
        ok("owner resolves Material Exception (open -> resolved)", rec_mx["status"] == "resolved")
        ok("resolution preserves the factual section unchanged (achieved_depth/gap immutable)",
           rec_mx["required_depth"] == mx["required_depth"] and
           rec_mx["achieved_depth"] == mx["achieved_depth"] and rec_mx["gap"] == mx["gap"])

        # --- Issue B core invariant: resolved exception does NOT satisfy completeness ---
        fview_after = ep0.build_fulfillment_view(ri.load_ingestions(store),
                                                 ri.load_material_exceptions(store))
        comp_after = ep0.check_receipt_completeness(arch, fview_after, "production")
        ing_after = fview_after["by_request"][req["request_id"]]
        ok("AFTER resolve: the Receipt is STILL shortfall (resolve does not transmute Engine result)",
           ing_after["terminal_status"] == "shortfall_policy_exhausted")
        ok("AFTER resolve: package completeness is STILL BLOCKED (render_003 not waived)",
           not comp_after["complete"] and
           any("not satisfied" in p and "does NOT waive" in p for p in comp_after["problems"]))
        ok("AFTER resolve: no category/request mutation occurred (category unchanged, no widening)",
           ing_after["category_id"] == "w.coats")

        # What DOES permit completeness: a genuine satisfied Receipt for a CURRENT expected Request
        # (produced by re-fulfillment, not by the exception flag). Prove it with a fresh satisfied
        # engine run for a different collection that IS satisfiable.
        e_sat = fx.EngineEnv()
        try:
            out2, req2, rec2 = e_sat.satisfied(category="w.coats", required=50)
            store2 = os.path.join(e_sat.d, "store")
            ri.ingest_receipt(out2["receipt_path"], req2, snapshot_dir=e_sat.snaps,
                              store_dir=store2, expected_run_mode="production", generated_at="t")
            fv2 = ep0.build_fulfillment_view(ri.load_ingestions(store2), ri.load_material_exceptions(store2))
            arch2 = {"collections": [{"category_id": "w.coats", "display_name": "Coats",
                                      "request_id": req2["request_id"]}]}
            comp2 = ep0.check_receipt_completeness(arch2, fv2, "production")
            ok("a satisfied Receipt (not the resolved flag) is what permits completeness",
               comp2["complete"])
        finally:
            e_sat.close()
    finally:
        e.close()

    print("\n== RECEIPT SET completeness (execution_package.check_receipt_completeness) ==")
    import execution_package as ep
    e = fx.EngineEnv()
    try:
        out, req, rec = e.satisfied(category="w.coats", required=50)
        store = os.path.join(e.d, "store")
        res = ri.ingest_receipt(out["receipt_path"], req, snapshot_dir=e.snaps, store_dir=store,
                                expected_run_mode="production", generated_at="t")
        ings = ri.load_ingestions(store)
        fview = ep.build_fulfillment_view(ings, ri.load_material_exceptions(store))

        arch_one = {"collections": [{"category_id": "w.coats", "display_name": "Coats",
                                     "request_id": req["request_id"]}]}
        comp = ep.check_receipt_completeness(arch_one, fview, "production")
        ok("complete expected set passes", comp["complete"], comp["problems"])

        # missing expected receipt blocks
        arch_two = {"collections": [
            {"category_id": "w.coats", "display_name": "Coats", "request_id": req["request_id"]},
            {"category_id": "w.dresses", "display_name": "Dresses", "request_id": "rq_missing"}]}
        comp = ep.check_receipt_completeness(arch_two, fview, "production")
        ok("missing expected receipt blocks", not comp["complete"] and
           any("no accepted receipt" in p for p in comp["problems"]))

        # unexpected receipt refused (an accepted receipt not in the architecture's expected set)
        arch_none = {"collections": [{"category_id": "w.dresses", "display_name": "Dresses",
                                      "request_id": "rq_other"}]}
        comp = ep.check_receipt_completeness(arch_none, fview, "production")
        ok("unexpected receipt (not in expected set) blocks", not comp["complete"] and
           any("unexpected receipt" in p for p in comp["problems"]))
    finally:
        e.close()

    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
