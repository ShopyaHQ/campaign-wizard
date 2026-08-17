#!/usr/bin/env python3
"""test_taxonomy_neutral.py — the campaign-neutral taxonomy view (task §25, AF-008 regression).

Proves a FRESH campaign's generation input cannot read the historical Almost Fall SEL/avail
selection markers from the active taxonomy registry, while canonical ids + durable metadata are
preserved and the historical selection remains available SEPARATELY for audit.
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

PASS, FAIL = [], []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %s %s%s" % ("PASS " if cond else "FAIL ", name, "" if cond else "  << " + str(detail)))


MARKER_TOKENS = ("sel", "avail", "avail-candidate")


def _has_marker(s):
    if not isinstance(s, str) or not s.strip():
        return False
    return s.strip().lower().split()[0].strip("().,") in MARKER_TOKENS


def main():
    import taxonomy as tx
    reg = tx.neutral_registry()

    ok("neutral registry parses the real registry (many nodes)",
       len(reg["nodes"]) > 50, len(reg["nodes"]))
    ok("neutral registry is labelled campaign_neutral",
       reg["registry_kind"] == "campaign_neutral")

    # (1) no node carries the raw marker key
    leaked_key = [n["category_id"] for n in reg["nodes"] if "_af_marker" in n]
    ok("no node carries the raw _af_marker key in the neutral view", not leaked_key, leaked_key)

    # (2) no VALUE anywhere equals a bare selection marker token
    leaked_val = []
    for n in reg["nodes"]:
        for k, v in n.items():
            if _has_marker(v) and k not in ("boundary", "why_durable"):  # prose fields excluded
                leaked_val.append((n["category_id"], k, v))
    # stricter: no field's FIRST token is a bare marker at all
    strict = [(n["category_id"], k, v) for n in reg["nodes"] for k, v in n.items()
              if isinstance(v, str) and v.strip().lower() in MARKER_TOKENS]
    ok("no neutral field value is a bare SEL/avail marker", not strict, strict)

    # (3) assert_neutral is the enforced guard
    try:
        tx.assert_neutral(reg)
        ok("assert_neutral passes on the neutral registry", True)
    except ValueError as e:
        ok("assert_neutral passes on the neutral registry", False, e)

    # (4) canonical ids + durable metadata preserved
    ids = tx.requestable_category_ids()
    ok("canonical category ids preserved (e.g. w.coats present)", "w.coats" in ids, ids[:5])
    ok("durable metadata preserved (display/boundary/season on a node)",
       all(reg["nodes"][0].get(f) for f in ("display_name", "boundary", "season")),
       reg["nodes"][0])
    ok("verticals enumerable from the neutral view",
       set(reg["verticals"]) >= {"fashion", "home_interior", "tech", "beauty", "travel"},
       reg["verticals"])

    # (5) the historical selection is available SEPARATELY (audit-only), NOT in the generation input
    hist = tx.historical_selection()
    ok("historical Almost Fall selection is available separately (audit only)",
       len(hist) > 0 and "w.coats" in hist, len(hist))
    ok("the neutral registry and the historical selection are DISTINCT surfaces",
       "_af_marker" not in reg["nodes"][0] and isinstance(hist, dict))

    # (6) CONTAMINATION GUARD: a contaminated node is caught by assert_neutral
    contaminated = {"nodes": [{"category_id": "x.test", "leaked": "SEL"}]}
    try:
        tx.assert_neutral(contaminated)
        ok("assert_neutral REJECTS a node whose value is a bare marker", False, "should have raised")
    except ValueError:
        ok("assert_neutral REJECTS a node whose value is a bare marker", True)
    try:
        tx.assert_neutral({"nodes": [{"category_id": "x", "_af_marker": "SEL"}]})
        ok("assert_neutral REJECTS a node still carrying _af_marker", False, "should have raised")
    except ValueError:
        ok("assert_neutral REJECTS a node still carrying _af_marker", True)

    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
