# NEXT PASS SCOPE — deferred and proposed, NOT current process

Destination rules (owner, 2026-08-07): items live here when they are proposed improvements,
unresolved weaknesses, infrastructure enhancements, evidence-pending ideas, or explicit
post-v1 deferrals. Nothing here is promoted into the current process SSOT merely because it
sounds sensible — promotion requires a demonstrated reusable lesson from a real run.

## CLOSED by the 2026-08-09 system-hardening pass (no longer open)
These were implemented and TESTED; they are not backlog anymore. Kept here as a closure record.
- Version semantics — Model B (current-canon + explicit migration): validator loads current canon,
  a stale-pinned run is refused (run_canon_version_mismatch) until `run.py migrate` records the
  bump; provenance kept in history. (was "functional schema-version pinning")
- VALIDATED bound to a real production build (run.py validate-execution; validation_binds_products_csv;
  validation_attempts no longer settable).
- Stale/legacy builds cannot satisfy VALIDATED (production-only attempt binding).
- Owner-decision ledger is BINARY (provisional_recommendation | owner_confirmed; governance_003).
- Reopen edges executable through the sanctioned interface (run.py reopen writes `invalidated`).
- Engine-owned canonical sellable-product identity (sellable_product_uid) + floor_eligible; the
  >=50 floor counts distinct sellable parents, so variants/colors/sizes/name-drift cannot inflate it.
- Versioned cross-repo contracts: curation_request_schema.yaml (Wizard->Engine) and
  truth_export_schema.yaml (Engine->Wizard, truth_contract_version).
- verify-live sanctioned LIVE path (verification bound to the executed build; no asserted boolean).
- Removed dead/phantom enforcement (p_downstream_superseded stub; frozen_collection_modified phantom
  check — reclassified below as post-LIVE); wired has_rail_position.

## Deferred infrastructure (from CLAUDE.md, parked 2026-08-06)
- README cleanup (still describes the pre-rebuild model)
- duplicate `status:` key on ABANDONED in workflow_state.schema.yaml
- archive semantics for old campaign run directories
- join-existing-campaign mechanics (replay/supersede now exist)
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

## Content system (from SHOPYA_CONTENT_CHARTER.yaml, explicitly deferred there)
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
- CLOSED 2026-08-10: the inventory depth model is settled as campaign charter render_003
  v0.7.0 — a single >=50 dependable-in_stock-unique-sellable HARD floor (floor and health
  target coincide). The 0.6.0 24-floor / >50-health split was an accidental regression,
  reversed the same day by owner Decision 1 (2026-08-10); the readiness split lives in
  content charter readiness_model. Remaining open item:
- Live sellout rebuild threshold: define after observing real live behavior.

## V2 product-ranking / fallback logic (owner-parked 2026-08-10 — future, NOT current launch)
Once Shopya has meaningful first-party data, extend the v1 selection ladder's Tier 2/3
ranking (content charter product_selection_ladder) with evidence such as: save rate, total
saves, user engagement, back-in-stock interest, restock behavior, durable popularity,
favorites, conversion/usefulness signals where available, category-specific lifecycle
behavior. Potential future content/product programs on those signals: back in stock ·
favorites · classics · enduring best products · popular right now · resurging products.
These are FUTURE ranking/content mechanisms, not claims the current system can make —
never simulated with guessed popularity. v1 uses the three-tier ladder only.

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
are no longer next-pass: spun out into a dedicated CollectionCuration workstream, now the standing
engine doc shopya-collection-curation/PDP_RESOLUTION_PROTOCOL.md (its kickoff doc was folded in and
removed in the 2026-08-11 decontamination). Almost Fall paused pending b004.

## Proposed SSOT updates awaiting owner ruling (moved from PROPOSED_SSOT_UPDATES.md, 2026-08-09)
1. Channel-failure vs thesis-failure classification as a formal rule (owner has applied it in
   practice; formal SSOT wording awaits yes/no).
2. Engine fetch-config guidance: root /products.json returns newest/bundles — hero staples
   need collection-handle endpoints.
3. Proposed-build mode semantics (PROPOSED status, QA-to-warnings, never import-ready).
4. Single-source pin concentration soft cap (the 9/9 East Fork case).
5. Doc-lint: mechanically flag any new top-level doc at validation time (enforces the
   no-new-docs rule in code rather than agent judgment).

## Freeze-integrity enforcement (owner ruling 2026-08-09 — POST-LIVE, deferred)
`frozen_collection_modified` is classified as POST-LIVE operational integrity, NOT part of the
initial LIVE gate (a collection is only modifiable after it is frozen at go-live). The former
check read a phantom field (`modified_since_freeze`, never written) and was removed in the
2026-08-09 hardening pass. Real enforcement requires an engine-side collection-diff: compare
live collection contents against the freeze snapshot's per-collection sha256 and report drift,
which a controlled writer records for the validator to consume (the pattern used by
verify-live / validate-execution). Until that lands, freeze integrity is not machine-enforced;
the refusal string is retained in the schema (status: not_yet_enforced) for when it does.
- problem: a frozen collection could be modified post-LIVE with no automatic detection.
- status: not machine-enforced (phantom check removed); refusal string retained.
- trigger: first real post-LIVE modification need, or a live campaign in operate/review.
- acceptance: an engine collection-diff writer records drift; a modified frozen collection with
  no recorded exception fails frozen_collection_modified; a test proves it fires and that an
  approved exception clears it.

## Owner authentication (deferred to Wizard UI)
- problem: `run.py record-decision --by product_owner` is free text — the status gate makes
  misuse visible/cross-checked but does NOT authenticate who the owner is. Same for who runs any
  controlled command. This is the only place "an owner decision" rests on honest self-labelling.
- status: prose acknowledges it; NOT claimed as authentication anywhere.
- trigger: the guided Wizard UI (which can carry a real identity/session).
- acceptance: an owner_confirmed decision is bound to an authenticated owner identity, not a CLI
  string; a test proves an unauthenticated caller cannot mint owner_confirmed.

## Cross-collection story rails (desired; technically blocked)
- problem: the current one-collection rail contract cannot express a rail whose pins span
  multiple category collections; these are a desired editorial model.
- status: allowed in the object model, marked 'required — technically blocked' when specced.
- trigger: a backend rail contract that accepts multi-collection membership.
- acceptance: a story rail with pins across >=2 collections validates and renders; the
  execution CSV/manifest carry it without minting a thematic collection.

## Phase 2 — channel-specific social visuals (deferred; recorded not implemented)
- problem: campaigns need channel-specific social prompts/assets from approved rails/products.
- status: recorded, NOT implemented; must preserve product truth (compose/art-direct verified
  imagery, never hallucinate or materially alter products).
- trigger: after the hardened E2E product is settled and imagery truth is available.
- acceptance: prompts/assets are generated from approved campaign rails+verified products with
  provenance; no product fact is invented or altered.

## Copy-QA gap (demonstrated 2026-08-10, Almost Fall r007 -> owner Amendment 2)
The campaign avoid-term lint caught explicit sale/discount vocabulary but MISSED comparative
cheapness/price framing ("cheaper than new" shipped to owner review in rail copy). Next
hardening pass: extend the mechanical avoid-terms/anti-slop layer (content charter T-9 family)
to comparative price framing (cheaper/cheapest-than, "for less", "half the price") and add a
semantic-review checklist item for price-comparison framing. The campaign-pass lint was
trivially corrected in place for this run; the durable rule belongs in the charter QA tiers.
