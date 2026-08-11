#!/usr/bin/env python3
"""Repository tests for the workflow state machine.

    python3 tests/test_validator.py

Covers the transition failures that matter, the reserved-hook behaviour, artifact structural
validation, and — most importantly — that a REFUSED transition leaves state.yaml untouched.
Exits non-zero if any case does not behave as specified. No pytest dependency.
"""
import copy, hashlib, os, shutil, subprocess, sys, tempfile
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VALIDATOR = os.path.join(ROOT, "scripts", "validate_state.py")
RUNNER = os.path.join(ROOT, "scripts", "run.py")
SCHEMA = os.path.join(ROOT, "schemas", "workflow_state.schema.yaml")
CHARTER = os.path.join(ROOT, "SHOPYA_CAMPAIGN_CHARTER.yaml")

PASS, FAIL = [], []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %s  %s%s" % ("PASS" if cond else "FAIL", name, ("  <- " + detail) if detail and not cond else ""))


def write(p, doc):
    with open(p, "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, sort_keys=False)
    return p


def validate(state_path, to=None, phase="all", runs="/tmp/__none__"):
    cmd = [sys.executable, VALIDATOR, "--state", state_path, "--schema", SCHEMA,
           "--charter", CHARTER, "--runs-dir", runs, "--phase", phase]
    if to:
        cmd += ["--to", to]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


# Minimal frame valid against stage0_frame.schema.yaml v1.1.0. Kept deliberately minimal:
# these tests exercise the STATE MACHINE. Stage 0 interpretation discipline is covered by
# tests/test_stage0.py against the real frames in campaigns/.
FRAME = {
    "owner_inputs": {
        "objective": {"raw": "x", "normalized": {}, "interpretation_status": "normalized"},
        "requested_launch": {"raw": "x", "normalized_date": "2026-08-06",
                             "interpretation_status": "normalized"},
        "planning_horizon": {"raw": "x", "minimum_weeks": 4, "maximum_weeks": 6,
                             "interpretation_status": "normalized"},
        "starting_territory": {"raw": "x", "normalized": "x", "interpretation_status": "normalized"},
        "exclusions": {"raw": [], "normalized_frames": [], "interpretation_status": "direct"},
    },
    "timing": {"requested_launch_date": "2026-08-06",
               "operational_interpretation": {"value": "x", "interpretation_status": "inferred"},
               "earliest_actual_campaign_launch": {"value": None, "interpretation_status": "not_supplied"},
               "desired_campaign_end": {"value": None, "interpretation_status": "not_supplied"}},
    "objective": {"desired_behavior": "x", "audience": "x", "event_mapping": "save.created",
                  "interpretation_status": "normalized"},
    "measurement": {"intended_event": "save.created", "audience_segment": "x",
                    "retrieval_status": "unknown", "baseline_available": "unknown",
                    "causal_incrementality_measurable": False,
                    "proxy": {"value": None, "interpretation_status": "not_supplied"}},
    "avoidance": {"prohibited_campaign_frames": [],
                  "evidence_may_describe_prohibited_frames": True,
                  "prohibited_frames_may_not_be_adopted_as_recommendations": True,
                  "additional_restrictions": {"value": [], "interpretation_status": "not_supplied"}},
    "scope": {"live_surfaces": ["explore"], "seams_available_for_consideration": ["S6"],
              "selected_seams": [], "executable_seams": ["S6"], "handoff_seams": []},
    "planning_horizon": "Q3 2026", "market": "US",
    "eligible_seams": ["S6"], "eligible_surfaces": ["explore"],
    "hard_constraints": [], "known_unknowns": [],
    "campaign_id": {"value": None, "status": None},
}

BASE = {
    "run": {"run_id": "cmp_01J0000000000000000000000A", "spec_version": None,
            "charter_version": None, "created_at": "2026-08-06T15:00:00Z"},
    "identity": {"campaign_id": {"value": None, "status": None, "confirmed_by_owner": False,
                                 "externally_referenced": False, "first_external_reference": None},
                 "display_name": None},
    "workflow": {"state": "NEW", "entered_at": "2026-08-06T15:00:00Z", "history": []},
    "owner_decisions": {}, "artifacts": {}, "invalidated": [],
    "execution_tracking": {"activation_architecture_status": "not_started",
                           "seam6_execution_status": "not_started",
                           "external_handoffs_status": "not_started",
                           "external_handoffs_implemented": "unknown"},
    "capability_claims": [], "validation_attempts": [],
    "collection_freeze": {"snapshot": [], "exceptions": []},
}


def main():
    tmp = tempfile.mkdtemp(prefix="shopya_tests_")
    try:
        spec_v = yaml.safe_load(open(SCHEMA))["schema"]["version"]
        chart_v = yaml.safe_load(open(CHARTER))["charter"]["version"]
        frame_p = write(os.path.join(tmp, "frame.yaml"), FRAME)
        sha = hashlib.sha256(open(frame_p, "rb").read()).hexdigest()

        def mk(**over):
            d = copy.deepcopy(BASE)
            d["run"]["spec_version"], d["run"]["charter_version"] = spec_v, chart_v
            d["artifacts"]["frame"] = {"path": frame_p, "sha256": sha, "status": "current"}
            for k, v in over.items():
                d[k] = v
            return d

        print("\n-- transition legality --")
        rc, out = validate(write(os.path.join(tmp, "a.yaml"), mk()), "FRAME_READY")
        ok("happy path NEW -> FRAME_READY passes", rc == 0, out)

        rc, out = validate(write(os.path.join(tmp, "b.yaml"), mk()), "VALIDATED")
        ok("illegal transition refused", rc != 0 and "illegal_transition" in out)

        print("\n-- F3: version semantics (Model B, current-canon + explicit migration) --")
        # A run pinned to an OLD charter version differs from the loaded canon -> refused.
        s = mk(); s["run"]["charter_version"] = "0.0.1-ancient"
        rc, out = validate(write(os.path.join(tmp, "v1.yaml"), s), "FRAME_READY")
        ok("run pinned to stale charter is refused against current canon",
           rc != 0 and "run_canon_version_mismatch" in out)
        # Recording a migration to the current canon version clears it.
        s = mk()
        s["run"]["charter_version"] = "0.0.1-ancient"
        s["run"]["migration"] = [{"from_charter_version": "0.0.1-ancient",
                                  "to_charter_version": chart_v,
                                  "from_spec_version": spec_v, "to_spec_version": spec_v,
                                  "at": "z", "by": "product_owner", "note": "migrate"}]
        s["run"]["charter_version"] = chart_v  # migration bumps the pin to canon
        rc, out = validate(write(os.path.join(tmp, "v2.yaml"), s), "FRAME_READY")
        ok("after migration to canon the run transitions", rc == 0, out)
        # A drift to a value that is NEITHER the NEW-pin NOR a migration target is refused.
        s = mk(); s["run"]["charter_version"] = "9.9.9-bogus"
        rc, out = validate(write(os.path.join(tmp, "v3.yaml"), s), "FRAME_READY")
        ok("silent version drift (no migration) is refused",
           rc != 0 and ("charter_version_changed_without_migration" in out
                        or "run_canon_version_mismatch" in out))

        print("\n-- owner decisions are not inferable --")
        s = mk(); s["workflow"]["state"] = "FRAME_READY"
        rc, out = validate(write(os.path.join(tmp, "c.yaml"), s), "RESEARCHING")
        ok("missing owner decision refused", rc != 0 and "closing_sentence_is_not_proof" in out)

        s = mk(); s["workflow"]["state"] = "FRAME_READY"
        s["owner_decisions"] = {"frame_accepted": {"status": "owner_confirmed", "decided": True,
                                                   "decided_by": "po",
                                                   "decided_at": "2026-08-06T15:10:00Z"}}
        rc, out = validate(write(os.path.join(tmp, "c2.yaml"), s), "RESEARCHING")
        ok("recorded owner decision passes", rc == 0, out)

        # F4 (binary ledger): a provisional_recommendation cannot satisfy an owner gate.
        s = mk(); s["workflow"]["state"] = "FRAME_READY"
        s["owner_decisions"] = {"frame_accepted": {"status": "provisional_recommendation",
                                                   "decided": False, "decided_by": "agent",
                                                   "decided_at": "z"}}
        rc, out = validate(write(os.path.join(tmp, "c3.yaml"), s), "RESEARCHING")
        ok("provisional_recommendation cannot satisfy the owner gate", rc != 0)
        # F4: a would-be 'fulfilled'/'validated' entry stamped as an owner decision is rejected
        # (engine fulfillment / validation are not owner decisions).
        s = mk(); s["workflow"]["state"] = "FRAME_READY"
        s["owner_decisions"] = {"frame_accepted": {"status": "fulfilled", "decided": True,
                                                   "decided_by": "product_owner",
                                                   "decided_at": "z"}}
        rc, out = validate(write(os.path.join(tmp, "c4.yaml"), s), "RESEARCHING")
        ok("a fulfilled/validated status in owner_decisions is rejected",
           rc != 0 and "decision_status_misstamped" in out)

        print("\n-- validation is an attempt, not a transition --")
        # products_csv is registered with a real sha; a passing attempt must be BOUND to it.
        csv_sha = sha  # reuse the frame file's sha as the "built CSV" hash
        s = mk(); s["workflow"]["state"] = "SEAM6_READY"
        s["execution_tracking"]["seam6_execution_status"] = "validated"
        s["artifacts"]["products_csv"] = {"path": frame_p, "sha256": csv_sha, "status": "current"}
        s["validation_attempts"] = [{"attempted_at": "x", "result": "failed", "failures": [{}]}]
        rc, out = validate(write(os.path.join(tmp, "d.yaml"), s), "VALIDATED")
        ok("failed attempt cannot reach VALIDATED", rc != 0 and
           "validation_failure_treated_as_transition" in out)

        # ADVERSARIAL (F2): an agent-authored 'passed' attempt with NO hash binding is refused.
        s["validation_attempts"] = [{"attempted_at": "x", "result": "passed", "failures": []}]
        rc, out = validate(write(os.path.join(tmp, "d1.yaml"), s), "VALIDATED")
        ok("agent-authored passed attempt (no output_sha256) cannot reach VALIDATED",
           rc != 0 and "not bound to the registered products_csv" in out)

        # ADVERSARIAL (F2): a passed attempt bound to the WRONG hash is refused.
        s["validation_attempts"] = [{"attempted_at": "x", "result": "passed",
                                     "output_sha256": "deadbeef", "failures": []}]
        rc, out = validate(write(os.path.join(tmp, "d1b.yaml"), s), "VALIDATED")
        ok("passed attempt bound to a mismatched hash cannot reach VALIDATED",
           rc != 0 and "not bound to the registered products_csv" in out)

        # ADVERSARIAL (F4): a hash-bound pass that used --allow-stale cannot reach VALIDATED.
        s["validation_attempts"] = [{"attempted_at": "x", "result": "passed",
                                     "output_sha256": csv_sha, "production": True,
                                     "allow_stale_used": True, "failures": []}]
        rc, out = validate(write(os.path.join(tmp, "d1c.yaml"), s), "VALIDATED")
        ok("a --allow-stale build cannot satisfy VALIDATED",
           rc != 0 and "not a production build" in out)
        # ADVERSARIAL (F4): an attempt not marked production is refused.
        s["validation_attempts"] = [{"attempted_at": "x", "result": "passed",
                                     "output_sha256": csv_sha, "failures": []}]
        rc, out = validate(write(os.path.join(tmp, "d1d.yaml"), s), "VALIDATED")
        ok("a non-production attempt cannot satisfy VALIDATED",
           rc != 0 and "not a production build" in out)

        # Only a hash-bound, production pass reaches VALIDATED.
        s["validation_attempts"] = [{"attempted_at": "x", "result": "passed",
                                     "output_sha256": csv_sha, "production": True,
                                     "allow_stale_used": False, "legacy_replay_used": False,
                                     "failures": []}]
        rc, out = validate(write(os.path.join(tmp, "d2.yaml"), s), "VALIDATED")
        ok("hash-bound production passing attempt reaches VALIDATED", rc == 0, out)

        s["validation_attempts"][-1]["invalidated_at"] = "y"
        s["validation_attempts"][-1]["invalidated_by_decision"] = "reopen_seam6_execution"
        rc, out = validate(write(os.path.join(tmp, "d3.yaml"), s), "VALIDATED")
        ok("invalidated pass requires revalidation", rc != 0)

        print("\n-- abandonment --")
        s = mk(); s["workflow"]["state"] = "LIVE"
        s["owner_decisions"] = {"abandon_run": {"status": "owner_confirmed", "decided": True, "decided_by": "po", "decided_at": "z"}}
        rc, out = validate(write(os.path.join(tmp, "e.yaml"), s), "ABANDONED")
        ok("abandon after LIVE refused", rc != 0 and "abandon_after_live" in out)

        s = mk(); s["workflow"]["state"] = "BRIEF_DRAFT"
        s["owner_decisions"] = {"abandon_run": {"status": "owner_confirmed", "decided": True, "decided_by": "po", "decided_at": "z"}}
        s["abandonment"] = {"run_id_status": "retained", "campaign_id_status": "never_minted"}
        rc, out = validate(write(os.path.join(tmp, "e2.yaml"), s), "ABANDONED")
        ok("pre-LIVE abandon with correct classification passes", rc == 0, out)

        s["abandonment"]["campaign_id_status"] = "released"
        rc, out = validate(write(os.path.join(tmp, "e3.yaml"), s), "ABANDONED")
        ok("wrong campaign_id classification refused", rc != 0)

        print("\n-- item 5: LIVE verification cannot be asserted --")
        def live_base():
            s = mk(); s["workflow"]["state"] = "CAMPAIGN_APPROVED"
            s["artifacts"]["products_csv"] = {"path": frame_p, "sha256": sha, "status": "current"}
            s["execution_tracking"]["seam6_execution_status"] = "executed"
            s["collection_freeze"] = {"snapshot": [{"collection_id": "c1", "frozen_at": "z",
                                                    "sha256": "x"}], "exceptions": []}
            # A real pre-LIVE CAMPAIGN_APPROVED run necessarily still carries the current bound
            # passing validation proof it reached VALIDATED with (prd.md §16.5: a post-validation
            # state must be supported by current valid execution proof, not only the verification
            # record). Without it, the post-validation coherence invariant correctly refuses.
            s["validation_attempts"] = [{"attempted_at": "t", "result": "passed",
                                         "production": True, "output_sha256": sha, "failures": []}]
            return s
        # ADVERSARIAL: asserting post_cache_verified=true with no computed record cannot reach LIVE.
        s = live_base()
        s["verification"] = {"post_cache_verified": True, "reprobe_at": "z"}
        rc, out = validate(write(os.path.join(tmp, "lv1.yaml"), s), "LIVE")
        ok("asserted post_cache_verified (no computed verification) cannot reach LIVE",
           rc != 0 and "verification" in out)
        # ADVERSARIAL: verification bound to the WRONG build hash refused.
        s = live_base()
        s["verification"] = {"post_cache_verified": True, "reprobe_at": "z", "result": "pass",
                             "build_sha256": "deadbeef", "method": "automated_probe"}
        rc, out = validate(write(os.path.join(tmp, "lv2.yaml"), s), "LIVE")
        ok("verification bound to a mismatched build hash cannot reach LIVE",
           rc != 0 and "build_sha256" in out)
        # ADVERSARIAL: human_observation without observed_by refused.
        s = live_base()
        s["verification"] = {"post_cache_verified": True, "reprobe_at": "z", "result": "pass",
                             "build_sha256": sha, "method": "human_observation"}
        rc, out = validate(write(os.path.join(tmp, "lv3.yaml"), s), "LIVE")
        ok("human-observed verification without observed_by refused",
           rc != 0 and "observed_by" in out)
        # A properly computed, build-bound verification reaches LIVE.
        s = live_base()
        s["verification"] = {"post_cache_verified": True, "reprobe_at": "z", "result": "pass",
                             "build_sha256": sha, "method": "automated_probe",
                             "executed_build": "b005"}
        rc, out = validate(write(os.path.join(tmp, "lv4.yaml"), s), "LIVE")
        ok("build-bound automated verification reaches LIVE", rc == 0, out)

        print("\n-- reopen obligations --")
        s = mk(); s["workflow"]["state"] = "BRIEF_APPROVED"
        s["owner_decisions"] = {"brief_reopened": {"status": "owner_confirmed", "decided": True, "decided_by": "po",
                                                   "decided_at": "z", "value": {"reason": "r"}}}
        s["artifacts"]["stage5_routes"] = {"path": frame_p, "status": "current"}
        rc, out = validate(write(os.path.join(tmp, "f.yaml"), s), "BRIEF_DRAFT")
        ok("reopen without supersession/invalidation refused",
           rc != 0 and "reopen_without_decision" in out)

        # F5: with obligations MET (artifacts superseded + invalidated populated + decision),
        # the reopen is EXECUTABLE — proving the edge is not a dead-end (was un-executable
        # before the run.py reopen writer existed).
        s = mk(); s["workflow"]["state"] = "BRIEF_APPROVED"
        s["owner_decisions"] = {"brief_reopened": {
            "status": "owner_confirmed", "decided": True, "decided_by": "po", "decided_at": "z",
            "value": {"reason": "scope changed", "invalidating_finding": "x",
                      "affected_artifacts": ["stage5_routes", "stage6_activation"]}}}
        s["artifacts"]["stage5_routes"] = {"path": frame_p, "status": "superseded",
                                           "supersession_reason": "reopen"}
        s["artifacts"]["stage6_activation"] = {"path": frame_p, "status": "superseded",
                                               "supersession_reason": "reopen"}
        s["artifacts"]["stage4_brief"] = {"path": frame_p, "status": "current"}
        s["invalidated"] = ["route_selected", "campaign_approved",
                            "execution_tracking.activation_architecture_status",
                            "execution_tracking.seam6_execution_status", "validation_attempts"]
        rc, out = validate(write(os.path.join(tmp, "f2.yaml"), s), "BRIEF_DRAFT")
        ok("reopen WITH all obligations met is executable", rc == 0, out)

        print("\n-- C2: each_has_keys vs each_has_non_null --")
        FAMS = ["cultural_or_editorial", "demand_or_behavioral", "commercial_or_category",
                "visual_or_design", "counter_trend_or_fatigue", "temporal_catalyst"]
        sig_ok = {"signal_id": "SIG-001", "claim": "c", "evidence_type": "cultural_or_editorial",
                  "source": "s", "source_date": None, "observed_date": "2026-08-06",
                  "geography": "US", "direct_observation": "o", "interpretation": None,
                  "confidence": "weak", "limitations": "l"}
        land = write(os.path.join(tmp, "land.md"), {"x": 1})
        def sigstate(sigs):
            st = mk(); st["workflow"]["state"] = "RESEARCHING"
            sp = write(os.path.join(tmp, "sigs.yaml"),
                       {"run_id": "r", "produced_at": "t",
                        "evidence_families_covered": FAMS, "stop_condition_met": True,
                        "stop_condition_basis": "b",
                        "deviations": [], "unavailable_data": [], "signals": sigs})
            st["artifacts"]["stage1_signals"] = {"path": sp, "status": "current"}
            st["artifacts"]["stage1_landscape"] = {"path": land, "status": "current"}
            st["stage1"] = {"evidence_families_covered": ["a"], "stop_condition_met": True,
                            "deviations": []}
            return st
        rc, out = validate(write(os.path.join(tmp, "k1.yaml"), sigstate([sig_ok])), "SIGNALS_READY")
        ok("a null value on a nullable field PASSES each_has_keys", rc == 0, out)

        missing = dict(sig_ok); missing.pop("limitations")
        rc, out = validate(write(os.path.join(tmp, "k2.yaml"), sigstate([missing])), "SIGNALS_READY")
        ok("an ABSENT key still fails each_has_keys",
           rc != 0 and "missing required key" in out and "limitations" in out)

        opp_null = {k: "x" for k in ["opportunity_id", "territory", "observation",
                    "cultural_tension", "audience_behavior", "why_now", "shopya_role",
                    "desired_user_action", "instrumentation_mapping", "supporting_signal_ids",
                    "relevant_seams", "surface_potential", "expiration", "confidence",
                    "assumptions", "operational_risks"]}
        opp_null["ownability"] = {"level": "L1", "rationale": None}
        st = mk(); st["workflow"]["state"] = "SIGNALS_READY"
        op = write(os.path.join(tmp, "opps.yaml"), {"opportunities": [opp_null] * 4})
        st["artifacts"]["stage2_opportunities"] = {"path": op, "status": "current"}
        st["artifacts"]["stage2_comparison"] = {"path": land, "status": "current"}
        rc, out = validate(write(os.path.join(tmp, "k3.yaml"), st), "OPPORTUNITIES_READY")
        ok("each_has_non_null still rejects a null where content is required",
           rc != 0 and "null or empty" in out)

        print("\n-- reserved hooks are not operational --")
        # F3: migration is now a real model (was a refused stub). A run.migration record whose
        # target matches the loaded canon is accepted; see the dedicated F3 block above.
        s = mk()
        s["run"]["charter_version"] = "0.1.0-old"
        s["run"]["migration"] = [{"from_charter_version": "0.1.0-old",
                                  "to_charter_version": chart_v, "from_spec_version": spec_v,
                                  "to_spec_version": spec_v, "at": "z", "by": "po", "note": "x"}]
        s["run"]["charter_version"] = chart_v
        rc, out = validate(write(os.path.join(tmp, "g.yaml"), s), "FRAME_READY")
        ok("a recorded migration to canon is accepted", rc == 0, out)

        rc, out = validate(write(os.path.join(tmp, "g2.yaml"), mk()), "FRAME_READY")
        ok("withdrawal enforcement warns that it is inactive",
           "withdrawal enforcement inactive" in out)

        print("\n-- artifact structural validation (separate phase) --")
        bad = dict(FRAME); bad.pop("planning_horizon")
        bp = write(os.path.join(tmp, "bad_frame.yaml"), bad)
        s = mk(); s["artifacts"]["frame"] = {"path": bp, "status": "current"}
        rc, out = validate(write(os.path.join(tmp, "h.yaml"), s), phase="artifacts")
        ok("frame missing required field refused",
           rc != 0 and "artifact_structure_invalid" in out and "planning_horizon" in out)

        bad2 = dict(FRAME); bad2["eligible_seams"] = ["S6", "S9"]
        bp2 = write(os.path.join(tmp, "bad_frame2.yaml"), bad2)
        s = mk(); s["artifacts"]["frame"] = {"path": bp2, "status": "current"}
        rc, out = validate(write(os.path.join(tmp, "h2.yaml"), s), phase="artifacts")
        ok("frame seam outside closed set refused", rc != 0 and "S9" in out)

        rc, out = validate(write(os.path.join(tmp, "h3.yaml"), mk()), phase="artifacts")
        ok("valid frame passes artifact phase", rc == 0, out)

        print("\n-- ATOMICITY: a refused transition must not touch state.yaml --")
        runs = os.path.join(tmp, "runs"); os.makedirs(runs)
        env = dict(os.environ, SHOPYA_CAMPAIGN_RUNS=runs)
        r = subprocess.run([sys.executable, RUNNER, "new"], capture_output=True, text=True, env=env)
        rid = next((l.split()[1] for l in r.stdout.splitlines() if l.startswith("run_id")), None)
        ok("run.py new mints a run", bool(rid), r.stdout + r.stderr)
        # NAMING_CONVENTIONS.md: unnamed runs are created under _drafts/ until promotion
        sp = os.path.join(runs, "_drafts", rid, "state.yaml")
        before = open(sp, "rb").read()
        r = subprocess.run([sys.executable, RUNNER, "transition", "--run", rid, "--to", "FRAME_READY"],
                           capture_output=True, text=True, env=env)
        after = open(sp, "rb").read()
        ok("transition without a frame is refused", r.returncode != 0)
        ok("state.yaml byte-identical after refusal", before == after)
        ok("no proposal file left behind",
           not os.path.exists(os.path.join(runs, "_drafts", rid, ".state.proposed.yaml")))
        ok("run dir holds only real artifacts after a refusal",
           sorted(os.listdir(os.path.join(runs, "_drafts", rid))) == ["state.yaml"],
           str(sorted(os.listdir(os.path.join(runs, "_drafts", rid)))))

        r = subprocess.run([sys.executable, RUNNER, "register-artifact", "--run", rid,
                            "--key", "frame", "--path", frame_p], capture_output=True, text=True, env=env)
        r2 = subprocess.run([sys.executable, RUNNER, "transition", "--run", rid, "--to", "FRAME_READY"],
                            capture_output=True, text=True, env=env)
        committed = yaml.safe_load(open(sp))
        ok("transition commits after the artifact exists",
           r2.returncode == 0 and committed["workflow"]["state"] == "FRAME_READY",
           r.stdout + r2.stdout + r2.stderr)
        print("\n-- C1: controlled state writes --")
        r = subprocess.run([sys.executable, RUNNER, "set", "--run", rid,
                            "--path", "workflow.state", "--value", "LIVE"],
                           capture_output=True, text=True, env=env)
        ok("set refuses a non-whitelisted path",
           r.returncode != 0 and "not a settable path" in r.stdout)
        # F2: validation_attempts is no longer agent-settable (only validate-execution writes it).
        r = subprocess.run([sys.executable, RUNNER, "set", "--run", rid,
                            "--path", "validation_attempts",
                            "--value-json", '[{"result":"passed"}]'],
                           capture_output=True, text=True, env=env)
        ok("set refuses validation_attempts (not settable — validate-execution only)",
           r.returncode != 0 and "not a settable path" in r.stdout)
        r = subprocess.run([sys.executable, RUNNER, "set", "--run", rid,
                            "--path", "execution_tracking.seam6_execution_status",
                            "--value", "bogus"], capture_output=True, text=True, env=env)
        ok("set refuses a value outside an enum", r.returncode != 0)
        r = subprocess.run([sys.executable, RUNNER, "set", "--run", rid,
                            "--path", "identity.display_name", "--value", "Test Name"],
                           capture_output=True, text=True, env=env)
        after = yaml.safe_load(open(sp))
        ok("set writes a whitelisted path atomically",
           r.returncode == 0 and after["identity"]["display_name"] == "Test Name")
        r = subprocess.run([sys.executable, RUNNER, "set", "--run", rid,
                            "--path", "identity.campaign_id.confirmed_by_owner", "--value", "true"],
                           capture_output=True, text=True, env=env)
        after = yaml.safe_load(open(sp))
        ok("set coerces booleans rather than storing strings",
           after["identity"]["campaign_id"]["confirmed_by_owner"] is True)

        ok("history records the transition type",
           committed["workflow"]["history"][-1]["transition_type"] == "forward")
        ok("a committed transition exits 0 and leaves no scratch in the run dir",
           r2.returncode == 0 and sorted(os.listdir(os.path.join(runs, "_drafts", rid))) == ["state.yaml"],
           str(sorted(os.listdir(os.path.join(runs, "_drafts", rid)))))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        for f in FAIL:
            print("  FAILED: %s" % f)
        sys.exit(1)


if __name__ == "__main__":
    main()
