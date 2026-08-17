#!/usr/bin/env python3
"""front_half_fixture.py — shared builders for structured front-half objects in tests.

At canon >= 1.8.0 every TRANSITIONING run is a vNext run: the augmented front-half states require
the structured objects + hash-bound approvals. Back-half tests that only exercise activation /
execution behavior still need a VALID vNext front half in state so the run is coherent. These
builders produce minimal, canonically-hashed objects + the state-file spine/approvals to inject,
reusing scripts/front_half.py so the hashes match the validator byte-for-byte.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import front_half as fh  # noqa: E402
import yaml  # noqa: E402


def _field(v, prov="owner_supplied"):
    return {"value": v, "provenance": prov}


def brief_payload(bid="rb_fx", rev="r001", run_id="cmp_fx", objective="obj"):
    return {"brief_id": bid, "revision": rev, "campaign_id": None, "run_id": run_id,
            "objective": _field(objective), "desired_behavior": _field("browse+save"),
            "market": _field("US"), "audience_context": _field("style-aware", "system_inferred"),
            "campaign_window": _field("Sep"), "territory": _field("almost-fall", "derived"),
            "exclusions": [], "owner_inputs": ["make it a moment"],
            "inferred_inputs": ["audience skews style-aware"], "assumptions": [],
            "unresolved_questions": ["which verticals lead?"],
            "provenance": {"objective": "owner_supplied"}}


def _sig(sid, fam="cultural"):
    return {"signal_id": sid, "family": fam, "claim": "c-" + sid, "source": "https://x/" + sid,
            "source_type": "editorial", "captured_at": "2026-08-10",
            "market_time_relevance": "current", "confidence": "medium",
            "evidence_strength": "moderate", "supports": [], "contradicts": [],
            "limitations": ["single source"], "provenance": "system_inferred"}


def ledger_payload(lid="rl_fx", rev="r001", brief_ref="rb_fx"):
    return {"ledger_id": lid, "revision": rev, "brief_ref": brief_ref,
            "signals": [_sig("s1", "cultural"), _sig("s2", "commercial"),
                        _sig("s3", "seasonal_temporal")]}


def _dir(did):
    return {"direction_id": did, "title": "t-" + did, "evidence_refs": ["s1", "s2"],
            "shopper_tension": "x", "why_now": "x", "shopya_role": "x", "desired_behavior": "x",
            "campaign_opportunity": "x", "vertical_implications_summary": "x",
            "risks_counterevidence": "x", "confidence": "medium"}


def directions_payload(did="cd_fx", rev="r001", ledger_ref="rl_fx"):
    return {"directions_id": did, "revision": rev, "ledger_ref": ledger_ref,
            "directions": [_dir("d1"), _dir("d2"), _dir("d3")], "recommended_direction_id": "d1"}


def spec_sections(depth=50):
    return {
        "premise": {"campaign_name": "Fx", "dek": "d", "central_tension": "x",
                    "point_of_view": "x", "why_now": "x", "shopya_role": "x",
                    "desired_behavior": "x", "exclusions": [], "voice_summary": "restrained",
                    "evidence_refs": ["d1"]},
        "vertical_strategies": {"verticals": [
            {"vertical_id": "fashion", "conviction_role": "lead", "interpretation": "x",
             "shopper_job": "x", "why_it_belongs": "x", "distinct_mechanism": "x",
             "evidence_refs": ["s1"], "risks_limits": "x", "content_role": "x",
             "collection_role": "lead", "default_role": "hero"},
            {"vertical_id": "tech", "conviction_role": "absent", "interpretation": "n/a",
             "shopper_job": "n/a", "why_it_belongs": "n/a", "distinct_mechanism": "n/a",
             "evidence_refs": [], "risks_limits": "n/a", "content_role": "none",
             "collection_role": "none", "default_role": "none"}]},
        "collection_selections": {"selections": [
            {"category_id": "w.coats", "display_name": "Coats", "vertical": "fashion",
             "campaign_role": "hero", "campaign_fit_rationale": "core",
             "distinct_shopper_product_job": "outerwear",
             "durable_infrastructure_consideration": "reusable", "evidence_refs": ["s1"],
             "requested_depth": depth, "charter_rule_ref": "render_003",
             "fulfillment_state": "not_yet_requested"},
            {"category_id": "w.knitwear", "display_name": "Knitwear", "vertical": "fashion",
             "campaign_role": "support", "campaign_fit_rationale": "layering",
             "distinct_shopper_product_job": "mid layers",
             "durable_infrastructure_consideration": "reusable", "evidence_refs": ["s2"],
             "requested_depth": depth, "charter_rule_ref": "render_003",
             "fulfillment_state": "not_yet_requested"}]},
        "rails": {"rails": [
            {"rail_id": "r_coats", "rail_type": "base_1c", "title": "The Coats", "hook_dek": "x",
             "source_collection_ids": ["w.coats"], "vertical_surface": "fashion",
             "editorial_job": "anchor", "placement_role": "top",
             "renderer_capability": "supported", "fallback_ref": None, "status": "intended"},
            {"rail_id": "r_layers", "rail_type": "story_xc", "title": "Layer Up", "hook_dek": "x",
             "source_collection_ids": ["w.coats", "w.knitwear"], "vertical_surface": "fashion",
             "editorial_job": "a layering story", "placement_role": "mid",
             "renderer_capability": "xc_rails_unsupported", "fallback_ref": None,
             "status": "intended"}]},
        "content_program": {"content": [
            {"content_id": "c1", "target_query": "how to layer", "evidence_refs": ["s1"],
             "search_intent": "informational", "seo_title": "How to Layer for Almost-Fall",
             "card_headline": "Master the in-between", "premise": "x", "outline_brief": "x",
             "linked_collection_ids": ["w.coats"], "linked_rail_ids": ["r_coats"],
             "placement": "explore", "priority": 1, "status": "to_produce"}]},
        "naming_voice": {"campaign_name": "Fx", "dek": "d",
                         "voice_principles": ["concrete"], "positive_examples": ["x"],
                         "negative_patterns": ["generic abstraction"],
                         "collection_naming_constraints": "x", "rail_voice_constraints": "x",
                         "content_voice_constraints": "x"},
        "default_composition": {"ordered_slots": [
            {"slot_id": "s1", "object_type": "base_rail", "object_id": "r_coats",
             "rationale": "anchor", "fallback_ref": None},
            {"slot_id": "s2", "object_type": "content", "object_id": "c1", "rationale": "teach",
             "fallback_ref": None}]},
        "seam_intent": {"collection_rail_relationships": {"w.coats": ["r_coats"]},
                        "rail_content_relationships": {"r_coats": ["c1"]},
                        "default_bindings": ["s1", "s2"],
                        "renderer_capability_notes": "xc unsupported",
                        "fallback_intent": "base only", "production_human_notes": "coats first"},
    }


def spec_payload(csid="cs_fx", rev="r001", parent=None, depth=50):
    return {"campaign_spec_id": csid, "revision": rev, "parent_revision": parent,
            "selected_direction_ref": {"directions_id": "cd_fx", "revision": "r001",
                                       "direction_id": "d1"},
            "sections": spec_sections(depth=depth)}


def write_object(tmpdir, kind, obj):
    """Write a built object to disk and return (path, sha256, spine)."""
    import hashlib
    path = os.path.join(tmpdir, "%s.%s.yaml" % (kind, obj["revision"]))
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(obj, f, sort_keys=False, allow_unicode=True)
    sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
    spine = fh.spine_for_object(obj, kind)
    spine["revisions"] = [{("campaign_spec_id" if kind == "campaign_spec" else "object_id"):
                           spine["object_id"], "revision": obj["revision"],
                           "canonical_hash": obj["canonical_hash"],
                           **({"composite_hash": obj["composite_hash"]} if kind == "campaign_spec" else {})}]
    return path, sha, spine


def inject_full_front_half(state, tmpdir, run_id="cmp_fx", depth=50):
    """Register all four structured objects + record all five hash-bound approvals + the direction
    selection into a state dict, so a canon-1.8.0 run is a VALID vNext run through SEAM6_READY. Adds
    to state['artifacts'], state['structured_objects'], state['owner_decisions']. Returns state."""
    arts = state.setdefault("artifacts", {})
    so = state.setdefault("structured_objects", {})
    od = state.setdefault("owner_decisions", {})

    brief = fh.build_research_brief(brief_payload(run_id=run_id))
    ledger = fh.build_research_ledger(ledger_payload())
    directions = fh.build_campaign_directions(directions_payload(), ledger=ledger)
    spec = fh.build_campaign_spec_revision(spec_payload(depth=depth))

    for kind, obj in (("research_brief", brief), ("research_ledger", ledger),
                      ("campaign_directions", directions), ("campaign_spec", spec)):
        path, sha, spine = write_object(tmpdir, kind, obj)
        arts[kind] = {"path": path, "sha256": sha, "status": "current"}
        so[kind] = spine

    def confirmed(value):
        return {"status": "owner_confirmed", "decided": True, "decided_by": "product_owner",
                "decided_at": "t", "value": value}

    bspine = so["research_brief"]
    od["kickoff_approved"] = confirmed({"object_id": bspine["object_id"],
                                        "revision": bspine["revision"],
                                        "canonical_hash": bspine["canonical_hash"]})
    dmatch = next(d for d in directions["directions"] if d["direction_id"] == "d1")
    od["direction_selected_v2"] = confirmed({"directions_id": directions["directions_id"],
                                             "revision": directions["revision"],
                                             "direction_id": "d1",
                                             "direction_hash": dmatch["direction_hash"]})
    sspine = so["campaign_spec"]
    sh = sspine["section_hashes"]
    od["premise_approved"] = confirmed({"object_id": sspine["object_id"],
                                        "revision": sspine["revision"], "section": "premise",
                                        "section_hash": sh["premise"]})
    od["verticals_approved"] = confirmed({"object_id": sspine["object_id"],
                                          "revision": sspine["revision"],
                                          "section": "vertical_strategies",
                                          "section_hash": sh["vertical_strategies"]})
    arch_sections = ["collection_selections", "rails", "content_program"]
    od["architecture_approved"] = confirmed({"object_id": sspine["object_id"],
                                             "revision": sspine["revision"],
                                             "composite_hash": fh.composite_hash(sh, arch_sections)})
    od["campaign_spec_approved"] = confirmed({"object_id": sspine["object_id"],
                                              "revision": sspine["revision"],
                                              "composite_hash": fh.composite_hash(sh, fh.CS_SECTIONS)})
    return state
