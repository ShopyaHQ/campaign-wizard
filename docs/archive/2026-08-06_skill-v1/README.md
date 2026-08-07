# Archive — instruction bundle v1, superseded 2026-08-06

**These documents are HISTORICAL. They are not authoritative and must not be followed.**

This directory holds the ten active-instruction files as they stood immediately before the
2026-08-06 reconciliation, preserved byte-for-byte. They are kept because they are the record of
how the process was reasoned about while it was being built, and because several of them are
cited as evidence in `SHOPYA_CAMPAIGN_CHARTER.yaml` for claims that supersede them.

Nothing in here describes the system as it works today.

## Contents

```
CLAUDE.md                              the original project kickoff/proposal document
skills/new-campaign/SKILL.md           the v1 skill
skills/new-campaign/references/        brief · csv_contract · interview · landscape ·
                                       naming_and_seo · plain_statement · render_rules
commands/new-campaign.md               the v1 slash command
```

## Why they were superseded

Nine direct contradictions with the current charter, schemas and workflow were identified in the
2026-08-06 reconciliation audit. Three were critical:

1. **The described process does not exist.** SKILL.md describes eight stages. The workflow
   specification in `schemas/workflow_state.schema.yaml` defines a different and larger set of
   states and transitions, and that file is the authority.
2. **No awareness of the control model.** Across all nine instruction files there is not one
   mention of `run.py`, `validate_state.py`, `state.yaml`, owner decisions, transitions,
   `run_id`, or `settable_paths` — which are the mechanisms the system actually runs on. An
   agent following these files would hand-edit state and bypass every gate.
3. **A disproved render rule.** `CLAUDE.md` and `references/render_rules.md` both state that a
   rail below twelve members "silently vanishes". The drop threshold is zero items; 12/10/12 are
   display caps. The charter records both files as the source of this false claim
   (`constraint_repo_001`, `surface_007`).

Six further contradictions concerned the `> 50 items` collection target, absolute
frozen-collection immutability, "exactly two deliverables", `collection_rank` as the pin-order
driver, the verbatim five-question interview, and the mandatory Plain Statement.

## What was preserved rather than discarded

Three requirements found only in these files are being carried forward into the current
contracts under a separate change: the three-layer campaign/collection/rail naming model
(`references/naming_and_seo.md`), the Group C scrape-output fields (`CLAUDE.md`), and the CSV
ordering and admin-execution facts (`references/csv_contract.md`).

## Note on the originals

The seven files under `skills/new-campaign/references/` still exist at their original path.
Nothing references them any longer — the replacement SKILL.md does not read them and the
replacement command does not name them — so they are orphaned rather than active. Removing them
from the working tree is a separate, git-reviewable change.
