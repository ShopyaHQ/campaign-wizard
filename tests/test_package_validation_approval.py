#!/usr/bin/env python3
"""End-to-end complete-package VALIDATION + manifest-bound APPROVAL + post-validation coherence
(task §27: VALIDATION + APPROVAL + POST-VALIDATION COHERENCE), driven through run.py with the REAL
validator and REAL Engine receipts.

    python3 tests/test_package_validation_approval.py

Flow: a run rests in SEAM6_READY -> ingest-receipt (real Engine receipt) -> build-package (A–G + F
manifest) -> validate-package (complete package, hash-bound) -> VALIDATED -> approve-package (bound
to the exact manifest) -> CAMPAIGN_APPROVED. Plus: products.csv-only cannot satisfy VALIDATED,
approval cannot be inferred, a stale manifest cannot authorize a new package.
"""
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
RUNNER = os.path.join(ROOT, "scripts", "run.py")
VALIDATOR = os.path.join(ROOT, "scripts", "validate_state.py")
SCHEMA = os.path.join(ROOT, "schemas", "workflow_state.schema.yaml")
CHARTER = os.path.join(ROOT, "SHOPYA_CAMPAIGN_CHARTER.yaml")

import cross_repo_fixture as fx  # noqa: E402
import truth_export_v2 as tev2  # noqa: E402

PASS, FAIL = [], []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %s  %s%s" % ("PASS" if cond else "FAIL", name,
                          ("  <- " + str(detail)[-400:]) if detail and not cond else ""))


def run(env, *args):
    r = subprocess.run([sys.executable, RUNNER, *args], capture_output=True, text=True, env=env)
    return r.returncode, r.stdout + r.stderr


def validate(env, rid, to=None):
    runs = env["SHOPYA_CAMPAIGN_RUNS"]
    sp = os.path.join(runs, "_drafts", rid, "state.yaml")
    cmd = [sys.executable, VALIDATOR, "--state", sp, "--schema", SCHEMA, "--charter", CHARTER,
           "--runs-dir", runs]
    if to:
        cmd += ["--to", to]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def load_state(env, rid):
    return yaml.safe_load(open(os.path.join(env["SHOPYA_CAMPAIGN_RUNS"], "_drafts", rid,
                                            "state.yaml")))


def seam6_state(rid, spec_v, chart_v, stage7_path, sha):
    """A run resting in SEAM6_READY with the frame/stage7 artifacts + ready status."""
    return {
        "run": {"run_id": rid, "spec_version": spec_v, "charter_version": chart_v,
                "run_mode": "production", "created_at": "t"},
        "identity": {"campaign_id": {"value": "pkg-test-2026", "status": "confirmed",
                                     "confirmed_by_owner": True, "externally_referenced": False,
                                     "first_external_reference": None},
                     "display_name": "Pkg Test"},
        "workflow": {"state": "SEAM6_READY", "entered_at": "t",
                     "history": [{"from": None, "to": "NEW", "at": "t",
                                  "pinned_spec_version": spec_v, "pinned_charter_version": chart_v,
                                  "pinned_run_mode": "production"}]},
        "owner_decisions": {}, "invalidated": [], "capability_claims": [],
        "artifacts": {"stage7_seam6": {"path": stage7_path, "sha256": sha, "status": "current"}},
        "validation_attempts": [],
        "execution_tracking": {"activation_architecture_status": "approved",
                               "seam6_execution_status": "ready",
                               "external_handoffs_status": "authored",
                               "external_handoffs_implemented": "unknown"},
        "collection_freeze": {"snapshot": [], "exceptions": []},
    }


def main():
    spec_v = yaml.safe_load(open(SCHEMA))["schema"]["version"]
    chart_v = yaml.safe_load(open(CHARTER))["charter"]["version"]
    e = fx.EngineEnv()
    tmp = tempfile.mkdtemp(prefix="shopya_pkg_")
    try:
        runs = os.path.join(tmp, "runs")
        rid = "cmp_PKGTEST00000000000000000001"
        rdir = os.path.join(runs, "_drafts", rid)
        os.makedirs(rdir)
        env = dict(os.environ, SHOPYA_CAMPAIGN_RUNS=runs)

        # --- real Engine satisfied receipt + snapshot ---
        out, req, rec = e.satisfied(category="w.coats", required=50)
        snap = out["receipt"]["truth_export"]["immutable_ref"]
        request_path = os.path.join(tmp, "request.json")
        json.dump(req, open(request_path, "w"))

        # --- judgment referencing the snapshot's real product_uids (12 rail + >=50 members) ---
        s = tev2.load_snapshot(snap, expect_export_id=out["receipt"]["truth_export"]["export_id"],
                               expect_export_sha256=out["receipt"]["truth_export"]["export_sha256"])
        uids = sorted(s["rows_by_uid"].keys())
        judgment = []
        for i, uid in enumerate(uids):
            rail = i < 12
            judgment.append({"product_uid": uid, "collection_name": "Almost Fall Coats",
                             "is_rail_item": rail,
                             "rail_name": "The Coats" if rail else None,
                             "rail_position": (i + 1) if rail else None,
                             "collection_position": i + 1, "annotation": ""})
        judgment_path = os.path.join(tmp, "judgment.json")
        json.dump(judgment, open(judgment_path, "w"))

        architecture = {
            "collections": [{"category_id": "w.coats", "display_name": "Almost Fall Coats",
                             "vertical": "w", "campaign_role": "hero", "sub_group": "fashion",
                             "request_id": req["request_id"]}],
            "rails": [{"rail_id": "r1", "rail_name": "The Coats", "rail_kind": "base",
                       "collection_id": "w.coats", "surface": "explore", "rail_position": 1}],
            "content": [{"content_id": "ct1", "target_query": "fall coats", "status": "to_produce"}],
            "renderer_capabilities": {"xc_rails_supported": False},
        }
        arch_path = os.path.join(tmp, "architecture.json")
        json.dump(architecture, open(arch_path, "w"))

        stage7 = os.path.join(tmp, "stage7.yaml")
        yaml.safe_dump({"rails": [{"rail_id": "r1", "collection_id": "w.coats", "rail_position": 0}],
                        "entities": [{"entity_type": "products", "eligible_count": 12}],
                        "collections": {"sub_group": "fashion"}}, open(stage7, "w"))
        sha = hashlib.sha256(open(stage7, "rb").read()).hexdigest()
        yaml.safe_dump(seam6_state(rid, spec_v, chart_v, stage7, sha),
                       open(os.path.join(rdir, "state.yaml"), "w"), sort_keys=False)

        print("\n== ingestion via run.py ==")
        rc, out_s = run(env, "ingest-receipt", "--run", rid, "--receipt", out["receipt_path"],
                        "--request", request_path, "--snapshot-dir", e.snaps,
                        "--no-campaign-check", "--no-run-check")
        ok("run.py ingest-receipt accepts the satisfied receipt", rc == 0, out_s)

        print("\n== build-package STAGES A–G only (Issue A: no manifest yet) ==")
        common = ["--architecture", arch_path, "--campaign", "pkg-test-2026",
                  "--campaign-name", "Almost Fall", "--build", "b001",
                  "--judgment", judgment_path, "--truth", snap]
        rc, out_s = run(env, "build-package", "--run", rid, *common)
        ok("run.py build-package stages the complete A–G components", rc == 0, out_s)
        st = load_state(env, rid)
        ok("build-package writes NO execution_manifest (F emitted only by validate-package)",
           "execution_manifest" not in (st.get("artifacts") or {}), st.get("artifacts"))
        pkg_dir = os.path.join(rdir, "execution", "package")
        ok("build-package leaves no F_execution_manifest.json on disk",
           not os.path.exists(os.path.join(pkg_dir, "F_execution_manifest.json")))

        print("\n== products.csv-only cannot satisfy VALIDATED ==")
        # A plain production attempt (no package_validated / manifest) + a products_csv, no manifest
        # artifact — must not reach VALIDATED.
        st2 = copy.deepcopy(st)
        st2["validation_attempts"] = [{"attempted_at": "t", "result": "passed", "production": True,
                                       "output_sha256": sha, "failures": []}]
        st2["artifacts"]["products_csv"] = {"path": stage7, "sha256": sha, "status": "current"}
        st2["execution_tracking"]["seam6_execution_status"] = "validated"
        yaml.safe_dump(st2, open(os.path.join(rdir, "state.yaml"), "w"), sort_keys=False)
        rc, out_s = validate(env, rid, "VALIDATED")
        ok("products.csv-only pass (no package_validated / no manifest) cannot reach VALIDATED",
           rc != 0 and ("COMPLETE A–G package" in out_s or "execution_manifest" in out_s), out_s)
        # restore the real post-stage state
        yaml.safe_dump(st, open(os.path.join(rdir, "state.yaml"), "w"), sort_keys=False)

        print("\n== validate-package VALIDATES then emits F -> VALIDATED ==")
        rc, out_s = run(env, "validate-package", "--run", rid, *common)
        ok("run.py validate-package PASSES and emits the manifest", rc == 0, out_s)
        st = load_state(env, rid)
        ok("execution_manifest now registered current (emitted AFTER validation)",
           (st["artifacts"].get("execution_manifest") or {}).get("status") == "current",
           st.get("artifacts"))
        st = load_state(env, rid)
        last = st["validation_attempts"][-1]
        ok("attempt is package-validated + bound to the manifest sha",
           last.get("package_validated") is True and
           last.get("package_manifest_sha256") == st["artifacts"]["execution_manifest"]["sha256"])
        rc, out_s = run(env, "transition", "--run", rid, "--to", "VALIDATED")
        ok("transition SEAM6_READY -> VALIDATED commits", rc == 0 and
           load_state(env, rid)["workflow"]["state"] == "VALIDATED", out_s)

        print("\n== approval cannot be inferred; must bind the exact manifest ==")
        rc, out_s = validate(env, rid, "CAMPAIGN_APPROVED")
        ok("VALIDATED alone is NOT enough for CAMPAIGN_APPROVED (no approval)",
           rc != 0 and ("execution_package_approved" in out_s or "not recorded" in out_s), out_s)

        # An approval bound to a WRONG manifest sha cannot gate.
        st = load_state(env, rid)
        cur_mid = json.load(open(fx_manifest_path(rdir, st)))["manifest_id"]
        st["owner_decisions"]["execution_package_approved"] = {
            "status": "owner_confirmed", "decided": True, "decided_by": "product_owner",
            "decided_at": "t", "value": {"manifest_id": cur_mid, "manifest_sha256": "deadbeef"}}
        yaml.safe_dump(st, open(os.path.join(rdir, "state.yaml"), "w"), sort_keys=False)
        rc, out_s = validate(env, rid, "CAMPAIGN_APPROVED")
        ok("approval bound to a wrong manifest sha cannot gate CAMPAIGN_APPROVED",
           rc != 0 and "manifest" in out_s, out_s)

        print("\n== approve-package (exact manifest) -> CAMPAIGN_APPROVED ==")
        # remove the forged decision, use the sanctioned approve-package writer
        st = load_state(env, rid)
        st["owner_decisions"].pop("execution_package_approved", None)
        yaml.safe_dump(st, open(os.path.join(rdir, "state.yaml"), "w"), sort_keys=False)
        rc, out_s = run(env, "approve-package", "--run", rid, "--by", "product_owner",
                        "--note", "approve for implementation")
        ok("run.py approve-package records the manifest-bound approval", rc == 0, out_s)
        rc, out_s = run(env, "transition", "--run", rid, "--to", "CAMPAIGN_APPROVED")
        ok("transition VALIDATED -> CAMPAIGN_APPROVED commits", rc == 0 and
           load_state(env, rid)["workflow"]["state"] == "CAMPAIGN_APPROVED", out_s)

        print("\n== stale package: a component change after approval invalidates ==")
        # supersede the manifest (as a reopen would): the run may no longer rest at CAMPAIGN_APPROVED
        st = load_state(env, rid)
        st["artifacts"]["execution_manifest"]["status"] = "superseded"
        st["artifacts"]["execution_manifest"]["supersession_reason"] = "component changed"
        yaml.safe_dump(st, open(os.path.join(rdir, "state.yaml"), "w"), sort_keys=False)
        rc, out_s = validate(env, rid)
        ok("CAMPAIGN_APPROVED resting on a superseded manifest is REFUSED",
           rc != 0 and ("stale_execution_proof" in out_s or "superseded" in out_s), out_s)

    finally:
        e.close()
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    sys.exit(1 if FAIL else 0)


def fx_manifest_path(rdir, st):
    """Resolve the registered execution_manifest path relative to the run dir."""
    p = st["artifacts"]["execution_manifest"]["path"]
    return p if os.path.isabs(p) else os.path.join(rdir, p)


if __name__ == "__main__":
    main()
