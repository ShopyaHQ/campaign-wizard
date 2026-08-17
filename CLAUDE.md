# Shopya Campaign Wizard

Plans campaigns for Shopya and produces the Seam 6 execution package: source collections,
product rails, and the CSV a human executes in admin. Everything else it authors is a handoff.

Campaigns lead with discovery, taste, and cultural relevance rather than promotional sales
language. Commercial usefulness should emerge through selection, context, and clear product
pathways.

## Authority

In this order. If two disagree, the higher one wins.

1. **`prd.md`** — the normative product & end-to-end operating model: lifecycle, owner
   checkpoints, structured campaign objects, repo boundaries, research model, revision/approval
   semantics, inter-repo handoffs, required deliverables, and system invariants. It references
   hard numbers by Charter rule ID; it does not restate them. **It states what the product MUST
   become; not all of it is built yet.** For what is actually implemented today vs. still target,
   read prd.md §22 (implementation-mapping appendix) — and treat
   `schemas/workflow_state.schema.yaml` as the authority for the process that currently runs. Do
   not assume a prd.md mechanism (Curation Receipt ingestion, structured `campaign_spec` revisions,
   typed/hash-bound approvals, a logged research runner, deterministic curation-request generation)
   exists in code until §22 or the schema confirms it.
2. **`SHOPYA_CAMPAIGN_CHARTER.yaml`** — product facts and approved rules (hard runtime/policy
   values), each with provenance and a status. Never assert product behaviour it does not record.
   A claim marked `proposed` or `unknown` is not a fact.
3. **`schemas/workflow_state.schema.yaml`** — the machine process specification. States,
   transitions, entry prerequisites, the predicate vocabulary, `settable_paths`, and the refusals.
   **Read it rather than assuming a process.** It changes; nothing else should restate its contents.
4. **`schemas/*.schema.yaml`** + the two versioned cross-repo contracts
   (`shopya-collection-curation/{curation_request_schema,truth_export_schema}.yaml`) — per-artifact
   and machine handoff structure.
5. **`schemas/interpretation_rules.yaml`** — how owner input may be normalised, and the
   interpretation-status vocabulary.
6. **`SHOPYA_CONTENT_CHARTER.yaml`** — approved editorial, voice and merchandising rules, and
   the canonical three-object model (collections own taxonomy · rails own editorial mixing ·
   content owns search/editorial acquisition). Numeric technical requirements (e.g. the >=50
   collection floor) live in the campaign charter and are referenced here, not redefined.

## The state file is never hand-edited

Every mutation goes through `scripts/run.py`:

```
new · status · review-inputs · record-decision · register-artifact · set · validate · transition
```

`set` writes only the paths whitelisted in `settable_paths`. If something you need is not
settable, that is a finding to report — not a reason to edit `state.yaml`.

## You are not the authority on whether a stage is complete

`scripts/validate_state.py` is. A transition commits only after it exits zero. Your saying a
stage is done is not evidence — see `refusals.closing_sentence_is_not_proof`. Report a refusal
with its failed predicates; never work around one.

## Owner decisions

Transitions that require an owner decision require a **human**. Record it with
`run.py record-decision`.

Never infer approval from silence, context, prior behaviour, or an agent-authored proposal.
Record an owner decision only when the owner explicitly states or confirms it — an explicit
approval in conversation does count — and preserve that basis in the decision record, so it
shows what was approved and on what. `--note` is where the basis goes.

An agent proposal is not an owner decision until it is confirmed.

At an owner decision gate, lead with the decision and the minimum information required to make
it — one primary decision, concrete choices, a recommended default. Detailed evidence, research
and process diagnostics stay available but secondary; they are never the default wall of text.

Automated verification and search recovery are exhausted before availability checks escalate to
the owner; owner verification is the fallback for irreducible ambiguity, not the default
operating path. (Owner-approved rule, 2026-08-07, demonstrated on the Almost Fall run: a 20-item
human checklist reduced to 6 items, all hard-gated. Formalize as an approved_rule charter claim
at the next charter revision — mid-run charter version changes are blocked by design.)

## Engine/wizard boundary (cardinal)

CollectionCuration owns PRODUCT TRUTH (what products exist and what is true about them now):
discovery, PDP verification, canonical identity + sellable_product_uid, price/currency,
availability, variants, provenance, truth export. The Campaign Wizard owns CAMPAIGN JUDGMENT
(which of those belong in this campaign, where, and why): premise, collection/rail/content
architecture, pins/order, copy, approvals, the execution CSV. The wizard consumes product truth
READ-ONLY and NEVER authors it; the engine NEVER makes campaign judgments. Full contract:
prd.md (§2 responsibilities, §9–§13 handoffs) and the two versioned handoff schemas
(shopya-collection-curation/{curation_request_schema,truth_export_schema}.yaml).

## Process, output model, naming — canonical homes

- What a completed campaign IS (lifecycle, owner checkpoints, structured objects, deliverables,
  invariants): prd.md — the product/E2E authority.
- The three-object model, merchandising, editorial/SEO, voice/anti-slop: SHOPYA_CONTENT_CHARTER.yaml.
- The >=50 collection-depth floor, rail pins, foundation readiness and other numeric/technical
  contracts: campaign charter (render_003, render_002, foundation_001).
- Naming/identity/build/review conventions: docs/NAMING_CONVENTIONS.md.
Do not restate those rules here; this file points at their one home.

## Documents: the locked set

Top-level canon is SEVEN wizard docs: CLAUDE.md, prd.md, SHOPYA_CAMPAIGN_CHARTER.yaml,
SHOPYA_CONTENT_CHARTER.yaml, docs/CATEGORY_TAXONOMY.md, docs/NAMING_CONVENTIONS.md,
docs/NEXT_PASS_SCOPE.md. (docs/E2E_PROCESS.md is retired to a tombstone pointer, not authority.)
Creating any new top-level document requires explicit owner approval. Iteration goes INTO the
canonical doc (version bump) or the campaign's review_book.md — never a sibling file. The /explore
seams contract's source of truth is the FRONTEND repo (agent_knowledge/…) — reference it; never
duplicate it here.

`docs/ALMOST_FALL_GOLDEN_BENCHMARK.md` is a **frozen calibration reference** (owner-approved
2026-08-12, status CLOSED) — NOT an eighth locked-set doc and NOT authority. It records the quality
bar a fresh `/new-campaign` must independently meet; its collection/rail/content examples are
representative, not immutable, and it is not iterated. It is **NOT a creative or research input to
campaign generation** — a fresh Almost Fall run must reach the bar from its own research_ledger, not
by copying the benchmark; the benchmark's role is post-hoc calibration/evaluation only. The selection
*rule* lives in the Content Charter (`collection_breadth` CB-1..CB-5); the launch floor in the
Campaign Charter (`render_003`).

## Scope

Authoring may span every seam relevant to the campaign. **Execution is Seam 6 only** — source
collections, product rails, the CSV. Everything else is a handoff brief, and a handoff is never
reported as implemented.

## Archived documents

`docs/archive/` holds superseded instructions, preserved as history. They are **not
authoritative** and must not be followed.

## Start

```
python3 scripts/run.py new                    # begin a run (run_mode: production, immutable)
python3 scripts/run.py new --diagnostic       # a sanctioned diagnostic run
python3 scripts/run.py status                 # current state and its legal transitions

# structured vNext front half (fresh runs, schema >= 1.8.0) — see "Now implemented" below:
python3 scripts/run.py register-object  --run <cmp_…> --kind research_brief|research_ledger|campaign_directions|campaign_spec --payload <p>
python3 scripts/run.py select-direction --run <cmp_…> --direction-id <id> --by product_owner
python3 scripts/run.py approve-object   --run <cmp_…> --id <checkpoint> --kind campaign_spec --binding object|section|composite [...] --by product_owner

# Request v2 for a fresh vNext production run derives from the exact approved Campaign Spec:
python3 scripts/generate_curation_request.py --run <cmp_…> --from-spec
# legacy/compatibility path (historical/testing only; NOT the normal vNext production path):
python3 scripts/generate_curation_request.py --run <cmp_…> --category-id <id> --required-depth 50
```

## Now implemented (this contract step)

- **Truth Export v2 consumer** — `scripts/truth_export_v2.py` verifies an immutable Engine
  snapshot (version + `export_id`/`export_sha256` + source binding), consumes read-only, refuses
  stale/tampered/v1, and INDEPENDENTLY recomputes Request-v2 eligibility (same sellable SET as the
  Engine) from the snapshot alone — never reading Engine internal logs or Source Profile config.
  `build_execution_csv.py` hydrates from a v2 snapshot through this consumer.
- **`run_mode`** is a run-level identity (`production`|`diagnostic`), set once at NEW and
  IMMUTABLE (not in `settable_paths`; validator refuses mutation). A Curation Request inherits it.
- **Deterministic Request v2 generation** — `scripts/generate_curation_request.py` is the one
  sanctioned path; it reads the run, inherits `run_mode`, emits an immutable, canonically-hashed
  Request v2 (contract 2.0.0). Engine validates/normalizes it; the request hash matches Engine's.
- **Curation Receipt v1 ingestion** — `scripts/receipt_ingest.py` (`run.py ingest-receipt`) is the
  ONE sanctioned Wizard path that ingests an immutable Engine Curation Receipt v1 mechanically:
  independently verifies the receipt (contract/self-hash/id-binds-core, no Engine runtime import —
  parity with the Engine verifier proven by a golden test), binds it to the exact Wizard-generated
  Request v2 (id + recomputed hash + run_mode + category), loads the bound Truth Export v2 snapshot
  and INDEPENDENTLY recomputes the eligible sellable SET (the trusted material for assembly), and
  distinguishes satisfied (achieved≥required) from a factual `shortfall_policy_exhausted`. A
  shortfall requires its matching Fulfillment Exception v1 and opens a Wizard-owned **Material
  Exception** (`open`|`resolved`) that BLOCKS assembly — no auto-widen/substitute. Owner resolution
  (`run.py resolve-material-exception`) records **campaign judgment ONLY: it never waives the
  material requirement (render_003), never makes a shortfall Receipt satisfy package completeness,
  and never unblocks assembly.** Completeness always requires a genuine satisfied Receipt for each
  current expected Request (for a fresh vNext run, the expected Request set is generated from the
  approved Campaign Spec's `collection_selections` — see the front-half + `--from-spec` items below),
  not the resolved flag. Ingestion refuses a diagnostic receipt in a production run, and tampered/
  mismatched/unexpected/duplicate artifacts.
- **Complete A–G execution package + immutable Execution Manifest** — `scripts/execution_package.py`
  produces the seven-class human execution package in a **frozen, non-self-attesting order**:
  `run.py build-package` STAGES A–G only (A Master CSV via the v2 builder; B Collection Creation
  Spec; C Rail/Feed Spec — honest renderer capability, no invented XC fallback; D Content Package;
  E Seam Handoffs; G Human Checklist) and writes NO manifest and makes NO validity claim. `run.py
  validate-package` then VALIDATES the staged A–G + deps + receipt-set completeness + coherence +
  diagnostic + renderer honesty (consulting NO manifest), and **only after that passes** emits the
  immutable, content-addressed **F Execution Manifest** over the already-validated set — recording
  the completed validator result as the manifest's `validation` block. F never pre-certifies its own
  validation; `verify_manifest` checks integrity/identity only and never treats the recorded
  `validation` block as proof of validity. Same semantic package → same `exmf_…` id; any component
  change → different id; same-id/different-bytes refused.
- **Complete-package validation + manifest-bound approval** — `run.py validate-package` (above)
  records a hash-bound attempt carrying `package_validated` + `package_manifest_sha256` bound to the
  F it just emitted; VALIDATED requires `execution_manifest` + `execution_package_validated` (a
  `products.csv`-only pass can never satisfy it). `run.py approve-package` records the owner
  `execution_package_approved` decision bound to the exact manifest id/sha; CAMPAIGN_APPROVED
  requires that manifest-bound approval (being VALIDATED is not approval). Post-validation coherence
  and the sanctioned reopen edges (VALIDATED/CAMPAIGN_APPROVED → SEAM6_READY) now also supersede the
  manifest and invalidate a stale package approval.
- **Structured vNext front half** — IMPLEMENTED (fresh runs pinned to workflow schema `>= 1.8.0`).
  `scripts/front_half.py` builds and canonically hashes four first-class structured objects that are
  the front-half AUTHORITY: `research_brief` (FRAME_READY), `research_ledger` (SIGNALS_READY),
  `campaign_directions` (OPPORTUNITIES_READY) and ONE `campaign_spec` carried as IMMUTABLE revisions
  (premise · vertical_strategies · collection_selections · rails · content_program · naming_voice ·
  default_composition · seam_intent), each section semantically hashed with an order-stable composite.
  `run.py register-object` writes each object (write-once revision file + state-file spine the
  validator recomputes); `run.py select-direction` / `run.py approve-object` record the FIVE typed,
  hash-bound owner checkpoints — kickoff, direction selection, premise + vertical (two distinct
  section approvals), architecture (one composite over collection_selections+rails+content_program),
  and the final **"build this"** composite over all eight sections. A material change re-mints the
  hash and DETERMINISTICALLY invalidates downstream approvals via the schema `dependency_graph`; a
  stale/superseded approval can never gate. The existing internal states are RETAINED as lifecycle
  markers — no second state machine; on a vNext run the legacy prose predicates are superseded by the
  structured objects (INTERVIEW_COMPLETE / BRIEF_DRAFT / ROUTES_READY are compatibility pass-throughs;
  ACTIVATION_READY / SEAM6_READY KEEP their real Seam-6 execution-prep gates and ADD the structured
  ones). Version-gated: historical (`< 1.8.0`) runs stay readable under the legacy predicates and are
  never migrated. Machine authority is `schemas/workflow_state.schema.yaml` (states/predicates/
  `dependency_graph`) + `schemas/{campaign_spec,front_half_objects}.schema.yaml` (object shapes) +
  `scripts/validate_state.py` (the judge). Prose artifacts are DERIVED review renderings / historical
  compatibility only — never a co-equal authority; owner approvals bind hashes, not files.
- **Request v2 from the exact approved Campaign Spec** — `generate_curation_request.py --from-spec` is
  the vNext PRODUCTION path: it derives `category_id` + `required_depth` from the approved spec's
  `collection_selections` and binds `spec_ref` to the exact `campaign_spec` id/revision/composite hash,
  refusing unless a CURRENT, non-stale `campaign_spec_approved` ("build this") decision exists. The
  legacy run-bound path (`spec_ref.kind = run`, `hash = null`) is COMPATIBILITY/historical only, not
  the normal vNext path. Request v2 semantics (contract 2.0.0, canonical hashing) are UNCHANGED — the
  proven back half (fulfillment → receipt → A–G package → manifest → approval → CAMPAIGN_APPROVED) is
  untouched.
