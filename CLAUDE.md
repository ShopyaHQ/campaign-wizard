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

# iterative owner checkpoint session (prd.md §15.1) — the owner-facing interface. CLI verbs and the
# thin local Campaign Console (run.py serve) are two adapters over scripts/checkpoint_core.py:
python3 scripts/run.py serve                        # launch the local Campaign Console (127.0.0.1:8765)
python3 scripts/run.py current-checkpoint --run <cmp_…>   # the current checkpoint the Wizard's way
python3 scripts/run.py answer-checkpoint  --run <cmp_…> --payload <p>   # submit intake
python3 scripts/run.py request-revision   --run <cmp_…> --ops-json '[…]'  # targeted revision + diff
python3 scripts/run.py run-next           --run <cmp_…>   # run the worker BEHIND the Wizard (research/spec)
python3 scripts/run.py approve-checkpoint --run <cmp_…> --by product_owner  # ONE owner action
python3 scripts/run.py diff-object        --run <cmp_…> --kind campaign_spec  # semantic diff
# the worker is configurable: export SHOPYA_WIZARD_WORKER_CMD='<cmd reading JSON stdin, writing JSON stdout>'
# (unset → a deterministic built-in worker; see console/workers/example_worker.py for the contract)

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
- **Iterative owner checkpoint session + thin Campaign Console** — IMPLEMENTED (prd.md §15.1). A
  checkpoint is an iterative guided session (`OPEN → INTAKE → DRAFT_READY → OWNER_REVIEW →
  REVISION_REQUESTED → … → APPROVED`), not "generate → approve". `scripts/checkpoint_core.py` is the
  SINGLE business-logic home: it derives the current checkpoint from state+schema, builds the
  Wizard-defined intake question framework (classifying each field owner_supplied / inferred_confirm /
  unresolved_input / derived_info), applies TARGETED revisions (field/section patch ops preserving
  every untouched field, minting a new immutable revision + deterministic dependency invalidation),
  computes the exact SEMANTIC DIFF, and records a SINGLE owner action per checkpoint (one Approve emits
  the whole decision set incl. the legacy compatibility id — closes AF-002). It is a presentation/
  control layer over the existing structured authority — NOT a second SSOT and NOT a second state
  machine. Two adapters call it: the CLI verbs (`current-checkpoint`/`answer-checkpoint`/
  `request-revision`/`approve-checkpoint`/`diff-object`, plus enriched `status`) and the thin local
  Campaign Console (`console/`, FastAPI + Jinja2, `run.py serve` on 127.0.0.1 — single owner, no auth/
  DB/deploy; deps isolated to the repo `.venv`, so Core + CLI + most tests still run under system
  Python). The Console renders the campaign list, the product-facing timeline, all five checkpoint
  views (intake/directions/premise+verticals/architecture/build-this), revision history + diff, and the
  fulfillment / material-exception / execution-package read views (Engine remains authority; the GUI
  never computes fulfillment). The agent works BEHIND the Wizard — the owner interacts with the Wizard,
  which orchestrates workers. Machine authority is unchanged: the five hash-bound approvals +
  `dependency_graph` + `validate_state.py`.
- **Worker orchestration behind the Wizard** — IMPLEMENTED (prd.md §15.1). `scripts/worker.py` is the
  Wizard-owned worker BOUNDARY: a `WorkerAdapter` interface with a configurable `SubprocessWorker`
  (`SHOPYA_WIZARD_WORKER_CMD` — a local command reading a JSON work request on stdin, writing a JSON
  structured result on stdout) and a deterministic `FakeWorker` (tests / explicit diagnostic ONLY —
  never a silent production fallback). `checkpoint_core.run_checkpoint_work` determines the work due
  at the current checkpoint (research → ledger+directions; the spec work → the whole campaign_spec),
  supplies the approved upstream context + output contract, invokes the worker, VALIDATES the returned
  artifact through the front-half builders (a structurally-malformed payload is a clean refusal, never
  a crash), and REGISTERS it as the next immutable revision. A worker failure records a WORK FAILED
  status, registers NO partial artifact, and leaves the run coherent + retryable. `run-next` (API +
  CLI `run.py run-next` + the Console "Run research / Run next" button with a Working/Failed banner)
  executes it. The owner drives the whole front half from the Console — new campaign · intake ·
  approve · select · run-next — and NEVER authors a generated object or converses with Claude.
- **Real Claude worker (production)** — IMPLEMENTED. `console/workers/claude_worker.py` is the real
  cognitive worker: it reads the Wizard work-request on stdin, builds a bounded neutral prompt per
  work type, invokes the local `claude` CLI non-interactively
  (`-p --output-format stream-json --verbose --permission-mode bypassPermissions`, in a throwaway
  temp cwd with `--add-dir` only that neutral dir — so the repo CLAUDE.md / golden benchmark /
  historical Almost Fall material is NEVER in scope), captures `tool_use` events to CONFIRM real web
  research actually ran (research with no `WebSearch`/`WebFetch` tool_use is refused — no faked
  research; the `usage` counters are unreliable, so detection is via stream-json events), extracts the
  single strict JSON envelope (prose around it tolerated; malformed/wrong-shape/wrong-kind refused),
  and emits ONLY the WorkerAdapter envelope on stdout (diagnostics to stderr). **Production fails
  CLOSED:** a production run with no real worker raises `worker_unavailable` — the fake is never
  silently selected. The Claude CLI is auto-detected on PATH (`SHOPYA_WIZARD_WORKER_CMD` overrides).
  The Console shows an "Agent worker: Ready / Unavailable" indicator. Proven end-to-end by
  `tests/smoke_real_claude_worker.py` (live: real current sources with today's `captured_at`, real
  distinct directions, real synthesis → Premise + Vertical Review). `console/workers/example_worker.py`
  is a deterministic reference worker for tests.
- **Full back-half owner flow in the Console** — IMPLEMENTED (prd.md §15.2). The browser owner-flow no
  longer ends at Build This — the Wizard→Engine handoff is driven from the Console, as THIN wrappers in
  `checkpoint_core` over the EXISTING proven back-half ops (NO Engine change, NO duplicated Engine
  logic, NO product truth authored in the GUI). After the approved Campaign Spec: `generate_requests`
  (Request v2 SET from the exact approved spec via `generate_curation_request`), `ingest_receipt`
  (mechanical Curation Receipt v1 ingestion via `receipt_ingest` — independent verify + exact request/
  truth-export binding + eligible-set recompute; a shortfall opens a Material Exception that BLOCKS
  assembly and whose owner resolution never waives render_003), `generate_execution_package` (the
  MECHANICAL production path — see the merchandising bullet), and `approve_package` (manifest-bound
  owner approval; a stale/superseded manifest invalidates it). The Console renders Generate Requests ·
  fulfillment status · Material Exception (with a resolution that does not unblock) · Generate
  Execution Package · execution-package review · APPROVE FOR IMPLEMENTATION, and the timeline now
  PROGRESSES through Fulfillment → Execution → Approved for Implementation → Live → Review instead of
  showing them perpetually "waiting". API endpoints + CLI verbs are adapters over the same core. The
  owner needs no CLI/Claude Code after `run.py serve`.
- **Post-fulfillment merchandising automation** — IMPLEMENTED (prd.md §15.2 step 5). After fulfillment,
  the owner clicks ONE button ("Generate Execution Package") and supplies NOTHING — no truth export,
  no product IDs, no curated rows, no Master CSV. The receipt-bound Truth Export snapshot is persisted
  automatically at ingestion (`_persist_bound_snapshot`); `generate_execution_package` loads it, runs
  the `post_fulfillment_merchandising` worker over each request's INDEPENDENTLY-VERIFIED eligible
  sellable set, and the worker performs merchandising JUDGMENT only — selecting/ordering/pinning actual
  fulfilled products into the spec's rails/collections. `build_execution_selection` is the
  SELECTION-AUTHORITY gate: a pick must be in the eligible set AND vouched by the bound snapshot; it
  refuses arbitrary/wrong-category/absent/duplicate UIDs and any product-fact mutation (price/
  availability/name/taxonomy stay the Engine's, referenced by UID). The validated immutable
  `execution_selection` materializes into the launch judgment that hydrates the Master CSV read-only
  from the bound Truth Export; A–G → validate → F in the frozen order. The worker (fake for tests; real
  `claude_worker.py post_fulfillment_merchandising` — bounded input, no web research) never authors
  product truth. Production fails closed; a `build-package` explicit-input path stays diagnostic/test/
  operator-only. Proven by `tests/test_merchandising_flow.py` + live `tests/smoke_real_merchandising.py`.
- **Campaign-neutral taxonomy input** — IMPLEMENTED (prd.md §25, closes AF-008). `scripts/taxonomy.py`
  yields the fresh-generation registry with the historical Almost Fall `SEL`/`avail` selection markers
  STRIPPED (canonical ids + durable metadata preserved); the historical selection is available only
  through `historical_selection()` for audit, never in the generation input. `assert_neutral` is the
  enforced guard; a regression suite proves fresh generation cannot read the historical selection
  markers.
