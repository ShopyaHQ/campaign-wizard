# Shopya Campaign Wizard

Runs a fixed, checkpoint-gated interview to lock a campaign concept, then curates the
products that fill it. Produces two artifacts per run and writes to nothing else.

    new campaign        (or /new-campaign)

- `CLAUDE.md` — the rules that are always true. Read automatically.
- `.claude/skills/new-campaign/` — the process: stages, gates, interview.
- `campaigns/<campaign-id>/` — one folder per run. Frozen when the run closes.
- `scripts/` — probe, slot, assemble.

Requires the sibling curation engine for Stage 4:

    ~/Desktop/CollectionCuration/          the engine (fetch profiles, log, write path)
    ~/Desktop/shopya-campaign-wizard/      this repo

Connect both folders to the Cowork session before running.
