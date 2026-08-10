#!/usr/bin/env python3
"""build_execution_csv.py — the MASTER campaign execution worklist (owner contract, 2026-08-07).

v2 (structural correction, 2026-08-07): CAMPAIGN JUDGMENT + ENGINE TRUTH -> CSV.

The wizard authors JUDGMENT ONLY. Every product fact — name, brand, canonical
PDP url, price, currency, availability, observation time, external_id — is
hydrated from the engine's current-truth export. There is nowhere in the input
for a wizard-authored URL (or any product fact) to enter the final CSV: rows
carrying product-fact keys are refused outright.

    python3 scripts/build_execution_csv.py --campaign almost-fall-2026 \
      --campaign-name "Almost Fall" --build b004 \
      --judgment <curated.json> --out <master.csv> [--truth PATH] [--allow-stale]

curated.json (judgment-only; ONE file, rail + body together):
  [{"product_uid": "...", "collection_name": "...", "is_rail_item": true|false,
    "rail_name": "..."|null, "rail_position": 1..12|null,
    "collection_position": 1..N, "annotation": "..."}]

Truth input: the engine's exports/current_truth.jsonl (regenerate with
`python3 tools/export_current_truth.py` in the engine). The meta line binds it
to a specific state of the engine log; a build against a truth file that no
longer matches the log refuses unless --allow-stale.

Grain and validation per owner ruling:
  is_rail_item TRUE  -> rail_name and rail_position (1..12) REQUIRED
  is_rail_item FALSE -> rail_name and rail_position MUST be null/blank
  exactly 12 rail items per collection; >=50 dependable in_stock UNIQUE members
  per collection (collection-depth hard floor, render_003 v0.7.0 — low_stock
  counted separately, never toward the floor); rail_position exactly 1..12;
  collection_position unique + contiguous 1..N; no duplicate product x collection
  rows; every hydrated url must be gate-clean (url_class == pdp) and every rail
  item currently available.
"""
import argparse, csv, hashlib, json, os, sys
from collections import defaultdict

COLS = ["campaign_id", "campaign_name", "build_id", "collection_name",
        "is_rail_item", "rail_name", "rail_position", "collection_position",
        "product_name", "brand", "product_url", "external_id",
        "price", "currency", "stock_status", "observed_at", "annotation"]

JUDGMENT_KEYS = {"product_uid", "collection_name", "is_rail_item", "rail_name",
                 "rail_position", "collection_position", "annotation"}
AVAILABLE = ("in_stock", "low_stock")
# Collection-depth HARD floor (charter render_003 v0.7.0, owner Decision 1 2026-08-10 restoring
# the 2026-08-09 ruling): every launched durable category collection must carry >=50 dependable
# in_stock UNIQUE sellable members. 49 fails, 50 passes. The 0.6.0-era 24-floor was an
# accidental regression, reversed. low_stock is reported separately and does NOT satisfy the
# floor; variants/duplicate identities never inflate (engine-owned sellable_product_uid).
COLLECTION_FLOOR = 50
COLLECTION_HEALTH_TARGET = 50   # floor and target coincide under the hard-50 rule

ENGINE_DEFAULT = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "shopya-collection-curation")


def log_stats(path):
    n, h = 0, hashlib.sha256()
    with open(path, "rb") as f:
        for line in f:
            n += 1
            h.update(line)
    return n, h.hexdigest()


# Engine->Wizard truth-export contract versions this builder supports. The wizard REFUSES an
# export whose truth_contract_version is not here; it never infers missing fields or falls back
# to legacy truth semantics. Bump in lockstep with the engine's TRUTH_CONTRACT_VERSION.
SUPPORTED_TRUTH_CONTRACTS = {"1.0.0"}
# Per-record fields the builder relies on; a row missing any is a contract violation, not a
# reason to infer a default.
TRUTH_REQUIRED_FIELDS = ("product_uid", "sellable_product_uid", "floor_eligible",
                         "url_class", "stock_status", "product_name", "brand", "url",
                         "price_native", "currency", "observed_at")


def load_truth(path, engine, allow_stale):
    recs = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    if not recs or recs[0].get("type") != "meta":
        sys.exit("STOP — %s has no meta line; regenerate with the engine's "
                 "export_current_truth.py" % path)
    meta, rows = recs[0], recs[1:]
    cv = meta.get("truth_contract_version")
    if cv not in SUPPORTED_TRUTH_CONTRACTS:
        sys.exit("STOP — truth export declares truth_contract_version %r; this builder supports "
                 "%s. Refusing rather than guessing at an incompatible contract."
                 % (cv, sorted(SUPPORTED_TRUTH_CONTRACTS)))
    for i, r in enumerate(rows):
        missing = [f for f in TRUTH_REQUIRED_FIELDS if f not in r]
        if missing:
            sys.exit("STOP — truth row %d (%s) is missing contract field(s) %s; the wizard never "
                     "infers product truth — regenerate the export"
                     % (i, r.get("product_uid", "?"), missing))
    log = os.path.join(engine, "product_results_log.jsonl")
    if os.path.exists(log):
        n, digest = log_stats(log)
        if (n, digest) != (meta.get("source_lines"), meta.get("source_sha256")):
            msg = ("truth export is STALE: engine log has %d lines, export was "
                   "generated from %d — regenerate exports/current_truth.jsonl"
                   % (n, meta.get("source_lines")))
            if not allow_stale:
                sys.exit("STOP — " + msg)
            print("WARNING: " + msg + " (--allow-stale)")
    elif not allow_stale:
        sys.exit("STOP — cannot verify truth freshness (no engine log at %s); "
                 "pass --allow-stale to override" % log)
    return {r["product_uid"]: r for r in rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", required=True); ap.add_argument("--campaign-name", required=True)
    ap.add_argument("--build", required=True)
    ap.add_argument("--judgment", required=True,
                    help="curated.json — campaign judgment ONLY (see docstring)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--engine", default=ENGINE_DEFAULT)
    ap.add_argument("--truth", default=None,
                    help="engine current-truth export (default: <engine>/exports/current_truth.jsonl)")
    ap.add_argument("--allow-stale", action="store_true")
    a = ap.parse_args()

    truth_path = a.truth or os.path.join(a.engine, "exports", "current_truth.jsonl")
    if not os.path.exists(truth_path):
        sys.exit("STOP — no engine truth export at %s.\nProduct facts are "
                 "hydrated from engine truth; run the engine's "
                 "tools/export_current_truth.py first." % truth_path)
    truth = load_truth(truth_path, a.engine, a.allow_stale)

    judgment = json.load(open(a.judgment, encoding="utf-8"))
    errors = []

    # ---- judgment purity: campaign fields only, nowhere for product facts ----
    for i, r in enumerate(judgment, 1):
        extra = set(r) - JUDGMENT_KEYS
        if extra:
            errors.append("row %d: judgment may not carry product facts or unknown "
                          "keys %s — product facts are hydrated from engine truth"
                          % (i, sorted(extra)))
        missing = {"product_uid", "collection_name", "is_rail_item",
                   "collection_position"} - set(r)
        if missing:
            errors.append("row %d: missing judgment keys %s" % (i, sorted(missing)))
    if errors:
        print("JUDGMENT REFUSED:"); [print("  ERROR: " + e) for e in errors]; sys.exit(1)

    out = []
    by_coll = defaultdict(list)
    for r in sorted(judgment, key=lambda x: (x["collection_name"],
                                             x["collection_position"])):
        uid = r["product_uid"]
        t = truth.get(uid)
        coll = r["collection_name"]
        if t is None:
            errors.append("%s / %s: uid not in engine truth — the engine does "
                          "not vouch for this product; resolve+verify it first"
                          % (coll, uid))
            continue
        if t.get("url_class") != "pdp":
            errors.append("%s / %s: engine's current url is not gate-clean "
                          "(%s: %s) — re-resolve the canonical PDP before it "
                          "can ship" % (coll, uid, t.get("url_class"), t.get("url")))
        rail = bool(r["is_rail_item"])
        if rail and t.get("stock_status") not in AVAILABLE:
            errors.append("%s / %s: rail item not available at build (%s)"
                          % (coll, uid, t.get("stock_status")))
        if rail and (not r.get("rail_name") or not r.get("rail_position")):
            errors.append("%s / %s: rail item missing rail_name/rail_position" % (coll, uid))
        if not rail and (r.get("rail_name") or r.get("rail_position")):
            errors.append("%s / %s: non-rail item carries rail fields" % (coll, uid))

        price = t.get("price_native")
        out.append({"campaign_id": a.campaign, "campaign_name": a.campaign_name,
                    "build_id": a.build, "collection_name": coll,
                    "is_rail_item": "TRUE" if rail else "FALSE",
                    "rail_name": r.get("rail_name") or "",
                    "rail_position": r.get("rail_position") or "",
                    "collection_position": r["collection_position"],
                    "product_name": t.get("product_name"), "brand": t.get("brand"),
                    "product_url": t.get("url"), "external_id": t.get("external_id", ""),
                    "price": "" if price is None else price,
                    "currency": t.get("currency", ""),
                    "stock_status": t.get("stock_status", "unknown"),
                    "observed_at": t.get("observed_at", ""),
                    "annotation": r.get("annotation") or ""})
        # Carry the ENGINE's canonical sellable identity + eligibility. The wizard
        # NEVER derives product identity — it consumes what the engine exported.
        by_coll[coll].append((uid, r, t.get("sellable_product_uid"),
                              bool(t.get("floor_eligible"))))

    # ---- grain QA (owner contract) ----
    for c, members in by_coll.items():
        uids = [u for u, _, _, _ in members]
        if len(set(uids)) != len(uids):
            errors.append("%s: duplicate product rows" % c)
        rail_pos = sorted(int(r["rail_position"]) for _, r, _, _ in members if r["is_rail_item"])
        if rail_pos != list(range(1, 13)):
            errors.append("%s: rail_position not exactly 1..12 (%d rail items)"
                          % (c, len(rail_pos)))
        # Collection-depth hard floor (charter render_003 v0.7.0):
        # COUNT(DISTINCT sellable_product_uid WHERE floor_eligible). The engine owns
        # both fields; floor_eligible already means pdp + in_stock + confidence in
        # {confirmed_live, verified}. Colorways/variants/name-drift collapse to one
        # sellable id, so they cannot inflate the floor.
        eligible = {sid for _, _, sid, elig in members if elig and sid}
        if len(eligible) < COLLECTION_FLOOR:
            ineligible = sum(1 for _, _, _, elig in members if not elig)
            errors.append("%s: %d distinct floor-eligible sellable products, need >=%d "
                          "(collection-depth hard floor render_003 v0.7.0; %d member rows not "
                          "floor-eligible — non-PDP / low_stock / unverified — not counted)"
                          % (c, len(eligible), COLLECTION_FLOOR, ineligible))
        cpos = sorted(int(r["collection_position"]) for _, r, _, _ in members)
        if cpos != list(range(1, len(members) + 1)):
            errors.append("%s: collection_position not contiguous 1..%d" % (c, len(members)))

    if errors:
        print("VALIDATION FAILURES:"); [print("  ERROR: " + e) for e in errors]; sys.exit(1)

    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS); w.writeheader(); w.writerows(out)
    print("%s: %d rows" % (a.out, len(out)))
    for c in sorted(by_coll):
        n = len(by_coll[c]); nr = sum(1 for _, r, _, _ in by_coll[c] if r["is_rail_item"])
        elig = len({sid for _, _, sid, e in by_coll[c] if e and sid})
        print("  %-24s %2d members (%d rail + %d body); %d floor-eligible sellable"
              % (c[:24], n, nr, n - nr, elig))
    print("  QA: judgment purity, engine-vouched uids, gate-clean PDPs, rail "
          "availability, grain 12 rail + >=%d sellable floor, positions — ALL PASS"
          % COLLECTION_FLOOR)


if __name__ == "__main__":
    main()
