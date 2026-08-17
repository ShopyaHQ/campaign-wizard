#!/usr/bin/env python3
"""Structured front-half OBJECT tests (spec 1.8.0) — research_brief, research_ledger,
campaign_directions, campaign_spec: provenance, evidence standards, immutable revisions,
canonical + composite hashing, and the CB-1/rail/content/default structural rules (task §28).

    python3 tests/test_front_half_objects.py

Pure builder-level tests (no validator/run.py subprocess). No pytest dependency.
"""
import copy, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import front_half as fh          # noqa: E402
import front_half_fixture as fx  # noqa: E402

PASS, FAIL = [], []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %s  %s%s" % ("PASS" if cond else "FAIL", name, ("  <- " + detail) if detail and not cond else ""))


def raises(fn, needle=""):
    try:
        fn()
        return False
    except fh.FrontHalfError as e:
        return needle in str(e)


def main():
    print("\n-- research_brief: provenance is first-class --")
    brief = fh.build_research_brief(fx.brief_payload())
    ok("brief stamps a canonical_hash", bool(brief.get("canonical_hash")))
    ok("brief preserves owner vs inferred vs derived provenance",
       brief["objective"]["provenance"] == "owner_supplied"
       and brief["audience_context"]["provenance"] == "system_inferred"
       and brief["territory"]["provenance"] == "derived")
    ok("brief inferred_inputs surfaces inference (not hidden)",
       isinstance(brief["inferred_inputs"], list) and len(brief["inferred_inputs"]) >= 1)
    bad = copy.deepcopy(fx.brief_payload()); bad["objective"] = "plain string, no provenance"
    ok("a material field without {value, provenance} is refused",
       raises(lambda: fh.build_research_brief(bad), "provenance"))
    bad2 = copy.deepcopy(fx.brief_payload()); bad2["market"] = {"value": "US", "provenance": "guessed"}
    ok("an invalid provenance source is refused",
       raises(lambda: fh.build_research_brief(bad2), "provenance"))

    print("\n-- research_brief: canonical hash is semantic, not whitespace --")
    p1 = fx.brief_payload(); p2 = fx.brief_payload()
    p2["assumptions"] = list(p1["assumptions"])   # same content, rebuilt
    ok("identical content -> identical canonical_hash",
       fh.build_research_brief(p1)["canonical_hash"] == fh.build_research_brief(p2)["canonical_hash"])
    p3 = fx.brief_payload(); p3["objective"] = fx._field("a DIFFERENT objective")
    ok("a material change -> a different canonical_hash",
       fh.build_research_brief(p3)["canonical_hash"] != brief["canonical_hash"])

    print("\n-- research_ledger: structured evidence + stable ids + standards --")
    ledger = fh.build_research_ledger(fx.ledger_payload())
    ok("ledger stamps a canonical_hash", bool(ledger.get("canonical_hash")))
    ok("every signal has a stable id + per-signal hash",
       all(s.get("signal_id") and s.get("signal_hash") for s in ledger["signals"]))
    dup = copy.deepcopy(fx.ledger_payload()); dup["signals"][1]["signal_id"] = "s1"
    ok("a duplicate signal_id is refused", raises(lambda: fh.build_research_ledger(dup), "duplicate"))
    unsourced = copy.deepcopy(fx.ledger_payload()); unsourced["signals"][0]["source"] = ""
    ok("an unsourced signal is refused (no unsourced trend claims)",
       raises(lambda: fh.build_research_ledger(unsourced), "unsourced"))
    bench = copy.deepcopy(fx.ledger_payload()); bench["signals"][0]["source_type"] = "golden_benchmark"
    ok("the CLOSED golden benchmark may not supply current market evidence",
       raises(lambda: fh.build_research_ledger(bench), "golden benchmark"))
    badfam = copy.deepcopy(fx.ledger_payload()); badfam["signals"][0]["family"] = "vibes"
    ok("a signal outside the research families is refused",
       raises(lambda: fh.build_research_ledger(badfam), "family"))
    empty = copy.deepcopy(fx.ledger_payload()); empty["signals"] = []
    ok("an empty ledger is refused", raises(lambda: fh.build_research_ledger(empty), "no signals"))

    print("\n-- campaign_directions: 2–4 distinct, evidence-backed, per-direction hash --")
    directions = fh.build_campaign_directions(fx.directions_payload(), ledger=ledger)
    ok("directions each carry a stable id + per-direction hash",
       all(d.get("direction_id") and d.get("direction_hash") for d in directions["directions"]))
    ok("2–4 directions accepted", 2 <= len(directions["directions"]) <= 4)
    one = copy.deepcopy(fx.directions_payload()); one["directions"] = one["directions"][:1]
    ok("fewer than 2 directions refused", raises(lambda: fh.build_campaign_directions(one), "2–4"))
    five = copy.deepcopy(fx.directions_payload())
    five["directions"] = five["directions"] + [fx._dir("d4"), fx._dir("d5")]
    ok("more than 4 directions refused", raises(lambda: fh.build_campaign_directions(five), "2–4"))
    badref = copy.deepcopy(fx.directions_payload())
    badref["directions"][0]["evidence_refs"] = ["s999"]
    ok("an evidence_ref absent from the ledger is refused",
       raises(lambda: fh.build_campaign_directions(badref, ledger=ledger), "absent from the ledger"))
    noref = copy.deepcopy(fx.directions_payload()); noref["directions"][0]["evidence_refs"] = []
    ok("a direction with no evidence_refs is refused",
       raises(lambda: fh.build_campaign_directions(noref), "evidence_refs"))

    print("\n-- campaign_spec: immutable revisions, section + composite hashes --")
    spec = fh.build_campaign_spec_revision(fx.spec_payload())
    ok("spec stamps 8 section hashes", set(spec["section_hashes"].keys()) == set(fh.CS_SECTIONS))
    ok("spec stamps a composite hash", bool(spec.get("composite_hash")))
    ok("composite hash is order-stable over the 8 sections",
       spec["composite_hash"] == fh.composite_hash(spec["section_hashes"], fh.CS_SECTIONS))
    spec_same = fh.build_campaign_spec_revision(fx.spec_payload())
    ok("identical sections -> identical composite hash",
       spec_same["composite_hash"] == spec["composite_hash"])
    # a material change to ONE section changes that section hash + composite, others unchanged.
    changed = copy.deepcopy(fx.spec_payload())
    changed["sections"]["premise"]["dek"] = "a different dek"
    spec2 = fh.build_campaign_spec_revision(changed)
    ok("a premise change re-hashes premise + composite",
       spec2["section_hashes"]["premise"] != spec["section_hashes"]["premise"]
       and spec2["composite_hash"] != spec["composite_hash"])
    ok("an unrelated section keeps its hash after a premise-only change",
       spec2["section_hashes"]["rails"] == spec["section_hashes"]["rails"])
    # an independent content-headline change does NOT move premise's hash (task §19 basis).
    ch2 = copy.deepcopy(fx.spec_payload())
    ch2["sections"]["content_program"]["content"][0]["card_headline"] = "totally new headline"
    spec3 = fh.build_campaign_spec_revision(ch2)
    ok("a content-headline change leaves premise section hash untouched",
       spec3["section_hashes"]["premise"] == spec["section_hashes"]["premise"]
       and spec3["section_hashes"]["content_program"] != spec["section_hashes"]["content_program"])

    print("\n-- campaign_spec: CB-1 / rails / content / default structural rules --")
    # collection: selection != fulfillment
    s = copy.deepcopy(fx.spec_payload())
    s["sections"]["collection_selections"]["selections"][0]["fulfillment_state"] = "satisfied"
    ok("a collection not in not_yet_requested state is refused (selection != fulfillment)",
       raises(lambda: fh.build_campaign_spec_revision(s), "not_yet_requested"))
    # depth floor render_003
    s = copy.deepcopy(fx.spec_payload())
    s["sections"]["collection_selections"]["selections"][0]["requested_depth"] = 49
    ok("requested_depth below the render_003 floor (50) is refused",
       raises(lambda: fh.build_campaign_spec_revision(s), "render_003") or
       raises(lambda: fh.build_campaign_spec_revision(s), ">= 50"))
    # base_1c exactly one source
    s = copy.deepcopy(fx.spec_payload())
    s["sections"]["rails"]["rails"][0]["source_collection_ids"] = ["w.coats", "w.knitwear"]
    ok("a base_1c rail with >1 source is refused",
       raises(lambda: fh.build_campaign_spec_revision(s), "EXACTLY ONE"))
    # story_xc multiple sources
    s = copy.deepcopy(fx.spec_payload())
    s["sections"]["rails"]["rails"][1]["source_collection_ids"] = ["w.coats"]
    ok("a story_xc rail with a single source is refused",
       raises(lambda: fh.build_campaign_spec_revision(s), "MULTIPLE"))
    # no orphan rails
    s = copy.deepcopy(fx.spec_payload())
    s["sections"]["rails"]["rails"][0]["source_collection_ids"] = ["w.notselected"]
    ok("an orphan rail (source not selected) is refused",
       raises(lambda: fh.build_campaign_spec_revision(s), "orphan"))
    # SEO title != card headline
    s = copy.deepcopy(fx.spec_payload())
    s["sections"]["content_program"]["content"][0]["card_headline"] = ""
    ok("content missing a DISTINCT card_headline is refused",
       raises(lambda: fh.build_campaign_spec_revision(s), "DISTINCT"))
    # default refs must resolve
    s = copy.deepcopy(fx.spec_payload())
    s["sections"]["default_composition"]["ordered_slots"][0]["object_id"] = "r_ghost"
    ok("a default slot referencing a non-existent rail is refused",
       raises(lambda: fh.build_campaign_spec_revision(s), "not in this spec"))
    # unequal conviction + zero-collection vertical are VALID (no quota/symmetry)
    ok("an 'absent' vertical + a lead vertical (unequal conviction, zero-collection) is VALID",
       bool(fh.build_campaign_spec_revision(fx.spec_payload()).get("composite_hash")))

    print("\n-- campaign_spec -> architecture adapter (feeds the proven A–G producers) --")
    arch = fh.campaign_spec_to_architecture(spec)
    ok("adapter emits collections/rails/content/default/renderer",
       set(arch) == {"collections", "rails", "content", "default_composition", "renderer_capabilities"})
    ok("adapter carries NO product-fact keys (judgment only)",
       all(not ({"price", "currency", "product_url", "sellable_product_uid"} & set(c))
           for c in arch["collections"]))
    ok("adapter translates base_1c -> base and story_xc -> xc",
       {r["rail_kind"] for r in arch["rails"]} == {"base", "xc"})

    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
