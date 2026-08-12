#!/usr/bin/env python3
"""Cross-repo golden tests: an Engine-produced immutable Truth Export v2 snapshot is verified
and consumed by the Wizard, and Engine + Wizard compute the SAME eligible sellable_product_uid
SET (not just counts) from the same Request-v2 eligibility. Also proves tamper/version/source/
taxonomy refusals.

    python3 tests/test_cross_repo_truth_export_v2.py

Engine located via one isolated constant ($SHOPYA_ENGINE_ROOT override).
"""
import os
import sys
import json
import tempfile
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
ENGINE_ROOT = os.environ.get("SHOPYA_ENGINE_ROOT") or os.path.join(
    os.path.dirname(ROOT), "shopya-collection-curation")
sys.path.insert(0, os.path.join(ENGINE_ROOT, "tools"))

import truth_export_v2 as wiz  # noqa: E402  (Wizard consumer)
import export_truth_v2 as eng  # noqa: E402  (Engine producer)
from eligibility import eligible_products  # noqa: E402
from sellable_identity import compute_sellable_uids  # noqa: E402
from taxonomy_membership import sellable_membership_view, make_membership  # noqa: E402
from taxonomy import load_taxonomy  # noqa: E402

PASS, FAIL = [], []
TAX = load_taxonomy()


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %s  %s%s" % ("PASS" if cond else "FAIL", name,
                          ("  <- " + detail) if detail and not cond else ""))


def obs(uid, brand, name, cw, url, stock="in_stock", conf="confirmed_live", price=100.0):
    return {"product_uid": uid, "brand": brand, "product_name": name, "colorway": cw,
            "price_native": price, "currency": "USD", "region": "US", "price_usd": price,
            "stock_status": stock, "url": url, "verification_url": url,
            "observed_at": "2026-08-12", "fetched_via": "platform_json", "status": "verified",
            "collection_ids": ["FW26-A"], "run_date": "2026-08-12", "confidence": conf}


def mem(uid, cid):
    return make_membership(uid, cid, "src", "e", "2026-08-12", "2026-08-12", taxonomy=TAX)


def make_fixture(rows, events, d):
    os.makedirs(d, exist_ok=True)
    plog = os.path.join(d, "p.jsonl"); tlog = os.path.join(d, "t.jsonl")
    with open(plog, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    with open(tlog, "w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
    return plog, tlog


def engine_eligible_set(rows_export, events, spec):
    """Engine-side eligible SET from the same authoritative rows + events."""
    rows = rows_export
    sv = sellable_membership_view(events, compute_sellable_uids(rows))
    return eligible_products(spec, rows, sv)["eligible_sellable_uids"]


def main():
    tmp = tempfile.mkdtemp()
    try:
        rows = [
            obs("a-brand:coat:black", "A Brand", "Coat", "black", "https://abrand.com/products/coat"),
            obs("b-brand:coat:navy", "B Brand", "Coat", "navy", "https://bbrand.com/products/coat", price=600.0),
            obs("c-brand:tee:white", "C Brand", "Tee", "white", "https://cbrand.com/products/tee", stock="low_stock"),
        ]
        events = [mem("a-brand:coat:black", "w.coats"), mem("b-brand:coat:navy", "w.coats"),
                  mem("c-brand:tee:white", "w.coats")]
        plog, tlog = make_fixture(rows, events, tmp)
        export = eng.build_export_v2(log_path=plog, taxonomy_log_path=tlog, generated_at="2026-08-12")
        snaps = os.path.join(tmp, "snaps")
        result = eng.write_snapshot(export, snapshot_dir=snaps)
        snap_path = result["snapshot_path"]

        # ---- HAPPY PATH: Wizard verifies + recomputes; SET equality ----
        spec = {"category_id": "w.coats", "price_usd_max": 300}
        snap = wiz.load_snapshot(snap_path, expect_export_id=result["export_id"],
                                 expect_export_sha256=result["export_sha256"])
        ok("Wizard verifies the exact Engine snapshot (id + sha256)", snap["meta"]["export_id"] == result["export_id"])
        wiz_set = wiz.eligible_sellable_set(spec, snap)
        eng_set = engine_eligible_set(export["rows"], events, spec)
        ok("Engine and Wizard compute the SAME eligible sellable SET (not just count)",
           wiz_set == eng_set and wiz_set == {"sp:a-brand:coat"}, "eng=%s wiz=%s" % (eng_set, wiz_set))

        # ---- TAMPERED snapshot -> Wizard refuses hash mismatch ----
        tampered = os.path.join(tmp, "tampered.jsonl")
        raw = open(snap_path, "rb").read().replace(b'"price_usd":100.0', b'"price_usd":5.0')
        open(tampered, "wb").write(raw)
        refused = False
        try:
            wiz.load_snapshot(tampered)
        except wiz.TruthExportError as e:
            refused = "export_sha256 mismatch" in str(e)
        ok("Wizard REFUSES a tampered snapshot (hash mismatch)", refused)

        # ---- WRONG export id / sha -> refused ----
        r1 = False
        try:
            wiz.load_snapshot(snap_path, expect_export_id="tex2_bogus")
        except wiz.TruthExportError:
            r1 = True
        ok("Wizard refuses a snapshot whose export_id != the bound reference", r1)
        r2 = False
        try:
            wiz.load_snapshot(snap_path, expect_export_sha256="deadbeef")
        except wiz.TruthExportError:
            r2 = True
        ok("Wizard refuses a snapshot whose export_sha256 != the bound reference", r2)

        # ---- TAXONOMY difference changes exported truth AND recomputed eligibility ----
        events2 = [mem("a-brand:coat:black", "w.jackets"),  # A now only w.jackets, not w.coats
                   mem("b-brand:coat:navy", "w.coats")]
        plog2, tlog2 = make_fixture(rows, events2, os.path.join(tmp, "f2"))
        export2 = eng.build_export_v2(log_path=plog2, taxonomy_log_path=tlog2, generated_at="2026-08-12")
        r3 = eng.write_snapshot(export2, snapshot_dir=snaps)
        ok("a taxonomy change yields a different export identity",
           r3["export_id"] != result["export_id"])
        snap2 = wiz.load_snapshot(r3["snapshot_path"])
        # A no longer confirmed for w.coats; B is >300 so excluded by price -> empty set
        ok("taxonomy change changes recomputed eligibility identically (empty w.coats<=300)",
           wiz.eligible_sellable_set(spec, snap2) == engine_eligible_set(export2["rows"], events2, spec)
           == set())

        # ---- SOURCE CONSTRAINT via stable source_id (two sources sharing a host) ----
        shared_rows = [
            obs("srcx:coat:1", "Source X", "Coat", "1", "https://sharedhost.com/x/products/coat"),
            obs("srcy:coat:1", "Source Y", "Coat", "1", "https://sharedhost.com/y/products/coat"),
        ]
        # inject explicit source_ids by giving each row a distinct source_id via the export
        # (the producer resolves from roster; here we simulate a shared host with distinct ids
        #  by post-stamping — mirrors what a real roster with two profiles on one host produces).
        sev = [mem("srcx:coat:1", "w.coats"), mem("srcy:coat:1", "w.coats")]
        sp, st = make_fixture(shared_rows, sev, os.path.join(tmp, "f3"))
        exp3 = eng.build_export_v2(log_path=sp, taxonomy_log_path=st, generated_at="2026-08-12")
        # stamp distinct stable source_ids (roster-independent, to exercise allow/deny by id)
        for r in exp3["rows"]:
            r["source_id"] = "src_X" if r["product_uid"].startswith("srcx") else "src_Y"
        r4 = eng.write_snapshot(exp3, snapshot_dir=snaps)
        snap3 = wiz.load_snapshot(r4["snapshot_path"])
        allow_spec = {"category_id": "w.coats", "merchant_allow": ["src_X"]}
        wiz_allow = wiz.eligible_sellable_set(allow_spec, snap3)
        eng_allow = engine_eligible_set(exp3["rows"], sev, allow_spec)
        ok("source_id allow-list selects the right source across a shared host (SET equal)",
           wiz_allow == eng_allow and wiz_allow == {"sp:source-x:coat"},
           "eng=%s wiz=%s" % (eng_allow, wiz_allow))
        deny_spec = {"category_id": "w.coats", "merchant_deny": ["src_X"]}
        ok("source_id deny-list excludes the right source (SET equal)",
           wiz.eligible_sellable_set(deny_spec, snap3)
           == engine_eligible_set(exp3["rows"], sev, deny_spec) == {"sp:source-y:coat"})

        # ---- v1 export cannot satisfy the v2 production flow ----
        v1 = os.path.join(tmp, "v1.jsonl")
        with open(v1, "w") as f:
            f.write(json.dumps({"type": "meta", "truth_contract_version": "1.0.0",
                                "export_sha256": "x"}) + "\n")
        r5 = False
        try:
            wiz.load_snapshot(v1)
        except wiz.TruthExportError as e:
            r5 = "not a supported v2" in str(e)
        ok("a v1 truth export is REFUSED by the v2 production consumer", r5)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        for x in FAIL:
            print("  FAILED: %s" % x)
        sys.exit(1)


if __name__ == "__main__":
    main()
