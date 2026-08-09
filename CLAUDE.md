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
5. **`SHOPYA_CONTENT_CHARTER.yaml`** — approved editorial, voice and merchandising rules, and
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
docs/E2E_PROCESS.md and the two versioned handoff schemas
(shopya-collection-curation/{curation_request_schema,truth_export_schema}.yaml).

## Process, output model, naming — canonical homes

- What a completed campaign IS (four parallel outputs, the six approval gates, fulfillment,
  the final execution package): docs/E2E_PROCESS.md — orchestration that references rule IDs.
- The three-object model, merchandising, editorial/SEO, voice/anti-slop: SHOPYA_CONTENT_CHARTER.yaml.
- The >=50 collection-depth floor and other numeric/technical contracts: campaign charter (render_003).
- Naming/identity/build/review conventions: docs/NAMING_CONVENTIONS.md.
Do not restate those rules here; this file points at their one home.

## Documents: the locked set

Top-level canon is SEVEN wizard docs: CLAUDE.md, SHOPYA_CAMPAIGN_CHARTER.yaml,
SHOPYA_CONTENT_CHARTER.yaml, docs/E2E_PROCESS.md, docs/CATEGORY_TAXONOMY.md,
docs/NAMING_CONVENTIONS.md, docs/NEXT_PASS_SCOPE.md. Creating any new top-level document
requires explicit owner approval. Iteration goes INTO the canonical doc (version bump) or the
campaign's review_book.md — never a sibling file. The /explore seams contract's source of truth
is the FRONTEND repo (agent_knowledge/…) — reference it; never duplicate it here.

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
