#!/usr/bin/env python3
"""receipt_ingest.py — the ONE sanctioned Wizard operation that ingests an immutable Engine
Curation Receipt v1 (task §3).

    ingest_receipt(receipt_path, expected_request, snapshot_dir=..., store_dir=...,
                   fulfillment_exception_path=None) -> IngestResult

WHAT THIS PROVES (task §0/§4/§5/§6). Given ONLY artifact REFERENCES, the Wizard:
  1. VERIFIES the receipt independently — contract version, self-hash, that receipt_id binds its
     own core, request-identity/run_mode/truth-export presence, factual terminal status. This
     re-implements the receipt contract's verification SEMANTICS from the artifact alone; it does
     NOT import the Engine's receipt verifier as authority and does NOT read Engine runtime state
     (task §4). Cross-repo parity with the Engine verifier is proven by a golden test, not trusted.
  2. BINDS the receipt to an EXACT Wizard-generated Request v2 (task §5): receipt.request.request_id
     == request.request_id AND receipt.request.request_sha256 == request.integrity.request_hash,
     with run_mode and category/eligibility identity identical. A receipt for another request,
     campaign, run, or category — or the same request_id with a wrong hash — is REFUSED. Never
     matched by filename or category label.
  3. Loads the EXACT immutable Truth Export v2 snapshot the receipt binds (by export_id +
     export_sha256), verifies it through the sanctioned Wizard v2 consumer, and INDEPENDENTLY
     recomputes the Request-v2 eligible sellable SET from the snapshot ALONE (task §6). The
     recomputed depth must equal receipt.eligibility.achieved_depth, and the recomputed SET — not
     a count — is the trusted Wizard-side material set for assembly (task §7/§11).
  4. Distinguishes SATISFIED (achieved >= required) from a factual SHORTFALL
     (shortfall_policy_exhausted): a shortfall requires the matching Fulfillment Exception v1
     (verified + bound), and opens a Wizard-owned Material Exception (task §8/§9) that BLOCKS
     production assembly until an owner resolves it. The Wizard NEVER auto-widens, substitutes,
     drops, or rewrites architecture.
  5. Refuses a diagnostic receipt in a production expectation (task §6/§25).

The caller supplies only refs + the expected Request v2 (which the Wizard itself generated with
generate_curation_request.py). The caller does NOT supply achieved depth, category, request hash,
truth-export hash, run mode, fulfillment status, or eligible products — every such value is derived
from immutable artifacts and independently re-verified (task §3).

STORAGE. An accepted receipt is recorded as an immutable Wizard-side ingestion record under
<store_dir>/receipt_ingestions/<receipt_id>.json (the receipt_id is the Engine's content-addressed
id, so the same receipt ingests idempotently). A Material Exception is recorded under
<store_dir>/material_exceptions/<material_exception_id>.json. Neither carries hand-authored facts.
"""
import hashlib
import json
import os

import truth_export_v2 as tev2

SUPPORTED_RECEIPT_CONTRACTS = frozenset({"1.0.0"})
SUPPORTED_FULFILLMENT_EXCEPTION_CONTRACTS = frozenset({"1.0.0"})
# The terminal statuses the Wizard understands. Mirrors the Engine's RECEIPTABLE_STATUSES, but
# is stated here independently — the Wizard does not import Engine constants as authority.
STATUS_SATISFIED = "satisfied"
STATUS_SHORTFALL = "shortfall_policy_exhausted"
RECEIPTABLE_STATUSES = frozenset({STATUS_SATISFIED, STATUS_SHORTFALL})

MATERIAL_EXCEPTION_CONTRACT_VERSION = "1.0.0"
INGESTION_CONTRACT_VERSION = "1.0.0"

# A Material Exception is CAMPAIGN JUDGMENT scaffolding, but its FACTUAL section is derived from
# Engine artifacts only. Allowed status: open | resolved (task §9).
MX_STATUS_OPEN = "open"
MX_STATUS_RESOLVED = "resolved"


class ReceiptIngestError(Exception):
    """A receipt/exception/binding invariant was violated (tamper, mismatch, missing, diagnostic
    in production, unresolved shortfall). Ingestion refuses; nothing is stored."""


# ---------------------------------------------------------------------------
# canonicalization + identity (independent re-implementation of the receipt contract)
# ---------------------------------------------------------------------------
def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_hex(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _artifact_sha256(artifact, sha_field):
    """sha256 of the artifact EXCLUDING its own self-referential sha field — the same rule the
    Engine stamps with. Independent implementation; parity proven by golden test."""
    m = {k: v for k, v in artifact.items() if k != sha_field}
    return _sha256_hex(_canonical(m))


def _receipt_identity_core(receipt):
    """The deterministic identity CORE of a receipt: everything EXCEPT id, self-sha and the
    non-semantic generated_at, with the provenance-only truth_export.immutable_ref stripped.
    Mirrors the Engine's _receipt_core projection so "rcpt_" + sha256(core)[:16] == receipt_id."""
    core = {k: v for k, v in receipt.items()
            if k not in ("receipt_id", "receipt_sha256", "generated_at")}
    core = json.loads(_canonical(core))   # deep copy, formatting-free
    if isinstance(core.get("truth_export"), dict):
        core["truth_export"].pop("immutable_ref", None)
    return core


def _exception_identity_core(exception):
    core = {k: v for k, v in exception.items()
            if k not in ("exception_id", "exception_sha256", "generated_at")}
    core = json.loads(_canonical(core))
    if isinstance(core.get("truth_export"), dict):
        core["truth_export"].pop("immutable_ref", None)
    return core


# ---------------------------------------------------------------------------
# independent receipt verification (task §4) — artifact-only, no Engine runtime
# ---------------------------------------------------------------------------
def verify_receipt(receipt):
    """Independently verify a Curation Receipt v1 from the artifact ALONE. Returns a dict of
    boolean checks; the caller decides. Establishes exactly what a Wizard-side reader can prove
    without Engine internal state (task §4/§15)."""
    checks = {}
    checks["version_supported"] = receipt.get("receipt_contract_version") in SUPPORTED_RECEIPT_CONTRACTS
    checks["receipt_sha256_valid"] = (
        _artifact_sha256(receipt, "receipt_sha256") == receipt.get("receipt_sha256"))
    checks["receipt_id_binds_core"] = (
        receipt.get("receipt_id") == "rcpt_" + _sha256_hex(
            _canonical(_receipt_identity_core(receipt)))[:16])
    req = receipt.get("request") or {}
    checks["has_request_identity"] = bool(req.get("request_id") and req.get("request_sha256"))
    checks["run_mode_valid"] = req.get("run_mode") in ("production", "diagnostic")
    ffb = receipt.get("fulfillment") or {}
    checks["terminal_status_factual"] = ffb.get("terminal_status") in RECEIPTABLE_STATUSES
    tex = receipt.get("truth_export") or {}
    checks["has_truth_export_binding"] = bool(tex.get("export_id") and tex.get("export_sha256"))
    elig = receipt.get("eligibility") or {}
    checks["eligibility_outcome_present"] = all(
        k in elig for k in ("category_id", "required_depth", "achieved_depth", "gap"))
    return checks


def verify_fulfillment_exception(exception):
    """Independently verify a Fulfillment Exception v1 from the artifact ALONE (task §8)."""
    checks = {}
    checks["version_supported"] = (
        exception.get("fulfillment_exception_contract_version")
        in SUPPORTED_FULFILLMENT_EXCEPTION_CONTRACTS)
    checks["exception_sha256_valid"] = (
        _artifact_sha256(exception, "exception_sha256") == exception.get("exception_sha256"))
    checks["exception_id_binds_core"] = (
        exception.get("exception_id") == "fxcp_" + _sha256_hex(
            _canonical(_exception_identity_core(exception)))[:16])
    checks["exception_kind_shortfall"] = exception.get("exception_kind") == STATUS_SHORTFALL
    req = exception.get("request") or {}
    checks["has_request_identity"] = bool(req.get("request_id") and req.get("request_sha256"))
    tex = exception.get("truth_export") or {}
    checks["has_truth_export_binding"] = bool(tex.get("export_id") and tex.get("export_sha256"))
    return checks


# ---------------------------------------------------------------------------
# Request v2 <-> Receipt binding (task §5)
# ---------------------------------------------------------------------------
def _request_identity(request_v2):
    """The identity fields of a Wizard-generated Request v2 the receipt must bind to.
    request_hash is recomputed from the artifact, never trusted from integrity."""
    integrity = request_v2.get("integrity") or {}
    return {
        "request_id": request_v2.get("request_id"),
        "request_sha256": _request_hash(request_v2),
        "stamped_hash": integrity.get("request_hash"),
        "run_mode": request_v2.get("run_mode"),
        "category_id": request_v2.get("category_id"),
        "required_depth": request_v2.get("required_depth"),
        "campaign_id": request_v2.get("campaign_id"),
        "run_ref": request_v2.get("run_ref"),
        "contract_version": request_v2.get("contract_version"),
    }


def _request_hash(request_v2):
    """Recompute the canonical Request v2 hash — the SAME algorithm the generator and the Engine
    use (json.dumps sort_keys, compact, minus integrity). The algorithm is the contract; no
    cross-repo import. Kept identical to generate_curation_request.request_hash."""
    payload = {k: v for k, v in request_v2.items() if k != "integrity"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False).encode("utf-8")).hexdigest()


def bind_receipt_to_request(receipt, request_v2, expected_campaign_id=None,
                            expected_run_ref=None):
    """Prove the receipt fulfils EXACTLY this Wizard-generated request (task §5). Returns a dict
    of boolean checks. Refuses a receipt for another request/campaign/run/category, or the same
    request_id with a wrong hash. Never matches by filename/label."""
    rid = _request_identity(request_v2)
    rreq = receipt.get("request") or {}
    relig = receipt.get("eligibility") or {}
    checks = {}
    # The presented request must itself be internally consistent (stamped hash matches recompute).
    checks["request_artifact_hash_consistent"] = (
        rid["stamped_hash"] is not None and rid["stamped_hash"] == rid["request_sha256"])
    checks["request_id_matches"] = (
        rreq.get("request_id") == rid["request_id"] and rid["request_id"] is not None)
    checks["request_sha256_matches"] = (
        rreq.get("request_sha256") == rid["request_sha256"] and rid["request_sha256"] is not None)
    checks["run_mode_matches"] = (
        rreq.get("run_mode") == rid["run_mode"] and rid["run_mode"] is not None)
    checks["request_contract_compatible"] = (
        rreq.get("request_contract_version") == rid["contract_version"])
    checks["category_matches"] = (
        relig.get("category_id") == rid["category_id"] and rid["category_id"] is not None)
    checks["required_depth_matches"] = (
        relig.get("required_depth") == rid["required_depth"])
    # Campaign/run association is correct when the caller asserts an expectation.
    checks["campaign_association_ok"] = (
        expected_campaign_id is None or rid["campaign_id"] == expected_campaign_id)
    checks["run_association_ok"] = (
        expected_run_ref is None or rid["run_ref"] == expected_run_ref)
    return checks


# ---------------------------------------------------------------------------
# Truth Export v2 verification + independent eligible-SET recomputation (task §6)
# ---------------------------------------------------------------------------
def _resolve_snapshot_path(receipt, snapshot_dir):
    """Locate the bound Truth Export v2 snapshot. Prefer the receipt's provenance immutable_ref
    when present + on disk; otherwise resolve <snapshot_dir>/<export_id>.jsonl (the Engine's
    content-addressed filename). The Wizard consumes by (export_id, export_sha256), so the path
    is just transport — never trusted for identity (task §26)."""
    tex = receipt.get("truth_export") or {}
    ref = tex.get("immutable_ref")
    if ref and os.path.exists(ref):
        return ref
    eid = tex.get("export_id")
    if snapshot_dir and eid:
        cand = os.path.join(snapshot_dir, "%s.jsonl" % eid)
        if os.path.exists(cand):
            return cand
    return ref  # may be None/missing — caller raises a precise refusal


def recompute_eligible_set(receipt, request_v2, snapshot_dir=None):
    """Load the EXACT bound Truth Export v2 snapshot and recompute the Request-v2 eligible
    sellable SET from it ALONE (task §6), using the sanctioned Wizard v2 consumer. Returns
    (eligible_set, snapshot_meta). Raises ReceiptIngestError on any missing/tampered/mismatched
    snapshot. Never reads Engine logs, taxonomy streams, or Source Profile config."""
    tex = receipt.get("truth_export") or {}
    eid, esha = tex.get("export_id"), tex.get("export_sha256")
    path = _resolve_snapshot_path(receipt, snapshot_dir)
    if not path or not os.path.exists(path):
        raise ReceiptIngestError(
            "bound Truth Export v2 snapshot for export_id %r not found (looked at immutable_ref "
            "and %r) — cannot recompute eligibility against an unverifiable snapshot"
            % (eid, snapshot_dir))
    try:
        snap = tev2.load_snapshot(path, expect_export_id=eid, expect_export_sha256=esha)
    except tev2.TruthExportError as e:
        raise ReceiptIngestError("bound Truth Export v2 snapshot refused: %s" % e)
    # The eligibility spec the Engine evaluated IS the request's eligibility block. The Wizard
    # recomputes the SET from the request + snapshot, mirroring the Engine kernel exactly.
    spec = request_v2.get("eligibility") or {"category_id": request_v2.get("category_id")}
    eligible = tev2.eligible_sellable_set(spec, snap)
    return eligible, snap["meta"]


# ---------------------------------------------------------------------------
# immutable Wizard-side storage (task §7/§9)
# ---------------------------------------------------------------------------
def _atomic_write_immutable(path, obj, identity_excludes=("stored_at",)):
    """Write canonical JSON immutably: same id + byte-identical -> no-op; same id + different
    SEMANTIC identity (everything but identity_excludes) -> refuse. Atomic replace."""
    raw = (_canonical(obj) + "\n").encode("utf-8")
    if os.path.exists(path):
        existing_raw = open(path, "rb").read()
        if existing_raw == raw:
            return False
        try:
            existing = json.loads(existing_raw.decode("utf-8"))
        except ValueError:
            existing = None

        def ident(o):
            return {k: v for k, v in (o or {}).items() if k not in identity_excludes}
        if existing is None or ident(existing) != ident(obj):
            raise ReceiptIngestError(
                "immutable record %s already exists with a DIFFERENT semantic identity — a "
                "receipt ingestion / material exception id is never overwritten with different "
                "content" % os.path.basename(path))
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return True


# ---------------------------------------------------------------------------
# Material Exception (task §9) — Wizard-owned; factual section derived from Engine artifacts
# ---------------------------------------------------------------------------
def _material_exception_core(receipt, exception):
    """Deterministic identity core for a Material Exception. The factual fields are DERIVED from
    the verified Engine receipt + fulfillment exception — never hand-authored (task §9)."""
    elig = receipt.get("eligibility") or {}
    return {
        "material_exception_contract_version": MATERIAL_EXCEPTION_CONTRACT_VERSION,
        "request_id": (receipt.get("request") or {}).get("request_id"),
        "request_sha256": (receipt.get("request") or {}).get("request_sha256"),
        "receipt_id": receipt.get("receipt_id"),
        "receipt_sha256": receipt.get("receipt_sha256"),
        "fulfillment_exception_id": exception.get("exception_id"),
        "fulfillment_exception_sha256": exception.get("exception_sha256"),
        "category_id": elig.get("category_id"),
        "required_depth": elig.get("required_depth"),
        "achieved_depth": elig.get("achieved_depth"),
        "gap": elig.get("gap"),
        "factual_reason": STATUS_SHORTFALL,
    }


def open_material_exception(receipt, exception, store_dir, generated_at=None):
    """Open (or idempotently re-open) a Wizard-owned Material Exception for a factual shortfall
    (task §9). status=open. No owner_resolution yet; the owner resolves it later. This BLOCKS
    production assembly. NO automatic campaign mutation, widening, or substitution."""
    core = _material_exception_core(receipt, exception)
    mx_id = "mtxc_" + _sha256_hex(_canonical(core))[:16]
    record = dict(core)
    record["material_exception_id"] = mx_id
    record["status"] = MX_STATUS_OPEN
    record["owner_resolution"] = None
    record["stored_at"] = generated_at or ""
    record["material_exception_sha256"] = _artifact_sha256(record, "material_exception_sha256")
    path = os.path.join(store_dir, "material_exceptions", "%s.json" % mx_id)
    wrote = _atomic_write_immutable(path, record,
                                    identity_excludes=("stored_at", "material_exception_sha256"))
    return {"material_exception_id": mx_id, "record": record, "path": path, "wrote": wrote}


# ---------------------------------------------------------------------------
# THE one sanctioned ingestion operation (task §3)
# ---------------------------------------------------------------------------
class IngestResult(dict):
    """Structured ingestion outcome. Truthy `accepted` means the receipt verified, bound, and its
    eligible set was independently recomputed. `terminal_status` is derived from the receipt.
    `material_exception` is set (and `blocks_assembly`) for a factual shortfall."""


def ingest_receipt(receipt_path, expected_request, snapshot_dir=None, store_dir=None,
                   fulfillment_exception_path=None, expected_run_mode="production",
                   expected_campaign_id=None, expected_run_ref=None, generated_at=None):
    """Ingest ONE immutable Curation Receipt v1 mechanically (task §3). `expected_request` is the
    exact Wizard-generated Request v2 (dict or path) this receipt must fulfil. Returns an
    IngestResult; raises ReceiptIngestError on any refusal. Stores an immutable ingestion record
    on acceptance; opens a Material Exception for a factual shortfall.

    The caller supplies only references + the expected request + the expected run_mode; every
    authoritative value is derived and re-verified from immutable artifacts."""
    receipt = _load_json(receipt_path, "receipt")
    request_v2 = _load_json(expected_request, "expected request v2") \
        if isinstance(expected_request, str) else expected_request

    # 1) independent receipt verification (task §4)
    rchecks = verify_receipt(receipt)
    if not all(rchecks.values()):
        raise ReceiptIngestError(
            "receipt failed independent verification: %s"
            % _failed(rchecks))

    # 2) diagnostic-in-production refusal (task §6/§25) — BEFORE binding, an authority check.
    receipt_mode = (receipt.get("request") or {}).get("run_mode")
    if expected_run_mode == "production" and receipt_mode != "production":
        raise ReceiptIngestError(
            "receipt run_mode is %r but a production ingestion refuses non-production artifacts — "
            "a diagnostic artifact can never satisfy a production package (task §6/§25)"
            % receipt_mode)
    if receipt_mode != expected_run_mode:
        raise ReceiptIngestError(
            "receipt run_mode %r does not match the expected run_mode %r"
            % (receipt_mode, expected_run_mode))

    # 3) Request <-> Receipt binding (task §5)
    bchecks = bind_receipt_to_request(receipt, request_v2,
                                      expected_campaign_id=expected_campaign_id,
                                      expected_run_ref=expected_run_ref)
    if not all(bchecks.values()):
        raise ReceiptIngestError(
            "receipt does not bind to the expected Wizard-generated Request v2: %s"
            % _failed(bchecks))

    # 4) independent eligible-SET recomputation from the bound snapshot (task §6)
    eligible_set, snap_meta = recompute_eligible_set(receipt, request_v2, snapshot_dir)
    elig = receipt.get("eligibility") or {}
    achieved = elig.get("achieved_depth")
    required = elig.get("required_depth")
    recomputed_depth = len(eligible_set)
    if recomputed_depth != achieved:
        raise ReceiptIngestError(
            "independent recomputation (%d eligible sellable products) does not match the "
            "receipt's achieved_depth (%r) — a hard contract/coherence failure, not a tolerance "
            "(task §6)" % (recomputed_depth, achieved))

    terminal = (receipt.get("fulfillment") or {}).get("terminal_status")

    result = IngestResult({
        "accepted": True,
        "receipt_id": receipt.get("receipt_id"),
        "receipt_sha256": receipt.get("receipt_sha256"),
        "request_id": (receipt.get("request") or {}).get("request_id"),
        "request_sha256": (receipt.get("request") or {}).get("request_sha256"),
        "category_id": elig.get("category_id"),
        "run_mode": receipt_mode,
        "terminal_status": terminal,
        "required_depth": required,
        "achieved_depth": achieved,
        "recomputed_depth": recomputed_depth,
        "eligible_sellable_set": sorted(eligible_set),
        "truth_export_id": (receipt.get("truth_export") or {}).get("export_id"),
        "truth_export_sha256": (receipt.get("truth_export") or {}).get("export_sha256"),
        "receipt_checks": rchecks,
        "binding_checks": bchecks,
        "material_exception": None,
        "blocks_assembly": False,
        "satisfied": False,
    })

    # 5) terminal-status semantics (task §7/§8)
    if terminal == STATUS_SATISFIED:
        if not (recomputed_depth >= required):
            raise ReceiptIngestError(
                "receipt is `satisfied` but the independently recomputed eligible depth %d < "
                "required %d — refusing to treat the request as fulfilled" % (recomputed_depth,
                                                                              required))
        result["satisfied"] = True
    elif terminal == STATUS_SHORTFALL:
        # A factual shortfall REQUIRES the matching Fulfillment Exception (task §8), then opens a
        # Wizard Material Exception that blocks assembly (task §9). No auto-widen/substitution.
        if not fulfillment_exception_path:
            raise ReceiptIngestError(
                "receipt is `shortfall_policy_exhausted` but no Fulfillment Exception was "
                "supplied — a shortfall requires its matching Fulfillment Exception v1 (task §8)")
        exception = _load_json(fulfillment_exception_path, "fulfillment exception")
        _verify_and_bind_exception(exception, receipt, required, achieved, elig.get("gap"))
        if store_dir is None:
            raise ReceiptIngestError(
                "a shortfall opens a Material Exception, which requires a store_dir")
        mx = open_material_exception(receipt, exception, store_dir, generated_at=generated_at)
        result["material_exception"] = mx["record"]
        result["material_exception_id"] = mx["material_exception_id"]
        result["blocks_assembly"] = True
    else:  # pragma: no cover - guarded by verify_receipt terminal_status_factual
        raise ReceiptIngestError("unhandled terminal status %r" % terminal)

    # 6) record the immutable ingestion (task §7). receipt_id is content-addressed by the Engine,
    #    so re-ingesting the same receipt is idempotent.
    if store_dir is not None:
        rec = {
            "ingestion_contract_version": INGESTION_CONTRACT_VERSION,
            "receipt_id": result["receipt_id"],
            "receipt_sha256": result["receipt_sha256"],
            "request_id": result["request_id"],
            "request_sha256": result["request_sha256"],
            "category_id": result["category_id"],
            "run_mode": result["run_mode"],
            "terminal_status": terminal,
            "required_depth": required,
            "achieved_depth": achieved,
            "recomputed_depth": recomputed_depth,
            "eligible_sellable_set": result["eligible_sellable_set"],
            "truth_export_id": result["truth_export_id"],
            "truth_export_sha256": result["truth_export_sha256"],
            "material_exception_id": result.get("material_exception_id"),
            "stored_at": generated_at or "",
        }
        rec["ingestion_sha256"] = _artifact_sha256(rec, "ingestion_sha256")
        ipath = os.path.join(store_dir, "receipt_ingestions", "%s.json" % result["receipt_id"])
        result["ingestion_record"] = rec
        result["ingestion_path"] = ipath
        result["wrote_ingestion"] = _atomic_write_immutable(
            ipath, rec, identity_excludes=("stored_at", "ingestion_sha256"))

    return result


def _verify_and_bind_exception(exception, receipt, required, achieved, gap):
    """Independently verify a Fulfillment Exception and prove it binds the SAME request /
    fulfillment / truth export / required-achieved-gap as the receipt (task §8). Refuses on any
    mismatch — the Wizard never accepts a shortfall exception for a different fulfillment."""
    echecks = verify_fulfillment_exception(exception)
    if not all(echecks.values()):
        raise ReceiptIngestError(
            "fulfillment exception failed independent verification: %s" % _failed(echecks))
    rreq = receipt.get("request") or {}
    ereq = exception.get("request") or {}
    if ereq.get("request_id") != rreq.get("request_id") or \
       ereq.get("request_sha256") != rreq.get("request_sha256"):
        raise ReceiptIngestError(
            "fulfillment exception binds a different request than the receipt (%s vs %s) — refusing"
            % (ereq.get("request_id"), rreq.get("request_id")))
    rff = receipt.get("fulfillment") or {}
    eff = exception.get("fulfillment") or {}
    if eff.get("fulfillment_id") != rff.get("fulfillment_id"):
        raise ReceiptIngestError(
            "fulfillment exception binds fulfillment %s but the receipt is %s — refusing"
            % (eff.get("fulfillment_id"), rff.get("fulfillment_id")))
    if eff.get("terminal_revision") != rff.get("terminal_revision"):
        raise ReceiptIngestError(
            "fulfillment exception terminal_revision %r != receipt %r — refusing"
            % (eff.get("terminal_revision"), rff.get("terminal_revision")))
    rtex = receipt.get("truth_export") or {}
    etex = exception.get("truth_export") or {}
    if etex.get("export_id") != rtex.get("export_id") or \
       etex.get("export_sha256") != rtex.get("export_sha256"):
        raise ReceiptIngestError(
            "fulfillment exception binds a different Truth Export snapshot than the receipt — "
            "refusing")
    if exception.get("required_depth") != required or exception.get("achieved_depth") != achieved \
       or exception.get("gap") != gap:
        raise ReceiptIngestError(
            "fulfillment exception depth facts (required/achieved/gap = %r/%r/%r) disagree with "
            "the receipt (%r/%r/%r) — refusing"
            % (exception.get("required_depth"), exception.get("achieved_depth"),
               exception.get("gap"), required, achieved, gap))
    if exception.get("category_id") != (receipt.get("eligibility") or {}).get("category_id"):
        raise ReceiptIngestError(
            "fulfillment exception category %r != receipt category %r — refusing"
            % (exception.get("category_id"), (receipt.get("eligibility") or {}).get("category_id")))


def _failed(checks):
    return ", ".join(sorted(k for k, v in checks.items() if not v))


def _load_json(path_or_obj, what):
    if isinstance(path_or_obj, (dict, list)):
        return path_or_obj
    if not os.path.exists(path_or_obj):
        raise ReceiptIngestError("%s not found: %s" % (what, path_or_obj))
    with open(path_or_obj, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# resolve a Material Exception (task §9) — owner judgment; open -> resolved
# ---------------------------------------------------------------------------
def resolve_material_exception(store_dir, material_exception_id, owner_resolution,
                               generated_at=None):
    """Record an owner JUDGMENT on an open Material Exception (open -> resolved). The
    owner_resolution is opaque campaign judgment supplied by the owner; the FACTUAL section
    (required/achieved/gap, bound receipt/exception/truth-export ids) is NEVER rewritten.

    CRITICAL (task §0 Issue B / §6 frozen rule): resolving a Material Exception is a DECISION
    RECORD ONLY. It does NOT — and can NEVER — waive product/material fulfillment. It does not
    change achieved_depth, does not make the shortfall Receipt satisfied, does not waive render_003,
    and does not make package completeness ignore the failed material requirement. A resolved
    Material Exception whose expected Request still has no satisfied Receipt leaves package
    completeness BLOCKED (check_receipt_completeness keys on the Receipt terminal status, NOT on the
    exception flag). What eventually permits completeness is a CURRENT expected Request set with a
    genuine satisfied Receipt per expected Request — produced by the (not-yet-built) architecture/
    request-revision flow, never by this call. There is no silent auto-resolution and no waiver."""
    path = os.path.join(store_dir, "material_exceptions", "%s.json" % material_exception_id)
    if not os.path.exists(path):
        raise ReceiptIngestError("no material exception %r under %s"
                                 % (material_exception_id, store_dir))
    record = json.load(open(path, encoding="utf-8"))
    if record.get("status") == MX_STATUS_RESOLVED:
        return record
    # A resolution is a NEW immutable record (facts preserved, status flips). We rewrite in place
    # only the resolution + status, keeping the factual identity core; the file's factual identity
    # is unchanged so this is a legitimate controlled transition, not a tamper.
    record["status"] = MX_STATUS_RESOLVED
    record["owner_resolution"] = owner_resolution
    record["resolved_at"] = generated_at or ""
    record["material_exception_sha256"] = _artifact_sha256(record, "material_exception_sha256")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(_canonical(record) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return record


def load_material_exceptions(store_dir):
    d = os.path.join(store_dir, "material_exceptions")
    out = []
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".json"):
            out.append(json.load(open(os.path.join(d, fn), encoding="utf-8")))
    return out


def load_ingestions(store_dir):
    d = os.path.join(store_dir, "receipt_ingestions")
    out = []
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".json"):
            out.append(json.load(open(os.path.join(d, fn), encoding="utf-8")))
    return out
