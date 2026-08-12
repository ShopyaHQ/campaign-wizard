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
        # A real execution manifest file with a manifest_id: the CAMPAIGN_APPROVED gate now binds
        # the approval to the exact manifest (id in the file, sha256 in the artifact record).
        manifest_file = os.path.join(tmp, "F_execution_manifest.json")
        with open(manifest_file, "w") as _f:
            json.dump({"manifest_id": "exmf_reopentest0001",
                       "manifest_contract_version": "1.0.0"}, _f)
        MSHA = hashlib.sha256(open(manifest_file, "rb").read()).hexdigest()
        MID = "exmf_reopentest0001"
        stage7 = write(os.path.join(tmp, "stage7.yaml"), {
            "rails": [{"rail_id": "r1", "collection_id": "c1", "rail_position": 0}],
            "entities": [{"entity_type": "products", "eligible_count": 12}],
            "collections": {"sub_group": "fashion"},
        })

        def approved_state(**over):
            """A run at CAMPAIGN_APPROVED with a bound production validation pass."""
            s = {
                "run": {"run_id": "cmp_TESTREOPEN0000000000000000", "spec_version": spec_v,
                        "charter_version": chart_v, "run_mode": "production", "created_at": "t"},
                "identity": {"campaign_id": {"value": "test-reopen-2026", "status": "confirmed",
                                             "confirmed_by_owner": True,
                                             "externally_referenced": False,
                                             "first_external_reference": None},
                             "display_name": "Test Reopen"},
                "workflow": {"state": "CAMPAIGN_APPROVED", "entered_at": "t", "history": []},
                "owner_decisions": {"execution_package_approved": {
                    "status": "owner_confirmed", "decided": True, "decided_by": "product_owner",
                    "decided_at": "t",
                    "value": {"manifest_id": MID, "manifest_sha256": MSHA}}},
                "invalidated": [],
                "capability_claims": [],
                "artifacts": {
                    "stage7_seam6": {"path": stage7, "status": "current"},
                    "products_csv": {"path": anchor, "sha256": sha, "status": "current"},
                    "execution_manifest": {"path": manifest_file, "sha256": MSHA,
                                           "status": "current"},
                },
                "validation_attempts": [{"attempted_at": "t", "result": "passed",
                                         "production": True, "output_sha256": sha,
                                         "package_validated": True,
                                         "package_manifest_sha256": MSHA,
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
            s["invalidated"] = ["execution_package_approved",
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
        # regenerate: fresh current products_csv + execution_manifest + a package-validated pass.
        s["artifacts"]["products_csv"] = {"path": anchor, "sha256": sha, "status": "current"}
        s["artifacts"]["execution_manifest"] = {"path": manifest_file, "sha256": MSHA,
                                                "status": "current"}
        s["validation_attempts"].append({"attempted_at": "t3", "result": "passed",
                                         "production": True, "output_sha256": sha,
                                         "package_validated": True,
                                         "package_manifest_sha256": MSHA, "failures": []})
        s["execution_tracking"]["seam6_execution_status"] = "validated"
        rc, out = validate(write(os.path.join(tmp, "a4.yaml"), s), "CAMPAIGN_APPROVED")
        ok("invalidated execution_package_approved cannot gate re-entry to CAMPAIGN_APPROVED",
           rc != 0 and "stale_decision_after_reopen" in out)
        # The owner re-records the decision (record-decision clears the invalidation):
        s2 = copy.deepcopy(s)
        s2["invalidated"].remove("execution_package_approved")
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
        ok("  execution_package_approved invalidated",
           "execution_package_approved" in after.get("invalidated", []))
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
        # prd.md §16.5 (fix 2026-08-11): the migrated run is STILL at CAMPAIGN_APPROVED (migrate
        # invalidates proof + downgrades status but does not transition state). A post-validation
        # state resting on invalidated proof is INCOHERENT and must be REFUSED — it is only made
        # coherent by reopening out of the post-validation state (see the A3 case below). This
        # assertion previously (wrongly) expected PASS, codifying the resting-state defect.
        rc, out = validate(os.path.join(rdir2, "state.yaml"))
        ok("  migrated run STILL at CAMPAIGN_APPROVED with invalidated proof is REFUSED "
           "(stale_execution_proof)", rc != 0 and "stale_execution_proof" in out, out)

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

        print("\n-- A3: post-validation coherence keyed on workflow.state (prd.md §16.5) --")
        # The resting-state defect: a post-validation workflow state must hold current valid
        # production proof REGARDLESS of the downgradable seam6_execution_status string.

        def stale_proof(state):
            """A run at `state` whose proof has been invalidated + superseded and whose
            execution status was downgraded to 'ready' — the exact shape a migrate/reopen
            leaves behind. execution_package_approved is NOT invalidated (this is a RESTING state, not
            a re-entry attempt), isolating the coherence check from stale_decision_after_reopen."""
            s = approved_state()
            s["workflow"]["state"] = state
            for key in ("products_csv", "execution_manifest"):
                s["artifacts"][key]["status"] = "superseded"
                s["artifacts"][key]["supersession_reason"] = "canon_migration"
            s["validation_attempts"][0]["invalidated_at"] = "t2"
            s["validation_attempts"][0]["invalidated_by_decision"] = "canon_migration"
            s["execution_tracking"]["seam6_execution_status"] = "ready"  # disarms the OLD guard
            return s

        rc, out = validate(write(os.path.join(tmp, "a3_val.yaml"), stale_proof("VALIDATED")))
        ok("VALIDATED + no current proof (status downgraded) is REFUSED",
           rc != 0 and "stale_execution_proof" in out, out)

        rc, out = validate(write(os.path.join(tmp, "a3_ca.yaml"), stale_proof("CAMPAIGN_APPROVED")))
        ok("CAMPAIGN_APPROVED + no current proof (status downgraded) is REFUSED",
           rc != 0 and "stale_execution_proof" in out, out)

        # CAMPAIGN_APPROVED + only the current CSV superseded (attempt still 'passed', status
        # still 'validated') — the binding predicate must reject a superseded anchor.
        s = approved_state()
        s["artifacts"]["products_csv"]["status"] = "superseded"
        s["artifacts"]["execution_manifest"]["status"] = "superseded"
        rc, out = validate(write(os.path.join(tmp, "a3_super.yaml"), s))
        ok("CAMPAIGN_APPROVED + superseded current CSV is REFUSED",
           rc != 0 and ("stale_execution_proof" in out or "stale_artifact_treated_as_current" in out),
           out)

        # Sanctioned reopen: workflow.state moved OUT to SEAM6_READY, proof invalidated. The
        # coherence invariant must NOT fire — a correctly reopened run is valid in its
        # downgraded state, and SEAM6_READY must not require validation proof.
        s = stale_proof("SEAM6_READY")
        s["invalidated"] = ["execution_package_approved"]
        rc, out = validate(write(os.path.join(tmp, "a3_reopened.yaml"), s))
        ok("reopened SEAM6_READY with stale proof invalidated is coherent (PASS)",
           rc == 0, out)

        # Genuine current bound proof in VALIDATED -> PASS.
        s = approved_state(); s["workflow"]["state"] = "VALIDATED"
        rc, out = validate(write(os.path.join(tmp, "a3_goodval.yaml"), s))
        ok("VALIDATED with genuine current bound production proof passes", rc == 0, out)

        # Genuine current proof + execution approval in CAMPAIGN_APPROVED -> PASS.
        rc, out = validate(write(os.path.join(tmp, "a3_goodca.yaml"), approved_state()))
        ok("CAMPAIGN_APPROVED with genuine current proof + approval passes", rc == 0, out)

        print("\n-- A4: the §16.5 exemption is ONLY the sanctioned reopen edge, not any exit --")
        # The exemption must be tied to transition_type: reopen, NOT to "target leaves the
        # post-validation set". A forward transition out of a post-validation state (notably
        # CAMPAIGN_APPROVED -> LIVE) must STILL require current proof — the LIVE gate is not a
        # substitute for the §16.5 invariant.

        # 1. stale CAMPAIGN_APPROVED proposing --to LIVE (forward) -> REFUSED by §16.5 itself.
        rc, out = validate(write(os.path.join(tmp, "a4_ca_live.yaml"),
                                 stale_proof("CAMPAIGN_APPROVED")), "LIVE")
        ok("stale CAMPAIGN_APPROVED --to LIVE is REFUSED by stale_execution_proof (not just the "
           "LIVE gate)", rc != 0 and "stale_execution_proof" in out, out)

        # 2. stale post-validation + a non-reopen forward target (VALIDATED -> CAMPAIGN_APPROVED)
        #    -> REFUSED by §16.5.
        rc, out = validate(write(os.path.join(tmp, "a4_val_ca.yaml"),
                                 stale_proof("VALIDATED")), "CAMPAIGN_APPROVED")
        ok("stale VALIDATED --to CAMPAIGN_APPROVED (forward) is REFUSED by stale_execution_proof",
           rc != 0 and "stale_execution_proof" in out, out)

        def fully_reopened(state):
            """`state` (post-validation) with EVERY reopen obligation for its -> SEAM6_READY edge
            met, per the schema's per-edge `invalidates` / `supersedes_artifacts`. This is the
            state as it exists WHILE the reopen transition to SEAM6_READY is being validated
            (workflow.state still the source). The two edges differ:
              CAMPAIGN_APPROVED -> SEAM6_READY (reopen_execution_post_approval): invalidates
                execution_package_approved + seam6_execution_status + validation_attempts + verification;
                supersedes products_csv + execution_manifest.
              VALIDATED -> SEAM6_READY (reopen_seam6_execution): invalidates execution_package_approved +
                seam6_execution_status; supersedes products_csv + execution_manifest (the whole
                A–G package is regenerated, so its manifest can no longer anchor VALIDATED)."""
            s = approved_state()
            s["workflow"]["state"] = state
            if state == "CAMPAIGN_APPROVED":
                decision = "reopen_execution_post_approval"
                inval = ["execution_package_approved", "execution_tracking.seam6_execution_status",
                         "validation_attempts", "verification"]
            else:  # VALIDATED
                decision = "reopen_seam6_execution"
                inval = ["execution_package_approved", "execution_tracking.seam6_execution_status"]
            for key in ("products_csv", "execution_manifest"):
                s["artifacts"][key]["status"] = "superseded"
                s["artifacts"][key]["supersession_reason"] = "reopen: regenerate execution"
            s["owner_decisions"][decision] = {
                "status": "owner_confirmed", "decided": True, "decided_by": "product_owner",
                "decided_at": "t", "value": {"reason": "regenerate stale execution"}}
            s["invalidated"] = inval
            s["validation_attempts"][0]["invalidated_at"] = "t2"
            s["validation_attempts"][0]["invalidated_by_decision"] = decision
            s["execution_tracking"]["seam6_execution_status"] = "ready"
            return s

        # 3. stale CAMPAIGN_APPROVED + sanctioned reopen --to SEAM6_READY, all obligations -> PASS.
        rc, out = validate(write(os.path.join(tmp, "a4_ca_reopen.yaml"),
                                 fully_reopened("CAMPAIGN_APPROVED")), "SEAM6_READY")
        ok("stale CAMPAIGN_APPROVED --to SEAM6_READY with all reopen obligations PASSES", rc == 0, out)

        # 4. stale VALIDATED + sanctioned reopen --to SEAM6_READY, all obligations -> PASS.
        rc, out = validate(write(os.path.join(tmp, "a4_val_reopen.yaml"),
                                 fully_reopened("VALIDATED")), "SEAM6_READY")
        ok("stale VALIDATED --to SEAM6_READY with all reopen obligations PASSES", rc == 0, out)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
