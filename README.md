# Shopya Campaign Wizard

Plans a Shopya campaign end to end and produces the human execution package (source collections,
product rails, the master execution CSV, and the seam/content handoffs). It consumes product truth
read-only from the CollectionCuration engine and never authors it.

    python3 scripts/run.py new        # begin a run
    python3 scripts/run.py status     # current state + legal transitions

## Where authority lives

- **`prd.md`** — the normative product & end-to-end operating model (lifecycle, owner checkpoints,
  structured objects, repo boundaries, handoffs, invariants).
- **`CLAUDE.md`** — the concise boot/authority map; read automatically.
- **`SHOPYA_CAMPAIGN_CHARTER.yaml`** — hard runtime/policy rules (numeric contracts) by rule ID.
- **`SHOPYA_CONTENT_CHARTER.yaml`** — editorial / merchandising / SEO / three-object-model rules.
- **`schemas/workflow_state.schema.yaml`** — machine states, transitions, refusals.
- **`docs/NAMING_CONVENTIONS.md`** — identifier / portable-asset / review-series grammar.

## Repo boundary

The sibling **`shopya-collection-curation`** engine owns product truth and fulfillment. The two
versioned cross-repo contracts are `curation_request_schema.yaml` (Wizard→Engine) and
`truth_export_schema.yaml` (Engine→Wizard). See `prd.md` §2 and §9–§13.

## Run / test

    python3 tests/test_validator.py            # and the other tests/*.py suites
    python3 scripts/run.py validate --run <id> # validate a run's state

The state file is never hand-edited — every mutation goes through `scripts/run.py`.
