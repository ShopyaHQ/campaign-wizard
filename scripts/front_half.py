#!/usr/bin/env python3
"""front_half.py — the structured Wizard front half (spec 1.8.0).

THE sanctioned path that authors the four first-class structured objects and their immutable
revisions, and that stamps the state-file structured_objects spine + section/composite hashes the
validator recomputes. Nothing here is hand-authored prose the agent must "remember to construct";
each object is BUILT and canonically HASHED by a producer, then registered.

Objects (owner ruling 2026-08-12 — structured is AUTHORITY, prose is derived/historical):

  research_brief       (task §3)  — kickoff normalized into the exact research problem, provenance-
                                    labelled per material field (owner_supplied|system_inferred|derived)
  research_ledger      (task §5)  — structured evidence, stable per-signal ids + hashes
  campaign_directions  (task §7)  — 2–4 genuinely distinct directions from the ledger, per-direction hash
  campaign_spec        (task §9+) — ONE logical object, IMMUTABLE revisions, eight section hashes +
                                    a composite hash; the front-half architecture authority

CANONICAL HASHING (must match validate_state.py._canonical_hash and the repo's other canonical
recipes byte-for-byte): json.dumps(obj, sort_keys=True, separators=(',',':'), ensure_ascii=False)
then sha256. Sorted keys + compact separators mean key order and whitespace never move the hash;
only semantic content does (task §18: "semantic normalized representation, not whitespace bytes").

IMMUTABILITY (task §18): register-object writes a NEW revision file (…​.r<NNN>.yaml) and never edits
an existing one. A material change to any section mints a new campaign_spec revision + parent link.

DEPENDENCY INVALIDATION (task §19): declared in the schema's dependency_graph. When an upstream
object/section materially changes (its hash moves), every downstream front-half approval is marked
invalidated (state.invalidated) — deterministic, never agent discretion. An independent leaf (e.g. a
content headline) does not touch an unrelated upstream approval.
"""
import hashlib
import json
import os

# ---- canonical hashing (identical recipe across run.py / validate_state.py / execution_package.py) ----
CS_SECTIONS = ["premise", "vertical_strategies", "collection_selections", "rails",
               "content_program", "naming_voice", "default_composition", "seam_intent"]


class FrontHalfError(Exception):
    """A structured-object invariant was violated. The producer refuses (never emits a bad object)."""


def canonical_hash(obj):
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False).encode("utf-8")).hexdigest()


def composite_hash(section_hashes, sections):
    """Order-stable composite over the named sections' hashes — same recipe the validator uses in
    p_approval_binds_spec_composite."""
    return canonical_hash([[s, section_hashes[s]] for s in sections])


# ---------------------------------------------------------------------------
# object builders + validators — each returns the canonical object (with hashes stamped)
# ---------------------------------------------------------------------------
def _require(obj, fields, what):
    missing = [f for f in fields if f not in obj or obj[f] in (None, "", [], {})]
    # allow explicitly-empty lists where the schema says a list may be [] (handled per-object below)
    return missing


PROVENANCE = {"owner_supplied", "system_inferred", "derived"}
RESEARCH_FAMILIES = {"cultural", "behavioral", "commercial", "competitive",
                     "seasonal_temporal", "platform_surface"}
VERTICALS = {"fashion", "home_interior", "tech", "beauty", "travel", "wellness_health"}


def build_research_brief(payload):
    """Validate + canonicalize a research_brief (task §3/§4). Every MATERIAL field must be
    {value, provenance}; provenance ∈ {owner_supplied, system_inferred, derived} so inference is
    never hidden."""
    req = ["brief_id", "revision", "campaign_id", "run_id", "objective", "desired_behavior",
           "market", "audience_context", "campaign_window", "territory", "exclusions",
           "owner_inputs", "inferred_inputs", "assumptions", "unresolved_questions", "provenance"]
    missing = [f for f in req if f not in payload]
    if missing:
        raise FrontHalfError("research_brief missing fields: %s" % sorted(missing))
    material = ["objective", "desired_behavior", "market", "audience_context",
                "campaign_window", "territory"]
    for f in material:
        v = payload.get(f)
        if not isinstance(v, dict) or "value" not in v or v.get("provenance") not in PROVENANCE:
            raise FrontHalfError(
                "research_brief.%s must be {value, provenance in %s} — inference is never hidden "
                "(task §3); got %r" % (f, sorted(PROVENANCE), v))
    obj = dict(payload)
    obj["object_kind"] = "research_brief"
    obj.pop("canonical_hash", None)
    obj["canonical_hash"] = canonical_hash(obj)
    return obj


def build_research_ledger(payload):
    """Validate + canonicalize a research_ledger (task §5/§6). Structured evidence, stable
    per-signal ids + per-signal hashes; evidence standards enforced."""
    for f in ["ledger_id", "revision", "brief_ref", "signals"]:
        if f not in payload:
            raise FrontHalfError("research_ledger missing field %r" % f)
    signals = payload.get("signals") or []
    if not signals:
        raise FrontHalfError("research_ledger has no signals — a ledger is structured evidence, "
                             "not an empty container (task §5)")
    sig_req = ["signal_id", "family", "claim", "source", "source_type", "captured_at",
               "market_time_relevance", "confidence", "evidence_strength", "supports",
               "contradicts", "limitations", "provenance"]
    seen = set()
    out_signals = []
    for i, sig in enumerate(signals, 1):
        miss = [f for f in sig_req if f not in sig]
        if miss:
            raise FrontHalfError("signal %d missing fields %s" % (i, sorted(miss)))
        if sig["family"] not in RESEARCH_FAMILIES:
            raise FrontHalfError("signal %r family %r not in %s"
                                 % (sig["signal_id"], sig["family"], sorted(RESEARCH_FAMILIES)))
        # evidence standards (task §6): no weak-source-masquerading, no benchmark-as-evidence.
        if sig.get("source_type") == "golden_benchmark":
            raise FrontHalfError("signal %r sources the CLOSED golden benchmark — the historical "
                                 "Almost Fall benchmark may never supply current market evidence "
                                 "(task §6/§27)" % sig["signal_id"])
        if not sig.get("source"):
            raise FrontHalfError("signal %r is unsourced — unsourced trend claims are refused "
                                 "(task §6)" % sig["signal_id"])
        if sig["signal_id"] in seen:
            raise FrontHalfError("duplicate signal_id %r" % sig["signal_id"])
        seen.add(sig["signal_id"])
        sig = dict(sig)
        sig.pop("signal_hash", None)
        sig["signal_hash"] = canonical_hash(sig)
        out_signals.append(sig)
    obj = dict(payload)
    obj["object_kind"] = "research_ledger"
    obj["signals"] = out_signals
    obj.pop("canonical_hash", None)
    obj["canonical_hash"] = canonical_hash(obj)
    return obj


def build_campaign_directions(payload, ledger=None):
    """Validate + canonicalize campaign_directions (task §7). 2–4 genuinely distinct directions,
    each with a stable id + per-direction canonical hash (the owner selection binds that hash).
    Every evidence_ref must resolve to a signal in the referenced ledger when one is supplied."""
    for f in ["directions_id", "revision", "ledger_ref", "directions", "recommended_direction_id"]:
        if f not in payload:
            raise FrontHalfError("campaign_directions missing field %r" % f)
    dirs = payload.get("directions") or []
    if not (2 <= len(dirs) <= 4):
        raise FrontHalfError("campaign_directions must carry 2–4 directions (task §7); got %d"
                             % len(dirs))
    dir_req = ["direction_id", "title", "evidence_refs", "shopper_tension", "why_now",
               "shopya_role", "desired_behavior", "campaign_opportunity",
               "vertical_implications_summary", "risks_counterevidence", "confidence"]
    ledger_sig_ids = None
    if ledger is not None:
        ledger_sig_ids = {s.get("signal_id") for s in (ledger.get("signals") or [])}
    seen = set()
    out = []
    for i, d in enumerate(dirs, 1):
        miss = [f for f in dir_req if f not in d]
        if miss:
            raise FrontHalfError("direction %d missing fields %s" % (i, sorted(miss)))
        if not d.get("evidence_refs"):
            raise FrontHalfError("direction %r has no evidence_refs — directions are derived from "
                                 "the ledger (task §7)" % d["direction_id"])
        if ledger_sig_ids is not None:
            bad = [r for r in d["evidence_refs"] if r not in ledger_sig_ids]
            if bad:
                raise FrontHalfError("direction %r cites evidence_refs %s absent from the ledger "
                                     "(task §7)" % (d["direction_id"], bad))
        if d["direction_id"] in seen:
            raise FrontHalfError("duplicate direction_id %r" % d["direction_id"])
        seen.add(d["direction_id"])
        d = dict(d)
        d.pop("direction_hash", None)
        d["direction_hash"] = canonical_hash(d)
        out.append(d)
    if payload["recommended_direction_id"] not in seen:
        raise FrontHalfError("recommended_direction_id %r is not one of the directions"
                             % payload["recommended_direction_id"])
    obj = dict(payload)
    obj["object_kind"] = "campaign_directions"
    obj["directions"] = out
    obj.pop("canonical_hash", None)
    obj["canonical_hash"] = canonical_hash(obj)
    return obj


COLLECTION_FLOOR = 50   # render_003 v0.7.0 (mirrors build_execution_csv / execution_package)


def _validate_campaign_spec_sections(sections):
    """Enforce the structural + charter rules that are representable at the front half (task §10–§17).
    Quality is NEVER judged by a fake numeric score; these are structural gates only."""
    if set(sections.keys()) != set(CS_SECTIONS):
        raise FrontHalfError("campaign_spec must carry exactly the eight sections %s; got %s"
                             % (CS_SECTIONS, sorted(sections.keys())))

    # collection_selections: CB-1 three gates representable; selection ≠ fulfillment; NO count target.
    selections = sections["collection_selections"].get("selections") or []
    sel_cats = set()
    for c in selections:
        for f in ["category_id", "campaign_fit_rationale", "distinct_shopper_product_job",
                  "fulfillment_state"]:
            if not c.get(f):
                raise FrontHalfError("collection_selection %r missing CB-1/selection field %r "
                                     "(task §12)" % (c.get("category_id"), f))
        if c.get("fulfillment_state") != "not_yet_requested":
            raise FrontHalfError("collection_selection %r: selection ≠ fulfillment — "
                                 "fulfillment_state must be 'not_yet_requested' at the front half "
                                 "(task §12)" % c.get("category_id"))
        depth = c.get("requested_depth")
        if not isinstance(depth, int) or depth < COLLECTION_FLOOR:
            raise FrontHalfError("collection_selection %r requested_depth must be an int >= %d "
                                 "(render_003)" % (c.get("category_id"), COLLECTION_FLOOR))
        sel_cats.add(c["category_id"])

    # rails: base_1c exactly one source; story_xc multiple; NO orphan rails; intent vs renderer separate.
    rail_ids = set()
    for r in sections["rails"].get("rails") or []:
        rid = r.get("rail_id")
        rt = r.get("rail_type")
        srcs = r.get("source_collection_ids") or []
        if rt not in ("base_1c", "story_xc"):
            raise FrontHalfError("rail %r rail_type must be base_1c|story_xc (task §13)" % rid)
        if rt == "base_1c" and len(srcs) != 1:
            raise FrontHalfError("rail %r base_1c must reference EXACTLY ONE collection (task §13)" % rid)
        if rt == "story_xc" and len(srcs) < 2:
            raise FrontHalfError("rail %r story_xc must reference MULTIPLE collections (task §13)" % rid)
        if rt == "story_xc" and not r.get("editorial_job"):
            raise FrontHalfError("rail %r story_xc must carry a genuine editorial story, not mere "
                                 "composition mechanics (task §13)" % rid)
        orphans = [s for s in srcs if s not in sel_cats]
        if orphans:
            raise FrontHalfError("rail %r references non-selected collection(s) %s — no orphan "
                                 "rails (task §13)" % (rid, orphans))
        rail_ids.add(rid)

    # content_program: SEO title ≠ card headline (distinct fields both present).
    content_ids = set()
    for c in sections["content_program"].get("content") or []:
        if not c.get("seo_title") or not c.get("card_headline"):
            raise FrontHalfError("content %r must carry DISTINCT seo_title AND card_headline "
                                 "(task §14)" % c.get("content_id"))
        content_ids.add(c.get("content_id"))

    # default_composition: refs must resolve to an existing rail/content; no leaked blocked objects.
    slots = sections["default_composition"].get("ordered_slots") or []
    seen_slot_ids = set()
    for sl in slots:
        ot, oid = sl.get("object_type"), sl.get("object_id")
        if ot not in ("base_rail", "story_rail", "content"):
            raise FrontHalfError("default slot %r object_type invalid (task §16)" % sl.get("slot_id"))
        if ot in ("base_rail", "story_rail") and oid not in rail_ids:
            raise FrontHalfError("default slot references rail %r not in this spec (task §16)" % oid)
        if ot == "content" and oid not in content_ids:
            raise FrontHalfError("default slot references content %r not in this spec (task §16)" % oid)
        if sl.get("slot_id") in seen_slot_ids:
            raise FrontHalfError("duplicate default slot_id %r (task §16)" % sl.get("slot_id"))
        seen_slot_ids.add(sl.get("slot_id"))


def build_campaign_spec_revision(payload):
    """Validate + canonicalize ONE immutable campaign_spec revision (task §9–§18). Stamps per-section
    hashes + the composite hash. Does NOT judge creative quality; enforces structure + charter rules."""
    for f in ["campaign_spec_id", "revision", "sections"]:
        if f not in payload:
            raise FrontHalfError("campaign_spec revision missing field %r" % f)
    sections = payload["sections"]
    _validate_campaign_spec_sections(sections)
    section_hashes = {s: canonical_hash(sections[s]) for s in CS_SECTIONS}
    obj = dict(payload)
    obj["object_kind"] = "campaign_spec"
    obj["section_hashes"] = section_hashes
    obj["composite_hash"] = composite_hash(section_hashes, CS_SECTIONS)
    # canonical_hash spans the whole revision (id + revision + sections + parent + selected_direction).
    core = {k: v for k, v in obj.items() if k not in ("canonical_hash",)}
    obj["canonical_hash"] = canonical_hash(core)
    return obj


# ---------------------------------------------------------------------------
# spine + revision file management (state mutation lives in run.py; these are pure helpers)
# ---------------------------------------------------------------------------
def spine_for_object(obj, artifact_key):
    """Build the structured_objects[kind] spine entry the validator recomputes against."""
    kind = obj["object_kind"]
    id_field = {"research_brief": "brief_id", "research_ledger": "ledger_id",
                "campaign_directions": "directions_id", "campaign_spec": "campaign_spec_id"}[kind]
    spine = {
        "object_kind": kind,
        "object_id": obj[id_field],
        "revision": obj["revision"],
        "canonical_hash": obj["canonical_hash"],
        "artifact_key": artifact_key,
    }
    if kind == "campaign_spec":
        spine["section_hashes"] = obj["section_hashes"]
        spine["composite_hash"] = obj["composite_hash"]
        spine["parent_revision"] = obj.get("parent_revision")
    return spine


def campaign_spec_to_architecture(spec_doc):
    """Adapter (task §22): project an APPROVED campaign_spec into the current-adapter architecture
    object the proven A–G producers already consume (execution_package.load_architecture).

    JUDGMENT ONLY — no product truth. This replaces the loose hand-authored judgment file for vNext
    flows: collections/rails/content/default_composition/renderer_capabilities are read straight from
    the spec sections, translating the spec's vocabulary (rail_type base_1c|story_xc, section titles)
    into the adapter's (rail_kind base|xc, rail_name). Product facts are NEVER added here."""
    sections = (spec_doc or {}).get("sections") or {}
    sel = (sections.get("collection_selections") or {}).get("selections") or []
    rails = (sections.get("rails") or {}).get("rails") or []
    content = (sections.get("content_program") or {}).get("content") or []
    collections = [{
        "category_id": c.get("category_id"),
        "display_name": c.get("display_name"),
        "request_id": c.get("request_id"),   # filled once Request v2 is generated; None pre-gen
    } for c in sel]
    arch_rails = [{
        "rail_id": r.get("rail_id"),
        "rail_name": r.get("title"),
        "rail_kind": "base" if r.get("rail_type") == "base_1c" else "xc",
        "source_collection_ids": r.get("source_collection_ids") or [],
        "fallback": r.get("fallback_ref"),
    } for r in rails]
    arch_content = [{
        "content_id": c.get("content_id"),
        "target_query": c.get("target_query"),
        "seo_title": c.get("seo_title"),
        "card_headline": c.get("card_headline"),
        "linked_rail": (c.get("linked_rail_ids") or [None])[0],
        "status": c.get("status"),
    } for c in content]
    # renderer capability: honest — the spec records per-rail intent; XC support is a renderer fact.
    xc_supported = any(r.get("renderer_capability") == "supported" and r.get("rail_type") == "story_xc"
                       for r in rails)
    return {
        "collections": collections,
        "rails": arch_rails,
        "content": arch_content,
        "default_composition": sections.get("default_composition"),
        "renderer_capabilities": {"xc_rails_supported": xc_supported},
    }


def downstream_approvals_for_change(dependency_graph, changed_node):
    """Given the schema dependency_graph and a node that materially changed, return the set of
    front-half approval decision ids whose bound object is at/below that node — i.e. must be
    invalidated. Deterministic, not agent discretion (task §19)."""
    # node -> the approval that binds it (mirrors front_half_approvals in the schema)
    node_to_approval = {
        "research_brief": "kickoff_approved",
        "selected_direction": "direction_selected_v2",
        "campaign_spec.premise": "premise_approved",
        "campaign_spec.vertical_strategies": "verticals_approved",
        # architecture composite binds these three:
        "campaign_spec.collection_selections": "architecture_approved",
        "campaign_spec.rails": "architecture_approved",
        "campaign_spec.content_program": "architecture_approved",
        # the final composite binds everything:
        "campaign_spec.composite": "campaign_spec_approved",
    }
    # compute the transitive downstream set of changed_node in the dependency graph
    downstream = set()
    frontier = [changed_node]
    # build reverse edges: node -> [dependents]
    rev = {}
    for node, meta in (dependency_graph or {}).items():
        for dep in (meta or {}).get("depends_on") or []:
            rev.setdefault(dep, []).append(node)
    while frontier:
        n = frontier.pop()
        for dependent in rev.get(n, []):
            if dependent not in downstream:
                downstream.add(dependent)
                frontier.append(dependent)
    affected_nodes = {changed_node} | downstream
    # the final composite is affected whenever any of its inputs changed
    approvals = set()
    for n in affected_nodes:
        if n in node_to_approval:
            approvals.add(node_to_approval[n])
    # the final "build this" composite depends on every spec section, so any spec/section change
    # (or an upstream change that re-mints the spec) invalidates it too.
    if any(str(n).startswith("campaign_spec") or n in ("selected_direction", "research_brief",
                                                        "research_ledger", "campaign_directions")
           for n in affected_nodes):
        approvals.add("campaign_spec_approved")
    return approvals
