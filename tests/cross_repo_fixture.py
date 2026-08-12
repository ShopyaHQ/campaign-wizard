#!/usr/bin/env python3
"""cross_repo_fixture.py — shared helper that drives the REAL Engine (CollectionCuration) to
produce genuine, immutable Curation Receipt v1 artifacts (satisfied / shortfall / diagnostic) plus
their exact Truth Export v2 snapshots, from a Wizard-generated Request v2. Used by the receipt
ingestion / package tests so the cross-repo contract is exercised end to end, not mocked.

Mirrors the Engine's own receipt-test harness (tools/../tests/test_curation_receipt.py): a fake
Engine store (product log + taxonomy log + source roster), start_fulfillment, drive to a terminal
status, emit_curation_receipt. The Wizard side then verifies/binds/recomputes independently.

Engine located via one isolated constant ($SHOPYA_ENGINE_ROOT override).
"""
import os
import sys
import json
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
ENGINE_ROOT = os.environ.get("SHOPYA_ENGINE_ROOT") or os.path.join(
    os.path.dirname(ROOT), "shopya-collection-curation")
sys.path.insert(0, os.path.join(ENGINE_ROOT, "tools"))

import generate_curation_request as gcr   # noqa: E402  (Wizard generator)
import fulfillment as ff                   # noqa: E402  (Engine)
import curation_receipt as cr              # noqa: E402  (Engine)
from taxonomy import load_taxonomy         # noqa: E402
from taxonomy_membership import make_membership  # noqa: E402

TAX = load_taxonomy()
READY = {"ready": True, "roster_working_profiles": 200, "required": 200}
DEFAULT_CATEGORY = "w.coats"


def _obs(uid, url, price=100.0, stock="in_stock", conf="confirmed_live"):
    return {"product_uid": uid, "brand": uid.split(":")[0], "product_name": "P " + uid,
            "colorway": "cw", "price_native": price, "currency": "USD", "region": "US",
            "price_usd": price, "stock_status": stock, "url": url, "verification_url": url,
            "observed_at": "2026-08-12", "fetched_via": "platform_json", "status": "verified",
            "collection_ids": ["C"], "run_date": "2026-08-12", "confidence": conf}


class EngineEnv(object):
    """A disposable real-Engine environment: product log + taxonomy log + source roster + snapshot
    dir + fulfillment/receipt/exception stores. Produces genuine Engine artifacts."""

    def __init__(self):
        self.d = tempfile.mkdtemp(prefix="shopya_xrepo_")
        self.plog = os.path.join(self.d, "p.jsonl")
        self.tlog = os.path.join(self.d, "t.jsonl")
        self.records = os.path.join(self.d, "records")
        self.receipts = os.path.join(self.d, "receipts")
        self.exceptions = os.path.join(self.d, "exceptions")
        self.snaps = os.path.join(self.d, "snaps")
        open(self.plog, "w").close()
        open(self.tlog, "w").close()
        self.srccfg = os.path.join(self.d, "brand_fetch_config.yaml")
        import yaml as _yaml
        with open(self.srccfg, "w") as f:
            _yaml.safe_dump({"brands": [
                {"source_id": "src-A", "brand": "Source A",
                 "storefront_url": "https://a.example", "access_method": "static_html"},
                {"source_id": "src-B", "brand": "Source B",
                 "storefront_url": "https://b.example", "access_method": "platform_json"},
            ]}, f)

    def seed(self, n, category=DEFAULT_CATEGORY, uid_prefix="seed"):
        """Append n confirmed in-stock sellable products in `category` to the logs."""
        rows, events = [], []
        for i in range(n):
            uid = "%s-%02d:p%02d:cw" % (uid_prefix, i, i)
            url = "https://%s-%02d.com/products/p%02d" % (uid_prefix, i, i)
            rows.append(_obs(uid, url))
            events.append(make_membership(uid, category, "src", "e", "2026-08-12",
                                          "2026-08-12", taxonomy=TAX))
        with open(self.plog, "a") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        with open(self.tlog, "a") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")

    def request(self, category=DEFAULT_CATEGORY, required_depth=50, run_mode="production",
                run_id="cmp_01KZCD765E6NNW2TZR1AFHQMWG", campaign_id="xrepo-2026"):
        """A genuine Wizard-generated Request v2 (deterministic, canonically hashed)."""
        run_state = {"run": {"run_id": run_id, "run_mode": run_mode},
                     "identity": {"campaign_id": {"value": campaign_id}}}
        art, errs = gcr.build_request(run_state, category, required_depth)
        assert not errs, errs
        return art

    def start(self, request, info=READY):
        return ff.start_fulfillment(request, records_dir=self.records, info=info,
                                    product_log_path=self.plog, taxonomy_log_path=self.tlog,
                                    snapshot_dir=self.snaps)

    def recompute(self, record):
        return ff.recompute_fulfillment(record, records_dir=self.records,
                                        product_log_path=self.plog, taxonomy_log_path=self.tlog,
                                        snapshot_dir=self.snaps)

    def emit(self, fid):
        return cr.emit_curation_receipt(fid, records_dir=self.records, receipts_dir=self.receipts,
                                        exceptions_dir=self.exceptions)

    # -- terminal drivers (mirror the Engine's own harness) --
    def satisfied(self, category=DEFAULT_CATEGORY, depth=55, required=50, run_mode="production",
                  **req_kw):
        self.seed(depth, category=category, uid_prefix="s-%s" % category.replace(".", ""))
        rec = self.start(self.request(category=category, required_depth=required,
                                      run_mode=run_mode, **req_kw))
        assert rec["status"] == ff.STATUS_SATISFIED, rec["status"]
        req = self._last_request(category, required, run_mode, req_kw)
        return self.emit(rec["fulfillment_id"]), req, rec

    def shortfall(self, category=DEFAULT_CATEGORY, depth=30, required=50, run_mode="production",
                  **req_kw):
        self.seed(depth, category=category, uid_prefix="sf-%s" % category.replace(".", ""))
        req = self.request(category=category, required_depth=required, run_mode=run_mode, **req_kw)
        rec = self.start(req)
        t = ff.add_source_task(rec, "src-A", None, records_dir=self.records, config_path=self.srccfg)
        ff.update_source_task(rec, t["task_id"], status="in_progress", records_dir=self.records)
        ff.update_source_task(rec, t["task_id"], status="succeeded",
                              terminal_reason="searched_no_eligible_pdps", records_dir=self.records)
        ff.record_discovery_pass(rec, "discovery", "more sources", accepted_source_ids=[],
                                 result="completed", records_dir=self.records, config_path=self.srccfg)
        rec = self.recompute(rec)
        assert rec["status"] == ff.STATUS_SHORTFALL, rec["status"]
        return self.emit(rec["fulfillment_id"]), req, rec

    def _last_request(self, category, required, run_mode, req_kw):
        return self.request(category=category, required_depth=required, run_mode=run_mode, **req_kw)

    def close(self):
        import shutil
        shutil.rmtree(self.d, ignore_errors=True)
