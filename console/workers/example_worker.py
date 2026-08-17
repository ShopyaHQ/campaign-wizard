#!/usr/bin/env python3
"""example_worker.py — a reference external worker for SHOPYA_WIZARD_WORKER_CMD.

The Wizard invokes a configured command with the structured work request as JSON on stdin and reads
a structured result ({"objects":[{"kind","payload"},...]}) as JSON on stdout. This reference worker
demonstrates the contract with a deterministic, dependency-free implementation — the exact seam where
a real cognitive worker (e.g. a Claude-CLI wrapper) is plugged in WITHOUT the Wizard hard-coding
business authority or credentials. It reuses scripts/worker.py's payload builders so the output is a
valid structured artifact the Wizard then validates + registers.

Plug in a real agent by replacing _produce() with a call that hands the work request to the agent and
returns the agent's structured object(s). Keep it stdin→stdout JSON; keep credentials out of the repo.
"""
import json
import os
import sys

ROOT = os.environ.get("SHOPYA_CAMPAIGN_ROOT",
                      os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import worker as wk   # reuse the deterministic payload builders (reference only)


def _produce(work_request):
    wt = work_request["work_type"]
    ctx = work_request.get("context") or {}
    return {"objects": wk._fake_objects(wt, ctx)}


def main():
    raw = sys.stdin.read()
    work_request = json.loads(raw)
    result = _produce(work_request)
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
