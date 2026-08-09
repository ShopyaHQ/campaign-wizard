#!/usr/bin/env python3
"""v2 builder tests: judgment purity, engine hydration, truth freshness, grain.

    python3 tests/test_execution_v2.py

The structural contract (owner, 2026-08-07): wizard authors judgment only;
every product fact in the master CSV is hydrated from the engine's
current-truth export. No pytest dependency.
"""
import csv, hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "scripts", "build_execution_csv.py")

PASS, FAIL = [], []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %s  %s%s" % ("PASS" if cond else "FAIL", name,
                          ("  <- " + detail) if detail and not cond else ""))


def make_engine_with(tmp, name, truth):
    """Fake engine dir `name`: a log file + a fresh truth export (meta matches log)."""
    eng = os.path.join(tmp, name)
    os.makedirs(os.path.join(eng, "exports"))
    log = os.path.join(eng, "product_results_log.jsonl")
    with open(log, "w") as f:
        for i in range(5):
            f.write(json.dumps({"filler": i}) + "\n")
    n, h = 0, hashlib.sha256()
    for line in open(log, "rb"):
        n += 1; h.update(line)
    tp = os.path.join(eng, "exports", "current_truth.jsonl")
    with open(tp, "w") as f:
        f.write(json.dumps({"type": "meta", "truth_contract_version": "1.0.0", "generated_at": "2026-08-07",
                            "source_lines": n, "source_sha256": h.hexdigest(),
                            "products": len(truth)}) + "\n")
        for t in truth:
            f.write(json.dumps(t) + "\n")
    return eng


def make_engine(tmp):
    """Fake engine: a log file + a truth export whose meta matches it."""
    eng = os.path.join(tmp, "engine")
    os.makedirs(os.path.join(eng, "exports"))
    log = os.path.join(eng, "product_results_log.jsonl")
    with open(log, "w") as f:
        for i in range(5):
            f.write(json.dumps({"filler": i}) + "\n")
    n, h = 0, hashlib.sha256()
    for line in open(log, "rb"):
        n += 1; h.update(line)

    truth = []
    # 50 distinct sellable products clear the collection-depth hard floor (render_003).
    # The ENGINE stamps sellable_product_uid + floor_eligible; the builder consumes them.
    for i in range(1, 51):
        uid = "brand-%02d:product-%02d:color" % (i, i)
        truth.append({
            "product_uid": uid, "brand": "Brand %02d" % i,
            "product_name": "Product %02d" % i, "colorway": "Color",
            "sellable_product_uid": "sp:brand-%02d:product-%02d" % (i, i),
            "floor_eligible": True,
            "url": "https://example-%02d.com/products/product-%02d" % (i, i),
            "url_class": "pdp", "verification_url": "https://x.com/products/p.js",
            "price_native": 100 + i, "currency": "USD", "price_usd": 100 + i,
            "stock_status": "in_stock", "observed_at": "2026-08-07",
            "status": "verified", "confidence": "confirmed_live",
            "fetched_via": "platform_json", "external_id": "", "collection_ids": ["T1"]})
    # a low_stock member: engine marks floor_eligible False (must NOT count toward floor)
    truth.append(dict(truth[0], product_uid="low:product:color",
                      sellable_product_uid="sp:low:product", floor_eligible=False,
                      url="https://low.com/products/low", stock_status="low_stock"))
    # sold out (for the rail-availability refusal); also not floor-eligible
    truth.append(dict(truth[0], product_uid="gone:product:color",
                      sellable_product_uid="sp:gone:product", floor_eligible=False,
                      url="https://gone.com/products/gone", stock_status="sold_out"))
    # engine-known but bad URL class; not floor-eligible
    truth.append(dict(truth[0], product_uid="badurl:product:color",
                      sellable_product_uid="sp:badurl:product", floor_eligible=False,
                      url="https://bad.com", url_class="root"))
    tp = os.path.join(eng, "exports", "current_truth.jsonl")
    with open(tp, "w") as f:
        f.write(json.dumps({"type": "meta", "truth_contract_version": "1.0.0", "generated_at": "2026-08-07",
                            "source_lines": n, "source_sha256": h.hexdigest(),
                            "products": len(truth)}) + "\n")
        for t in truth:
            f.write(json.dumps(t) + "\n")
    return eng


def judgment_rows(n=50):
    """n launched members (12 rail + body). Default 50 clears the depth floor."""
    rows = []
    for i in range(1, n + 1):
        rail = i <= 12
        rows.append({"product_uid": "brand-%02d:product-%02d:color" % (i, i),
                     "collection_name": "Test Coll",
                     "is_rail_item": rail,
                     "rail_name": "The Rail" if rail else None,
                     "rail_position": i if rail else None,
                     "collection_position": i,
                     "annotation": "note %d" % i})
    return rows


def run_build(tmp, eng, rows, extra=()):
    jp = os.path.join(tmp, "j.json"); json.dump(rows, open(jp, "w"))
    outp = os.path.join(tmp, "out.csv")
    r = subprocess.run([sys.executable, BUILD, "--campaign", "t",
                        "--campaign-name", "T", "--build", "b900",
                        "--judgment", jp, "--out", outp, "--engine", eng,
                        *extra], capture_output=True, text=True)
    return r, outp


def main():
    tmp = tempfile.mkdtemp(prefix="shopya_exec2_")
    try:
        eng = make_engine(tmp)

        print("\n-- happy path: hydration from engine truth --")
        r, outp = run_build(tmp, eng, judgment_rows())
        ok("compliant judgment builds", r.returncode == 0, r.stdout + r.stderr)
        got = list(csv.DictReader(open(outp)))
        ok("grain holds for one collection (50 rows: 12 rail + 38 body)", len(got) == 50)
        ok("product facts hydrated from truth (url)",
           got[0]["product_url"] == "https://example-01.com/products/product-01")
        ok("price/currency hydrated from truth",
           got[0]["price"] == "101" and got[0]["currency"] == "USD")
        ok("rail fields only on rail rows",
           all((x["is_rail_item"] == "TRUE") == bool(x["rail_name"]) for x in got))

        print("\n-- judgment purity: nowhere for product facts to enter --")
        rows = judgment_rows(); rows[0]["product_url"] = "https://evil.example.com"
        r, _ = run_build(tmp, eng, rows)
        ok("a wizard-authored product_url is refused",
           r.returncode == 1 and "may not carry product facts" in r.stdout)
        rows = judgment_rows(); rows[3]["price"] = 9.99
        r, _ = run_build(tmp, eng, rows)
        ok("a wizard-authored price is refused",
           r.returncode == 1 and "may not carry product facts" in r.stdout)

        print("\n-- engine vouching --")
        rows = judgment_rows()
        rows[23]["product_uid"] = "never:seen:this"
        r, _ = run_build(tmp, eng, rows)
        ok("uid the engine does not vouch for is refused",
           r.returncode == 1 and "not in engine truth" in r.stdout)
        rows = judgment_rows(); rows[23]["product_uid"] = "badurl:product:color"
        r, _ = run_build(tmp, eng, rows)
        ok("engine-known product with non-PDP current url is refused",
           r.returncode == 1 and "not gate-clean" in r.stdout)
        rows = judgment_rows(); rows[0]["product_uid"] = "gone:product:color"
        r, _ = run_build(tmp, eng, rows)
        ok("sold-out rail item is refused",
           r.returncode == 1 and "not available at build" in r.stdout)

        print("\n-- truth contract version --")
        # unsupported truth_contract_version -> refuse (never guess an incompatible contract)
        eng_badv = make_engine_with(tmp, "eng_badv", [dict(
            product_uid="b:p:c", brand="B", product_name="P", sellable_product_uid="sp:b:p",
            floor_eligible=True, url="https://b/p", url_class="pdp", stock_status="in_stock",
            price_native=1, currency="USD", observed_at="x", confidence="confirmed_live")])
        tp = os.path.join(eng_badv, "exports", "current_truth.jsonl")
        lines = open(tp).readlines()
        lines[0] = json.dumps({"type": "meta", "truth_contract_version": "9.9.9",
                               "source_lines": 5, "source_sha256": "x", "products": 1}) + "\n"
        # keep source hash matching so ONLY the version is wrong
        import hashlib as _h
        n2, hh = 0, _h.sha256()
        for ln in open(os.path.join(eng_badv, "product_results_log.jsonl"), "rb"):
            n2 += 1; hh.update(ln)
        lines[0] = json.dumps({"type": "meta", "truth_contract_version": "9.9.9",
                               "source_lines": n2, "source_sha256": hh.hexdigest(),
                               "products": 1}) + "\n"
        open(tp, "w").writelines(lines)
        r, _ = run_build(tmp, eng_badv, judgment_rows())
        ok("unsupported truth_contract_version is refused",
           r.returncode == 1 and "truth_contract_version" in (r.stdout + r.stderr))

        # missing required field -> refuse (never infer)
        eng_miss = make_engine_with(tmp, "eng_miss", [dict(
            product_uid="b:p:c", brand="B", product_name="P", sellable_product_uid="sp:b:p",
            floor_eligible=True, url="https://b/p", url_class="pdp", stock_status="in_stock",
            currency="USD", observed_at="x")])  # price_native missing
        r, _ = run_build(tmp, eng_miss, judgment_rows())
        ok("truth row missing a required contract field is refused",
           r.returncode == 1 and "missing contract field" in (r.stdout + r.stderr))

        print("\n-- truth freshness --")
        with open(os.path.join(eng, "product_results_log.jsonl"), "a") as f:
            f.write(json.dumps({"filler": "new"}) + "\n")
        r, _ = run_build(tmp, eng, judgment_rows())
        ok("stale truth export refuses",
           r.returncode == 1 and "STALE" in (r.stdout + r.stderr))
        r, _ = run_build(tmp, eng, judgment_rows(), extra=("--allow-stale",))
        ok("--allow-stale overrides with a warning",
           r.returncode == 0 and "WARNING" in r.stdout)

        print("\n-- grain / collection-depth floor (engine sellable identity) --")
        rows = judgment_rows(49)
        r, _ = run_build(tmp, eng, rows, extra=("--allow-stale",))
        ok("49 distinct sellable products refuses (need >=50)",
           r.returncode == 1 and "need >=50" in r.stdout)
        # 50 members but one is low_stock (engine floor_eligible=False) -> 49 eligible -> refuses.
        rows = judgment_rows(49)
        rows.append({"product_uid": "low:product:color", "collection_name": "Test Coll",
                     "is_rail_item": False, "rail_name": None, "rail_position": None,
                     "collection_position": 50, "annotation": "low"})
        r, _ = run_build(tmp, eng, rows, extra=("--allow-stale",))
        ok("engine-ineligible (low_stock) member does not count toward the >=50 floor",
           r.returncode == 1 and "need >=50" in r.stdout and "not floor-eligible" in r.stdout)
        # ADVERSARIAL: 50 member rows that the ENGINE resolves to only 5 distinct
        # sellable products (colorway/variant inflation) must REFUSE. This is the
        # core F1 guarantee — variants cannot fake collection depth.
        infl_truth = []
        for j in range(50):
            infl_truth.append(dict(
                product_uid="infl-%02d:p:color" % j, brand="Inflate", product_name="P",
                sellable_product_uid="sp:inflate:p-%d" % (j % 5),  # only 5 distinct
                floor_eligible=True, colorway="c%d" % j,
                url="https://inflate.com/products/p-c%d" % j, url_class="pdp",
                verification_url="https://x/p.js", price_native=10, currency="USD",
                price_usd=10, stock_status="in_stock", observed_at="2026-08-07",
                status="verified", confidence="confirmed_live",
                fetched_via="platform_json", external_id="", collection_ids=["T1"]))
        eng2 = make_engine_with(tmp, "engine_infl", infl_truth)
        infl_rows = [{"product_uid": "infl-%02d:p:color" % j, "collection_name": "Infl",
                      "is_rail_item": j < 12, "rail_name": "R" if j < 12 else None,
                      "rail_position": (j + 1) if j < 12 else None,
                      "collection_position": j + 1, "annotation": ""} for j in range(50)]
        r, _ = run_build(tmp, eng2, infl_rows)
        ok("50 rows / 5 sellable products (variant inflation) REFUSES",
           r.returncode == 1 and "distinct floor-eligible sellable products, need >=50" in r.stdout)

        rows = judgment_rows()
        rows[11]["is_rail_item"] = False; rows[11]["rail_name"] = None; rows[11]["rail_position"] = None
        r, _ = run_build(tmp, eng, rows, extra=("--allow-stale",))
        ok("11 rail items refuses (needs exactly 12)",
           r.returncode == 1 and "rail_position not exactly 1..12" in r.stdout)
        rows = judgment_rows()
        rows[23]["collection_position"] = 99
        r, _ = run_build(tmp, eng, rows, extra=("--allow-stale",))
        ok("non-contiguous collection_position refuses",
           r.returncode == 1 and "not contiguous" in r.stdout)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        for f in FAIL:
            print("  FAILED: %s" % f)
        sys.exit(1)


if __name__ == "__main__":
    main()
