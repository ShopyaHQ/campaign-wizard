#!/usr/bin/env python3
"""build_csv.py — assemble the Seam 6 execution CSV from curated rows.

    python3 scripts/build_csv.py --campaign seasonal-turn-2026 \
        --rows curated.json --out campaigns/<run>/execution/products.csv \
        [--engine ../shopya-collection-curation] [--pin 12]

CONTRACT (charter SHOPYA_CAMPAIGN_CHARTER.yaml)
  rail_001  one rail : one collection. Structurally enforced.
  rail_002  rail_position is REQUIRED for every pinned row. It is the product's order WITHIN
            its rail and is what feed.include_ids order encodes. It is NOT the rail's position
            on the page — that is the rail's sort_order and never appears per row.
  rail_003  collection_rank is DEPRECATED and non-operative. Retained for human diagnostics
            only; emitting it produces a WARNING, never a failure.
  render_001 technical minimum is 1 AVAILABLE product. Zero is a hard failure.
  render_002 presentation quality minimum is 12 available products, overridable only by a
            documented, approved quality_exception.

AVAILABILITY
  Availability is NOT in the curation engine's collection CSVs. It is joined at build time from
  the engine's append-only product_results_log.jsonl, matched on normalised product URL, taking
  the most recent observation. Three outcomes, and `unknown` is never counted as available:
      in_stock / low_stock -> available
      sold_out             -> unavailable
      anything else, or no log entry -> unknown
  Quality minimums are measured on AVAILABLE products only. A collection of 29 rows of which 16
  are available is a 16-product collection for this purpose.
"""
import argparse, csv, json, os, sys
from collections import defaultdict

COLS = ["campaign_id", "collection_name", "rail_name", "rail_position", "pinned",
        "collection_rank", "product_url", "product_name", "brand", "price", "currency",
        "image_url", "stock_status", "observed_at", "notes"]

TECHNICAL_MINIMUM = 1
QUALITY_MINIMUMS = {"products": 12, "collections": 10, "brands": 12}
AVAILABLE = ("in_stock", "low_stock")


def norm(u):
    return (u or "").split("?")[0].rstrip("/")


def load_availability(engine):
    """url -> {stock_status, observed_at} from the most recent observation."""
    path = os.path.join(engine, "product_results_log.jsonl")
    if not os.path.exists(path):
        return None
    latest = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            u = norm(d.get("url"))
            if not u:
                continue
            if u not in latest or (d.get("observed_at") or "") >= (latest[u].get("observed_at") or ""):
                latest[u] = d
    return latest


def classify(rec):
    if rec is None:
        return "unknown", None
    st = (rec.get("stock_status") or "unknown").lower()
    return (st if st in AVAILABLE or st == "sold_out" else "unknown"), rec.get("observed_at")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--rows", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--engine", default=os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), "shopya-collection-curation"))
    ap.add_argument("--pin", type=int, default=12)
    ap.add_argument("--entity-type", default="products")
    ap.add_argument("--exceptions", help="JSON map {collection_name: {approved, approved_by, rationale}}")
    a = ap.parse_args()

    rows = json.load(open(a.rows, encoding="utf-8"))
    exceptions = json.load(open(a.exceptions, encoding="utf-8")) if a.exceptions else {}
    avail_index = load_availability(a.engine)
    if avail_index is None:
        sys.exit("STOP — no product_results_log.jsonl under %s.\n"
                 "Availability cannot be established, so quality minimums cannot be checked.\n"
                 "Point --engine at the curation engine." % a.engine)

    by_coll = defaultdict(list)
    for r in rows:
        by_coll[r["collection_name"]].append(r)

    bad = [c for c, rs in by_coll.items() if len({r.get("rail_name") for r in rs}) > 1]
    if bad:
        sys.exit("ERROR: each rail must reference exactly one collection — %s\n"
                 "One rail = one collection. Fix the plan, not the CSV." % bad)

    out, summary, hard, quality, warnings = [], [], [], [], []
    minimum = QUALITY_MINIMUMS.get(a.entity_type, 12)

    for coll, rs in by_coll.items():
        rs = sorted(rs, key=lambda r: r.get("rank", 10 ** 6))
        enriched = []
        for i, r in enumerate(rs, 1):
            status, seen = classify(avail_index.get(norm(r.get("product_url"))))
            enriched.append((i, r, status, seen))

        available = [e for e in enriched if e[2] in AVAILABLE]
        unknown = [e for e in enriched if e[2] == "unknown"]
        unavailable = [e for e in enriched if e[2] == "sold_out"]

        # rail_position: 1..N over AVAILABLE products in collection-rank order. Deterministic,
        # and it never pins something a shopper cannot act on.
        pinned_ids = {id(e[1]): pos for pos, e in enumerate(available[:a.pin], 1)}

        for rank, r, status, seen in enriched:
            pos = pinned_ids.get(id(r))
            out.append({
                "campaign_id": a.campaign, "collection_name": coll,
                "rail_name": r.get("rail_name", ""),
                "rail_position": pos if pos else "",
                "pinned": "yes" if pos else "no",
                "collection_rank": rank,
                "product_url": r.get("product_url", ""), "product_name": r.get("product_name", ""),
                "brand": r.get("brand", ""), "price": r.get("price", ""),
                "currency": r.get("currency", "USD"), "image_url": r.get("image_url", ""),
                "stock_status": status, "observed_at": seen or "",
                "notes": r.get("notes", ""),
            })

        summary.append((coll, len(enriched), len(available), len(unknown), len(unavailable),
                        min(len(available), a.pin)))
        if len(available) < TECHNICAL_MINIMUM:
            hard.append((coll, len(available)))
        elif len(available) < minimum:
            exc = exceptions.get(coll) or {}
            if exc.get("approved") is True and exc.get("approved_by") and exc.get("rationale"):
                warnings.append("WARNING: %s has limited inventory resilience (%d available, "
                                "minimum %d) — approved exception by %s"
                                % (coll, len(available), minimum, exc["approved_by"]))
            else:
                quality.append((coll, len(available)))

    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(out)

    print("%s: %d rows across %d collection(s)" % (a.out, len(out), len(by_coll)))
    print("  %-28s %5s %5s %5s %5s %6s" % ("collection", "rows", "avail", "unk", "gone", "pinned"))
    for c, t, av, un, so, pin in summary:
        print("  %-28s %5d %5d %5d %5d %6d" % (c[:28], t, av, un, so, pin))
    warnings.append("WARNING: collection_rank is deprecated and has no persistence effect. "
                    "Use rail_position to control feed include_ids order.")
    for w_ in warnings:
        print("  " + w_)

    if hard:
        for c, n in hard:
            print("\nERROR: entity %r has zero eligible items and cannot render" % c)
        sys.exit(1)
    if quality:
        for c, n in quality:
            print("\nERROR: entity %r is below the approved presentation-quality minimum "
                  "(%d available, minimum %d)" % (c, n, minimum))
        print("Curate past the minimum, or supply an approved quality_exception via --exceptions.")
        sys.exit(1)


if __name__ == "__main__":
    main()
