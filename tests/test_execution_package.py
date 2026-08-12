#!/usr/bin/env python3
"""A–G package + Execution Manifest tests (task §27: A–G GENERATION + MANIFEST + VALIDATION).

    python3 tests/test_execution_package.py

Uses real Engine receipts (cross_repo_fixture) so the fulfillment view is genuine, then exercises
execution_package.py: every A–G artifact is generated mechanically and deterministically; the F
manifest hashes every component + all Request/Receipt/Truth deps; identity is immutable and content
-addressed; a component mutation changes/refuses manifest identity; unsupported XC rails are honest.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import receipt_ingest as ri  # noqa: E402
import execution_package as ep  # noqa: E402
import cross_repo_fixture as fx  # noqa: E402

PASS, FAIL = [], []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %s  %s%s" % ("PASS" if cond else "FAIL", name,
                          ("  <- " + str(detail)[-300:]) if detail and not cond else ""))


def make_fview(e, store):
    """Ingest a real satisfied receipt and return (fview, request)."""
    out, req, rec = e.satisfied(category="w.coats", required=50)
    ri.ingest_receipt(out["receipt_path"], req, snapshot_dir=e.snaps, store_dir=store,
                      expected_run_mode="production", generated_at="t")
    fview = ep.build_fulfillment_view(ri.load_ingestions(store),
                                      ri.load_material_exceptions(store))
    return fview, req


def architecture(req):
    return {
        "collections": [{"category_id": "w.coats", "display_name": "Almost Fall Coats",
                         "vertical": "w", "campaign_role": "hero", "sub_group": "fashion",
                         "request_id": req["request_id"]}],
        "rails": [
            {"rail_id": "r1", "rail_name": "The Coats", "rail_kind": "base",
             "collection_id": "w.coats", "surface": "explore", "rail_position": 1,
             "pins": ["sp:a", "sp:b"], "order": 1},
            {"rail_id": "r2", "rail_name": "Cross-Season Story", "rail_kind": "xc",
             "source_collection_ids": ["w.coats"], "surface": "explore", "order": 2},
        ],
        "content": [{"content_id": "ct1", "target_query": "fall coats", "seo_title": "Coats",
                     "card_headline": "The coats", "premise": "p", "outline_brief": "b",
                     "linked_collection": "w.coats", "placement": "explore", "status": "to_produce"}],
        "default_composition": {"objects": ["w.coats"]},
        "renderer_capabilities": {"xc_rails_supported": False},
    }


def main():
    print("\n== A–G generation (deterministic, mechanical) ==")
    e = fx.EngineEnv()
    try:
        store = os.path.join(e.d, "store")
        fview, req = make_fview(e, store)
        arch = architecture(req)

        b = ep.build_collection_creation_spec(arch, fview)
        c = ep.build_rail_feed_spec(arch)
        d = ep.build_content_production_package(arch)
        se = ep.build_seam_handoffs(arch, fview)
        g = ep.build_human_checklist(arch, fview)

        ok("B binds each collection's Request/Receipt/Truth Export ids",
           b["collections"][0]["fulfillment_request_id"] == req["request_id"] and
           b["collections"][0]["receipt_id"] and b["collections"][0]["truth_export_id"])
        ok("B records achieved dependable depth + launch readiness",
           b["collections"][0]["achieved_dependable_depth"] == 55 and
           b["collections"][0]["launch_ready"] is True)
        ok("C marks base rail executable, XC rail honestly NOT executable (no fallback invented)",
           c["rails"][0]["executable"] is True and c["rails"][1]["executable"] is False and
           c["rails"][1]["fallback"] is None)
        ok("D emits a content-production record per approved piece",
           len(d["content_pieces"]) == 1 and d["content_pieces"][0]["content_id"] == "ct1")
        ok("E emits actionable handoffs (collection + rails + content + default)",
           any(h["to"] == "admin_collection_creation" for h in se["handoffs"]) and
           any(h["to"] == "admin_default_composition" for h in se["handoffs"]))
        ok("G emits a deterministic checklist (guidance, not proof)",
           g["items"] and all(item["done"] is False for item in g["items"]))

        # determinism: same inputs -> byte-identical canonical output
        ok("B is deterministic (same inputs -> identical bytes)",
           ep._canonical(b) == ep._canonical(ep.build_collection_creation_spec(arch, fview)))
        ok("C is deterministic", ep._canonical(c) == ep._canonical(ep.build_rail_feed_spec(arch)))
    finally:
        e.close()

    print("\n== FROZEN SEQUENCE: stage -> validate -> emit F (Issue A, no self-attestation) ==")
    e = fx.EngineEnv()
    try:
        store = os.path.join(e.d, "store")
        fview, req = make_fview(e, store)
        arch = architecture(req)
        pkg = os.path.join(e.d, "pkg")
        os.makedirs(pkg)
        csvp = os.path.join(pkg, "A_master.csv")
        open(csvp, "w").write("campaign_id,collection_name\nx,Coats\n")
        csv_sha = ep.file_sha256(csvp)

        # STEP 1: stage A–G — NO manifest is written by staging.
        staged = ep.stage_components(arch, fview, out_dir=pkg, master_csv_path=csvp,
                                     master_csv_sha256=csv_sha)
        ok("staging writes NO F manifest (build-package cannot pre-certify)",
           not os.path.exists(os.path.join(pkg, "F_execution_manifest.json")))
        ok("staging writes B/C/D/E/G on disk", all(
            os.path.exists(staged["paths"][k]) for k in ("B", "C", "D", "E", "G")))

        # STEP 2: validate the staged package — consults NO manifest.
        result = ep.validate_package(arch, fview, pkg, staged, "production")
        ok("validate_package PASSES on a coherent complete package", result["ok"], result["problems"])

        # emit BEFORE a passing validation is impossible: emit_manifest refuses a non-ok result.
        try:
            ep.emit_manifest(arch, fview, pkg, staged, "c", req["run_ref"], "production",
                             validation_result={"ok": False, "problems": ["forced"]}, generated_at="t")
            ok("emit_manifest refuses to certify an unvalidated package", False, "did not refuse")
        except ep.PackageError:
            ok("emit_manifest refuses to certify an unvalidated package (Issue A)", True)

        # STEP 3: emit F over the VALIDATED set — validation recorded FROM the completed result.
        emitted = ep.emit_manifest(arch, fview, pkg, staged, "xrepo-2026", req["run_ref"],
                                   "production", validation_result=result,
                                   architecture_ref="arch.json", architecture_sha256="deadbeef",
                                   generated_at="t")
        man = emitted["manifest"]
        ok("F is written only after validation (exists post-emit)",
           os.path.exists(os.path.join(pkg, "F_execution_manifest.json")))
        ok("every A/B/C/D/E/G component is hashed in the manifest",
           all(man["components"][k]["sha256"] for k in ("A", "B", "C", "D", "E", "G")))
        ok("manifest binds the exact Request/Receipt/Truth Export ids+hashes",
           man["dependencies"][0]["request_id"] == req["request_id"] and
           man["dependencies"][0]["receipt_sha256"] and man["dependencies"][0]["truth_export_sha256"])
        ok("manifest id is content-addressed (exmf_ + sha[:16] of the core)",
           man["manifest_id"] == "exmf_" + ep._sha256_hex(ep._canonical(
               {k: v for k, v in man.items()
                if k not in ("manifest_id", "manifest_sha256", "generated_at")}))[:16])
        ok("manifest RECORDS the completed validation result (audit, not self-certified)",
           man["validation"]["ok"] and "validated_request_ids" in man["validation"])

        # verify_manifest checks INTEGRITY ONLY — it must NOT rely on the recorded validation block.
        vok, vchecks = ep.verify_manifest(man, out_dir=pkg,
                                          expect_manifest_sha256=man["manifest_sha256"])
        ok("verify_manifest confirms integrity (self-hash + id + files)", vok, vchecks)
        ok("verify_manifest does NOT include a self-attesting validation_ok check",
           "validation_ok" not in vchecks)

        # ADVERSARIAL (Issue A): hand-set the manifest's recorded validation cannot make an
        # incoherent package verify — verify_manifest ignores that block; and re-deriving the
        # authoritative validation still runs independently.
        forged = json.loads(json.dumps(man))
        forged["components"]["B"]["sha256"] = "deadbeef"          # break a component binding
        forged["validation"]["ok"] = True                        # but claim validated
        # recompute the forged manifest's self identity so only the component sha is "wrong on disk"
        fcore = {k: v for k, v in forged.items()
                 if k not in ("manifest_id", "manifest_sha256", "generated_at")}
        forged["manifest_id"] = "exmf_" + ep._sha256_hex(ep._canonical(fcore))[:16]
        forged["manifest_sha256"] = ep._artifact_sha256(forged, "manifest_sha256")
        fvok, _ = ep.verify_manifest(forged, out_dir=pkg)
        ok("a manifest claiming validation=true but with a broken component fails verify",
           not fvok)

        # determinism + immutability
        emitted2 = ep.emit_manifest(arch, fview, pkg, staged, "xrepo-2026", req["run_ref"],
                                    "production", validation_result=result,
                                    architecture_ref="arch.json", architecture_sha256="deadbeef",
                                    generated_at="t-different")
        ok("same validated package -> same manifest id (deterministic)",
           emitted2["manifest_id"] == emitted["manifest_id"])

        arch2 = json.loads(json.dumps(arch))
        arch2["content"][0]["seo_title"] = "Different Title"
        pkg2 = os.path.join(e.d, "pkg2")
        os.makedirs(pkg2)
        open(os.path.join(pkg2, "A_master.csv"), "w").write(open(csvp).read())
        staged2 = ep.stage_components(arch2, fview, out_dir=pkg2, master_csv_path=csvp,
                                      master_csv_sha256=csv_sha)
        result2 = ep.validate_package(arch2, fview, pkg2, staged2, "production")
        emitted3 = ep.emit_manifest(arch2, fview, pkg2, staged2, "xrepo-2026", req["run_ref"],
                                    "production", validation_result=result2, generated_at="t")
        ok("a component (content) change yields a DIFFERENT manifest id",
           emitted3["manifest_id"] != emitted["manifest_id"])

        try:
            forged2 = dict(man)
            forged2["package_revision"] = 999
            forged2["manifest_sha256"] = "x"
            ep._write_manifest_immutable(emitted["manifest_path"], forged2)
            ok("overwrite collision refused", False, "no error raised")
        except ep.PackageError:
            ok("overwrite collision refused (same id, different semantic bytes)", True)
    finally:
        e.close()

    print("\n== validate_package blocks incoherent packages (invalid B/C/D/E/G) ==")
    e = fx.EngineEnv()
    try:
        store = os.path.join(e.d, "store")
        fview, req = make_fview(e, store)
        arch = architecture(req)
        pkg = os.path.join(e.d, "pkg")
        os.makedirs(pkg)
        csvp = os.path.join(pkg, "A_master.csv")
        open(csvp, "w").write("x\n")
        staged = ep.stage_components(arch, fview, out_dir=pkg, master_csv_path=csvp,
                                     master_csv_sha256=ep.file_sha256(csvp))
        # corrupt a staged component on disk after staging -> validation must fail (coherence)
        with open(staged["paths"]["C"], "a") as f:
            f.write("tampered\n")
        result = ep.validate_package(arch, fview, pkg, staged, "production")
        ok("a tampered/incoherent component fails validate_package",
           not result["ok"] and not result["checks"]["all_components_present_and_coherent"])
        # ... and therefore no manifest can be emitted
        try:
            ep.emit_manifest(arch, fview, pkg, staged, "c", req["run_ref"], "production",
                             validation_result=result, generated_at="t")
            ok("no manifest is emitted over an incoherent package", False, "emitted anyway")
        except ep.PackageError:
            ok("no manifest is emitted over an incoherent package", True)
    finally:
        e.close()

    print("\n== validation blocks on shortfall / open Material Exception ==")
    e = fx.EngineEnv()
    try:
        store = os.path.join(e.d, "store")
        out, req, rec = e.shortfall(category="w.coats", required=50)
        ri.ingest_receipt(out["receipt_path"], req, snapshot_dir=e.snaps, store_dir=store,
                          fulfillment_exception_path=out["exception_path"],
                          expected_run_mode="production", generated_at="t")
        fview = ep.build_fulfillment_view(ri.load_ingestions(store),
                                          ri.load_material_exceptions(store))
        arch = {"collections": [{"category_id": "w.coats", "display_name": "Coats",
                                 "request_id": req["request_id"]}]}
        pkg = os.path.join(e.d, "pkg")
        os.makedirs(pkg)
        csvp = os.path.join(pkg, "A_master.csv")
        open(csvp, "w").write("x\n")
        staged = ep.stage_components(arch, fview, out_dir=pkg, master_csv_path=csvp,
                                     master_csv_sha256=ep.file_sha256(csvp))
        result = ep.validate_package(arch, fview, pkg, staged, "production")
        ok("shortfall + open Material Exception fails validate_package",
           not result["ok"] and not result["checks"]["receipt_set_complete"])
    finally:
        e.close()

    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
