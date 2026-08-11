---
description: Start or resume a Shopya campaign run
---

Read `CLAUDE.md`, then `prd.md` (the product/E2E authority) and
`schemas/workflow_state.schema.yaml` (the machine process).

Run `python3 scripts/run.py new` to begin, or `python3 scripts/run.py status --run <run_id>` to
resume. Mutate state only through `run.py`. Stop at every owner-decision gate.
