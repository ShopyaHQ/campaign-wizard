# Shopya Campaign Wizard

Plans campaigns for Shopya and produces the Seam 6 execution package: source collections,
product rails, and the CSV a human executes in admin. Everything else it authors is a handoff.

## What this tool is / Definition of Done

The product is seven steps:

1. Start `/new-campaign`.
2. Run fresh current-trend research and report what is happening.
3. Work back and forth with the owner to refine and explicitly approve the campaign direction.
4. Lock the campaign premise, collections/rails, tone/copy, and product-selection logic
   through that conversation.
5. Produce the frontend campaign content and execution artifacts.
6. Run the existing CSV builder, and validate the resulting worklist for the concrete
   execution requirements already implemented.
7. Deliver the CSV/handoff. End.

**Definition of done:** a fresh invocation can take a real campaign from zero context to final
CSV through an interactive, human-approved campaign-development loop, without the owner
needing to understand or manually repair the underlying workflow.

**Acceptance test:** start a completely new campaign with only the normal information an owner
would reasonably provide. Run fresh research. Work with the owner naturally until the campaign
is something they would actually publish. Produce the campaign, collections, rails, frontend
content and products, then generate the CSV. If that works end to end, v1 is done.

**Operating constraint — any proposed work must answer: what failure in that end-to-end
experience does this fix?** The states, validators and charters below are supporting machinery,
judged only by whether they make those seven steps reliable. They are not the product.

## Deferred / not required for v1 done

README cleanup · duplicate `status:` key in the workflow schema · functional schema-version
pinning · archive semantics · replay/supersede mechanics · additional schemas or workflow
expansion not demonstrated necessary by the acceptance run. Parked, not lost. Do not work on
these unless the acceptance run exposes one as a concrete blocker.

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

## Naming conventions (owner-locked, 2026-08-07)

Three separate identities, never conflated in one filename: campaign_id (human, kebab-case),
run_id (immutable cmp_<ULID>), build_id (b001, b002 — immutable execution revisions, never
overwritten). Full rules: docs/NAMING_CONVENTIONS.md. Both halves are live as of
2026-08-07: execution-asset naming AND the campaigns/<campaign_id>/runs/<run_id>/ layout
(_drafts/ for unnamed kickoffs; `run.py promote` performs the controlled promotion when
campaign_id locks; artifact paths are stored run-root-relative).

## Engine/wizard boundary (owner ruling, 2026-08-07)

CollectionCuration owns product truth: discovery, fetching, normalized observations (identity,
canonical PDP, retailer/brand, price/currency, availability, variants, timestamps, verification
provenance). The Campaign Wizard owns campaign judgment: which products belong, collection/rail
assignment, editorial ordering, annotations, copy, approvals, and the execution worklist. The
wizard consumes product truth READ-ONLY; the builder's refusal to run without the engine log is
deliberate boundary enforcement. The wizard does not append observations to the engine datastore
— the Almost Fall run reached across this boundary as a demonstrated temporary fallback, and the
formalized engine-owned verification interface is next-pass work (see docs/NEXT_PASS_SCOPE.md).

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
