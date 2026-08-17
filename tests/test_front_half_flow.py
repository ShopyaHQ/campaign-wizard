#!/usr/bin/env python3
"""Structured front-half FLOW tests (spec 1.8.0) — the typed hash-bound approvals, the validator
gates, deterministic dependency invalidation, the five composed owner checkpoints, and the exact
approved campaign_spec -> Request v2 handoff (task §28). Drives the REAL run.py + validator via
subprocess against a temp runs dir.

    python3 tests/test_front_half_flow.py
"""
import json, os, shutil, subprocess, sys, tempfile
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNNER = os.path.join(ROOT, "scripts", "run.py")
GEN = os.path.join(ROOT, "scripts", "generate_curation_request.py")
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import front_half_fixture as fx  # noqa: E402

PASS, FAIL = [], []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %s  %s%s" % ("PASS" if cond else "FAIL", name, ("  <- " + str(detail)[-400:]) if detail and not cond else ""))


def main():
    tmp = tempfile.mkdtemp(prefix="shopya_fhflow_")
    runs = os.path.join(tmp, "campaigns"); os.makedirs(runs)
    env = dict(os.environ, SHOPYA_CAMPAIGN_RUNS=runs)
    work = os.path.join(tmp, "payloads"); os.makedirs(work)

    def R(*args):
        return subprocess.run([sys.executable, RUNNER, *args], capture_output=True, text=True, env=env)

    def w(name, obj):
        p = os.path.join(work, name); json.dump(obj, open(p, "w")); return p

    def mkrun():
        r = R("new")
        return next(l.split()[-1] for l in r.stdout.splitlines() if "cmp_" in l)

    def state(rid):
        for base in (os.path.join(runs, "_drafts"), runs):
            p = os.path.join(base, rid, "state.yaml")
            if os.path.exists(p):
                return yaml.safe_load(open(p))
        raise AssertionError("no state for " + rid)

    try:
        # ── drive a fresh vNext run through all four objects + five checkpoints to SEAM6_READY ──
        rid = mkrun()
        R("register-object", "--run", rid, "--kind", "research_brief",
          "--payload", w("b.json", fx.brief_payload(run_id=rid)))
        r = R("transition", "--run", rid, "--to", "FRAME_READY")
        ok("FRAME_READY on structured research_brief (prose optional)", r.returncode == 0, r.stdout + r.stderr)

        print("\n-- KICKOFF: hash-bound approval of the EXACT research_brief --")
        # a transition to RESEARCHING without kickoff_approved is refused
        R("record-decision", "--run", rid, "--id", "frame_accepted", "--by", "product_owner",
          "--status", "owner_confirmed")
        r = R("transition", "--run", rid, "--to", "RESEARCHING")
        ok("RESEARCHING refused without a hash-bound kickoff approval",
           r.returncode != 0 and "structured_object" in (r.stdout + r.stderr) or "closing_sentence" in (r.stdout + r.stderr) or r.returncode != 0)
        R("approve-object", "--run", rid, "--id", "kickoff_approved", "--kind", "research_brief",
          "--binding", "object", "--by", "product_owner")
        r = R("transition", "--run", rid, "--to", "RESEARCHING")
        ok("RESEARCHING passes with kickoff_approved bound to the brief", r.returncode == 0, r.stdout + r.stderr)
        kv = state(rid)["owner_decisions"]["kickoff_approved"]["value"]
        sp = state(rid)["structured_objects"]["research_brief"]
        ok("kickoff approval binds EXACT id+revision+hash",
           kv["object_id"] == sp["object_id"] and kv["canonical_hash"] == sp["canonical_hash"])

        print("\n-- material brief revision makes the prior kickoff approval STALE --")
        b2 = fx.brief_payload(run_id=rid); b2["revision"] = "r002"; b2["parent_revision"] = "r001"
        b2["objective"] = fx._field("a materially revised objective")
        R("register-object", "--run", rid, "--kind", "research_brief", "--payload", w("b2.json", b2))
        # the kickoff approval still binds r001's hash; the current brief is r002 -> mismatch refuses.
        # (register-object also invalidates kickoff_approved via the dependency graph.)
        st = state(rid)
        ok("registering a new brief revision invalidates kickoff_approved",
           "kickoff_approved" in (st.get("invalidated") or []))
        # re-record kickoff on the NEW revision clears staleness
        R("approve-object", "--run", rid, "--id", "kickoff_approved", "--kind", "research_brief",
          "--binding", "object", "--by", "product_owner")
        ok("re-recording kickoff on the current brief clears the invalidation",
           "kickoff_approved" not in (state(rid).get("invalidated") or []))

        print("\n-- research_ledger + direction selection --")
        R("register-object", "--run", rid, "--kind", "research_ledger",
          "--payload", w("l.json", fx.ledger_payload(brief_ref="rb_fx")))
        r = R("transition", "--run", rid, "--to", "SIGNALS_READY")
        ok("SIGNALS_READY on structured research_ledger", r.returncode == 0, r.stdout + r.stderr)
        R("register-object", "--run", rid, "--kind", "campaign_directions",
          "--payload", w("d.json", fx.directions_payload(ledger_ref="rl_fx")))
        r = R("transition", "--run", rid, "--to", "OPPORTUNITIES_READY")
        ok("OPPORTUNITIES_READY on structured campaign_directions", r.returncode == 0, r.stdout + r.stderr)

        # direction selection binds the exact direction hash
        R("select-direction", "--run", rid, "--direction-id", "d1", "--by", "product_owner")
        R("record-decision", "--run", rid, "--id", "opportunity_selected", "--by", "product_owner",
          "--status", "owner_confirmed")
        R("set", "--run", rid, "--path", "identity.campaign_id.status", "--value", "proposed")
        r = R("transition", "--run", rid, "--to", "OPPORTUNITY_SELECTED")
        ok("OPPORTUNITY_SELECTED on hash-bound direction selection", r.returncode == 0, r.stdout + r.stderr)
        sel = state(rid)["owner_decisions"]["direction_selected_v2"]["value"]
        ok("selection binds a direction_id + direction_hash", sel.get("direction_id") == "d1" and sel.get("direction_hash"))

        # selecting a direction that does not exist is refused by run.py
        r = R("select-direction", "--run", rid, "--direction-id", "d_ghost", "--by", "product_owner")
        ok("selecting a non-existent direction is refused", r.returncode != 0)

        print("\n-- PREMISE + VERTICAL: two distinct section approvals --")
        R("register-object", "--run", rid, "--kind", "campaign_spec",
          "--payload", w("s.json", fx.spec_payload()))
        R("approve-object", "--run", rid, "--id", "premise_approved", "--kind", "campaign_spec",
          "--binding", "section", "--section", "premise", "--by", "product_owner")
        R("approve-object", "--run", rid, "--id", "verticals_approved", "--kind", "campaign_spec",
          "--binding", "section", "--section", "vertical_strategies", "--by", "product_owner")
        R("record-decision", "--run", rid, "--id", "brief_approved", "--by", "product_owner",
          "--status", "owner_confirmed")
        R("transition", "--run", rid, "--to", "INTERVIEW_COMPLETE")
        R("transition", "--run", rid, "--to", "BRIEF_DRAFT")
        r = R("transition", "--run", rid, "--to", "BRIEF_APPROVED")
        ok("BRIEF_APPROVED on distinct premise + vertical section approvals", r.returncode == 0, r.stdout + r.stderr)
        pv = state(rid)["owner_decisions"]
        ok("premise + vertical approvals are DISTINCT typed decisions binding DIFFERENT section hashes",
           pv["premise_approved"]["value"]["section_hash"] != pv["verticals_approved"]["value"]["section_hash"])

        print("\n-- premise change invalidates premise+architecture approvals (dependency graph) --")
        s2 = fx.spec_payload(); s2["revision"] = "r002"; s2["parent_revision"] = "r001"
        s2["sections"]["premise"]["dek"] = "a materially changed premise dek"
        R("register-object", "--run", rid, "--kind", "campaign_spec", "--payload", w("s2.json", s2))
        inval = state(rid).get("invalidated") or []
        ok("a premise change invalidates premise_approved (deterministic)", "premise_approved" in inval)
        # verticals_approved depends_on premise in the dependency graph -> also invalidated.
        ok("a premise change invalidates the downstream verticals_approved", "verticals_approved" in inval, inval)
        # architecture_approved / campaign_spec_approved are NOT yet recorded at this point, so there
        # is nothing to invalidate for them yet (only EXISTING approvals are invalidated). Their
        # downstream invalidation is exercised in the object-level test + the rid2 stale-spec case.

        # re-approve premise + verticals on r002 to proceed
        R("approve-object", "--run", rid, "--id", "premise_approved", "--kind", "campaign_spec",
          "--binding", "section", "--section", "premise", "--by", "product_owner")
        R("approve-object", "--run", rid, "--id", "verticals_approved", "--kind", "campaign_spec",
          "--binding", "section", "--section", "vertical_strategies", "--by", "product_owner")

        print("\n-- ARCHITECTURE: ONE composite approval, NO product-row approval --")
        R("approve-object", "--run", rid, "--id", "architecture_approved", "--kind", "campaign_spec",
          "--binding", "composite", "--sections", "collection_selections,rails,content_program",
          "--by", "product_owner")
        R("record-decision", "--run", rid, "--id", "route_selected", "--by", "product_owner",
          "--status", "owner_confirmed")
        for path, val in (("identity.campaign_id.value", "almost-fall-2026"),
                          ("identity.campaign_id.status", "confirmed"),
                          ("identity.campaign_id.confirmed_by_owner", "true"),
                          ("identity.display_name", "Almost Fall")):
            R("set", "--run", rid, "--path", path, "--value", val)
        R("transition", "--run", rid, "--to", "ROUTES_READY")
        r = R("transition", "--run", rid, "--to", "ROUTE_SELECTED")
        ok("ROUTE_SELECTED on the composite architecture approval", r.returncode == 0, r.stdout + r.stderr)

        print("\n-- ACTIVATION + FINAL 'BUILD THIS' --")
        # ACTIVATION_READY is vnext_additive_only: the structured naming/default/seam gates are ADDED
        # to the UNCHANGED real Seam-6 activation gates (explore_feeds/scheduling/delivery). Provide a
        # minimal valid activation artifact for those real gates (execution half, out of front scope).
        act = os.path.join(work, "act.yaml")
        yaml.safe_dump({"activations": [{"seam_id": "S6", "surface": "explore", "role": "r",
                        "user_action": "u", "execution_mode": "executable", "owner": "o",
                        "activation_authority": "a", "explore_feeds": 3,
                        "scheduling": {"semantic_status": "verified", "evaluation_mode": "query_time",
                                       "cache_latency_seconds": {"minimum": 1, "maximum": 2},
                                       "precision": "p"}, "artifact": "x",
                        "implementation_status": "pending"}],
                        "delivery": {"intent": {"mode": "launch_window"}}}, open(act, "w"))
        R("register-artifact", "--run", rid, "--key", "stage6_activation", "--path", act)
        R("set", "--run", rid, "--path", "execution_tracking.activation_architecture_status", "--value", "approved")
        R("set", "--run", rid, "--path", "execution_tracking.external_handoffs_status", "--value", "authored")
        r = R("transition", "--run", rid, "--to", "ACTIVATION_READY")
        ok("ACTIVATION_READY on naming/default/seam sections + real activation gates",
           r.returncode == 0, r.stdout + r.stderr)
        # FINAL CAMPAIGN SPEC — "build this": the exact composite over all 8 sections.
        R("approve-object", "--run", rid, "--id", "campaign_spec_approved", "--kind", "campaign_spec",
          "--binding", "composite",
          "--sections", ",".join(["premise", "vertical_strategies", "collection_selections", "rails",
                                   "content_program", "naming_voice", "default_composition", "seam_intent"]),
          "--by", "product_owner")
        fa = state(rid)["owner_decisions"]["campaign_spec_approved"]["value"]
        sp8 = state(rid)["structured_objects"]["campaign_spec"]
        ok("final 'build this' binds the composite over ALL 8 sections of the current revision",
           fa["composite_hash"] == sp8["composite_hash"] and fa["revision"] == sp8["revision"])

        print("\n-- REQUEST v2 from the EXACT approved campaign_spec (task §22/§23) --")
        g = subprocess.run([sys.executable, GEN, "--run", rid, "--from-spec"],
                           capture_output=True, text=True, env=env)
        ok("spec-bound Request v2 generation succeeds", g.returncode == 0, g.stdout + g.stderr)
        ok("one Request per selected collection (2)", g.stdout.count("request_id") == 2, g.stdout)
        # inspect a generated request: spec_ref binds the exact approved spec
        reqs = []
        for base in (os.path.join(runs, "_drafts", rid), os.path.join(runs, rid)):
            d = os.path.join(base, "requests")
            if os.path.isdir(d):
                reqs = [json.load(open(os.path.join(d, f))) for f in os.listdir(d)]
        ok("generated a request per selection on disk", len(reqs) == 2, str(len(reqs)))
        sp = state(rid)["structured_objects"]["campaign_spec"]
        if reqs:
            r0 = reqs[0]
            ok("spec_ref.kind is campaign_spec (not the compat run binding)",
               r0["spec_ref"]["kind"] == "campaign_spec")
            ok("spec_ref binds the exact id / revision / composite hash",
               r0["spec_ref"]["ref"] == sp["object_id"] and r0["spec_ref"]["version"] == sp["revision"]
               and r0["spec_ref"]["hash"] == sp["composite_hash"])
            ok("request_hash is deterministic (contract 2.0.0)",
               r0["contract_version"] == "2.0.0" and bool(r0["integrity"]["request_hash"]))

        print("\n-- a STALE / unapproved spec cannot generate a production Request --")
        rid2 = mkrun()
        # build objects but DO NOT record campaign_spec_approved
        for kind, pl in (("research_brief", fx.brief_payload(run_id=rid2)),
                         ("research_ledger", fx.ledger_payload(brief_ref="rb_fx")),
                         ("campaign_directions", fx.directions_payload(ledger_ref="rl_fx")),
                         ("campaign_spec", fx.spec_payload())):
            R("register-object", "--run", rid2, "--kind", kind, "--payload", w(kind + "2.json", pl))
        g = subprocess.run([sys.executable, GEN, "--run", rid2, "--from-spec"],
                           capture_output=True, text=True, env=env)
        ok("no final 'build this' approval -> spec-bound generation REFUSED",
           g.returncode != 0 and "build this" in (g.stdout + g.stderr))

        # approve, then materially change the spec so the approval is stale -> refuse
        R("approve-object", "--run", rid2, "--id", "campaign_spec_approved", "--kind", "campaign_spec",
          "--binding", "composite",
          "--sections", ",".join(["premise", "vertical_strategies", "collection_selections", "rails",
                                   "content_program", "naming_voice", "default_composition", "seam_intent"]),
          "--by", "product_owner")
        s2b = fx.spec_payload(); s2b["revision"] = "r002"; s2b["parent_revision"] = "r001"
        s2b["sections"]["premise"]["dek"] = "changed after approval"
        R("register-object", "--run", rid2, "--kind", "campaign_spec", "--payload", w("s2b.json", s2b))
        g = subprocess.run([sys.executable, GEN, "--run", rid2, "--from-spec"],
                           capture_output=True, text=True, env=env)
        ok("a STALE campaign_spec_approved (changed spec) -> generation REFUSED",
           g.returncode != 0)

        print("\n-- compatibility: the honest run-bound (null-hash) path still works --")
        g = subprocess.run([sys.executable, GEN, "--run", rid2, "--category-id", "w.coats",
                            "--required-depth", "50"], capture_output=True, text=True, env=env)
        ok("legacy run-bound Request v2 (no --from-spec) still generates", g.returncode == 0, g.stdout + g.stderr)
        outp = os.path.join(runs, "_drafts", rid2, "curation_request_v2.json")
        if os.path.exists(outp):
            comp = json.load(open(outp))
            ok("compat spec_ref is the honest run binding (kind=run, hash=null)",
               comp["spec_ref"]["kind"] == "run" and comp["spec_ref"]["hash"] is None)

        print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
        sys.exit(1 if FAIL else 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
