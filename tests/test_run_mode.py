#!/usr/bin/env python3
"""Adversarial tests for the run-level run_mode identity (creation, defaults, immutability,
inheritance into Request v2).

    python3 tests/test_run_mode.py
"""
import os
import sys
import subprocess
import tempfile
import shutil

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN = os.path.join(ROOT, "scripts", "run.py")
VALIDATOR = os.path.join(ROOT, "scripts", "validate_state.py")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import generate_curation_request as wiz  # noqa: E402

PASS, FAIL = [], []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %s  %s%s" % ("PASS" if cond else "FAIL", name,
                          ("  <- " + detail) if detail and not cond else ""))


def _new(*extra):
    r = subprocess.run([sys.executable, RUN, "new", *extra], capture_output=True, text=True)
    rid = None
    for line in (r.stdout + r.stderr).splitlines():
        if line.startswith("run_id"):
            rid = line.split()[1]
    return rid, r.stdout + r.stderr


def _state_path(rid):
    return os.path.join(ROOT, "campaigns", "_drafts", rid, "state.yaml")


def _validate(rid):
    r = subprocess.run([sys.executable, VALIDATOR, "--state", _state_path(rid)],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def main():
    created = []
    try:
        # ---- default production ----
        rid, out = _new("--note", "run_mode test")
        created.append(rid)
        st = yaml.safe_load(open(_state_path(rid)))
        ok("normal new run defaults run_mode=production",
           st["run"]["run_mode"] == "production")
        ok("run_mode pinned in NEW history",
           st["workflow"]["history"][0].get("pinned_run_mode") == "production")
        rc, _ = _validate(rid)
        ok("production run validates", rc == 0)

        # ---- explicit diagnostic ----
        drid, _ = _new("--diagnostic")
        created.append(drid)
        dst = yaml.safe_load(open(_state_path(drid)))
        ok("--diagnostic creates run_mode=diagnostic", dst["run"]["run_mode"] == "diagnostic")

        # ---- run.py set cannot change run_mode (not settable) ----
        r = subprocess.run([sys.executable, RUN, "set", "--run", rid,
                            "--path", "run.run_mode", "--value", "diagnostic"],
                           capture_output=True, text=True)
        ok("run.py set REFUSES run.run_mode (not a settable path)",
           "not a settable path" in (r.stdout + r.stderr))

        # ---- manual tamper -> validator refuses (immutable) ----
        s = yaml.safe_load(open(_state_path(drid)))
        s["run"]["run_mode"] = "production"       # tamper diagnostic -> production
        yaml.safe_dump(s, open(_state_path(drid), "w"))
        rc, out = _validate(drid)
        ok("tampered run_mode is REFUSED (run_mode_mutated)",
           rc != 0 and "run_mode_mutated" in out)

        # ---- invalid run_mode refused ----
        s2 = yaml.safe_load(open(_state_path(rid)))
        s2["run"]["run_mode"] = "replay"
        # keep the NEW pin consistent so we test the ENUM check, not mutation
        for h in s2["workflow"]["history"]:
            if h.get("to") == "NEW":
                h["pinned_run_mode"] = "replay"
        yaml.safe_dump(s2, open(_state_path(rid), "w"))
        rc, out = _validate(rid)
        ok("invalid run_mode value is REFUSED (run_mode_invalid)",
           rc != 0 and "run_mode_invalid" in out)

        # ---- inheritance: request inherits run's mode; cannot self-promote ----
        prod_art, _ = wiz.build_request(
            {"run": {"run_id": "cmp_01KZCD765E6NNW2TZR1AFHQMWG", "run_mode": "production"},
             "identity": {"campaign_id": {"value": "c"}}}, "w.coats", 50)
        ok("generated request inherits production run_mode", prod_art["run_mode"] == "production")
        diag_art, _ = wiz.build_request(
            {"run": {"run_id": "cmp_01KZCD765E6NNW2TZR1AFHQMWG", "run_mode": "diagnostic"},
             "identity": {"campaign_id": {"value": "c"}}}, "w.coats", 50)
        ok("generated request inherits diagnostic run_mode", diag_art["run_mode"] == "diagnostic")
        # a request generated from a run has exactly the run's mode (no elevation knob)
        ok("generator has no way to elevate authority above the run",
           prod_art["run_mode"] == "production" and diag_art["run_mode"] == "diagnostic")

        # ---- a run with no run_mode (pre-1.7.0) cannot generate a v2 request ----
        none_art, errs = wiz.build_request(
            {"run": {"run_id": "cmp_x", "run_mode": None}, "identity": {"campaign_id": {}}},
            "w.coats", 50)
        ok("a run lacking run_mode cannot generate a v2 request", none_art is None and errs)
    finally:
        for rid in created:
            d = os.path.dirname(_state_path(rid))
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)

    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        for f in FAIL:
            print("  FAILED: %s" % f)
        sys.exit(1)


if __name__ == "__main__":
    main()
