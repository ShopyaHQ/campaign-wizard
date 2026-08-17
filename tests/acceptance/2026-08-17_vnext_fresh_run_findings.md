# ACCEPTANCE FINDINGS LEDGER — fresh vNext `/new-campaign` run, 2026-08-17

**NON-AUTHORITATIVE.** This file is an acceptance-run observation record for the GUI pre-build
study. It is **not** canon, not process authority, not campaign authority, and not a creative or
research input to any campaign. Nothing here may be cited as a rule. It is scoped to run
`cmp_01M082A54KGFHF14AD5G7DG3KJ` and to the state of the two repos recorded below.

| | |
|---|---|
| Run | `cmp_01M082A54KGFHF14AD5G7DG3KJ` (run_mode `production`, spec 1.8.0, charter 0.8.0) |
| Wizard HEAD | `821d78b2c9723c0953e1c4149045c6b4621c80ee` — "Wire vNext front half into workflow and Request v2 generation" |
| Engine HEAD | `99d865b1dbc14938b467c8d31d7cffb926bb0e26` — "Add Curation Receipt and Fulfillment Exception artifacts" |
| Started | 2026-08-17T14:34:20Z |
| Code changed during run | none so far |
| Revisions registered | research_brief rb_001 r001 -> r002 (owner revision, 2026-08-17T14:45Z) |

---

## AF-001
- **checkpoint / timestamp:** §0 starting state · 2026-08-17T14:30Z
- **category:** NONBLOCKING TECH DEBT
- **severity:** P3
- **object/command:** `python3 -m pytest -q` at the Wizard repo root
- **expected:** files named `tests/test_*.py` are collected and run by pytest
- **actual:** `collected 0 items` / `no tests ran`, exit 2. The suites are argv-less scripts with a
  `main()` under `if __name__ == "__main__"`, not pytest test functions. Run directly they pass:
  335 assertions across 13 Wizard files, 341 across 11 Engine files, 0 failures.
- **repro:** `cd <wizard> && python3 -m pytest -q`
- **evidence:** README.md:26-28 documents the real runner (`python3 tests/test_validator.py`).
- **owner impact:** none directly; operator/CI confusion only. Exit is non-zero, so no false green.
- **workaround:** ran every suite directly, per README.
- **code changed:** no
- **disposition:** log only
- **GUI implication:** a Console "run checks" affordance must invoke the real runner, not pytest.

## AF-002
- **checkpoint / timestamp:** Checkpoint 1 KICKOFF REVIEW · 2026-08-17T14:37Z
- **category:** UX FRICTION (also AGENT-DEPENDENCY LEAK)
- **severity:** P2
- **object/command:** `FRAME_READY -> RESEARCHING` entry prerequisites
- **expected:** one owner checkpoint produces one recorded owner decision
- **actual:** the transition requires TWO decision records for the same single owner act —
  `kickoff_approved` (typed, hash-bound, via `approve-object`) **and** the legacy
  `frame_accepted` (untyped, unbound, via `record-decision`). Neither alone passes.
- **repro:** `python3 scripts/run.py validate --run <run> --to RESEARCHING` after registering the
  brief → `REFUSED — 2 failure(s)`: `owner_decisions.kickoff_approved` absent AND
  `owner_decisions.frame_accepted` absent.
- **evidence:** `schemas/workflow_state.schema.yaml` RESEARCHING.entry_prerequisites (the comment
  states "kickoff_approved IS frame_accepted for vNext; the legacy id is kept for pre-1.8.0 runs").
- **owner impact:** the owner says "approve" once; the operator must remember to write two records.
  No correctness hole (missing either one is correctly refused) — the risk is operator error and
  the appearance of two decisions in the audit trail where the owner made one.
- **note:** the same dual-record pattern recurs at direction (`direction_selected_v2` +
  `opportunity_selected`), premise (`brief_approved`) and architecture (`route_selected`). To be
  confirmed at each checkpoint as the run proceeds.
- **workaround:** none yet (checkpoint not yet approved)
- **code changed:** no
- **disposition:** log only (P2 — not fixed during the run, per §8)
- **GUI implication:** one Approve button must emit the whole decision set atomically; the legacy id
  should never be an operator-visible concept.

## AF-003
- **checkpoint / timestamp:** Checkpoint 1 KICKOFF REVIEW · 2026-08-17T14:38Z
- **category:** MISSING CONTROL (also PRESENTATION GAP)
- **severity:** P2
- **object/command:** `python3 scripts/run.py review-inputs --run <run>`
- **expected:** the sanctioned owner-facing kickoff review renderer works on a fresh vNext run
- **actual:** `FATAL: no current frame artifact registered for this run.` The command reads only the
  legacy `frame` artifact, which a vNext run does not produce (FRAME_READY passes on the structured
  `research_brief` alone). There is **no** sanctioned renderer for `research_brief`,
  `research_ledger`, `campaign_directions` or `campaign_spec`.
- **repro:** `run.py new` → `register-object --kind research_brief` → `transition --to FRAME_READY`
  → `review-inputs`
- **evidence:** `scripts/run.py:cmd_review_inputs` (frame-only); run dir contains only
  `research_brief.r001.yaml` + `state.yaml`.
- **owner impact:** HIGH for this study. Every checkpoint report in this run is hand-rendered by
  the agent from the YAML. The presentation standard in §5 is currently an agent behaviour, not a
  product capability — exactly the dependency the GUI is meant to remove.
- **workaround:** agent renders the checkpoint report from the registered revision file.
- **code changed:** no
- **disposition:** log only (P2)
- **GUI implication:** MUST HAVE. The five checkpoint reports are the GUI's primary surface, and
  they need a machine renderer (API returning the structured object + provenance split), not prose.

## AF-004
- **checkpoint / timestamp:** Checkpoint 1 KICKOFF REVIEW · 2026-08-17T14:36Z
- **category:** OBSERVABILITY GAP (also PRESENTATION GAP)
- **severity:** P2
- **object/command:** `python3 scripts/run.py status --run <run>`
- **expected:** status shows where the run is in the five-checkpoint ladder, which decision is next,
  and the exact id/revision/hash that decision would bind
- **actual:** status prints state, versions, campaign_id, an artifact list by filename, a decision
  count and the legal next states. It shows **no** structured-object id, revision, canonical hash,
  section hashes, checkpoint position, or pending-approval list.
- **repro:** `run.py status --run cmp_01M082A54KGFHF14AD5G7DG3KJ`
- **evidence:** to obtain the hash this checkpoint binds
  (`35ce3486…78e2`) the operator must open `state.yaml` (`structured_objects.research_brief`) or the
  revision file directly.
- **owner impact:** §4 requires showing the owner the exact hash a decision binds; the sanctioned
  interface does not surface it. Every checkpoint needs a manual state-file read.
- **workaround:** parsed `state.yaml` with a one-off python read.
- **code changed:** no
- **disposition:** log only (P2)
- **GUI implication:** MUST HAVE — a run header with checkpoint chips (1..5), current object
  id/revision, and hash behind a "Details" disclosure.

## AF-005
- **checkpoint / timestamp:** Checkpoint 1 KICKOFF REVIEW · 2026-08-17T14:35Z
- **category:** MISSING CONTROL
- **severity:** P3
- **object/command:** `run.py register-object --kind research_brief --payload <file>`
- **expected:** a sanctioned way to obtain the required payload shape for a structured object
- **actual:** no scaffold/template/`--print-schema` command exists. The operator must read
  `schemas/front_half_objects.schema.yaml` + `scripts/front_half.py` and hand-author the JSON;
  otherwise required fields are discovered one refusal at a time.
- **repro:** `run.py register-object --help` (no scaffold subcommand exists)
- **owner impact:** none directly (operator-side), but it is a place where a correct payload depends
  on the agent having read the schema rather than on the tool.
- **workaround:** read the schema and the builder before authoring; payload accepted first attempt.
- **code changed:** no
- **disposition:** log only
- **GUI implication:** the kickoff form IS the scaffold; the API needs a shape/validation endpoint.

## AF-006
- **checkpoint / timestamp:** §0 starting state · 2026-08-17T14:34Z
- **category:** PRESENTATION GAP
- **severity:** P3
- **object/command:** every `validate_state.py` invocation
- **expected:** a reserved, inactive enforcement path is not narrated on every run
- **actual:** `WARNING: withdrawal enforcement inactive: charter.withdrawn_versions is not defined
  (reserved, v1)` prints on every validate; at `run.py new` it prints **twice**.
- **repro:** `run.py new`
- **owner impact:** low — noise at the top of every owner-facing command output.
- **code changed:** no
- **disposition:** log only
- **GUI implication:** validator output needs severity channels so a GUI can suppress reserved-path
  notices and surface real refusals.

## AF-007
- **checkpoint / timestamp:** §0 starting state · 2026-08-17T14:33Z
- **category:** NONBLOCKING TECH DEBT
- **severity:** P3
- **object/command:** `prd.md` §22 implementation-mapping appendix
- **expected:** §22 reflects the audited current state (CLAUDE.md defers to it for what is built)
- **actual:** two back-half rows are stale. §22 records "Assembly + validation — **Partial** …
  validation/manifest currently bind the products CSV, not the full package" and "Execution
  approval — Enforced with the §16.5 coherence defect open", while CLAUDE.md's "Now implemented"
  section records the complete A–G package + immutable F manifest + manifest-bound approval + the
  post-validation coherence fix, and `tests/test_execution_package.py` (26),
  `test_package_validation_approval.py` (14) and `test_post_approval_reopen.py` (33) all pass.
- **owner impact:** the §0 "docs agree" check needed cross-reading three sources. Front-half rows
  are accurate and agree with the schema; only the back-half rows drift.
- **code changed:** no
- **disposition:** log only — does not affect this run's front half.
- **GUI implication:** none.

## AF-008
- **checkpoint / timestamp:** Checkpoint 1 KICKOFF REVIEW (owner revision) · 2026-08-17T14:44Z
- **category:** CORRECTNESS (fresh-run contamination control)
- **severity:** P2
- **object/command:** `docs/CATEGORY_TAXONOMY.md` — the platform SSOT category registry
- **expected:** on a fresh run whose protocol seals all historical Almost Fall material, the
  canonical registry a campaign MUST select from can be read without exposing the historical
  Almost Fall selection set
- **actual:** the registry embeds per-node historical campaign annotations inline. Its header
  declares `AF = Almost Fall status (SEL = selected this campaign · avail = in registry, not
  selected now)` and every node line ends in a `SEL`/`avail` marker. Reading the registry for a
  legitimate, campaign-neutral purpose (enumerating the seven current Shopya verticals for the
  brief's `territory` scope) unavoidably exposed the operator to the historical Almost Fall
  selection markers for the women's-fashion nodes. No unannotated or filtered view exists.
- **repro:** `sed -n 1,40p docs/CATEGORY_TAXONOMY.md`
- **evidence:** header lines 17-21; node lines under `## WOMEN'S FASHION`.
- **owner impact:** the "benchmark is sealed" guarantee is weaker than it reads. The golden
  benchmark doc was NOT opened, but the historical selection set leaks through the registry the
  campaign is required to use. For an acceptance run whose purpose is proving INDEPENDENT
  generation, this is a real isolation gap.
- **workaround / declaration:** exposure is declared here rather than concealed. The `SEL`/`avail`
  markers are treated as contaminated and will NOT be used as a selection input at the
  ARCHITECTURE checkpoint; collection selection will be justified from this run's own
  `research_ledger`. The registry's own header already states the markers are non-canonical
  annotations and that the canonical historical selection lives in the campaign review book —
  which remains unopened.
- **code changed:** no
- **disposition:** log only (P2 — per §8 not fixed during the run)
- **GUI implication:** a campaign-neutral registry view (or annotations moved out of the SSOT into
  per-campaign records) is needed before a Console surfaces the taxonomy for selection.

## AF-009
- **checkpoint / timestamp:** Checkpoint 1 KICKOFF REVIEW (owner revision) · 2026-08-17T14:46Z
- **category:** OBSERVABILITY GAP (also PRESENTATION GAP)
- **severity:** P2
- **object/command:** `register-object --kind research_brief` producing `rb_001/r002`
- **expected:** when an owner revision mints a new immutable revision, a sanctioned command shows
  what materially changed between the prior and the new revision
- **actual:** no diff capability exists anywhere in `run.py` (subcommands: new · list · status ·
  record-decision · supersede-artifact · validate-execution · ingest-receipt ·
  resolve-material-exception · build-package · validate-package · register-object ·
  select-direction · approve-object · approve-package · verify-live · reopen · migrate · promote ·
  register-artifact · set · review-inputs · unregister-artifact · validate · transition).
  `register-object` prints only the new hash. The spine records `r001`/`r002` hashes with no delta.
  Both revision files are on disk, so a diff is possible — but only by hand.
- **repro:** register a second revision, then look for any sanctioned way to see the change set.
- **evidence:** to tell the owner what changed I ran a one-off python field comparison:
  changed = revision · campaign_window · territory · exclusions · owner_inputs · inferred_inputs ·
  assumptions · unresolved_questions · provenance; unchanged = brief_id · campaign_id · run_id ·
  objective · desired_behavior · market · audience_context.
- **owner impact:** HIGH at every revision cycle. The owner is asked to approve a new hash without
  any product-provided evidence of what moved; they must trust the agent's narration. This
  directly weakens the hash-binding guarantee's usefulness — the binding is exact, but what it
  binds is not legible.
- **workaround:** hand-computed field-level comparison, reported in the checkpoint.
- **code changed:** no
- **disposition:** log only (P2)
- **GUI implication:** MUST HAVE — a revision diff view (r001 -> r002, changed sections highlighted,
  per-section hashes for `campaign_spec`) is the single highest-value surface observed so far.

## AF-010
- **checkpoint / timestamp:** Checkpoint 1 KICKOFF REVIEW (owner revision) · 2026-08-17T14:45Z
- **category:** MISSING CONTROL
- **severity:** P3
- **object/command:** `register-object --payload <whole object>`
- **expected:** an owner revision touching four fields can be applied field-wise
- **actual:** revisions are whole-object only. Applying four owner edits required re-authoring the
  entire payload including all seven unchanged fields; `run.py set` writes only `settable_paths` in
  `state.yaml` (identity, display_name, execution_tracking, collection_freeze) and cannot touch a
  structured object. Any accidental drift in an untouched field would silently mint a new hash.
- **repro:** `run.py set --help`; `schemas/workflow_state.schema.yaml:settable_paths`
- **owner impact:** indirect. Combined with AF-009 (no diff) the system has no mechanism that would
  catch an unintended change to a field the owner did not ask to change.
- **workaround:** carried unchanged fields forward verbatim, then verified by field comparison that
  exactly the intended fields changed.
- **code changed:** no
- **disposition:** log only
- **GUI implication:** the checkpoint form should edit fields and let the API assemble the revision.

---

### Counts so far
P0: 0 · P1: 0 · P2: 5 (AF-002, AF-003, AF-004, AF-008, AF-009) · P3: 5 (AF-001, AF-005, AF-006, AF-007, AF-010)
