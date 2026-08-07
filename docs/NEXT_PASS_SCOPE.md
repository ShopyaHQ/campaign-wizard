# NEXT PASS SCOPE — deferred and proposed, NOT current process

Destination rules (owner, 2026-08-07): items live here when they are proposed improvements,
unresolved weaknesses, infrastructure enhancements, evidence-pending ideas, or explicit
post-v1 deferrals. Nothing here is promoted into the current process SSOT merely because it
sounds sensible — promotion requires a demonstrated reusable lesson from a real run.

## Deferred infrastructure (from CLAUDE.md, parked 2026-08-06)
- README cleanup (still describes the pre-rebuild model)
- duplicate `status:` key on ABANDONED in workflow_state.schema.yaml
- functional schema-version pinning (currently descriptive; LRN-014)
- archive semantics for old campaign run directories
- replay / supersede / join-existing-campaign mechanics
- additional schemas or workflow expansion not demonstrated necessary

## Signal-ledger enhancements (proposed in learning logs, not applied)
- `retrieval_status` on signals — first-class "source exists, was not read" (LRN-010)
- `collection_context: in_run | carried | owner_supplied` field (LRN-011) — currently handled
  by declaring carried ids in `deviations`, which works
- per-family minimum signal counts / thin-coverage warning (LRN-013)

## Research depth (owner-flagged 2026-08-07)
- broaden evidence classes for the standard scan: retailer merchandising APIs, social/creator
  signals (currently thinnest class — best source this run was 8 months old), first-party
  Shopya behaviour when ghostframe2025 becomes queryable
- volume-bearing search data source (autocomplete gives ordering only)

## Content system (from SHOPYA_CONTENT_CHARTER.proposed, explicitly deferred there)
- rail_subtitle (no frontend field exists)
- product-annotation display verification (API field exists; render path unverified)
- automated brand scoring (rejected: single score hides which layer failed)
- mechanised swap test and syntactic-template detection (rubric first)

## Pending technical validations (charter pending_validations — capability-blocking only)
- s6_window_semantics · collection_item_order_persistence · first_party_event_retrieval ·
  list_viewed_firing_semantics · rail_view_all_destination · explore_default_set_normalization ·
  sanity_window_production_path · include_ids_order_survives

## Guided wizard experience (VALIDATED next-pass requirement, 2026-08-07)
Observed in the acceptance run: the process works, but the interface is not yet a usable
wizard — the owner receives research, implementation detail, QA, process updates and several
decisions in one block, requiring expert interpretation to navigate.
Target: preserve the intelligence and auditability underneath; expose a short guided decision
flow by default. A normal checkpoint leads with (1) what we found, 1-3 points; (2) the
recommendation in plain language; (3) ONE primary decision; (4) 2-4 concrete choices with a
recommended default; (5) one sentence on what happens next; (6) reasoning/research/QA as
optional detail, never default wall-of-text. Guided steps mirror the demonstrated process:
kickoff → research result → direction → premise → architecture → inventory reality → naming/
copy → assembly → final review → CSV. Not permission to build UI yet.
Evidence from the acceptance run (2026-08-07): the final-acceptance step worked as a compact
card — campaign line, collections/rails table with verified counts, 2-3 material caveats,
single Publish / Change decision, evidence kept under the hood. Owner accepted on that card
alone. This card is the demonstrated shape of the wizard's final-review step. (No new SSOT
rule — the checkpoint-presentation rule in CLAUDE.md already covers the operating principle.)

## Verification (owner-directed 2026-08-07)
- Formalize the agent-first verification rule (now in CLAUDE.md) as an `approved_rule` claim in
  the campaign charter at its next revision. Mid-run charter version changes are blocked by
  design (`charter_version_changed_without_migration`), so the claim waits for the bump.
- UX observation demonstrated on the Almost Fall run: human fallback verification should
  eventually be presented as a compact guided task — one unresolved product at a time, yes/no
  availability, automatic backup progression — not a manual research checklist.

## Engine/wizard boundary (owner architectural ruling, 2026-08-07 acceptance review)
Governing boundary (now recorded in CLAUDE.md): CollectionCuration answers "what products
exist and what is true about them right now?" — the wizard answers "which of those products
should this campaign use, where, and why?" The Almost Fall run proved the wizard workflow but
verification was accomplished by temporarily reaching across this boundary; the next version
formalizes the handoff rather than duplicating or migrating the capability. Three changes:
1. Engine-owned verification interface. The wizard requests "verify these N candidates";
   the engine performs/searches/records the observations and returns results. The wizard
   never appends to product_results_log.jsonl and never needs to know how retailers were probed.
2. Truthful provenance. Extend the engine's fetched_via enum to the verification methods
   actually used: pdp_fetch is currently a contract violation (~20 rows outside the enum),
   and human verification recorded as browser_agent is an incorrect label — add a
   human_verification value (and any other real methods) instead of squeezing.
3. Separate canonical identity from evidence location. product_url must mean the product's
   canonical PDP; a separate verification_url / evidence reference captures where availability
   was confirmed (a Macy's category page proves a brooch is for sale but is not its PDP).
   In the Almost Fall CSV ~10 rows carry a category/retailer URL in product_url — usable by
   a human, not a clean production contract.
4. Builder hydration (confirmed leak, inspected 2026-08-07): build_csv.py takes price,
   currency, product_url, product_name and brand from wizard-authored curated.json; only
   stock_status and observed_at are joined from the engine at build time. Next pass:
   curated.json carries only campaign fields (product reference, collection, rail, editorial
   rank, pin intent, annotation) and the builder hydrates current product facts from the
   engine's latest observation.

## DONE 2026-08-07 (owner accelerated: "make changes now") — directory restructure
Convention is LOCKED (docs/NAMING_CONVENTIONS.md); owner moved implementation ahead of
go-live; executed and validated same day. Work: campaigns/<campaign_id>/runs/<run_id>/ layout; campaigns/_drafts/ for unnamed
kickoffs with controlled promotion at campaign_id lock; artifact registration paths relative
to run root; campaign.yaml metadata file; migrate the four existing runs; update run.py
run_dir derivation and validator sibling scan; record executed_build in execution tracking.

## Charter revision queue addition (2026-08-07, inventory depth ruling)
- Split render_002 into rail-readiness / collection-readiness / execution-readiness claims and
  add the inventory depth model (floor 2x rail capacity, launch target >50) at the next
  campaign-charter revision (mid-run version changes blocked). Operating rules live now in
  content charter 0.7.0-proposed §10.
- Live sellout rebuild threshold: define after observing real live behavior.

## Ingest process (owner ruling 2026-08-07)
Current truth: products enter Shopya by owner manual add; duplicates auto-identified. Building
a real ingest process is deferred — when it lands, fold in the engine-owned catalog capture
(stopped mid-operation 2026-08-07) and the catalog->feed->upsert pipeline decision.

## Expanded Phase 1 surface requirement (owner, 2026-08-07) — implementation items
- Multi-surface campaigns: default Explore + six filtered views (>=3 product rails each) +
  editorial/content rails. Gated on: explore_002 cap revision (4 -> per-surface model),
  explore default-set normalization (explore_001 prerequisite), sub_group vocabulary decision
  (implemented enum has wellness_health; requirement names Outdoors & Sports — frontend change
  or mapping ruling needed), S5 editorial inject cap (2) vs content-rail ambitions.
- Master execution CSV extension: target_surface/sub_group per rail + rail sort_order;
  collection-reuse-across-rails ruling (current builder enforces 1 collection : 1 rail).
- Content system: ideation stage + per-idea package (title, thesis, why-now, surface, takeaway,
  related rails, format, sources, generation prompt, headline/dek options, cover brief,
  handoff status) — build AFTER frontend/post-schema truth established.

## PHASE 2 — DEFERRED NEXT-ROUND SCOPE (owner, 2026-08-07; recorded, NOT implemented)
Generate channel-specific social-media visual prompts/assets from approved campaign rails and
products, preserving product truth and campaign visual direction.

## ELEVATED (owner, 2026-08-07): PDP resolution tool — now an ACTIVE separate workstream
The product_url/verification_url separation and engine-owned verification interface items above
are no longer next-pass: spun out into a dedicated CollectionCuration session (see
shopya-collection-curation/SCRAPER_TOOL_KICKOFF.md). Almost Fall paused pending b004.
