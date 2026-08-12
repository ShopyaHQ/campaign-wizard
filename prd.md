# Shopya Campaign System — Product & E2E Operating Model (PRD)

**Status:** CANONICAL — normative product/E2E authority. Promoted 2026-08-11.
**Version:** 1.0.0
**Product:** Shopya Campaign Wizard + CollectionCuration
**Primary entry point:** `/new-campaign`

This is the single normative authority for the product and the end-to-end operating model. It
supersedes the former `docs/E2E_PROCESS.md` process narrative. Hard numeric values are referenced by
stable Campaign Charter rule ID (e.g. `render_003`, `render_002`, `foundation_001`), never restated
here. The Workflow Schema (`schemas/workflow_state.schema.yaml`) remains the machine authority for
states and transitions.

---

# 0. What this document is (authority model)

This PRD is the normative authority for the **product and the end-to-end operating model**. It owns:
product objective; the campaign lifecycle; Campaign Wizard responsibilities; CollectionCuration
responsibilities; human vs LLM responsibilities; the research process; the structured campaign
objects; owner checkpoints; revision semantics; inter-repo handoffs; required deliverables; system
invariants; and the implementation / human / live handoff model.

## What this PRD does NOT own

It is **not** the numeric-policy source of truth. Hard, mutable policy values live in the
**Campaign Charter** (`SHOPYA_CAMPAIGN_CHARTER.yaml`) under stable rule IDs and are referenced here,
never independently redefined:

* collection launch depth → Campaign Charter `render_003`;
* rail capacity / presentation quality → Campaign Charter `render_002`;
* technical rendering minimum → Campaign Charter `render_001`;
* owner-approval model / binary decision ledger → Campaign Charter `governance_003`;
* version + execution-proof integrity → Campaign Charter `governance_001`;
* handoff-not-implemented discipline → Campaign Charter `scope_002`;
* foundation readiness → Campaign Charter `foundation_001` (§7).

No transient value (e.g. a current roster count) belongs in this PRD or the Charter.

It is also **not** the machine state authority. The **Workflow Schema**
(`schemas/workflow_state.schema.yaml`) remains the authority for internal states, transitions,
predicates and refusals. This PRD names product phases; the appendix (§22) maps each phase to the
internal states that implement it.

## Vocabularies (exactly two)

* **Product phases / owner checkpoints** — the owner-facing language used throughout this PRD.
* **Workflow states** — the internal machine language (`NEW … LIVE … REVIEWED`).

The historical `M0/M1/M2…` milestone numbering is retired from normative language and is not used as
a third vocabulary.

## Relationship to `docs/E2E_PROCESS.md`

`docs/E2E_PROCESS.md` has been superseded by this PRD and holds no normative authority; its normative
content is absorbed here. It survives only as a tombstone pointer to this PRD so existing links do not
silently break. It is not a second implementation narrative, and no replacement process document
exists; the implementation mapping lives in §22.

---

# 1. Product objective

`/new-campaign` takes an owner from a fresh campaign request to a complete, human-executable Shopya
campaign package.

The owner participates in a small number of meaningful judgment checkpoints. The owner does not
inspect thousands of product rows and does not need to understand the state machine, scraping
infrastructure, schemas, or validation machinery.

The complete lifecycle:

**structured kickoff → research → campaign directions → premise → vertical strategy →
collection/rail/content architecture → owner-approved final Campaign Spec → CollectionCuration
fulfillment → Wizard assembly of the complete human execution package → production validation →
execution-package approval → human implementation → live verification.**

The mature experience is a **guided Wizard**. Default presentation is concise and decision-oriented;
research evidence, provenance, rejected alternatives, product truth, validator results and
implementation detail remain available under the hood.

The owner makes **taste, strategy and business decisions**. The Wizard handles **research, campaign
intelligence, architecture, orchestration and assembly**. CollectionCuration handles **product
discovery, truth and fulfillment**. The human implementation team executes **collections, rails,
content, seams and go-live**.

---

# 2. Governing responsibility split

Two cooperating repositories with a hard, code-enforced boundary.

## A. `shopya-campaign-wizard` — campaign judgment and orchestration

Answers: **which valid products, collections, rails and content belong in this campaign, where, and
why?**

Owns: structured kickoff; campaign framing; external trend/cultural/search/SEO research; research
synthesis; campaign-direction generation; owner checkpoints; premise; vertical interpretations;
campaign subset selection from the canonical taxonomy; rail concepts and editorial rails;
SEO/content concepts; naming and copy; Default/All composition; campaign-specific
inclusion/exclusion judgment; price/range/brand expectations as campaign judgment; rail pin
selection and ordering after fulfillment; content/product bindings after fulfillment; the state
machine; the decision ledger; validation orchestration; the master execution CSV;
collection/rail/content/seam handoffs; the human execution checklist.

**The Wizard does not author authoritative product truth**: canonical product identity;
authoritative product name; canonical PDP URL; availability; price; currency; images; variants;
merchant-fetch truth; product verification; product freshness. Those belong to CollectionCuration.

## B. `shopya-collection-curation` — product truth and fulfillment

Answers: **what products exist, and what is true about them right now?**

Owns: the global Source/Merchant Roster; merchant/source method discovery; scrape/fetch method
history; product discovery; canonical PDP verification; product identity; `sellable_product_uid`;
variant normalization; stock/availability; price/currency; imagery; provenance; confidence;
freshness; product-truth writes; truth exports; re-verification; human residual verification where
automation genuinely fails.

**CollectionCuration makes no campaign judgment**: premise; editorial fit; rail concepts; rail
names; pin order; article ideas; Default composition; campaign voice; owner judgment. It may report
**factual** fulfillment alternatives (§13) but never recommends what the campaign should do. It
fulfills specifications provided by the Wizard.

## Human vs LLM responsibilities

* **Owner (human):** taste, strategy, business decisions; the checkpoint approvals in §15;
  material-exception decisions; go-live authorization where a release policy requires it.
* **Wizard LLM/agent:** authors campaign judgment into structured objects; runs Wizard research;
  proposes directions/premise/architecture; orchestrates fulfillment; assembles the execution
  package; turns Engine fulfillment facts into campaign judgment (§13). Never authors product truth;
  never records an owner decision as confirmed on the owner's behalf.
* **CollectionCuration LLM/agent + tooling:** discovers and verifies product truth; reports
  fulfillment facts; never makes campaign judgment.
* **Human implementation team:** executes the approved package in Shopya admin, Sanity, and code
  seams; performs go-live.

---

# 3. Research and online-tool ownership

The boundary is the **question being answered**, not whether the web is used.

**Campaign Wizard owns online research** answering *"What is happening and what campaign should
Shopya create?"* — trend/cultural, editorial, retailer-positioning, search/query/autocomplete,
SEO/content-intent, seasonal/context, category-opportunity, and first-party Shopya behavior when
available.

**CollectionCuration owns online work** answering *"Which products exist and what is true about
them?"* — product discovery, merchant crawling, PDP discovery/verification, stock, price, variants,
imagery, canonical product URLs, merchant scrape methods, re-verification.

**Engineering repository inspection** (grep, code inspection, schema audits, implementation
debugging) is an engineering activity, not campaign-runtime research; it may inspect either
repository when maintaining the system.

The Wizard therefore requires a proper **logged research runner** that produces the `research_ledger`
(§6), rather than delegating all internet work to CollectionCuration.

---

# 4. Run mode (run-level execution intent)

Every run carries an immutable **run mode**, set when the run is created:

* `production`
* `diagnostic`

Rules:

* run mode is set at run creation and is **immutable for the life of the run**;
* a normal `/new-campaign` creates a `production` run;
* curation requests **inherit** the run's mode and may not independently self-declare greater
  authority than the run that produced them;
* **migration is an operation, not a run mode** — migrating a run does not change its mode;
* **test fixtures are test harnesses, not persisted run modes**;
* **diagnostic artifacts and proof can never satisfy production fulfillment, validation, approval, or
  live gates** (system invariant, §16).

Diagnostic operation below foundation readiness (§7) is permitted precisely because diagnostic
outputs are structurally incapable of satisfying production gates.

---

# 5. Core campaign object model

## Durable Category Collection

A reusable Shopya taxonomy shelf (e.g. Women's Coats & Trenches; Men's Knitwear; Candles & Home
Fragrance; Headphones; Lip Color; Carry-On Luggage; Trail Footwear).

Rules: references one canonical active taxonomy node; category-shaped, not campaign-themed; reusable
across campaigns; **a launched collection must satisfy the collection-depth floor and its associated
no-padding / no-silent-widening / low-stock-excluded / variant-non-inflation semantics — Campaign
Charter `render_003`**; inability to clear the floor becomes a material exception (§13).
**Collections own taxonomy.**

## Campaign Rail

A campaign-specific merchandising/editorial object (e.g. "Coats you can't wear yet"; "The first dark
lip"; "Safe to buy before September").

Rules: campaign-specific title/hook/copy; **pin capacity per Campaign Charter `render_002`**; draws
only from valid CollectionCuration product truth; may express trend, color, texture, behavior, use
case, styling, price, or cultural story; may conceptually draw across several durable collections.
Cross-collection story rails remain valid desired objects even where the current backend cannot yet
execute them (marked required — technically blocked, never worked around with thematic collections).
**Rails own editorial merchandising.**

## Content Piece

A search/editorial acquisition object (e.g. "Best Fall Trench Coats for 2026"; "Trail Runners vs
Hiking Boots").

Rules: grounded in demonstrated search/query intent; target query, SEO title and content-card
headline remain distinct; adds context/guidance a product rail cannot communicate alone; links into
collections, rails and ultimately exact products; exact product bindings occur only after
CollectionCuration fulfillment; prompt-ready content may be handed to another authoring system
without being falsely described as published. **Content owns search/editorial acquisition.**

## Global platform foundations

**Category Taxonomy.** Every campaign starts from the complete approved Shopya taxonomy registry
(`docs/CATEGORY_TAXONOMY.md`), which is platform infrastructure. The owner does not approve the
complete taxonomy on every campaign; the Wizard selects a campaign-specific subset. The global
`CATEGORY_TAXONOMY` (complete approved registry) and the per-campaign `collection_selections` section
of the Campaign Spec stay separate. Every campaign collection must reference an active global
taxonomy node; a missing category surfaces a `proposed_taxonomy_addition` for separate taxonomy
governance — never silently created campaign-specific taxonomy.

**Source/Merchant Roster.** CollectionCuration maintains a reusable global source foundation. Its
readiness requirement is Campaign Charter `foundation_001` (§7). A campaign uses relevant subsets of
the roster; it does not query the whole roster every campaign.

---

# 6. The structured front half (first-class objects)

The conceiving half of the campaign is modeled as a **small set of first-class structured objects**,
not prose files the agent synchronizes by hand, and not one schema/state per thought.

## `research_brief`

Canonical normalized output of the structured kickoff. Contains: objective; desired shopper behavior;
timing/window; market; surfaces; exclusions; avoid terms; constraints; research questions; evidence
families; freshness requirements; known unknowns; and, per field, whether the value was **supplied by
the owner or inferred by the Wizard**. Inference must never silently become owner fact. The owner
approves the normalized brief (§15).

## `research_ledger`

The structured evidence produced by Wizard research. Each signal records: evidence family;
observation (what was literally seen); source; source date; retrieval date; freshness; interpretation
(separable from observation); confidence; limitations. This is where external research provenance
lives. Fabrication of search volume, keyword difficulty, growth rates, first-party demand, or
availability is prohibited unless directly supported. The `research_ledger` is **evidence supporting
owner decisions; it does not itself normally require owner approval**.

## `campaign_directions`

A structured set of candidate directions. Each direction follows the stable chain **evidence →
shopper tension → why now → Shopya role → desired behavior → campaign opportunity** and is compared
under the stable campaign-direction rubric (evidence strength, timeliness, Shopya fit, ownability,
multi-vertical extensibility, merchandising potential, editorial/content potential, operational
feasibility, exclusion compliance). Scoring may aid comparison but must not manufacture false
numerical precision. The owner chooses / merges / amends (§15).

## `campaign_spec` — one logical object, immutable revisions

The premise, vertical strategies, collection selections, rails, content program, naming/voice,
Default composition and seam intent are **structured sections of ONE logical Campaign Spec**, not
unrelated files.

```
campaign_spec
├── premise
├── vertical_strategies
├── collection_selections
├── rails
├── content_program
├── naming_voice
├── default_composition
└── seam_intent
```

The Campaign Spec is **one logical object with immutable revisions**, not one mutable monolithic
file:

```
cs_r001 → cs_r002 → cs_r003 → …
```

Each revision contains the complete coherent Campaign Spec at that revision. Each material section
carries a deterministic **section hash**. This permits precise owner approval (bind to a section at a
revision) and precise dependency invalidation (§8). The final approved Campaign Spec deterministically
generates the CollectionCuration curation requests (§9).

### The sections in detail

* **premise** — what the campaign is fundamentally saying: intended shopper behavior; key tension;
  why-now; Shopya role; major exclusions; what the campaign deliberately is not. It does not select
  collections/rails/articles.
* **vertical_strategies** — how the premise manifests independently across the required verticals
  (Fashion, Home & Interior, Tech & Electronics, Beauty & Grooming, Travel & Luggage, Outdoors &
  Sports): why the campaign matters here; fresh vertical-specific evidence; shopper tension;
  interpretation; merchandising territories; content/editorial territories; exclusions; rejected
  hypotheses. The Fashion mechanism must not be mechanically copied into every vertical.
* **collection_selections** — durable canonical taxonomy shelves selected for this campaign (required
  selection counts and gender applicability per Campaign Charter / Content Charter; see §14). Per
  selection: canonical category ID; display name; category boundary; inclusion logic; exclusions;
  gender where relevant; campaign relevance; fulfillment requirements; price/range expectations;
  representative ideal products/brands as guidance.
* **rails** — every selected collection's rail scope: target surface; rail title; hook/supporting
  copy; base or story type; source collection(s); activation priority; delivery path; execution
  feasibility; technical blocker where applicable. Thematic/color/texture ideas live here, not in
  durable taxonomy.
* **content_program** — per selected collection, an evidence-backed content/search opportunity or an
  explicit justified none. Per concept: target query; evidence state; search intent; recommended
  format; SEO title; content-card headline; premise; outline; **link INTENT** (target
  collection/category, target rail, product role) pre-fulfillment — exact product bindings occur only
  after fulfillment; target surface; campaign-wide vs vertical-specific.
* **naming_voice** — durable/category-shaped collection names; campaign-personality rail names; voice
  constraints; prompt-ready content at specification level.
* **default_composition** — Default/All is a deliberate late editorial step (lead rails,
  vertical/category balance, global order, campaign-wide vs vertical-only content, blocked
  placements, editorial rhythm) — never automatic aggregation and not a seventh vertical.
* **seam_intent** — S1–S6 expectations and which outputs are Wizard-executable, human-admin executed,
  code-owned, Sanity/content handoff, or technically blocked. The S1–S6 seam contract is owned by the
  frontend repo; this section references that contract, never restates it.

---

# 7. Foundation readiness (`foundation_001`)

Foundation readiness is owned by Campaign Charter rule **`foundation_001`**, authored during
promotion (§23) with these resolved semantics:

* production readiness requires **>=200 working Source/Merchant profiles**;
* a working profile has a registered source identity **plus** a demonstrated repeatable method
  capable of producing product truth that clears the PDP/product-truth gate;
* discovery-only capability does not count;
* production CollectionCuration fulfillment is blocked until the rule passes;
* there is **no normal production waiver**.

`foundation_001` does **not** invent hard per-vertical / per-category / per-price-tier quotas unless
those are separately owner-approved with measurable definitions; useful coverage across
vertical/category/price tiers remains a roster-quality objective and audit dimension, not an undefined
hard gate. No transient roster count belongs in the rule, the PRD, or the Charter.

**Target product semantics:**

> Production collection fulfillment cannot begin until `foundation_001` passes.

The caller-authored `foundation_shortfall_acknowledged` bypass is removed from the target product
model. Diagnostic operation below readiness is permitted only because diagnostic outputs are
structurally incapable of satisfying production gates (§4, §16). An extraordinary production waiver is
not designed now; it may be introduced later only by an explicit new owner governance decision if a
real need emerges.

---

# 8. Revision semantics and declared dependencies

Owner/LLM back-and-forth is normal and part of the product. Each new revision (of the
`research_brief`, `campaign_directions`, or `campaign_spec`) must identify: the previous revision; the
owner feedback/input that caused it; the changed sections; the unchanged sections; the rationale; the
evidence impact; and the downstream dependency impact. Owner-approved judgment is never silently
overwritten.

**Every structured Campaign Spec section declares its upstream dependencies. Revision invalidation is
derived from the declared dependency graph, not improvised by the agent.** Changing a section
invalidates only the approvals and work that declare a dependency on it; unrelated approved sections
and unrelated research are not reopened.

The dependency graph is directional but **not necessarily purely linear** — sections may declare
explicit independent dependencies. Conceptually:

```
premise
  → vertical_strategies
      → collection_selections / rails / content_program
          → naming_voice / default_composition / seam_intent
              → final Campaign Spec approval
                  → curation requests / fulfillment
                      → assembly
```

---

# 9. Typed owner decisions

Owner decisions are structurally typed. The binary status distinction is retained and remains a
Campaign Charter `governance_003` rule:

* `provisional_recommendation` (agent proposal, owner approval pending);
* `owner_confirmed` (genuinely explicit owner confirmation).

Each explicit approval additionally carries semantic targeting so that what was approved, and on what
exact object, is unambiguous: `decision_type`; `target_type`; `target_revision`; `target_section(s)`
(where applicable); and the target artifact/section **hash(es)**.

**Approval-target immutability.** Once emitted as an approval-target revision/artifact, it is
immutable; any modification creates a new revision. This applies at minimum to `research_brief`,
`campaign_directions`, `campaign_spec`, and execution manifests/packages. Every owner approval binds
to an already-existing immutable target — never to a target that will be materialized later.

**Canonical hashing.** Deterministic hashes are computed over a **canonical normalized semantic
representation** of the target, not over incidental presentation bytes (e.g. YAML whitespace or key
ordering). The PRD requires stable semantic hashing; it does not prescribe a canonicalization
implementation — the exact serialization contract is an implementation/schema-design decision.

Every explicit owner checkpoint is hash-bound:

### Frame approval
```
decision_type: research_brief_approval
target_type:   research_brief
target_revision: rb_rNNN
target_sha256:   <brief-revision hash>
```

### Campaign direction
```
decision_type: campaign_direction_selection
target_type:   campaign_directions
target_revision: cd_rNNN
selected_direction_id: <id>
target_sha256:   <selected-direction hash>
```

### Campaign Spec section approval (premise, vertical strategy)
```
decision_type: campaign_spec_section_approval
target_type:   campaign_spec
target_revision: cs_rNNN
target_section:  vertical_strategies
target_sha256:   <section hash>
```

### Architecture approval (one composite decision)
Checkpoint 5 (§15) is ONE human judgment covering `collection_selections`, `rails` and
`content_program` together — one owner action → one ledger event → exact hashes for every approved
architecture section:
```
decision_type: campaign_architecture_approval
target_type:   campaign_spec
target_revision: cs_rNNN
target_sections:
  collection_selections: <section hash>
  rails:                 <section hash>
  content_program:       <section hash>
```
Individual `campaign_spec_section_approval` decisions remain valid for the single-section checkpoints
(premise, vertical strategy).

### Final Campaign Spec approval
```
decision_type: final_campaign_spec_approval
target_type:   campaign_spec
target_revision: cs_rNNN
target_sha256:   <full spec-revision hash>
```
Meaning: **build this specification.** Occurs before product fulfillment.

### Execution-package approval
```
decision_type: execution_package_approval
target_type:   execution_manifest
target_sha256:   <manifest/build hash>
```
Meaning: **this validated package is approved for human implementation.** Occurs after validation and
is structurally distinct from final Campaign Spec approval.

### Material-exception approval
Binds to the **exact proposed amended Campaign Spec revision** the Wizard has already materialized
(§13) — never to an abstract decision that will later create the authoritative revision:
```
decision_type: material_exception_resolution
target_type:   campaign_spec
target_revision: cs_rNNN          # the proposed amended revision, already emitted and immutable
target_sha256:   <proposed-revision hash>
```
If the owner amends the proposal, the Wizard produces another immutable candidate revision and
presents that exact revision for confirmation.

The `research_ledger` does not normally require owner approval. **Approval is never inferred** from
silence, chat context, an agent-authored proposal, or approval of another object (system invariant,
§16).

> **Implementation note (subordinate to the normative rule):** this typed model requires a fresh-run
> schema version; it is not retrofitted onto in-flight historical runs. Migration implementation is
> out of scope for this PRD.

---

# 10. Wizard → CollectionCuration handoff and transport

The **approved Campaign Spec deterministically generates** the versioned curation requests. A
hand-authored request is not part of the intended normal flow.

**Requests are generated from unique durable-collection fulfillment requirements, not mechanically
one request per vertical/surface placement.** A single canonical durable collection reused across
multiple verticals or surfaces normally has one fulfillment requirement and one authoritative
product-truth pool; its multiple placements, rails and editorial uses remain Wizard-owned campaign
objects. Separate fulfillment requirements are generated only when the approved Campaign Spec
genuinely specifies materially different product constraints that cannot share one collection truth
pool. This prevents duplicate sourcing for shared campaign placements.

Each request contains **campaign judgment only**: contract version; campaign/run reference; inherited
run mode (§4); canonical category ID; gender where relevant; required depth (per `render_003`);
inclusion logic; exclusions; avoid terms; range/price expectations; merchant/brand preferences where
judgmental; ideal-product examples as guidance; campaign context. It must not contain authoritative
product identity, name, price, currency, availability, PDP, variants, or image truth.
CollectionCuration validates the request against the engine-owned request schema and refuses any
request carrying a forbidden product-fact key.

**Transport is transport-independent.** The logical Wizard↔Engine contract must survive a future move
from filesystem to package/API/service without changing campaign semantics. The current
implementation uses a filesystem artifact transport as the v1 adapter, subject to the normative
requirements: configured/explicit transport roots (no architectural reliance on `../sibling-repo`
assumptions); a contract version; deterministic artifact/request identity; content hashes; immutable
request and response artifacts; and a clear producer and consumer for each. Physical on-disk layout is
an implementation decision for the structured-object/transport work, not a normative element of this
PRD.

---

# 11. CollectionCuration fulfillment

CollectionCuration fulfills the approved Campaign Spec. **Production fulfillment may begin only when
`foundation_001` passes** (§7).

Order of work: satisfy foundation readiness; mine existing valid truth first; targeted sourcing
against approved category specs using known roster methods (any newly learned method becomes reusable
engine knowledge); PDP-verify; produce **the launch depth required by `render_003`** per approved
category collection; maintain product truth/provenance. The engine has no identity fallback in the
Wizard, performs no silent widening, and makes no campaign judgments.

**Human residual verification** should be batched where practical. Any item requiring unresolved human
verification remains ineligible until verified; unresolved items do not block unrelated
products/categories unless they prevent the relevant approved collection from satisfying its
production requirement.

If the approved spec cannot be fulfilled, the engine returns a **fulfillment_exception** (§13) — a
product-truth/fulfillment-fact object. The Wizard turns that into a campaign-judgment
`material_exception` (§13). Normal product substitutions do not require owner approval.

---

# 12. CollectionCuration → Wizard return

Two distinct return concepts.

## Curation Receipt

**CollectionCuration is the sole author of the Curation Receipt.** It reports fulfillment status for
each request as orchestration metadata: request ID/hash; category; status; required depth;
`engine_reported_eligible_depth`; fulfilled/shortfall; a factual `fulfillment_exception_ref` pointing
to any `fulfillment_exception` (§13); failure reason; and a truth-export reference/version/hash. The
receipt carries fulfillment **state**, not product facts, and it does **not** carry any
campaign-judgment field — no `material_exception` indicator and no suggested scope change. The Engine
reports fulfillment-failure facts; the Wizard alone decides whether they constitute a campaign
material exception (§13). Factual candidate alternatives, where useful, belong on the
`fulfillment_exception`.

> The receipt is NOT authoritative proof that a collection clears its launch-depth gate.

The Wizard must independently validate the referenced current Truth Export and **recompute** the
applicable floor from Engine-owned `sellable_product_uid` / `floor_eligible`. The Wizard may continue
only when: (a) the Engine receipt reports fulfilled; AND (b) the Wizard's independent recomputation
against the referenced current Truth Export passes. A mismatch between receipt fulfillment/depth and
Wizard recomputation is a **hard contract/coherence failure**, not a normal tolerance.

## Truth Export

The versioned authoritative product truth, consumed **read-only** by the Wizard. The Wizard must
validate: contract version; provenance/hash; freshness/currentness; and engine ownership of product
identity/facts. Staleness, unsupported version, or missing required fields are refused.

Lifecycle: `approved campaign_spec → deterministic curation requests → engine fulfillment → curation
receipts (+ fulfillment_exceptions) + truth export → Wizard independent verification → assembly`.

---

# 13. Fulfillment exceptions and material exceptions

Fulfillment reality and campaign judgment are two different objects with two different authors.

## Engine `fulfillment_exception` (product-truth/fulfillment facts only)

Authored by CollectionCuration. Contains: request ID/hash; category; required depth; achieved
eligible depth; failure classification/reason; merchant/source constraints; and **factual** candidate
taxonomy scopes and their eligible counts where available. The Engine may expose factual alternatives.
**It does not recommend what the campaign should do**, and it does not author campaign impact.

## Wizard `material_exception` (campaign judgment)

The Wizard creates a `material_exception` whenever a post-final-spec **factual, technical,
fulfillment, or operational** finding requires changing approved campaign judgment. Possible sources
include: an Engine `fulfillment_exception`; a Wizard assembly constraint; a frontend/seam
impossibility; a content/product reality conflict; or other technical evidence requiring an
approved-spec change. An Engine `fulfillment_exception` is **one possible input, not the only
origin**. The Wizard alone determines campaign impact and recommendation.

A `material_exception` contains: the affected (currently approved) Campaign Spec revision; the
affected collections/rails/content/Default; campaign impact; Wizard recommendation; concrete owner
options; and the exact decision required. **Only the Wizard turns fulfillment reality into campaign
judgment.**

**Revision timing.** The owner never approves a future revision that has not yet been materialized.
Correct flow:

```
approved Campaign Spec
  → factual/technical/fulfillment/operational finding
    → Wizard prepares the EXACT proposed amended Campaign Spec revision (immutable candidate)
      → owner sees the exception + the proposed delta/replacement revision
        → owner approves/amends THAT exact revision (material_exception_resolution, §9)
```

The material-exception decision binds to the **proposed amended Campaign Spec revision/hash** that
already exists (§9). If the owner amends the proposal, the Wizard produces another immutable candidate
revision and presents that exact revision for confirmation. Approving the proposed revision makes it
the authoritative Campaign Spec and invalidates only work that declares a dependency on the changed
sections (§8).

Only material campaign-judgment changes interrupt the owner after final Campaign Spec approval — e.g.
a collection cannot reach the required depth; category scope must change; an approved rail cannot be
fulfilled; price/brand/range substantially misses the approved spec; product reality invalidates an
approved content concept; a required seam is technically impossible. Normal SKU substitutions do not
interrupt the owner.

---

# 14. Collection selection structure and gender

Structural validators MAY enforce: valid taxonomy IDs; required selection counts (per Campaign Charter
/ Content Charter); and valid gender applicability.

The **no-mechanical-mirroring principle** — men's and women's selections chosen independently on
strength rather than mirrored — is **editorial/strategic quality governance**, owned by the Content
Charter and enforced through architecture-generation instruction, semantic QA, and owner-visible
selection rationale. It is **not** a simplistic validator that rejects matching men's/women's
categories: two independently chosen sets may legitimately overlap.

---

# 15. Owner checkpoints

A small number of meaningful interactions. At each, the owner sees a concise decision-oriented card
(what we found · what it means · recommended decision · 2–4 concrete choices · what happens next), with
evidence available underneath. Each checkpoint binds a **typed, hash-bound decision** (§9) to an exact
structured object/revision.

| # | Checkpoint | Owner sees | Owner decides | Binds decision to |
|---|---|---|---|---|
| 1 | Kickoff / Frame | normalized `research_brief` | is this the problem to solve? | `research_brief` revision + hash |
| 2 | Campaign direction | `campaign_directions` + rubric | which opportunity | directions revision/hash + selected direction id + hash |
| 3 | Premise | `campaign_spec.premise` | is this the campaign idea we mean? | premise section (cs_rNNN, hash) |
| 4 | Vertical strategy | `campaign_spec.vertical_strategies` | does it translate across Shopya? | vertical_strategies section (cs_rNNN, hash) |
| 5 | Architecture | collection_selections + rails + content_program | are these the right objects? | `campaign_architecture_approval` — one composite decision over those sections (cs_rNNN, per-section hashes) |
| 6 | Final Campaign Spec | complete Campaign Spec revision | build this specification | `final_campaign_spec_approval` (cs_rNNN, full hash) |
| 7 | Material exception | exception + proposed amended revision (only if needed) | approve / amend the proposed revision | `material_exception_resolution` → the already-materialized proposed cs_rNNN + hash |
| 8 | Execution-package approval | compact readiness/exceptions card | approve package for implementation | `execution_package_approval` (manifest/build hash) |

**Execution-package approval is the normal final owner-judgment checkpoint.** After it, human
implementation → sanctioned live verification → LIVE. LIVE is reached through verified operational
evidence bound to the executed build; it does not require another `owner_confirmed` campaign-judgment
decision unless a separate deployment/release policy is explicitly introduced later. "Go-live /
verification" is retained in the lifecycle UX as an operational step, not as another mandatory
campaign-judgment approval.

The owner never reviews the 50+ products per collection, and product-row approval is not a normal
checkpoint.

---

# 16. System invariants (normative)

Requirements the system MUST satisfy. Stated as targets; not weakened to describe current
implementation state.

1. The Wizard never authors product truth; CollectionCuration consumes campaign judgment but never
   makes campaign placement/editorial judgment and never authors campaign impact or recommendations.
2. Production fulfillment respects Campaign Charter launch-depth rules (`render_003`) and begins only
   when `foundation_001` passes (§7).
3. Production validation is current and hash-bound to the current execution package.
4. Stale, legacy, diagnostic, superseded, or manually-asserted proof cannot satisfy production
   validation.
5. **A run in a post-validation workflow state (VALIDATED or CAMPAIGN_APPROVED) MUST be supported by
   current valid execution proof bound to the current execution package.** A stale or superseded
   execution package invalidates that state through sanctioned reopen semantics.
6. Final Campaign Spec approval is not execution-package approval; the two are structurally distinct
   typed, hash-bound decisions (§9).
7. An owner decision is never inferred from silence, chat context, an agent-authored proposal, or
   approval of another object; the decision ledger is binary and typed (Campaign Charter
   `governance_003` + §9).
8. Live verification binds to the executed build; there is no asserted-boolean live path.
9. Handoff work is never reported as authored, implemented, or live (Campaign Charter `scope_002`).
10. The Wizard→Engine request contains campaign judgment only; product facts cannot leak into it.
11. The Engine truth export is authoritative for product facts and is consumed read-only, with
    contract-version, provenance/hash and freshness validated at consumption; a Curation Receipt is
    orchestration metadata and is never accepted as proof a collection clears its launch-depth gate
    (§12).
12. Diagnostic-mode artifacts/proof can never satisfy production fulfillment, validation, approval, or
    live gates (§4).
13. Campaign Spec revision invalidation is derived from the declared dependency graph, not improvised
    (§8).

---

# 17. Wizard final assembly

After fulfillment, the Wizard produces the production execution candidate. Inputs: the approved
Campaign Spec; the accepted Engine Curation Receipts and the current Truth Export (independently
verified per §12). Responsibilities and outputs:

* select the rail pins per approved rail logic (Campaign Charter `render_002`) and order them;
* write product annotations;
* evaluate launch-freshness (per the Charter/Content-Charter freshness rules);
* bind exact verified products into the approved content program (link intent → concrete bindings);
* finalize Default/All composition deliberately;
* perform mechanical anti-slop QA and avoid-terms lint;
* perform semantic/editorial QA;
* **emit the complete human execution package** (§20, artifacts A–G) as the production candidate —
  not merely the products CSV.

The complete package is produced here, before production validation and before execution-package
approval, so the owner approves an already-assembled package. Normal compliant fulfillment does not
require owner line-by-line approval; only a material exception (§13) escalates.

---

# 18. Production validation

The Wizard validates the **complete** production execution package (§20, artifacts A–G), not merely
the products CSV. Validation is evidence-bound and requires: the current supported curation/truth
contracts; current Engine truth; the production execution builder; an immutable build; output hashes;
and manifest binding. A stale, legacy, superseded, diagnostic, manually-asserted, or improperly-bound
build cannot satisfy production validation.

Output: the current validated execution package plus an **immutable execution manifest that
enumerates, references and hashes every authoritative package artifact** — at minimum the master
execution CSV, Collection Creation Spec, Rail/Feed Spec, Content Production Package, Seam Handoffs, the
Human Execution Checklist, and the truth-export reference/version/hash, together with any other
executable artifact the current campaign requires. This is the `VALIDATED` state; per invariant §16.5
it must remain supported by current valid execution proof.

---

# 19. Execution-package approval, human implementation and LIVE

**Execution-package approval.** The complete human execution package already exists (assembled in §17,
validated and manifest-bound in §18) before the owner is asked. The owner receives a compact
readiness/exceptions card (not thousands of product rows) and approves the current validated package.
The approval binds to the exact **execution manifest that covers the complete package** (§9, §18) and
means: *this validated package is approved for human implementation.* It is explicitly distinct from
final Campaign Spec approval. **After approval these artifacts may not silently change: any material
package change requires a new build/manifest and the appropriate revalidation and reapproval**
(consistent with invariant §16.5).

**Human implementation and LIVE.** A human/admin executes the approved package. The Wizard never
reports authored/implemented/live work that occurred only as a handoff. After implementation, the
sanctioned live-verification path records real evidence bound to the executed build (campaign/run;
executed build; build hash; live identifiers; observed result; verification method; provenance). Only
then does the run reach LIVE — an operational fact established by verified evidence, not by a further
default campaign-judgment approval. Post-live monitoring, refreshes and review follow separately.

---

# 20. Human execution package

The Wizard produces a complete package for the human who builds the campaign in Shopya:

* **A. Master Execution CSV** — one row per product × launched collection membership: campaign/build;
  target surface; collection; engine-hydrated product facts; `is_rail_item`; rail name if true; rail
  position if true. No separate rail/body CSVs.
* **B. Collection Creation Spec** — per collection: canonical category; name; description; full
  launched membership; cover/art direction where applicable.
* **C. Rail / Feed Spec** — per rail: target surface; display title; supporting copy; source
  collection(s); pins; pin order; sort order; delivery path; technical blocker if applicable.
* **D. Content Production Package** — per approved piece: target query; evidence; search intent; SEO
  titles; content-card headline; premise; full outline; research/source requirements; exact
  collection/rail/product bindings; production-ready writing prompt; cover/content-card visual brief;
  placement. Prompts may be used by the owner or another content system; never described as published.
* **E. Seam Handoffs** — S1–S5 specifications for anything the Wizard cannot execute.
* **F. Execution Manifest** — the authoritative binding record for the **complete** package: campaign;
  run; build; validation result; truth-export version/reference; and a reference + hash for **every**
  package artifact (A–E and G), so approval covers the exact package the human will execute (§18, §19).
* **G. Human Execution Checklist** — the ordered operational sequence: create collections; add
  memberships; create rails/feeds; add/pin/order rail products; generate approved content from
  prompts; publish/place Sanity content; implement S1–S5 seams; verify rendered campaign; execute
  sanctioned live verification.

---

# 21. Final intended end state

A new owner runs `/new-campaign` and moves from zero context to: current research; differentiated
campaign directions; approved premise; approved six-vertical strategy; approved
collection/rail/content architecture; approved final Campaign Spec; CollectionCuration-fulfilled
product catalog; Wizard-assembled and validated execution package; complete product/content/seam human
handoff; and a verified live campaign — without needing to understand workflow schemas, the state
machine, scraper internals, product identity logic, validation hashes, or cross-repo implementation
machinery.

---

# 22. Implementation mapping (non-normative appendix)

Subordinate to the normative sections above. This reflects the **audited current state** and the
**target enforcing mechanism**; it does not claim nonexistent authoring commands/schemas already
exist. The Workflow Schema remains the machine authority for states.

| Product phase | Target structured object | Current workflow state(s) | Current implementation status | Target enforcing mechanism |
|---|---|---|---|---|
| Kickoff / Frame | `research_brief` | FRAME_READY → RESEARCHING | **Partial** — frame schema + interpretation-discipline tests exist; no authoring command | frame/brief schema + sanctioned authoring/validate command + `research_brief_approval` |
| Research | `research_ledger` | RESEARCHING → SIGNALS_READY | **Partial** — signal schema + evidence-family/stop-condition predicates; no sufficiency check, no command | research runner + ledger schema/validators |
| Campaign directions | `campaign_directions` | SIGNALS_READY → OPPORTUNITIES_READY → OPPORTUNITY_SELECTED | **Implemented differently / prose-heavy** — expressed as opportunities/routes; PRD chain not a code object; untested | directions schema + rubric + `campaign_direction_selection` |
| Premise | `campaign_spec.premise` | INTERVIEW_COMPLETE → BRIEF_DRAFT ⇄ BRIEF_APPROVED | **Folded into brief** — no distinct premise object | spec-section schema + section approval |
| Vertical strategy | `campaign_spec.vertical_strategies` | (within BRIEF/ROUTES states) | **Prose-only** — `vertical_strategy_matrix.md`, no schema/gate/test | spec-section schema + section approval |
| Architecture | collection_selections + rails + content_program | ROUTES_READY → ROUTE_SELECTED → ACTIVATION_READY | **Prose-heavy / implemented differently** — `three_layer_map_v2.md` upstream; enforced only at execution grain | spec-section schemas + section approvals |
| Naming / final spec | `campaign_spec` naming_voice + default_composition + seam_intent | SEAM6_READY (spec) | **Partial** — `naming_and_assembly.yaml` + a final-spec decision; consolidation is prose | consolidated Campaign Spec + `final_campaign_spec_approval` |
| Fulfillment | curation requests → receipts + fulfillment_exceptions + truth export | (engine; no wizard state) | **Largely enforced (engine)** — request gate, forbidden-facts, foundation gate; request/receipt loop not yet wired | deterministic request gen + receipts + `foundation_001` gate + truth-export contract |
| Assembly + validation | complete human execution package → validated, manifest-bound package | VALIDATED | **Partial** — judgment-purity, hydration, hash-bound production-only validation exist, but validation/manifest currently bind the products CSV, not the full package | `validate-execution` extended to assemble + validate + hash-bind the complete package (A–G) |
| Execution approval | execution manifest | CAMPAIGN_APPROVED | **Enforced with the §16.5 coherence defect open** | `execution_package_approval` + coherence fix (dev step 2) |
| Go-live | verification record | LIVE | **Enforced (structural)** — bound to executed build | sanctioned verify-live path |
| Review | measurement + review | REVIEWED | **Enforced** | schema |

**Notes.** Several internal states advance the **same** logical Campaign Spec through immutable
revisions; one Campaign Spec section does **not** equal one state, and the historical
state-per-artifact layout must not force the Campaign Spec back into disconnected files. The 17
internal workflow states are retained for the initial implementation; a later dedicated state-model
review may prune obsolete states and is not combined with the front-half restructuring.

---

# 23. Development implications (non-normative appendix)

Subordinate to the normative PRD. Implementation order:

1. **Promotion transaction — one coherent authority migration (COMPLETED 2026-08-11):** this PRD is
   canonical `prd.md`; `foundation_001` authored in the Campaign Charter (§7 semantics); `CLAUDE.md`
   authority map points here; `docs/E2E_PROCESS.md` reduced to a tombstone pointer; active `M`-number
   vocabulary removed from authoritative docs/code comments; agent/skill pointers updated; no stale
   active pointer treats the superseded E2E process as canonical.
2. Fix the existing post-validation state-coherence defect (invariant §16.5): current-state coherence
   keyed to the workflow state, not a downgradable status field; migrate/reopen semantics made
   coherent with it; adversarial tests inverted/added.
3. Add fresh-run / vNext schema support for run mode (§4), the structured front-half objects (§6),
   typed/hash-bound approvals (§9), and declared section dependencies (§8).
4. Add sanctioned authoring/validation commands for those objects.
5. Wire deterministic Wizard→Engine curation-request generation from the approved Campaign Spec (§10).
6. Implement Engine Curation Receipts + `fulfillment_exception`s and Wizard ingestion +
   `material_exception` generation (§12, §13).
7. Remove the old normal production foundation bypass and enforce `foundation_001` (§7).
8. Implement owner checkpoint-card generation from the structured objects (§15).
9. Add upstream / adversarial / cross-repo tests, charter↔implementation consistency tests, and an
   engine truth-export **producer** test (kickoff cannot invent owner constraints; evidence requires
   provenance; a direction cannot advance without required rationale; owner feedback creates a
   revision, not an overwrite; vertical strategy covers the six surfaces independently; architecture
   refers to real taxonomy IDs; spec approval binds to an exact revision/hash; an upstream-section
   change invalidates only declared dependents; requests are generated only from an approved spec; no
   product facts leak into requests; receipt-vs-recomputation mismatch fails hard).
10. Run a fresh Almost Fall `/new-campaign` regression from zero.

**Acceptance criterion.** Repair of the historical Almost Fall run is NOT the acceptance criterion.

> A fresh Almost Fall run traverses the complete guided system without manual artifact
> synchronization, hidden hand edits, approval ambiguity, or repeated corrective prompting.
