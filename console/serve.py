#!/usr/bin/env python3
"""console/serve.py — launcher for the thin local Campaign Console (task §19).

Runs the FastAPI app on 127.0.0.1 with uvicorn. Invoked by `python3 scripts/run.py serve`, which
re-execs this under the repo .venv (where fastapi/uvicorn live). Single owner, local, no auth.
"""
import argparse
import os
import sys

ROOT = os.environ.get("SHOPYA_CAMPAIGN_ROOT",
                      os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "console"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def main():
    ap = argparse.ArgumentParser(description="Shopya Campaign Console (local, single-owner).")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    os.environ.setdefault("SHOPYA_CAMPAIGN_ROOT", ROOT)
    import uvicorn
    uvicorn.run("api:app", host=a.host, port=a.port, log_level="info")


if __name__ == "__main__":
    main()
