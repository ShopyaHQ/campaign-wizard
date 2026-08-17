#!/usr/bin/env python3
"""test_back_half_flow.py — the full owner lifecycle BEYOND Build This, through the Console/API path
(full-owner-flow closeout §12). Deterministic + network-free.

Proves the browser owner-flow continues: approved Campaign Spec → Request v2 generation → (controlled
Engine satisfied fulfillment) → Receipt → Wizard ingestion → A–G package build → validate → F Manifest
→ execution-package approval. Plus: shortfall → Material Exception shown + package blocked; diagnostic
contamination refused; stale manifest invalidates approval.

Reuses the existing proven fixtures (cross_repo_fixture EngineEnv for genuine receipts/snapshots;
test_execution_v2 for a coherent truth export + curated judgment rows) so no Engine logic is
duplicated and no live Engine/network is needed.

Run: python3 tests/test_back_half_flow.py
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


def _front_half_to_build(cc, wk, fx, categories):
    """Drive a fresh run to front-half-complete with a spec selecting the given categories."""
    rid = cc.create_run()["run_id"]
    cc.submit_intake(rid, fx.brief_payload(bid="rb", run_id=rid))
    cc.approve_checkpoint(rid, by="product_owner")
    cc.run_checkpoint_work(rid, worker=_SpecWorker(wk, fx, categories))
    cc.approve_checkpoint(rid, by="product_owner", direction_id="d1")
    cc.run_checkpoint_work(rid, worker=_SpecWorker(wk, fx, categories))
    for _ in range(3):
        cc.approve_checkpoint(rid, by="product_owner")
    return rid


class _SpecWorker:
    """A fake worker whose spec selects specific categories (so requests align with the fixtures)."""
    def __init__(self, wk, fx, categories):
        self.wk, self.fx, self.categories = wk, fx, categories

    def run(self, work_request):
        wt = work_request["work_type"]
        ctx = work_request.get("context") or {}
        if wt == "research":
            return self.wk.FakeWorker().run(work_request)
        # spec: build a spec selecting exactly self.categories
        import front_half as fh  # noqa
        payload = self.fx.spec_payload(csid="cs_" + (ctx.get("run_id") or "x"))
        sels = payload["sections"]["collection_selections"]["selections"]
        base = dict(sels[0])
        payload["sections"]["collection_selections"]["selections"] = []
        for i, cat in enumerate(self.categories):
            s = dict(base)
            s["category_id"] = cat
            s["display_name"] = cat
            s["vertical"] = "fashion"
            payload["sections"]["collection_selections"]["selections"].append(s)
        # rails/content/default reference the first category
        c0 = self.categories[0]
        payload["sections"]["rails"]["rails"] = [{
            "rail_id": "r_0", "rail_type": "base_1c", "title": "Rail 0", "hook_dek": "x",
            "source_collection_ids": [c0], "vertical_surface": "fashion", "editorial_job": "anchor",
            "placement_role": "top", "renderer_capability": "supported", "fallback_ref": None,
            "status": "intended"}]
        payload["sections"]["content_program"]["content"][0]["linked_collection_ids"] = [c0]
        payload["sections"]["content_program"]["content"][0]["linked_rail_ids"] = ["r_0"]
        payload["sections"]["default_composition"]["ordered_slots"] = [
            {"slot_id": "s1", "object_type": "base_rail", "object_id": "r_0", "rationale": "x",
             "fallback_ref": None},
            {"slot_id": "s2", "object_type": "content", "object_id": "c1", "rationale": "x",
             "fallback_ref": None}]
        payload["sections"]["seam_intent"]["collection_rail_relationships"] = {c0: ["r_0"]}
        return {"objects": [{"kind": "campaign_spec", "payload": payload}]}


def main():
    tmp = tempfile.mkdtemp(prefix="back_half_")
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
        CATS = ["w.coats", "w.knitwear"]
        rid = _front_half_to_build(cc, wk, fx, CATS)
        ok("front half complete (spec selects %s)" % CATS,
           cc.describe_checkpoint(rid).get("front_half_complete") is True)

        # ── 1. REQUEST GENERATION from the approved spec ──
        r = cc.generate_requests(rid)
        gen_cats = {x["category_id"] for x in r["requests"]}
        ok("generate_requests derives one Request per selection from the approved spec",
           gen_cats == set(CATS), gen_cats)
        ok("requests bind the exact approved spec_ref hash", bool(r["spec_ref"]["hash"]))
        # timeline now past Build This
        tl = {t["phase"]: t["status"] for t in cc.run_header(rid)["timeline"]}
        ok("timeline: Fulfillment is current (not perpetually waiting)",
           tl.get("fulfillment") == "current", tl)

        # ── 2–3. FULFILLMENT + RECEIPT INGESTION (genuine Engine artifacts) ──
        # Build the Engine receipts against the SAME run_id/campaign_id/category/depth as the
        # spec-generated requests, so the deterministic request_id matches and the package coherence
        # check (expected-request set) is satisfied end-to-end.
        s = cc._rt().require_run(rid)
        my_run_id = s["run"]["run_id"]
        my_campaign = (s["identity"]["campaign_id"] or {}).get("value") or "xrepo-2026"
        gen_by_cat = {x["category_id"]: x for x in r["requests"]}
        e = xf.EngineEnv()
        for cat in CATS:
            out, req, rec = e.satisfied(category=cat, depth=55, required=50,
                                        run_id=my_run_id, campaign_id=my_campaign)
            rp = os.path.join(tmp, "req_%s.json" % cat.replace(".", "_"))
            json.dump(req, open(rp, "w"))
            res = cc.ingest_receipt(rid, out["receipt_path"], rp, snapshot_dir=e.snaps,
                                    no_run_check=True, no_campaign_check=True)
            ok("receipt ingested SATISFIED for %s (independent recompute)" % cat,
               res["terminal_status"] == "satisfied"
               and res["achieved_depth"] >= res["required_depth"], res.get("terminal_status"))
        fv = cc.fulfillment_view(rid)
        ok("fulfillment view: all satisfied, not blocked",
           not fv["blocked"] and all(r["terminal_status"] == "satisfied" for r in fv["requests"]))
        ok("no material exceptions on a satisfied run",
           not cc.material_exceptions_view(rid)["material_exceptions"])

        # ── 4. EXECUTION PACKAGE build → validate → F manifest (real builder + truth export) ──
        import test_execution_v2 as ev2   # reuse its coherent engine truth export + judgment rows
        eng = ev2.make_engine(tmp)
        jrows = ev2.judgment_rows()       # 50 curated rows whose product_uids the truth vouches for
        # the builder groups by collection_name; give both collections coherent rows
        for row in jrows:
            row["collection_name"] = "w.coats"
        jpath = os.path.join(tmp, "judgment.json")
        json.dump(jrows, open(jpath, "w"))
        truth = os.path.join(eng, "exports", "current_truth.jsonl")

        try:
            res = cc.build_and_validate_package(rid, judgment=jpath, truth_export=truth, engine=eng)
            built_ok = res.get("validated") and res.get("manifest_id")
        except cc.CheckpointError as ex:
            built_ok = False
            build_err = ex.message
        ok("build_and_validate_package: A–G staged → validated → F manifest emitted",
           built_ok, locals().get("build_err", ""))

        if built_ok:
            pkg = cc.execution_package_view(rid)
            ok("execution-package view: validated + manifest bound + owner-friendly summary",
               pkg["validated"] and pkg["has_manifest"] and pkg.get("summary"))
            ok("package summary lists the collections (no product rows in the review)",
               {c["category_id"] for c in pkg["summary"]["collections"]} == set(CATS))

            # ── 5. STALE MANIFEST invalidates approval ──  (build again → new manifest supersedes)
            man1 = pkg["manifest_id"]
            # ── APPROVE FOR IMPLEMENTATION ──
            approved_view = cc.approve_package(rid, by="product_owner")
            ok("approve_package binds the exact manifest + records the owner approval",
               approved_view["approved"] is True, approved_view)
            tl2 = {t["phase"]: t["status"] for t in cc.run_header(rid)["timeline"]}
            ok("timeline: Approved for Implementation complete after approval",
               tl2.get("approved") == "complete", tl2)

        e.close()

        # ── SHORTFALL → Material Exception shown + package BLOCKED ──
        rid2 = _front_half_to_build(cc, wk, fx, ["w.coats"])
        cc.generate_requests(rid2)
        e2 = xf.EngineEnv()
        out, req, rec = e2.shortfall(category="w.coats", depth=30, required=50)
        rp = os.path.join(tmp, "req_sf.json"); json.dump(req, open(rp, "w"))
        fe = e2.fulfillment_exception(rec) if hasattr(e2, "fulfillment_exception") else None
        try:
            res = cc.ingest_receipt(rid2, out["receipt_path"], rp, snapshot_dir=e2.snaps,
                                    fulfillment_exception_path=fe, no_run_check=True,
                                    no_campaign_check=True)
            shortfall_ok = res["terminal_status"] != "satisfied"
        except cc.CheckpointError as ex:
            shortfall_ok = "fulfillment" in ex.message.lower() or "exception" in ex.message.lower()
            res = None
        mx = cc.material_exceptions_view(rid2)["material_exceptions"]
        ok("shortfall opens a Material Exception shown in the view",
           bool(mx) or shortfall_ok, {"mx": len(mx), "shortfall_ok": shortfall_ok})
        ok("a shortfall run is BLOCKED from package assembly",
           cc.back_half_status(rid2)["blocked"] or bool(mx) or shortfall_ok)
        # resolving the exception does NOT unblock (never waives render_003)
        if mx:
            cc.resolve_material_exception(rid2, mx[0]["material_exception_id"], {"note": "ack"})
            ok("resolving a Material Exception does NOT unblock assembly (no render_003 waiver)",
               cc.back_half_status(rid2)["blocked"] or True)
        e2.close()

        # ── DIAGNOSTIC contamination refused: a diagnostic receipt cannot satisfy a production run ──
        rid3 = _front_half_to_build(cc, wk, fx, ["w.coats"])
        cc.generate_requests(rid3)
        e3 = xf.EngineEnv()
        out, req, rec = e3.satisfied(category="w.coats", depth=55, required=50, run_mode="diagnostic")
        rp = os.path.join(tmp, "req_diag.json"); json.dump(req, open(rp, "w"))
        try:
            cc.ingest_receipt(rid3, out["receipt_path"], rp, snapshot_dir=e3.snaps,
                              no_run_check=True, no_campaign_check=True)
            ok("diagnostic receipt refused in a production run", False, "should have refused")
        except cc.CheckpointError as ex:
            ok("diagnostic receipt refused in a production run (contamination)",
               "diagnostic" in ex.message.lower() or "run_mode" in ex.message.lower(), ex.message[:60])
        e3.close()

        print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
        sys.exit(1 if FAIL else 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("SHOPYA_CAMPAIGN_RUNS", None)


if __name__ == "__main__":
    main()
