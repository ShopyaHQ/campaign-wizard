#!/usr/bin/env python3
"""Stage 0 interpretation regression tests.

    python3 tests/test_stage0.py

Each case corresponds to a real failure recorded in a run's learning.yaml. They assert against
EVERY Stage 0 frame present in campaigns/, so a future frame cannot quietly reintroduce a
corrected mistake. Structure and interpretation discipline only — never content quality.
"""
import glob, os, re, subprocess, sys
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNNER = os.path.join(ROOT, "scripts", "run.py")
QUARANTINE = "_to_delete"

PASS, FAIL = [], []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %s  %s%s" % ("PASS" if cond else "FAIL", name, ("  <- " + detail) if detail and not cond else ""))


def frames():
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "campaigns", "*", "frame.yaml"))):
        if os.sep + QUARANTINE + os.sep in p:
            continue
        with open(p, encoding="utf-8") as f:
            out.append((os.path.basename(os.path.dirname(p)), yaml.safe_load(f)))
    return out


def blob(x):
    """Flatten any nested structure to one lowercase string."""
    if isinstance(x, dict):
        return " ".join(blob(v) for v in x.values())
    if isinstance(x, list):
        return " ".join(blob(v) for v in x)
    return str(x).lower()


COUNTERFACTUAL = ["otherwise would", "than they would", "incremental", "causal lift",
                  "baseline-relative", "more than they", "uplift"]
NEVER_SUPPLIED = ["shop now", "buy now", "don't miss", "dont miss", "limited time",
                  "save money", "act fast", "urgency", "hurry"]


def main():
    fs = frames()
    ok("at least one Stage 0 frame exists", bool(fs))
    if not fs:
        sys.exit(1)

    for rid, fr in fs:
        tag = rid[:12]
        oi = fr.get("owner_inputs") or {}
        tm = fr.get("timing") or {}
        ob = fr.get("objective") or {}
        av = fr.get("avoidance") or {}
        sc = fr.get("scope") or {}
        ms = fr.get("measurement") or {}

        print("\n-- %s --" % rid)

        # 1 · LRN-001
        rl = oi.get("requested_launch") or {}
        el = tm.get("earliest_actual_campaign_launch") or {}
        ok("[%s] today normalizes to a date but does not prove launch is possible" % tag,
           bool(rl.get("normalized_date")) and tm.get("requested_launch_date") is not None
           and el.get("value") is None and el.get("interpretation_status") == "not_supplied",
           "earliest_actual_campaign_launch=%r" % el)

        # 2 · LRN-002
        ph = oi.get("planning_horizon") or {}
        de = tm.get("desired_campaign_end") or {}
        ok("[%s] planning horizon does not populate a campaign end date" % tag,
           ph.get("minimum_weeks") is not None and ph.get("maximum_weeks") is not None
           and de.get("value") is None and de.get("interpretation_status") == "not_supplied",
           "desired_campaign_end=%r" % de)

        # 3 · LRN-003
        hits = [w for w in COUNTERFACTUAL if w in blob(ob) + blob(oi.get("objective"))]
        ok("[%s] objective makes no counterfactual or lift claim" % tag,
           not hits and ms.get("causal_incrementality_measurable") is False,
           "found %s" % hits)

        # 4 · LRN-004
        added = [w for w in NEVER_SUPPLIED
                 if w in blob(av) + blob(fr.get("hard_constraints")) + blob(oi.get("exclusions"))]
        ar = av.get("additional_restrictions") or {}
        ok("[%s] no exclusions the owner never supplied" % tag,
           not added and ar.get("value") in ([], None)
           and ar.get("interpretation_status") == "not_supplied",
           "found %s / additional_restrictions=%r" % (added, ar))

        # 5 · LRN-005
        ok("[%s] prohibited framing may still be described in research" % tag,
           av.get("evidence_may_describe_prohibited_frames") is True
           and av.get("prohibited_frames_may_not_be_adopted_as_recommendations") is True)

        # 6 · LRN-006
        avail = sc.get("seams_available_for_consideration") or []
        sel = sc.get("selected_seams")
        ok("[%s] available seams do not appear as selected" % tag,
           len(avail) > 0 and sel == [] and not set(avail) & set(sel or []),
           "available=%s selected=%r" % (avail, sel))

        # 7 · LRN-007
        px = ms.get("proxy") or {}
        ok("[%s] no measurement proxy is automatically selected" % tag,
           px.get("value") is None and px.get("interpretation_status") == "not_supplied"
           and ms.get("retrieval_status") in ("unknown", "unavailable",
                                              "externally_queryable", "queryable"),
           "proxy=%r" % px)

        # every owner-input field carries a status
        missing = [k for k, v in oi.items()
                   if not isinstance(v, dict) or not v.get("interpretation_status")]
        ok("[%s] every owner-input field declares interpretation_status" % tag,
           not missing, "missing on %s" % missing)

    print("\n-- interface --")
    rid = fs[0][0]
    r = subprocess.run([sys.executable, RUNNER, "review-inputs", "--run", rid],
                       capture_output=True, text=True)
    out = r.stdout
    # 8 — assert the MECHANISM, not a transient value. Once the owner confirms a proposal it
    # is no longer proposed, so asserting on live output alone made this test decay.
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import importlib.util as _il
    _sp = _il.spec_from_file_location("runmod", RUNNER)
    _m = _il.module_from_spec(_sp); _sp.loader.exec_module(_m)
    ok("a proposed value renders as needing confirmation",
       "YES" in _m.CONFIRM["proposed"] and _m.CONFIRM["inferred"].startswith("no")
       and _m.CONFIRM["not_supplied"].startswith("no"))
    ok("review-inputs reports its pending count either way",
       ("need confirmation" in out) or ("Nothing needs confirmation" in out), out[-300:])
    ok("review-inputs labels inferences without demanding confirmation",
       "no - labelled inference" in out)
    ok("review-inputs shows not-supplied values rather than hiding them",
       "the owner did not supply this" in out)
    ok("review-inputs states that lift is not claimed", "not claimed" in out)
    ok("review-inputs creates no decision and no transition",
       "record-decision" not in out.split("Confirm with:")[0] and r.returncode == 0)

    print("\n-- quarantine --")
    r = subprocess.run([sys.executable, RUNNER, "list"], capture_output=True, text=True)
    ok("quarantine is not discovered as a run", QUARANTINE not in r.stdout)
    stray = os.path.join(ROOT, "campaigns", QUARANTINE, "state.proposed.stray.yaml")
    if os.path.exists(stray):
        r = subprocess.run([sys.executable, RUNNER, "register-artifact", "--run", rid,
                            "--key", "_probe", "--path", stray], capture_output=True, text=True)
        ok("quarantined file cannot be registered as an artifact",
           r.returncode != 0 and "quarantined" in (r.stdout + r.stderr))

    print("\n-- schema lint --")
    bad = []
    for p in glob.glob(os.path.join(ROOT, "schemas", "*.yaml")):
        for i, line in enumerate(open(p, encoding="utf-8"), 1):
            if re.match(r"^\s*[A-Za-z_]+:\{", line):
                bad.append("%s:%d" % (os.path.basename(p), i))
    ok("no missing space after a mapping colon in any schema", not bad, str(bad))

    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        for f in FAIL:
            print("  FAILED: %s" % f)
        sys.exit(1)


if __name__ == "__main__":
    main()
