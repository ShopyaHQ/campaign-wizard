# Shopya Campaign Wizard

Plans campaigns for Shopya and produces the Seam 6 execution package: source collections,
product rails, and the CSV a human executes in admin. Everything else it authors is a handoff.

Campaigns lead with discovery, taste, and cultural relevance rather than promotional sales
language. Commercial usefulness should emerge through selection, context, and clear product
pathways.

## Authority

In this order. If two disagree, the higher one wins.

1. **`SHOPYA_CAMPAIGN_CHARTER.yaml`** — product facts and approved rules, each with provenance
   and a status. Never assert product behaviour it does not record. A claim marked `proposed`
   or `unknown` is not a fact.
2. **`schemas/workflow_state.schema.yaml`** — the process specification. States, transitions,
   entry prerequisites, the predicate vocabulary, `settable_paths`, and the refusals. **Read it
   rather than assuming a process.** It changes; nothing else should restate its contents.
3. **`schemas/*.schema.yaml`** — per-artifact structure.
4. **`schemas/interpretation_rules.yaml`** — how owner input may be normalised, and the
   interpretation-status vocabulary.
5. **`SHOPYA_CONTENT_CHARTER.proposed.yaml`** — editorial, voice and merchandising rules.
   Proposed, not yet in force; consult it, do not cite it as binding.

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

## Phase 1 campaign output requirement (owner-locked, 2026-08-07)

A completed campaign = four parallel outputs (strategy, merchandising, editorial/content,
execution) across Default + six verticals — full definition and the permanent process model in
docs/E2E_PROCESS.md (§CAMPAIGN OUTPUT REQUIREMENT, folded 2026-08-09; the earlier
docs/archive/PHASE1_CAMPAIGN_OUTPUT_REQUIREMENT.md is history, not authoritative). Critical principle: within each vertical, product
and editorial opportunities are developed IN PARALLEL from the same premise/evidence/tension —
content is never appended after merchandising, and the owner architecture checkpoint receives
both. Default/All composition is a deliberate editorial step, never automatic aggregation.
Future campaigns carry this from kickoff; Almost Fall's Fashion work is the locked first
vertical prototype and the remaining verticals + content layer are extension artifacts (a
one-time migration exception). Phase 2 (social visual prompts preserving product truth)
remains separately deferred.

## Naming conventions (owner-locked, 2026-08-07)

Three separate identities, never conflated in one filename: campaign_id (human, kebab-case),
run_id (immutable cmp_<ULID>), build_id (b001, b002 — immutable execution revisions, never
overwritten). Full rules: docs/NAMING_CONVENTIONS.md. Both halves are live as of 2026-08-07:
execution-asset naming AND the campaigns/<campaign_id>/runs/<run_id>/ layout (_drafts/ for
unnamed kickoffs; `run.py promote` performs the controlled promotion when campaign_id locks;
artifact paths are stored run-root-relative).

## Engine/wizard boundary (owner ruling, 2026-08-07)

CollectionCuration owns product truth: discovery, fetching, normalized observations (identity,
canonical PDP, retailer/brand, price/currency, availability, variants, timestamps, verification
provenance). The Campaign Wizard owns campaign judgment: which products belong, collection/rail
assignment, editorial ordering, annotations, copy, approvals, and the execution worklist. The
wizard consumes product truth READ-ONLY; the builder's refusal to run without the engine log is
deliberate boundary enforcement. The wizard does not append observations to the engine datastore
— the Almost Fall run reached across this boundary as a demonstrated temporary fallback; the
formalized engine-owned verification interface is now an ACTIVE separate workstream (see
shopya-collection-curation/SCRAPER_TOOL_KICKOFF.md). Availability verification and
catalog-ingest readiness are separate execution requirements; neither implies the other.

## Documents: the locked set (owner, 2026-08-09)

Top-level canon is SEVEN wizard docs: CLAUDE.md, SHOPYA_CAMPAIGN_CHARTER.yaml,
SHOPYA_CONTENT_CHARTER.proposed.yaml, docs/E2E_PROCESS.md, docs/CATEGORY_TAXONOMY.md,
docs/NAMING_CONVENTIONS.md, docs/NEXT_PASS_SCOPE.md. Creating any new top-level document
requires explicit owner approval (this was an owner rule from day one — enforce it).
Iteration output goes INTO the canonical doc as a version bump, or into the campaign's
review book — never a sibling file. One-shot prompts/work orders are archived on completion.
Per campaign run, the single living campaign document is review_book.md (r-series rounds);
iteration artifacts are marked superseded via `run.py supersede-artifact` as they are absorbed.
The /explore seams contract's source of truth is the FRONTEND repo
(agent_knowledge/sanity/PRESENTABLE_ASSETS.md + agent_knowledge/campaigns/
CAMPAIGN_AUTHORING_CONTRACT.md) — reference it; never duplicate it here.

## Scope

Authoring may span every seam relevant to the campaign. **Execution is Seam 6 only** — source
collections, product rails, the CSV. Everything else is a handoff brief, and a handoff is never
reported as implemented.

## Archived documents

`docs/archive/` holds superseded instructions, preserved as history. They are **not
authoritative** and must not be followed. See that directory's `README.md`.

## Start

```
python3 scripts/run.py new        # begin a run
python3 scripts/run.py status     # current state and its legal transitions
```
