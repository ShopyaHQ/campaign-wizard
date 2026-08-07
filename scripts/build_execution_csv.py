#!/usr/bin/env python3
"""build_execution_csv.py — the MASTER campaign execution worklist (owner contract, 2026-08-07).

One row per product x collection membership. Contains rail items + collection body.
NEVER contains the engine-side reserve pool. Grain and validation per owner ruling:
  is_rail_item TRUE  -> rail_name and rail_position (1..12) REQUIRED
  is_rail_item FALSE -> rail_name and rail_position MUST be blank
  campaign QA: >=24 members and exactly 12 rail items per collection; rail_position exactly
  1..12; no duplicate product x collection rows.

    python3 scripts/build_execution_csv.py --campaign almost-fall-2026 \
      --campaign-name "Almost Fall" --build b003 \
      --rails <curated.json> --bodies <bodies.csv> --out <master.csv> [--engine PATH]

Availability (stock_status, observed_at) is joined read-only from the engine's
product_results_log.jsonl exactly as build_csv.py does. curated.json remains an internal
machine artifact; this CSV is the only file the operator works from.
"""
import argparse, csv, json, os, sys
from collections import defaultdict
from build_csv import load_availability, norm, classify, AVAILABLE

COLS = ["campaign_id", "campaign_name", "build_id", "collection_name",
        "is_rail_item", "rail_name", "rail_position", "collection_position",
        "product_name", "brand", "product_url", "external_id",
        "price", "currency", "stock_status", "observed_at", "annotation"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", required=True); ap.add_argument("--campaign-name", required=True)
    ap.add_argument("--build", required=True)
    ap.add_argument("--rails", required=True); ap.add_argument("--bodies", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--engine", default=os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), "shopya-collection-curation"))
    a = ap.parse_args()

    avail = load_availability(a.engine)
    if avail is None:
        sys.exit("STOP — no product_results_log.jsonl under %s" % a.engine)

    rails = json.load(open(a.rails, encoding="utf-8"))
    bodies = list(csv.DictReader(open(a.bodies, encoding="utf-8")))
    out, errors = [], []
    by_coll_rail = defaultdict(list); by_coll_all = defaultdict(list)

    for r in sorted(rails, key=lambda x: (x["collection_name"], x.get("rank", 999))):
        st, seen = classify(avail.get(norm(r["product_url"])))
        if st not in AVAILABLE:
            errors.append("rail item not available at build: %s / %s (%s)" % (r["collection_name"], r["product_name"], st))
        pos = len(by_coll_rail[r["collection_name"]]) + 1
        by_coll_rail[r["collection_name"]].append(1)
        out.append({"campaign_id": a.campaign, "campaign_name": a.campaign_name, "build_id": a.build,
            "collection_name": r["collection_name"], "is_rail_item": "TRUE",
            "rail_name": r["rail_name"], "rail_position": pos, "collection_position": pos,
            "product_name": r["product_name"], "brand": r["brand"], "product_url": r["product_url"],
            "external_id": "", "price": r.get("price", ""), "currency": r.get("currency", "USD"),
            "stock_status": st, "observed_at": seen or "", "annotation": r.get("notes", "")})
        by_coll_all[r["collection_name"]].append((r["brand"], r["product_name"]))

    body_pos = defaultdict(lambda: 12)
    for b in bodies:
        c = b["collection_name"]
        st, seen = classify(avail.get(norm(b["product_url"])))
        body_pos[c] += 1
        out.append({"campaign_id": a.campaign, "campaign_name": a.campaign_name, "build_id": a.build,
            "collection_name": c, "is_rail_item": "FALSE", "rail_name": "", "rail_position": "",
            "collection_position": body_pos[c],
            "product_name": b["product_name"], "brand": b["brand"], "product_url": b["product_url"],
            "external_id": "", "price": b.get("price", ""), "currency": b.get("currency", "USD"),
            "stock_status": st, "observed_at": seen or "", "annotation": ""})
        by_coll_all[c].append((b["brand"], b["product_name"]))

    # ---- validation (owner contract) ----
    for row in out:
        if row["is_rail_item"] == "TRUE" and (not row["rail_name"] or not row["rail_position"]):
            errors.append("rail item missing rail_name/rail_position: %s" % row["product_name"])
        if row["is_rail_item"] == "FALSE" and (row["rail_name"] or row["rail_position"]):
            errors.append("non-rail item carries rail fields: %s" % row["product_name"])
    for c, members in by_coll_all.items():
        n_rail = len(by_coll_rail[c])
        if n_rail != 12: errors.append("%s: %d rail items, need exactly 12" % (c, n_rail))
        if len(members) < 24: errors.append("%s: %d members, need >=24" % (c, len(members)))
        if len(set(members)) != len(members): errors.append("%s: duplicate product rows" % c)
        got = sorted(int(r["rail_position"]) for r in out if r["collection_name"] == c and r["is_rail_item"] == "TRUE")
        if got != list(range(1, 13)): errors.append("%s: rail_position not exactly 1..12" % c)

    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS); w.writeheader(); w.writerows(out)
    print("%s: %d rows" % (a.out, len(out)))
    for c in sorted(by_coll_all):
        print("  %-24s %2d members (12 rail + %d body)" % (c[:24], len(by_coll_all[c]), len(by_coll_all[c]) - 12))
    if errors:
        print("\nVALIDATION FAILURES:"); [print("  ERROR: " + e) for e in errors]; sys.exit(1)
    print("  QA: rail/body integrity, membership >=24, positions 1..12, no duplicates — ALL PASS")

if __name__ == "__main__":
    main()
