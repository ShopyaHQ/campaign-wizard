# END-TO-END CAMPAIGN PROCESS — wizard + CollectionCuration (proposed revision, 2026-08-09)
# Incorporates: category-constrained 6/12 gendered collections · >=50 hard floor · 200+ brand
# roster · rails as first-class · SEO content into Sanity S5 · seams contract & six-stage
# framework · engine truth pipeline · v2 builder · naming conventions · review-book r-series.
# STATUS: APPROVED IN DIRECTION 2026-08-09 with 12 structural clarifications applied below.

## Standing boundary (constant across every phase)
ENGINE (CollectionCuration) owns product truth: brand roster + scrape-method log, discovery,
PDP gate, single write path (product_truth.py), identity repair, availability, prices,
provenance, truth export, worklists, human-residual checklists.
WIZARD owns campaign judgment: premise, interpretations, collection/rail/content architecture,
naming/copy, pins, Default composition, execution CSV (as pure consumer of engine truth),
handoff briefs, state machine, decision ledger.
Wizard never authors product facts. Engine never makes campaign judgments.

## PHASE 0 — FOUNDATIONS (maintained, not per-campaign)
Engine deliverables: 200+ brand roster (on-trend Gen Z/millennial, all six verticals, curated
like a world-class mall floorplan) in brand_fetch_config — per brand: URL, platform, working
scrape method, attempt history, PDP pattern; truth pipeline operational.
Wizard deliverables: charters/schemas/naming/SSOT current; seams contract pinned in docs.
REQUIREMENT: no campaign sources from a brand absent from the roster — using a new brand
CREATES its roster entry (method learned, attempts logged) as part of the work.
MILESTONE M0: FOUNDATIONS_READY.

## PHASE 1 — KICKOFF & DEFINE  (framework stage 1; owner gate)
/new-campaign mints run in _drafts. Deliverables: occasion + window + DELIVERY PATH declared
(evergreen | manual-timed | registry | tagged); one-line idea; audience; surfaces + vertical
territories; avoid_terms; campaign id <slug>-<year> derived, owner-confirmed, then immutable
-> promote to campaigns/<campaign_id>/runs/<run_id>.
HARD GATES: no campaign id -> no writes; no avoid_terms -> no lint basis.
MILESTONE M1: CONCEPT LOCKED.

## PHASE 2 — RESEARCH & PREMISE  (owner gate)
Deliverables: fresh trend research + SEO/KEYWORD research per vertical (rising queries, search
intent, seasonal query patterns — the content slate's evidence base is born HERE, not after
merchandising); premise workshop; owner-worded premise.
MILESTONE M2: PREMISE APPROVED.

## PHASE 3 — SEAM LEDGER & SURFACE SNAPSHOT  (framework stage 2; owner gate)
Deliverables: live catalog probe (existing feeds, sort_orders, sub_groups); seam ledger
instantiated (S1-S5 handoff scope, S6 + collections in scope, outfit-canvas noted); delivery
path per planned rail slotted against the snapshot.
MILESTONE M3: SCOPE AGREED.

## PHASE 4 — INTERPRETATIONS + THREE-LAYER CONCEPTS  (framework stage 3; owner gate)
Per vertical, IN PARALLEL from the same evidence-backed interpretation — three inseparable
layers (a collection without its rail scope and content slate is an INCOMPLETE deliverable):
  a) COLLECTION MAP — 6 category-constrained collections (one category/sub-category each;
     x2 men/women where the category obviously genders -> 12; thesis, shopper job, category
     bounds, brand seeds from roster, inclusion/exclusion logic);
  b) RAIL SCOPE — every collection's rail name(s) + hooks + supporting copy, display-grade
     verbatim titles (§4 standard), cross-collection STORY RAILS (texture/color/price
     editorial mixes live here, not as collections), per-vertical collections-rail;
  c) SEO CONTENT SLATE — keyword-grounded: content types chosen for rankability per query
     class, search-shaped clickable titles (title = the query, multiple options), premise +
     full outline per piece, exact product/collection link plan, Sanity S5 target.
Plus: cross-vertical reuse register; Default composition placeholder.
MILESTONE M4: SPEC APPROVED (ONE combined owner review: collections + rails + content).
HARD GATE: no approved spec -> no curation.

## PHASE 5 — CURATION & INVENTORY REALITY  (framework stage 4; engine-owned; owner gate)
HANDOFF wizard->engine: curation brief per collection (category bounds, brand seeds,
avoid_terms, targets: 12 pins + >=50 dependable in_stock unique body).
Engine work: mine existing truth FIRST (reuse report: pins / memberships / uniques counted
separately); targeted sourcing through roster channels; ALL writes via product_truth.py
behind the PDP gate; identity repair; every attempt updates the roster method log; human
fallback = ONE batched residual checklist, never a stop.
HANDOFF engine->wizard: regenerated exports/current_truth.jsonl + per-collection depth report
(dependable in-stock vs >=50 HARD floor; low-stock separate, never counted; natural ceiling
+ channel-failure vs thesis-failure classification).
MILESTONE M5: INVENTORY REALITY ACCEPTED (owner: accept / trim / rescope per collection).

## PHASE 6 — NAMING, COPY & PROMPT-READY CONTENT  (owner gate)
Deliverables: collection names/descriptions; rail titles (render verbatim — display-grade);
product annotations; anti-slop QA (mechanical AND semantic) + avoid_terms lint; approved
content slate -> PROMPT-READY packages with placement-map bindings to concrete verified
products; spotlight picks.
MILESTONE M6: NAMING & CONTENT LOCKED.

## PHASE 7 — ASSEMBLY & DEFAULT COMPOSITION  (owner gate via review book)
Deliverables: judgment file (curated.json — product_uid + placement judgment ONLY); 12 pins
per rail in order; live bodies (>=50 in_stock unique); Default/All composed deliberately (lead rails, probed
global sort_orders, campaign collections-rail, OUTFIT-CANVAS source collection chosen — first
collections feed wins placement, use it deliberately; campaign-wide vs vertical-only content);
REVIEW BOOK cut as rNNN (immutable round) -> owner line-by-line review.
MILESTONE M7: ASSEMBLY ACCEPTED (review book marks returned).

## PHASE 8 — EXECUTION PACKAGE  (framework stage 5; validator-gated)
Engine: truth re-export; launch freshness (every pin current-cycle; low-stock pins recheck
again at import). Wizard v2 builder: master execution CSV bNNN + immutable manifest;
S6 ADMIN SPEC (per feed: slug, verbatim name, entity, sub_group, unique probed sort_order,
delivery path) — output is a spec a human executes until admin write access exists;
SANITY HANDOFF BRIEFS for every ❌ seam (S1 hero package, S2/S3 art, S5 posts = the content
pieces with campaign tag, placement, cover briefs); collections-rail manifest.
MILESTONE M8: EXECUTION PACKAGE VALIDATED (state validator + build QA PASS; wizard stops at
prompt_ready/spec — never claims authored, imported, or live).

## PHASE 9 — ACCEPTANCE & GO-LIVE  (framework stage 6; owner + human execution)
Acceptance card -> owner PUBLISH. Human executes: probe_feeds (live order), admin import
(products, collections, feeds per S6 spec), Sanity authoring from briefs, S1 package window
(code = activation authority). Owner verifies live page post-cache (~10 min).
Wizard records: executed_build, verification, collection freeze snapshot -> LIVE.
MILESTONE M9: LIVE.

## PHASE 10 — OPERATE & REVIEW
Availability drift -> immutable bNNN rebuilds; engine weekly re-observe refreshes truth;
sellout handling per freeze/exception rules; measurement + review artifacts close the run
-> REVIEWED (terminal, versions unpin).
MILESTONE M10: REVIEWED.

## Requirements summary (the non-negotiables, one place)
6 collections/vertical (12 where gendered) · every collection category-constrained ·
>=50 dependable in-stock unique HARD floor, 12 pins, low-stock reported separately, never counted ·
no padding, natural ceilings reported · rails + SEO content mandatory with every collection ·
200+ brand roster, every brand method-logged in engine · all product facts engine-only ·
PDP gate absolute · immutable b/r series + controlled asset vocabulary · decision ledger for
every owner gate · avoid_terms lint everywhere · probe before every sort_order · delivery
path declared before any rail plan · handoff briefs for every seam the wizard cannot execute.

## STRUCTURAL CLARIFICATIONS (owner, 2026-08-09 — these win over any conflicting line above)
1. THREE-OBJECT MODEL (locked):
   CATEGORY COLLECTION = durable taxonomy shelf: exactly one category/subcategory; gendered
   only when the category/shopper experience meaningfully genders; >=50 dependable in_stock
   UNIQUE products (variants and duplicate identities never inflate; low-stock separate,
   never satisfies); no texture/color/mood/campaign mixes; reusable across campaigns.
   CAMPAIGN RAIL = campaign-specific editorial merchandising: display-grade name/copy; 12
   pins; hook may be trend/color/texture/behavior/price/use-case; pins resolve to valid
   category-collection membership; rail name is NOT an intrinsic property of the collection.
   CONTENT PIECE = search/editorial acquisition object: demonstrated query intent; adds what
   rails cannot; links into real collections/rails/products; S5/Sanity handoff.
   Collections own taxonomy. Rails own editorial mixing. Cross-collection story rails that
   the one-collection rail contract cannot express are specced and marked
   'required — technically blocked by current one-collection rail contract' — NEVER worked
   around with thematic collections.
2. GENDER: no mirrored pairs. Fashion = minimum 6 relevant women's + 6 relevant men's
   categories chosen independently on strength. Other verticals gender only where taxonomy,
   assortment and shopper behavior genuinely justify (outdoor apparel may; gear generally
   not; beauty/grooming never mechanically duplicated; fragrance/grooming segmentation
   follows actual category/search behavior). Gendering decisions reported explicitly.
3. FLOOR: '>=50 dependable in_stock unique products per launched category collection' is the
   only sanctioned wording. Cannot support 50 honestly -> report category-scope failure and
   propose the nearest defensible parent category; never off-thesis fill.
4. SOURCE / MERCHANT ROSTER (renamed from brand roster; engine file name may persist for
   compatibility): brand DTC + multi-brand retailers + department stores + accepted
   marketplaces. Per profile: identity, type, URL, vertical/category coverage, geography,
   platform, PDP patterns, working fetch method, attempt/failure history, last success,
   catalog-capture capability. 200+ is a maintained GLOBAL foundation, not per-campaign
   query load. Coverage reported by vertical/category AND price tier — raw count is not
   evidence. Any new source used creates/updates its profile.
5. RAIL SCOPE: every collection SELECTED INTO A CAMPAIGN must have its campaign rail scope
   defined before the collection deliverable is complete. One durable collection supports
   different campaign rails over time.
6. SEO STANDARD: titles tightly match target query and intent, in natural search language,
   click value immediately clear — not robotic exact-match, not affiliate filler. Per
   opportunity: target query, related cluster, intent, source/evidence, seasonal/rising
   signal where available, recommended type, multiple titles. NEVER invent volume/difficulty/
   growth numbers absent from sources.
7. CONTENT LINKING TIMING: Phase 4 = link INTENT (target collection/category, target rail,
   product types/examples, role of links). Post-Phase-5 = bind to exact launched collections,
   rails, verified products, canonical URLs. Generation prompts receive concrete bindings
   only after product truth exists.
8. GATES REWORDED: no campaign-scoped downstream/execution writes until the campaign id is
   owner-confirmed (draft-run state may exist under _drafts). Campaign-specific content
   generation cannot proceed until campaign avoid_terms is confirmed; global Shopya voice/
   anti-slop rules always apply.
9. SCALE REPORTING always distinguishes: category collections · collection memberships ·
   rail-pin memberships · unique products · sources/merchants · brands represented.
   N collections x 50 is never described as N*50 unique products.
10. ALMOST FALL FASHION MIGRATION: prototype preserved as historical approved artifacts;
    expanded execution restructures onto category collections. First Coats of Fall maps
    ~cleanly to a category collection; Suede, Sheer & Denim and Fall Accents survive as
    campaign rail/story concepts (cross-collection; blocked-marked), not durable collections.
11. BEAUTY/GROOMING: no pre-decided gender split; propose the six strongest categories on
    taxonomy/search/assortment/behavior; ambiguous segmentation goes to restructure review.
12. NEXT DELIVERABLE: restructured three-layer vertical map + source roster plan; NO sourcing
    until reviewed.

## PROCESS CORRECTIONS (owner, 2026-08-09, round 2)
Phase 4 content = LINK INTENT only (intended collection/category, intended rail, intended
product role). Exact product links bind only after curation.
Phase 5: CollectionCuration supplies >=50 qualifying product truth per category collection.
THE ENGINE DOES NOT CHOOSE CAMPAIGN PINS. The wizard selects the 12 pins later from approved
rail/editorial logic.
FLOOR FAILURE PROTOCOL: a canonical category that cannot clear >=50 is never silently
widened. Report: achieved depth · reason · nearest defensible parent-category alternative ·
impact on rail/content architecture. Parent-category replacement REQUIRES OWNER APPROVAL.
RAIL FIELDS (locked vocabulary): rail_type base|story · collection_scope 1C|XC ·
execution_status executable_now|technically_blocked · activation_priority lead|supporting|
optional. Every selected collection has >=1 base 1C rail spec; scoped rails and activated
rails are not automatically the same thing.
QUERY EVIDENCE CLASSES: verified | directional | candidate_unverified — with query, source,
date, intent, seasonality where available. Volume/difficulty never invented.
SEO FIELDS: target_query, seo_title, content_card_headline are separate objects.
WORKING MERCHANT: defined by demonstrated ability to satisfy the engine's product-truth/PDP
gate — never by method label alone. Unique-merchant count is the 200 metric; a merchant may
satisfy multiple coverage quotas but counts once. Brand identity is separate from
merchant/source identity.
BEAUTY: unified by default; Men's Grooming remains a later candidate on evidence only.

## CAMPAIGN OUTPUT REQUIREMENT (folded from PHASE1_CAMPAIGN_OUTPUT_REQUIREMENT.md, 2026-08-09)
A completed campaign = FOUR parallel outputs across Default + the surfaced verticals:
STRATEGY (premise + vertical interpretations) · MERCHANDISING (selected category collections
from docs/CATEGORY_TAXONOMY.md — >=6 selections per surfaced vertical; 12 pins; >=50
dependable in_stock unique floor; rails per the three-object model) · EDITORIAL/CONTENT
(>=1 candidate opportunity per selected collection or explicit no-opportunity finding;
content floor scales with collections — one paired concept per launched collection; 3-5
priority pieces per vertical; wizard stops at prompt_ready, never claims authored/published;
placement bindings required before a prompt is complete: rail placement + collection(s) +
concrete verified products, bound post-curation) · EXECUTION (master CSV via v2 builder,
manifests, S6 admin spec, Sanity handoff briefs incl. S5 content posts, collections-rail
manifest). Default/All composition is a deliberate late editorial step (lead rails, global
order, category representation, campaign-wide vs vertical-only content, editorial balance)
— never automatic aggregation, and not a seventh vertical.
PHASE 2 (deferred, recorded not implemented): channel-specific social visual prompts/assets
from approved rails/products preserving product truth — may compose/art-direct verified
imagery, never hallucinate or materially alter products.

## OWNER APPROVAL MODEL (owner ruling 2026-08-09 — AUTHORITATIVE; charter governance_003)
The owner is NOT asked to review or approve every final product, article binding or execution
row. The process is checkpoint-driven so material campaign judgments are approved BEFORE
expensive fulfillment. Owner approval is progressive across SIX gates:
  1. kickoff/frame · 2. campaign premise · 3. vertical interpretations ·
  4. collection + rail + content architecture · 5. naming/voice/content direction ·
  6. FINAL CAMPAIGN SPECIFICATION.
The final campaign-spec approval is a CONCISE review — selected durable category collections;
category boundaries; rail concepts/names/hooks; SEO/content keywords + opportunities; article
concepts/title examples; representative ideal products/brands; range/price/brand expectations;
important exclusions; Default/surface composition; all other intended campaign/seam
deliverables. It is NOT a line-by-line review of the 50+ products per collection. Once the
owner approves this specification, CAMPAIGN JUDGMENT IS LOCKED.

FULFILLMENT AFTER APPROVAL. CollectionCuration then fulfils the approved product specification:
mine existing product truth; source/scrape as needed; PDP-verify; produce >=50 qualifying
in_stock unique products per approved category collection; maintain product truth/provenance.
The engine makes NO campaign judgments. The wizard then consumes engine output and: selects/
orders rail pins under the already-approved rail spec; binds verified products to the approved
content/linking plan; produces the master execution CSV; produces seam/content handoffs;
validates compliance. NORMAL COMPLIANT FULFILLMENT DOES NOT CREATE A NEW OWNER-APPROVAL
REQUIREMENT. Escalate to the owner ONLY for a MATERIAL EXCEPTION: collection cannot reach 50;
category scope must change; an approved rail cannot be fulfilled; price/brand/range substantially
misses the approved spec; product reality invalidates an approved content concept; a required
seam is technically impossible; any change that materially alters what the owner approved.

DECISION-LEDGER SEMANTICS (enforced: schema owner_decisions.status + validator). The ledger is
BINARY — provisional_recommendation | owner_confirmed. decided_by: product_owner is possible
ONLY for a genuinely explicit owner confirmation. Engine fulfillment lives in product truth,
validation in validation_attempts, material exceptions in their own artifacts — none are owner
decisions and none are stored in owner_decisions.

## FINAL EXECUTION PACKAGE (for the human who builds the campaign in Shopya)
1. MASTER PRODUCT CSV — all live collection memberships in one file: campaign; target surface;
   collection; product; is_rail_item; rail name (where true); rail position (where true);
   execution product facts HYDRATED FROM CollectionCuration (never wizard-authored).
2. COLLECTION SPEC — names, descriptions, categories, product memberships, cover direction.
3. RAIL/FEED SPEC — surface, display title, copy, collection source(s), pins/order, sort
   order, delivery path.
4. SEAM HANDOFF PACKAGE — S1-S5 specs for anything the wizard cannot execute.
5. CONTENT PRODUCTION PACKAGE — per approved piece: target query; search intent/evidence;
   SEO title options; content-card headline; premise; full outline; research/source
   requirements; linked collection/rail; exact verified product links (after curation);
   production-ready article-generation prompt; cover/content-card brief; placement.
6. HUMAN EXECUTION CHECKLIST — one ordered operational list: create collections; add products;
   create rails/feeds; pin/order; create/publish content; populate seams; implementation;
   verification.

## E2E DEFINITION (authoritative process spine, owner 2026-08-09)
research -> workshop -> premise approval -> vertical strategy approval ->
collection/rail/content architecture approval -> final campaign-spec approval ->
CollectionCuration product fulfillment -> Wizard assembly + validation ->
complete human execution/content handoff package -> human implementation -> live verification.
