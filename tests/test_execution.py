#!/usr/bin/env python3
"""Execution-readiness tests: the feed cap, the CSV rail contract, and availability.

    python3 tests/test_execution.py

Covers the three corrections in the execution-readiness pass. No pytest dependency.
"""
import csv, json, os, shutil, subprocess, sys, tempfile
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VALIDATOR = os.path.join(ROOT, "scripts", "validate_state.py")
BUILD = os.path.join(ROOT, "scripts", "build_csv.py")
SCHEMA = os.path.join(ROOT, "schemas", "workflow_state.schema.yaml")
CHARTER = os.path.join(ROOT, "SHOPYA_CAMPAIGN_CHARTER.yaml")
ENGINE = os.path.join(os.path.dirname(ROOT), "shopya-collection-curation")

PASS, FAIL = [], []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %s  %s%s" % ("PASS" if cond else "FAIL", name, ("  <- " + detail) if detail and not cond else ""))


def write(p, doc):
    with open(p, "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, sort_keys=False)
    return p


def main():
    tmp = tempfile.mkdtemp(prefix="shopya_exec_")
    try:
        spec_v = yaml.safe_load(open(SCHEMA))["schema"]["version"]
        chart_v = yaml.safe_load(open(CHARTER))["charter"]["version"]

        # ─────────── 1 · sum_max ───────────
        print("\n-- feed cap: sum_max, not count_max --")

        def act(feeds):
            """Minimal ACTIVATION_READY-shaped state with the given explore_feeds values."""
            acts = []
            for i, f in enumerate(feeds):
                a = {"seam_id": "S%d" % i, "surface": "explore", "role": "r", "user_action": "u",
                     "execution_mode": "executable", "owner": "o", "activation_authority": "a",
                     "scheduling": {"semantic_status": "verified", "evaluation_mode": "query_time",
                                    "cache_latency_seconds": {"minimum": 1, "maximum": 2},
                                    "precision": "p"},
                     "artifact": "x", "implementation_status": "pending"}
                if f is not None:
                    a["explore_feeds"] = f
                acts.append(a)
            ap = write(os.path.join(tmp, "act.yaml"),
                       {"activations": acts, "delivery": {"intent": {"mode": "launch_window"}}})
            st = {"run": {"run_id": "cmp_T", "spec_version": spec_v, "charter_version": chart_v,
                          "created_at": "t"},
                  "identity": {"campaign_id": {"value": None, "status": None,
                                               "confirmed_by_owner": False,
                                               "externally_referenced": False,
                                               "first_external_reference": None},
                               "display_name": None},
                  "workflow": {"state": "ROUTE_SELECTED", "entered_at": "t", "history": []},
                  "owner_decisions": {}, "invalidated": [], "capability_claims": [],
                  "validation_attempts": [],
                  "artifacts": {"stage6_activation": {"path": ap, "status": "current"}},
                  "execution_tracking": {"activation_architecture_status": "approved",
                                         "external_handoffs_status": "authored",
                                         "seam6_execution_status": "not_started",
                                         "external_handoffs_implemented": "unknown"},
                  "collection_freeze": {"snapshot": [], "exceptions": []}}
            return write(os.path.join(tmp, "st.yaml"), st)

        def run(feeds):
            r = subprocess.run([sys.executable, VALIDATOR, "--state", act(feeds),
                                "--schema", SCHEMA, "--charter", CHARTER,
                                "--runs-dir", "/tmp/__none__", "--to", "ACTIVATION_READY",
                                "--phase", "transition"], capture_output=True, text=True)
            return r.returncode, r.stdout + r.stderr

        rc, out = run([2, 2])
        ok("2 + 2 passes the cap of 4", rc == 0, out[-300:])
        rc, out = run([2, 3])
        ok("2 + 3 refuses", rc != 0 and "sums to 5" in out)
        rc, out = run([100, 100, 100])
        ok("three activations of 100 refuse (count_max would have passed this)",
           rc != 0 and "sums to 300" in out)
        rc, out = run([2, None])
        ok("an undeclared explore_feeds fails rather than being skipped",
           rc != 0 and "undeclared" in out)
        rc, out = run([2, "two"])
        ok("a non-numeric explore_feeds fails clearly", rc != 0 and "not numeric" in out)
        rc, out = run([0, 4])
        ok("handoff seams may declare 0", rc == 0, out[-300:])

        # ─────────── 2 & 3 · CSV contract + availability ───────────
        print("\n-- CSV rail contract and availability --")
        if not os.path.exists(os.path.join(ENGINE, "product_results_log.jsonl")):
            ok("curation engine reachable", False, "no engine at %s" % ENGINE)
        else:
            rows = []
            for coll, rail, folder in [("Perfume Wardrobe", "The Scent You Keep", "B6_perfume-wardrobe"),
                                       ("The Summer Bag", "The Bag That Survives The Turn", "X1_the-summer-bag")]:
                src = os.path.join(ENGINE, "collections", folder, "products.csv")
                for i, r in enumerate(csv.DictReader(open(src, encoding="utf-8")), 1):
                    rows.append({"collection_name": coll, "rail_name": rail, "rank": i,
                                 "product_url": r.get("URL", ""), "product_name": r.get("Product", ""),
                                 "brand": r.get("Brand", ""), "price": r.get("Price_USD", ""),
                                 "currency": "USD", "image_url": "", "notes": ""})
            rp = os.path.join(tmp, "curated.json")
            json.dump(rows, open(rp, "w"))
            outp = os.path.join(tmp, "p.csv")
            r = subprocess.run([sys.executable, BUILD, "--legacy-replay", "--campaign", "t", "--rows", rp,
                                "--out", outp, "--engine", ENGINE], capture_output=True, text=True)
            ok("build succeeds on a compliant collection set", r.returncode == 0, r.stdout + r.stderr)
            got = list(csv.DictReader(open(outp, encoding="utf-8")))
            ok("rail_position is emitted as a column", "rail_position" in got[0])
            pinned = [x for x in got if x["pinned"] == "yes"]
            ok("every pinned row carries a rail_position", all(x["rail_position"] for x in pinned))
            ok("no unpinned row carries a rail_position",
               all(not x["rail_position"] for x in got if x["pinned"] == "no"))
            ok("rail_position is contiguous 1..N per rail",
               all(sorted(int(x["rail_position"]) for x in pinned if x["collection_name"] == c)
                   == list(range(1, len([y for y in pinned if y["collection_name"] == c]) + 1))
                   for c in {x["collection_name"] for x in pinned}))
            ok("no sold-out or unknown product is ever pinned",
               {x["stock_status"] for x in pinned} <= {"in_stock", "low_stock"},
               str({x["stock_status"] for x in pinned}))
            ok("stock_status is resolved for every row, never blank",
               all(x["stock_status"] for x in got))
            out2 = os.path.join(tmp, "p2.csv")
            subprocess.run([sys.executable, BUILD, "--legacy-replay", "--campaign", "t", "--rows", rp,
                            "--out", out2, "--engine", ENGINE], capture_output=True, text=True)
            ok("output is deterministic across builds",
               open(outp, "rb").read() == open(out2, "rb").read())
            ok("collection_rank is retained but warned about",
               "collection_rank is deprecated" in r.stdout)

            thin = [x for x in rows if x["collection_name"] == "The Summer Bag"][:10]
            tp = os.path.join(tmp, "thin.json"); json.dump(thin, open(tp, "w"))
            r = subprocess.run([sys.executable, BUILD, "--legacy-replay", "--campaign", "t", "--rows", tp,
                                "--out", os.path.join(tmp, "t.csv"), "--engine", ENGINE],
                               capture_output=True, text=True)
            ok("a collection below the quality minimum on AVAILABLE products refuses",
               r.returncode == 1 and "below the approved presentation-quality minimum" in r.stdout)
            ok("the refusal counts available, not total rows",
               "4 available" in r.stdout, r.stdout[-200:])

            ep = os.path.join(tmp, "exc.json")
            json.dump({"The Summer Bag": {"approved": True, "approved_by": "product_owner",
                                          "rationale": "diagnostic"}}, open(ep, "w"))
            r = subprocess.run([sys.executable, BUILD, "--legacy-replay", "--campaign", "t", "--rows", tp,
                                "--out", os.path.join(tmp, "t2.csv"), "--engine", ENGINE,
                                "--exceptions", ep], capture_output=True, text=True)
            ok("an approved quality_exception downgrades the refusal to a warning",
               r.returncode == 0 and "limited inventory resilience" in r.stdout)

            r = subprocess.run([sys.executable, BUILD, "--legacy-replay", "--campaign", "t", "--rows", rp,
                                "--out", os.path.join(tmp, "n.csv"), "--engine", "/tmp/__no_engine__"],
                               capture_output=True, text=True)
            ok("build refuses when availability cannot be established",
               r.returncode != 0 and "Availability cannot be established" in (r.stdout + r.stderr))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        for f in FAIL:
            print("  FAILED: %s" % f)
        sys.exit(1)


if __name__ == "__main__":
    main()
