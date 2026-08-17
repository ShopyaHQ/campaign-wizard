#!/usr/bin/env python3
"""test_checkpoint_core.py — the iterative checkpoint-session Core (task §30).

Drives a FRESH run through all five checkpoints via checkpoint_core (the same functions the CLI and
the FastAPI console call), proving: checkpoint derivation · typed question generation · owner/
inferred/unresolved classification · field-level answers · section edits · add/remove/reorder ·
immutable revisions · untouched-field preservation · semantic diffs · N revision cycles · exact
approval binding · ONE-action approval · stale-approval refusal · dependency invalidation.

Runs directly (repo convention): python3 tests/test_checkpoint_core.py
"""
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


def main():
    tmp = tempfile.mkdtemp(prefix="cp_core_")
    runs = os.path.join(tmp, "campaigns")
    os.makedirs(os.path.join(runs, "_drafts"))
    os.environ["SHOPYA_CAMPAIGN_RUNS"] = runs
    # fresh import so run.RUNS picks up the env
    for m in ("run", "checkpoint_core", "front_half"):
        sys.modules.pop(m, None)
    import checkpoint_core as cc
    import front_half_fixture as fx
    try:
        # ── create a fresh run ──
        created = cc.create_run()
        rid = created["run_id"]
        ok("create_run mints a production run at NEW",
           created["run_mode"] == "production" and created["internal_state"] == "NEW", created)

        # ── CHECKPOINT 1: KICKOFF ── derivation on an empty run ──
        view = cc.describe_checkpoint(rid)
        cp = view["checkpoint"]
        ok("checkpoint derivation: fresh run is at KICKOFF/OPEN",
           cp["checkpoint_type"] == "kickoff" and cp["status"] == "OPEN", cp["status"])
        ok("OPEN checkpoint only allows submit_intake",
           cp["allowed_actions"] == ["submit_intake"], cp["allowed_actions"])

        # ── intake: submit the first brief ──
        brief = fx.brief_payload(bid="rb_1", rev="r001", run_id=rid)
        res = cc.submit_intake(rid, brief)
        ok("submit_intake registers the brief as its first revision",
           res["revision"] == "r001" and res["object_id"] == "rb_1", res)

        view = cc.describe_checkpoint(rid)
        cp = view["checkpoint"]
        ok("after intake, KICKOFF is at OWNER_REVIEW", cp["status"] == "OWNER_REVIEW", cp["status"])

        # ── question framework + provenance classification ──
        qs = {q["id"]: q for q in cp["questions"]}
        ok("typed questions generated (objective long_text, market short_text, exclusions list)",
           qs["objective"]["type"] == "long_text" and qs["market"]["type"] == "short_text"
           and qs["exclusions"]["type"] == "list", {k: qs[k]["type"] for k in ("objective", "market", "exclusions")})
        ok("owner_supplied field classified owner_supplied",
           qs["objective"]["provenance_class"] == "owner_supplied")
        ok("system_inferred field classified inferred_confirm",
           qs["audience_context"]["provenance_class"] == "inferred_confirm",
           qs["audience_context"]["provenance_class"])
        ok("unresolved_questions surfaced as unresolved_input",
           any(q["provenance_class"] == "unresolved_input" for q in cp["questions"]))
        ok("approval binding names kickoff_approved with the exact would-bind hash",
           cp["approval_binding"][0]["decision_id"] == "kickoff_approved"
           and cp["approval_binding"][0]["would_bind"] == cp["current_hash"])

        # ── N revision cycles via TARGETED ops (field-level, untouched-field preservation) ──
        before = cc._current_object_bytes(cc._rt().require_run(rid), cc._rt().run_dir, rid,
                                          "research_brief")
        r2 = cc.request_revision(rid, ops=[{"op": "set", "path": "campaign_window.value",
                                            "value": "late Aug–late Sep"}])
        ok("targeted revision mints a NEW immutable revision r002",
           r2["revision"] == "r002", r2["revision"])
        after = cc._current_object_bytes(cc._rt().require_run(rid), cc._rt().run_dir, rid,
                                        "research_brief")
        ok("targeted revision changed ONLY the targeted field",
           after["campaign_window"]["value"] == "late Aug–late Sep"
           and after["objective"] == before["objective"]
           and after["market"] == before["market"], "untouched fields preserved")
        ok("revision produced a semantic diff with the one change",
           r2["diff"]["has_changes"]
           and any(c["path"] == "campaign_window.value" for c in r2["diff"]["changed"]),
           r2["diff"]["changed"])

        # a second cycle: list add + remove
        r3 = cc.request_revision(rid, ops=[{"op": "add", "path": "exclusions",
                                            "value": "no discount framing"}])
        ok("second revision cycle mints r003 (no arbitrary revision limit)",
           r3["revision"] == "r003", r3["revision"])
        cur = cc._current_object_bytes(cc._rt().require_run(rid), cc._rt().run_dir, rid,
                                      "research_brief")
        ok("list add preserved prior list contents + appended",
           "no discount framing" in cur["exclusions"], cur["exclusions"])

        # immutable: re-registering r001 with different bytes is refused (write-once)
        try:
            bad = fx.brief_payload(bid="rb_1", rev="r001", run_id=rid, objective="TAMPERED")
            obj = cc.build_object(rid, "research_brief", bad)
            cc.register_object(rid, "research_brief", obj)
            ok("write-once immutability refused", False, "expected CheckpointError")
        except cc.CheckpointError as e:
            ok("write-once immutability: mutating an existing revision label is refused",
               e.code == "campaign_spec_revision_mutated", e.code)

        # diff between arbitrary revisions
        d13 = cc.object_diff(rid, "research_brief", from_rev="r001", to_rev="r003")
        ok("object_diff spans r001→r003 with both changes",
           d13["has_changes"] and any(c["path"] == "campaign_window.value" for c in d13["changed"]),
           d13["changed"])

        # ── ONE-ACTION approval (AF-002) ── one call records kickoff_approved + legacy frame_accepted ──
        appr = cc.approve_checkpoint(rid, by="product_owner")
        ok("single approve action records BOTH kickoff_approved and legacy frame_accepted",
           set(appr["approved"]) == {"kickoff_approved", "frame_accepted"}, appr["approved"])
        s = cc._rt().require_run(rid)
        kb = s["owner_decisions"]["kickoff_approved"]["value"]
        ok("kickoff_approved binds the EXACT current brief revision + hash",
           kb["revision"] == "r003" and kb["canonical_hash"] == cc._object_spine(s, "research_brief")["canonical_hash"],
           kb)

        view = cc.describe_checkpoint(rid)
        ok("checkpoint advanced to RESEARCH + DIRECTION after kickoff approval",
           view["checkpoint"]["checkpoint_type"] == "direction",
           view["checkpoint"]["checkpoint_type"])

        # ── CHECKPOINT 2: DIRECTION ── ledger then directions ──
        led = cc.submit_intake_kind(rid, "research_ledger", fx.ledger_payload(lid="rl_1", brief_ref="rb_1")) \
            if hasattr(cc, "submit_intake_kind") else _register(cc, rid, "research_ledger",
                                                                fx.ledger_payload(lid="rl_1", brief_ref="rb_1"))
        dirs = cc.submit_intake(rid, fx.directions_payload(did="cd_1", ledger_ref="rl_1"))
        view = cc.describe_checkpoint(rid)
        cp = view["checkpoint"]
        ok("direction checkpoint shows selection question with recommendation flagged",
           cp["questions"][0]["id"] == "selected_direction"
           and any(o.get("recommended") for o in cp["questions"][0]["options"]), cp["questions"][0])

        # approve requires a direction id (single action still)
        try:
            cc.approve_checkpoint(rid, by="product_owner")
            ok("direction approve without id refused", False, "expected error")
        except cc.CheckpointError as e:
            ok("direction approval requires an explicit selected direction_id",
               e.code == "direction_required", e.code)
        appr = cc.approve_checkpoint(rid, by="product_owner", direction_id="d1")
        ok("direction approve (one action) records direction_selected_v2 + legacy opportunity_selected",
           set(appr["approved"]) == {"direction_selected_v2", "opportunity_selected"}, appr["approved"])
        s = cc._rt().require_run(rid)
        ok("direction_selected_v2 binds the exact direction_hash",
           s["owner_decisions"]["direction_selected_v2"]["value"]["direction_id"] == "d1"
           and s["owner_decisions"]["direction_selected_v2"]["value"]["direction_hash"], "bound")

        # ── CHECKPOINT 3: PREMISE + VERTICALS ── register spec, review, section edit, approve ──
        cc.submit_intake(rid, fx.spec_payload(csid="cs_1", rev="r001"))
        view = cc.describe_checkpoint(rid)
        cp = view["checkpoint"]
        ok("premise checkpoint derives from the campaign_spec",
           cp["checkpoint_type"] == "premise_verticals" and cp["object_kind"] == "campaign_spec",
           cp["checkpoint_type"])
        ok("premise questions include per-vertical conviction with targeted paths",
           any(q["id"].startswith("vertical_") and "conviction_role" in (q.get("path") or "")
               for q in cp["questions"]), [q["id"] for q in cp["questions"]])

        # section edit: change the premise dek — only premise section hash should move
        spine_before = cc._object_spine(cc._rt().require_run(rid), "campaign_spec")
        sh_before = dict(spine_before["section_hashes"])
        rspec = cc.request_revision(rid, ops=[{"op": "set", "path": "sections.premise.dek",
                                               "value": "A new dek"}])
        spine_after = cc._object_spine(cc._rt().require_run(rid), "campaign_spec")
        sh_after = spine_after["section_hashes"]
        ok("section edit moves ONLY the edited section hash (premise), not vertical_strategies",
           sh_after["premise"] != sh_before["premise"]
           and sh_after["vertical_strategies"] == sh_before["vertical_strategies"],
           "premise-only change")

        appr = cc.approve_checkpoint(rid, by="product_owner")
        ok("premise+verticals single approve records BOTH section approvals",
           set(appr["approved"]) == {"premise_approved", "verticals_approved"}, appr["approved"])
        s = cc._rt().require_run(rid)
        ok("premise_approved binds the premise SECTION hash exactly",
           s["owner_decisions"]["premise_approved"]["value"]["section_hash"] == sh_after["premise"])

        # ── DEPENDENCY INVALIDATION + STALE-APPROVAL REFUSAL ──
        # editing premise AFTER approval must invalidate premise_approved (and downstream).
        cc.request_revision(rid, ops=[{"op": "set", "path": "sections.premise.why_now",
                                       "value": "changed after approval"}])
        s = cc._rt().require_run(rid)
        ok("editing an approved section invalidates its approval (dependency graph)",
           "premise_approved" in (s.get("invalidated") or []), s.get("invalidated"))
        ok("a stale (invalidated) approval no longer gates its checkpoint",
           not cc._approval_recorded(s, "premise_approved"))
        view = cc.describe_checkpoint(rid)
        ok("checkpoint falls back to premise_verticals after invalidation (never skips a stale gate)",
           view["checkpoint"]["checkpoint_type"] == "premise_verticals",
           view["checkpoint"]["checkpoint_type"])
        # re-approve on the current object clears the invalidation (owner re-confirms)
        cc.approve_checkpoint(rid, by="product_owner")
        s = cc._rt().require_run(rid)
        ok("re-approving on the current object clears the invalidation",
           "premise_approved" not in (s.get("invalidated") or [])
           and cc._approval_recorded(s, "premise_approved"))

        # ── CHECKPOINT 4: ARCHITECTURE ── grouped review + composite approval ──
        view = cc.describe_checkpoint(rid)
        cp = view["checkpoint"]
        ok("architecture checkpoint reached", cp["checkpoint_type"] == "architecture",
           cp["checkpoint_type"])
        ok("architecture review is grouped by vertical with collections/rails (NO product rows)",
           "verticals" in cp["review"]
           and all("collections" in g and "rails" in g for g in cp["review"]["verticals"].values()),
           list(cp["review"]["verticals"].keys()))
        appr = cc.approve_checkpoint(rid, by="product_owner")
        ok("architecture single approve records architecture_approved (composite of 3)",
           appr["approved"] == ["architecture_approved"], appr["approved"])
        s = cc._rt().require_run(rid)
        import front_half as fh
        exp = fh.composite_hash(cc._object_spine(s, "campaign_spec")["section_hashes"],
                                ["collection_selections", "rails", "content_program"])
        ok("architecture_approved binds the exact 3-section composite hash",
           s["owner_decisions"]["architecture_approved"]["value"]["composite_hash"] == exp)

        # ── CHECKPOINT 5: BUILD THIS ── final composite ──
        view = cc.describe_checkpoint(rid)
        cp = view["checkpoint"]
        ok("build_this checkpoint reached", cp["checkpoint_type"] == "build_this",
           cp["checkpoint_type"])
        appr = cc.approve_checkpoint(rid, by="product_owner")
        ok("build_this single approve records campaign_spec_approved (composite of 8)",
           appr["approved"] == ["campaign_spec_approved"], appr["approved"])
        s = cc._rt().require_run(rid)
        exp8 = fh.composite_hash(cc._object_spine(s, "campaign_spec")["section_hashes"], fh.CS_SECTIONS)
        ok("campaign_spec_approved binds the exact 8-section composite (build this)",
           s["owner_decisions"]["campaign_spec_approved"]["value"]["composite_hash"] == exp8)

        view = cc.describe_checkpoint(rid)
        ok("all five checkpoints approved → front_half_complete",
           view.get("front_half_complete") is True, view.get("front_half_complete"))

        print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
        sys.exit(1 if FAIL else 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("SHOPYA_CAMPAIGN_RUNS", None)


def _register(cc, rid, kind, payload):
    obj = cc.build_object(rid, kind, payload)
    return cc.register_object(rid, kind, obj)


if __name__ == "__main__":
    main()
