#!/usr/bin/env python3
"""Post-regression correction tests (owner directive 2026-08-10).

    python3 tests/test_post_approval_reopen.py

A1 — CAMPAIGN_APPROVED -> SEAM6_READY reopen: the edge exists, its obligations are
enforced, and a STALE APPROVAL CAN NEVER REMAIN CURRENT once execution is reopened.
A2 — canon migration obligations: a migrated run may not retain traversed hash-bound
proof that fails the current canon (the Almost Fall r002 case, as a test).

Style matches tests/test_validator.py: plain script, external validator subprocess,
run.py exercised end-to-end against a temp SHOPYA_CAMPAIGN_RUNS dir. No pytest.
"""
import copy, hashlib, json, os, shutil, subprocess, sys, tempfile
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VALIDATOR = os.path.join(ROOT, "scripts", "validate_state.py")
RUNNER = os.path.join(ROOT, "scripts", "run.py")
SCHEMA = os.path.join(ROOT, "schemas", "workflow_state.schema.yaml")
CHARTER = os.path.join(ROOT, "SHOPYA_CAMPAIGN_CHARTER.yaml")

PASS, FAIL = [], []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %s  %s%s" % ("PASS" if cond else "FAIL", name,
                          ("  <- " + str(detail)[-300:]) if detail and not cond else ""))


def write(p, doc):
    with open(p, "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, sort_keys=False)
    return p


def validate(state_path, to=None, phase="all"):
    cmd = [sys.executable, VALIDATOR, "--state", state_path, "--schema", SCHEMA,
           "--charter", CHARTER, "--runs-dir", "/tmp/__none__", "--phase", phase]
    if to:
        cmd += ["--to", to]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def main():
    tmp = tempfile.mkdtemp(prefix="shopya_reopen_tests_")
    try:
        spec_v = yaml.safe_load(open(SCHEMA))["schema"]["version"]
        chart_v = yaml.safe_load(open(CHARTER))["charter"]["version"]

        anchor = write(os.path.join(tmp, "anchor.yaml"), {"x": 1})
        sha = hashlib.sha256(open(anchor, "rb").read()).hexdigest()
        stage7 = write(os.path.join(tmp, "stage7.yaml"), {
            "rails": [{"rail_id": "r1", "collection_id": "c1", "rail_position": 0}],
            "entities": [{"entity_type": "products", "eligible_count": 12}],
            "collections": {"sub_group": "fashion"},
        })

        def approved_state(**over):
            """A run at CAMPAIGN_APPROVED with a bound production validation pass."""
            s = {
                "run": {"run_id": "cmp_TESTREOPEN0000000000000000", "spec_version": spec_v,
                        "charter_version": chart_v, "created_at": "t"},
                "identity": {"campaign_id": {"value": "test-reopen-2026", "status": "confirmed",
                                             "confirmed_by_owner": True,
                                             "externally_referenced": False,
                                             "first_external_reference": None},
                             "display_name": "Test Reopen"},
                "workflow": {"state": "CAMPAIGN_APPROVED", "entered_at": "t", "history": []},
                "owner_decisions": {"campaign_approved": {
                    "status": "owner_confirmed", "decided": True, "decided_by": "product_owner",
                    "decided_at": "t"}},
                "invalidated": [],
                "capability_claims": [],
                "artifacts": {
                    "stage7_seam6": {"path": stage7, "status": "current"},
                    "products_csv": {"path": anchor, "sha256": sha, "status": "current"},
                    "execution_manifest": {"path": anchor, "sha256": sha, "status": "current"},
                },
                "validation_attempts": [{"attempted_at": "t", "result": "passed",
                                         "production": True, "output_sha256": sha,
                                         "failures": []}],
                "execution_tracking": {"activation_architecture_status": "approved",
                                       "seam6_execution_status": "validated",
                                       "external_handoffs_status": "authored",
                                       "external_handoffs_implemented": "unknown"},
                "collection_freeze": {"snapshot": [], "exceptions": []},
            }
            for k, v in over.items():
                s[k] = v
            return s

        print("\n-- A1: the reopen edge exists and its obligations gate it --")
        s = approved_state()
        rc, out = validate(write(os.path.join(tmp, "a1.yaml"), s), "SEAM6_READY")
        ok("reopen without the owner decision is refused",
           rc != 0 and "reopen_execution_post_approval" in out)

        s = approved_state()
        s["owner_decisions"]["reopen_execution_post_approval"] = {
            "status": "owner_confirmed", "decided": True, "decided_by": "product_owner",
            "decided_at": "t", "value": {"reason": "stale execution"}}
        rc, out = validate(write(os.path.join(tmp, "a2.yaml"), s), "SEAM6_READY")
        ok("reopen with decision but WITHOUT supersession/invalidation is refused",
           rc != 0 and "reopen_without_decision" in out)

        def reopened_state():
            s = approved_state()
            s["owner_decisions"]["reopen_execution_post_approval"] = {
                "status": "owner_confirmed", "decided": True, "decided_by": "product_owner",
                "decided_at": "t", "value": {"reason": "stale execution"}}
            for key in ("products_csv", "execution_manifest"):
                s["artifacts"][key]["status"] = "superseded"
                s["artifacts"][key]["supersession_reason"] = "post-approval reopen"
            s["invalidated"] = ["campaign_approved",
                                "execution_tracking.seam6_execution_status",
                                "validation_attempts", "verification"]
            s["validation_attempts"][0]["invalidated_at"] = "t2"
            s["validation_attempts"][0]["invalidated_by_decision"] = \
                "reopen_execution_post_approval"
            s["execution_tracking"]["seam6_execution_status"] = "ready"
            return s

        rc, out = validate(write(os.path.join(tmp, "a3.yaml"), reopened_state()), "SEAM6_READY")
        ok("reopen with ALL obligations met is executable", rc == 0, out)

        print("\n-- A1 adversarial: the stale approval cannot remain current --")
        # After the reopen, fabricate a fresh bound pass and try to re-enter
        # CAMPAIGN_APPROVED on the OLD (invalidated) approval. Must be refused.
        s = reopened_state()
        s["workflow"]["state"] = "VALIDATED"
        s["artifacts"]["products_csv"] = {"path": anchor, "sha256": sha, "status": "current"}
        s["validation_attempts"].append({"attempted_at": "t3", "result": "passed",
                                         "production": True, "output_sha256": sha,
                                         "failures": []})
        s["execution_tracking"]["seam6_execution_status"] = "validated"
        rc, out = validate(write(os.path.join(tmp, "a4.yaml"), s), "CAMPAIGN_APPROVED")
        ok("invalidated campaign_approved cannot gate re-entry to CAMPAIGN_APPROVED",
           rc != 0 and "stale_decision_after_reopen" in out)
        # The owner re-records the decision (record-decision clears the invalidation):
        s2 = copy.deepcopy(s)
        s2["invalidated"].remove("campaign_approved")
        rc, out = validate(write(os.path.join(tmp, "a5.yaml"), s2), "CAMPAIGN_APPROVED")
        ok("a genuinely re-recorded approval gates again", rc == 0, out)

        # A superseded products_csv can never anchor VALIDATED, even with a matching pass.
        s = reopened_state()
        s["workflow"]["state"] = "SEAM6_READY"
        s["validation_attempts"] = [{"attempted_at": "t", "result": "passed",
                                     "production": True, "output_sha256": sha, "failures": []}]
        s["execution_tracking"]["seam6_execution_status"] = "validated"
        rc, out = validate(write(os.path.join(tmp, "a6.yaml"), s), "VALIDATED")
        ok("superseded products_csv cannot satisfy VALIDATED even with a matching pass",
           rc != 0 and "stale_artifact_treated_as_current" in out)

        # An invalidated verification can never satisfy LIVE.
        s = approved_state()
        s["collection_freeze"] = {"snapshot": [{"collection_id": "c1", "frozen_at": "z",
                                                "sha256": "x"}], "exceptions": []}
        s["execution_tracking"]["seam6_execution_status"] = "executed"
        s["verification"] = {"post_cache_verified": True, "reprobe_at": "z", "result": "pass",
                             "build_sha256": sha, "method": "automated_probe",
                             "executed_build": "b005", "invalidated_at": "t2",
                             "invalidated_by_decision": "reopen_execution_post_approval"}
        rc, out = validate(write(os.path.join(tmp, "a7.yaml"), s), "LIVE")
        ok("an invalidated verification cannot satisfy LIVE",
           rc != 0 and "invalidated" in out)

        print("\n-- A1 writer: run.py reopen performs the invalidation atomically --")
        runs = os.path.join(tmp, "runs")
        rid = "cmp_TESTREOPEN0000000000000001"
        rdir = os.path.join(runs, "_drafts", rid)
        os.makedirs(rdir)
        s = approved_state()
        s["run"]["run_id"] = rid
        s["verification"] = {"post_cache_verified": True, "reprobe_at": "z", "result": "pass",
                             "build_sha256": sha, "method": "automated_probe",
                             "executed_build": "b003"}
        write(os.path.join(rdir, "state.yaml"), s)
        env = dict(os.environ, SHOPYA_CAMPAIGN_RUNS=runs)
        r = subprocess.run([sys.executable, RUNNER, "reopen", "--run", rid,
                            "--to", "SEAM6_READY", "--by", "product_owner",
                            "--reason", "regenerate stale execution"],
                           capture_output=True, text=True, env=env)
        after = yaml.safe_load(open(os.path.join(rdir, "state.yaml")))
        ok("run.py reopen prepares the edge", r.returncode == 0, r.stdout + r.stderr)
        ok("  passing attempt stamped invalidated",
           after["validation_attempts"][0].get("invalidated_at") is not None)
        ok("  verification stamped invalidated",
           after["verification"].get("invalidated_at") is not None)
        ok("  products_csv + execution_manifest superseded",
           all(after["artifacts"][k]["status"] == "superseded"
               for k in ("products_csv", "execution_manifest")))
        ok("  campaign_approved invalidated",
           "campaign_approved" in after.get("invalidated", []))
        ok("  seam6_execution_status downgraded to ready",
           after["execution_tracking"]["seam6_execution_status"] == "ready")
        r2 = subprocess.run([sys.executable, RUNNER, "transition", "--run", rid,
                             "--to", "SEAM6_READY"], capture_output=True, text=True, env=env)
        after2 = yaml.safe_load(open(os.path.join(rdir, "state.yaml")))
        ok("  transition to SEAM6_READY commits", r2.returncode == 0 and
           after2["workflow"]["state"] == "SEAM6_READY", r2.stdout + r2.stderr)

        print("\n-- A2: canon migration invalidates stale traversed proof (r002 case) --")
        rid2 = "cmp_TESTMIGRATE0000000000000001"
        rdir2 = os.path.join(runs, "_drafts", rid2)
        os.makedirs(rdir2)
        s = approved_state()
        s["run"]["run_id"] = rid2
        s["run"]["spec_version"] = "1.4.0"       # pre-hardening pins
        s["run"]["charter_version"] = "0.3.0"
        # pre-hardening attempts: passing, but no output_sha256 / production stamp
        s["validation_attempts"] = [
            {"attempted_at": "t1", "result": "passed", "failures": []},
            {"attempted_at": "t2", "result": "passed", "failures": []},
        ]
        write(os.path.join(rdir2, "state.yaml"), s)
        r = subprocess.run([sys.executable, RUNNER, "migrate", "--run", rid2,
                            "--by", "product_owner", "--note", "test"],
                           capture_output=True, text=True, env=env)
        after = yaml.safe_load(open(os.path.join(rdir2, "state.yaml")))
        ok("migrate re-pins to current canon", r.returncode == 0 and
           after["run"]["spec_version"] == spec_v and
           after["run"]["charter_version"] == chart_v, r.stdout + r.stderr)
        ok("  unbound passing attempts stamped invalidated by canon_migration",
           all(a.get("invalidated_by_decision") == "canon_migration"
               for a in after["validation_attempts"]))
        ok("  seam6_execution_status downgraded from validated",
           after["execution_tracking"]["seam6_execution_status"] == "ready")
        ok("  stale execution artifacts superseded",
           all(after["artifacts"][k]["status"] == "superseded"
               for k in ("products_csv", "execution_manifest")))
        ok("  obligation recorded on the migration record",
           after["run"]["migration"][-1].get("proof_invalidated") is not None)
        rc, out = validate(os.path.join(rdir2, "state.yaml"))
        ok("  migrated run validates clean under current canon (not semantically "
           "post-VALIDATED)", rc == 0, out)

        # Migration must NOT touch live, bound, production proof.
        rid3 = "cmp_TESTMIGRATE0000000000000002"
        rdir3 = os.path.join(runs, "_drafts", rid3)
        os.makedirs(rdir3)
        s = approved_state()
        s["run"]["run_id"] = rid3
        s["run"]["spec_version"] = "1.5.0"       # stale pin, but proof is current-canon-valid
        write(os.path.join(rdir3, "state.yaml"), s)
        r = subprocess.run([sys.executable, RUNNER, "migrate", "--run", rid3,
                            "--by", "product_owner", "--note", "test"],
                           capture_output=True, text=True, env=env)
        after = yaml.safe_load(open(os.path.join(rdir3, "state.yaml")))
        ok("migration leaves valid hash-bound production proof untouched",
           r.returncode == 0 and
           after["validation_attempts"][0].get("invalidated_at") is None and
           after["artifacts"]["products_csv"]["status"] == "current",
           r.stdout + r.stderr)

        print("\n-- A2 invariant: status/proof coherence is validator-enforced --")
        s = approved_state()
        s["validation_attempts"] = [{"attempted_at": "t", "result": "passed", "failures": []}]
        rc, out = validate(write(os.path.join(tmp, "m1.yaml"), s))
        ok("'validated' status with unbound proof is refused (stale_execution_proof)",
           rc != 0 and "stale_execution_proof" in out)
        s = approved_state()   # bound production pass -> coherent
        rc, out = validate(write(os.path.join(tmp, "m2.yaml"), s))
        ok("'validated' status with live bound production proof passes", rc == 0, out)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
