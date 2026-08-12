#!/usr/bin/env python3
"""truth_export_v2.py — Wizard READ-ONLY consumer of an immutable Truth Export v2 snapshot.

The Wizard binds a production build to an EXACT immutable snapshot (export_id + export_sha256),
verifies it, and INDEPENDENTLY recomputes Request-v2 machine eligibility from the snapshot
truth alone — never reading Engine internal logs, taxonomy streams, or Source Profile config.

Everything the Wizard needs comes through the export contract:
  * meta.truth_contract_version (must be supported — 2.0.0);
  * meta.export_id / meta.export_sha256 (content identity; recomputed and matched);
  * meta source bindings (source_lines/source_sha256/taxonomy_source_sha256/taxonomy_ref) —
    optionally re-checked against the live engine to detect staleness;
  * per-row product truth (incl. source_id) + a taxonomy section of confirmed memberships.

REFUSES: unsupported version; export_sha256 mismatch (tampered); missing required product
fields; a v1 export presented to the v2 production flow.

The eligibility recomputation MIRRORS the Engine kernel exactly (floor + confirmed-membership at
the sellable grain + price + source_id merchant allow/deny), so Engine and Wizard produce the
SAME eligible sellable_product_uid SET from the same request+snapshot.
"""
import hashlib
import json

SUPPORTED_TRUTH_CONTRACTS_V2 = {"2.0.0"}

# per-row required product-truth fields (v2). A row missing any is a contract violation.
V2_REQUIRED_FIELDS = ("product_uid", "sellable_product_uid", "floor_eligible", "url_class",
                      "stock_status", "product_name", "brand", "url", "price_native",
                      "currency", "observed_at")


class TruthExportError(Exception):
    pass


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def verify_export_sha256(lines):
    """Recompute export_sha256 over the snapshot (excluding the stamped field) and match."""
    meta = lines[0]
    stamped = meta.get("export_sha256")
    if not stamped:
        return False
    m2 = {k: v for k, v in meta.items() if k != "export_sha256"}
    prelim = "\n".join(_canonical(x) for x in ([m2] + lines[1:])) + "\n"
    return stamped == hashlib.sha256(prelim.encode("utf-8")).hexdigest()


def load_snapshot(path, expect_export_id=None, expect_export_sha256=None,
                  engine_bindings=None):
    """Open + verify an immutable v2 snapshot. Returns a dict:
        {meta, rows_by_uid, confirmed_by_sellable, taxonomy_ref}.
    Raises TruthExportError on any refusal.

    expect_export_id / expect_export_sha256: if given (the reference a build is bound to),
        they MUST match — this is how the Wizard consumes an EXACT snapshot, not 'whatever is
        current'. engine_bindings (optional): {source_lines, source_sha256} to detect staleness."""
    raw = open(path, "rb").read()
    lines = [json.loads(l) for l in raw.decode("utf-8").splitlines() if l.strip()]
    if not lines or lines[0].get("type") != "meta":
        raise TruthExportError("snapshot has no meta line: %s" % path)
    meta = lines[0]

    cv = meta.get("truth_contract_version")
    if cv not in SUPPORTED_TRUTH_CONTRACTS_V2:
        raise TruthExportError(
            "truth_contract_version %r is not a supported v2 production contract (%s) — a v1 "
            "export cannot satisfy the v2 production flow" % (cv, sorted(SUPPORTED_TRUTH_CONTRACTS_V2)))

    if not verify_export_sha256(lines):
        raise TruthExportError("export_sha256 mismatch — snapshot is tampered or corrupt")

    if expect_export_id is not None and meta.get("export_id") != expect_export_id:
        raise TruthExportError("export_id %r does not match the bound reference %r"
                               % (meta.get("export_id"), expect_export_id))
    if expect_export_sha256 is not None and meta.get("export_sha256") != expect_export_sha256:
        raise TruthExportError("export_sha256 does not match the bound reference")

    if engine_bindings is not None:
        if (meta.get("source_lines"), meta.get("source_sha256")) != \
           (engine_bindings.get("source_lines"), engine_bindings.get("source_sha256")):
            raise TruthExportError("snapshot is STALE relative to the live engine product log")

    rows_by_uid, taxonomy = {}, None
    for rec in lines[1:]:
        if rec.get("type") == "taxonomy":
            taxonomy = rec
            continue
        missing = [f for f in V2_REQUIRED_FIELDS if f not in rec]
        if missing:
            raise TruthExportError("row %s missing required field(s) %s"
                                   % (rec.get("product_uid", "?"), missing))
        rows_by_uid[rec["product_uid"]] = rec
    if taxonomy is None:
        raise TruthExportError("v2 snapshot is missing its taxonomy section")

    return {
        "meta": meta,
        "rows_by_uid": rows_by_uid,
        "confirmed_by_sellable": {k: set(v) for k, v in
                                  (taxonomy.get("confirmed_memberships") or {}).items()},
        "taxonomy_ref": taxonomy.get("taxonomy_ref"),
    }


# ---------------------------------------------------------------------------
# eligibility recomputation — MIRRORS the Engine kernel exactly
# ---------------------------------------------------------------------------
_FLOOR_CONFIDENCE = ("confirmed_live", "verified")


def _floor_eligible(rec):
    return (rec.get("url_class") == "pdp" and rec.get("stock_status") == "in_stock"
            and rec.get("confidence") in _FLOOR_CONFIDENCE)


def _price_ok(rec, spec):
    p = rec.get("price_usd")
    lo, hi = spec.get("price_usd_min"), spec.get("price_usd_max")
    if lo is not None and (p is None or p < lo):
        return False
    if hi is not None and (p is None or p > hi):
        return False
    return True


def _merchant_ok(rec, spec):
    ident = rec.get("source_id") or rec.get("brand")   # stable source_id preferred (§8)
    allow, deny = spec.get("merchant_allow"), spec.get("merchant_deny")
    if deny and ident in set(deny):
        return False
    if allow and ident not in set(allow):
        return False
    return True


def eligible_sellable_set(spec, snapshot):
    """Recompute the eligible sellable_product_uid SET from the snapshot alone, mirroring the
    Engine kernel: a sellable counts iff SOME row passes floor+price+merchant AND the sellable
    has a confirmed membership for the requested category. collection_ids never participate."""
    category = spec.get("category_id")
    confirmed = snapshot["confirmed_by_sellable"]
    passing_rows = set()      # sellable_uids with >=1 row passing floor+price+merchant
    for rec in snapshot["rows_by_uid"].values():
        su = rec.get("sellable_product_uid")
        if su is None:
            continue
        if _floor_eligible(rec) and _price_ok(rec, spec) and _merchant_ok(rec, spec):
            passing_rows.add(su)
    return {su for su in passing_rows if category in confirmed.get(su, set())}


def eligible_depth(spec, snapshot):
    return len(eligible_sellable_set(spec, snapshot))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="verify + inspect a Truth Export v2 snapshot")
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--expect-id")
    ap.add_argument("--expect-sha256")
    a = ap.parse_args()
    snap = load_snapshot(a.snapshot, expect_export_id=a.expect_id,
                         expect_export_sha256=a.expect_sha256)
    m = snap["meta"]
    print("VERIFIED Truth Export v2 snapshot")
    print("  export_id   %s" % m.get("export_id"))
    print("  contract    %s" % m.get("truth_contract_version"))
    print("  products %s | sellable %s | floor-eligible %s | with-confirmed-taxonomy %s"
          % (m.get("products"), m.get("sellable_products"),
             m.get("floor_eligible_sellable_products"),
             m.get("confirmed_membership_sellable_products")))
