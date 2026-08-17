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

## Campaign Console (local GUI)

The owner-facing interface is a thin local web console over the Wizard Core spanning the WHOLE campaign
lifecycle (prd.md §15.1–§15.2): Kickoff → Research + Direction → Premise + Verticals → Architecture →
Build This → Fulfillment → Execution → Approved for Implementation → Live → Review. After Build This the
Console generates the Request v2 set, shows fulfillment/material-exception status, ingests receipts, and
then **Generate Execution Package** runs the Wizard's post-fulfillment merchandising (it selects, orders
and pins the fulfilled eligible products into the campaign's rails/collections, loads the receipt-bound
Truth Export automatically, and builds+validates the A–G package + F manifest) — the owner supplies **no**
truth export, product IDs, curated rows or Master CSV, then takes the manifest-bound Approve for
Implementation. The owner does not fall back to the CLI or an agent. One-time setup, then one launch command:

    python3 -m venv .venv
    .venv/bin/pip install -r console/requirements.txt   # fastapi, uvicorn, jinja2, python-multipart, httpx
    python3 scripts/run.py serve                         # http://127.0.0.1:8765  (Ctrl-C to stop)

Single owner, local only (binds 127.0.0.1), no auth, no database, no deploy. The console and the CLI
are two adapters over the same `scripts/checkpoint_core.py`; the CLI keeps working under system Python
with none of the console dependencies:

    python3 scripts/run.py current-checkpoint --run <id>   # the current checkpoint, the Wizard's way
    python3 scripts/run.py answer-checkpoint  --run <id> --payload <p>
    python3 scripts/run.py request-revision   --run <id> --ops-json '[{"op":"set","path":"…","value":"…"}]'
    python3 scripts/run.py run-next           --run <id>   # run the research/synthesis worker behind the Wizard
    python3 scripts/run.py approve-checkpoint --run <id> --by product_owner
    python3 scripts/run.py diff-object        --run <id> --kind campaign_spec

### Worker configuration (research/synthesis behind the Wizard)

`run-next` and the Console's "Run research / Run next" button execute a real cognitive worker BEHIND
the Wizard: the Wizard determines the work, invokes the worker, validates the returned structured
artifact, and registers it. The owner interacts only with the Console — never with Claude directly.

**Default (recommended): the bundled Claude worker.** If the `claude` CLI is installed and
authenticated, it is auto-detected — no configuration needed:

    claude --version          # confirm the Claude CLI is installed + logged in
    python3 scripts/run.py serve
    # the Console header shows: Agent worker: Ready (Claude CLI)

The bundled worker (`console/workers/claude_worker.py`) invokes Claude non-interactively, performs
real current web research for the research phase, and returns a strict JSON envelope. It runs in a
throwaway temp directory so it cannot read the repo (no CLAUDE.md / golden benchmark / historical
Almost Fall material) — generation stays uncontaminated.

**Production fails closed.** A production run with no real worker available raises
`worker_unavailable` — the deterministic fake worker is NEVER a silent production fallback. The fake
is used only by automated tests and explicit diagnostic runs.

**Override the worker** with your own command (must read a JSON work request on stdin and write
`{"objects":[{"kind","payload"},…]}` on stdout; keep credentials out of the repo):

    export SHOPYA_WIZARD_WORKER_CMD='python3 console/workers/example_worker.py'

`console/workers/example_worker.py` is a deterministic reference worker (the contract, for tests).
Prove the real path end-to-end (live Claude, network) with the manual smoke:

    python3 tests/smoke_real_claude_worker.py   # disposable run; real research → Premise + Vertical Review

## Run / test

    python3 tests/test_validator.py            # and the other tests/*.py suites (system Python)
    .venv/bin/python tests/test_console_api.py # the API + GUI + synthetic E2E suite (needs the venv)
    python3 scripts/run.py validate --run <id> # validate a run's state

The state file is never hand-edited — every mutation goes through `scripts/run.py`.
