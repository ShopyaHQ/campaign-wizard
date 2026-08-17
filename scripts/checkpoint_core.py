#!/usr/bin/env python3
"""checkpoint_core.py — the iterative owner-checkpoint SESSION layer (task §4/§5/§14/§15).

This is the missing product primitive. The structured front half (research_brief · research_ledger
· campaign_directions · immutable campaign_spec revisions) and its typed hash-bound approvals are
ALREADY the authority (front_half.py + validate_state.py + the workflow schema). What did NOT exist
was the *iterative guided session* AROUND each checkpoint:

    OPEN → INTAKE → DRAFT_READY → OWNER_REVIEW → REVISION_REQUESTED → DRAFT_READY → … → APPROVED

with structured intake questions the WIZARD (not the agent) defines, owner/inferred/unresolved
classification, targeted (field/section) revision that preserves untouched fields, an exact semantic
diff, and a SINGLE owner action per checkpoint. This module is that layer.

DESIGN RULES (hard):
  • NO second SSOT. The authoritative objects remain the immutable revisions on disk + the state
    spine. A "session" is a thin DERIVED view + the pending intake answers; it duplicates no
    campaign truth. `describe_checkpoint()` recomputes everything from state + schema every call.
  • NO duplicated business logic. Registration, hashing, dependency invalidation and typed approval
    all go through front_half.py and the same state-mutation helpers run.py uses. The CLI and the
    FastAPI console both call THIS module; neither re-implements the rules.
  • PURE-STDLIB. No FastAPI/Jinja import here so the CLI + core tests run under system Python with
    zero new deps. Functions RETURN values or raise CheckpointError — never sys.exit / print.
  • SINGLE ACTION (AF-002). One owner "approve" emits the whole decision set for that checkpoint
    atomically (the typed hash-bound decision AND its legacy compatibility id), so the owner/GUI
    issue exactly one approval per checkpoint.

The five front-half checkpoints (schema front_half_approvals), in ladder order:
  1 KICKOFF                 research_brief         binds kickoff_approved (object)
  2 RESEARCH + DIRECTION    campaign_directions    binds direction_selected_v2 (direction)
  3 PREMISE + VERTICALS     campaign_spec          binds premise_approved + verticals_approved
  4 ARCHITECTURE            campaign_spec           binds architecture_approved (composite of 3)
  5 BUILD THIS              campaign_spec           binds campaign_spec_approved (composite of 8)
"""
import copy
import json
import os
import sys

import yaml

import front_half as fh

# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------
class CheckpointError(Exception):
    """An illegal checkpoint action (wrong phase, unknown field, stale object). The caller (CLI or
    API adapter) turns this into an exit / structured HTTP error. Carries a machine `code`."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# checkpoint catalogue — the WIZARD defines these, not the agent (acceptance criterion).
# Each entry: the product-facing checkpoint, the authoritative object kind, the approval id(s) it
# binds, the ladder position, and the workflow state that becomes reachable once it is approved.
# ---------------------------------------------------------------------------
CHECKPOINTS = [
    {
        "checkpoint_type": "kickoff",
        "ordinal": 1,
        "title": "Kickoff",
        "object_kind": "research_brief",
        "approval_ids": ["kickoff_approved"],
        "legacy_ids": ["frame_accepted"],
        "opens_state": "RESEARCHING",
        "prompt": "Is this the problem to solve?",
    },
    {
        "checkpoint_type": "direction",
        "ordinal": 2,
        "title": "Research + Direction",
        "object_kind": "campaign_directions",
        "approval_ids": ["direction_selected_v2"],
        "legacy_ids": ["opportunity_selected"],
        "opens_state": "OPPORTUNITY_SELECTED",
        "prompt": "Which opportunity do we pursue?",
    },
    {
        "checkpoint_type": "premise_verticals",
        "ordinal": 3,
        "title": "Premise + Verticals",
        "object_kind": "campaign_spec",
        "approval_ids": ["premise_approved", "verticals_approved"],
        "legacy_ids": [],
        "opens_state": "BRIEF_APPROVED",
        "prompt": "Is this the campaign idea, and does it translate across Shopya?",
    },
    {
        "checkpoint_type": "architecture",
        "ordinal": 4,
        "title": "Architecture",
        "object_kind": "campaign_spec",
        "approval_ids": ["architecture_approved"],
        "legacy_ids": [],
        "opens_state": "ROUTE_SELECTED",
        "prompt": "Are these the right objects — collections, rails, content?",
    },
    {
        "checkpoint_type": "build_this",
        "ordinal": 5,
        "title": "Build This",
        "object_kind": "campaign_spec",
        "approval_ids": ["campaign_spec_approved"],
        "legacy_ids": [],
        "opens_state": "SEAM6_READY",
        "prompt": "Build this exact specification?",
    },
]
CHECKPOINT_BY_TYPE = {c["checkpoint_type"]: c for c in CHECKPOINTS}

# session status vocabulary (interaction state — NOT a workflow state)
S_OPEN = "OPEN"                    # no authoritative object yet; intake is the affordance
S_INTAKE = "INTAKE"               # intake answers pending
S_DRAFT_READY = "DRAFT_READY"     # a draft object exists, awaiting owner review
S_OWNER_REVIEW = "OWNER_REVIEW"   # object present and not stale; owner may approve/revise
S_REVISION_REQUESTED = "REVISION_REQUESTED"  # owner asked for a change; a new draft is due
S_APPROVED = "APPROVED"           # this checkpoint's approval(s) recorded, current, not stale


# ---------------------------------------------------------------------------
# ladder derivation — which checkpoint is current, purely from state.
# ---------------------------------------------------------------------------
def _decisions(state):
    return state.get("owner_decisions") or {}


def _invalidated(state):
    return state.get("invalidated") or []


def _approval_recorded(state, approval_id):
    """A front-half approval GATES only if it is owner_confirmed AND not currently invalidated."""
    rec = _decisions(state).get(approval_id)
    if not rec or not rec.get("decided"):
        return False
    if approval_id in _invalidated(state):
        return False
    return True


def _checkpoint_approved(state, cp):
    return all(_approval_recorded(state, aid) for aid in cp["approval_ids"])


def current_checkpoint(state):
    """The first checkpoint in ladder order that is not yet fully approved (its approvals recorded,
    current, non-stale). None once all five are approved (front half complete)."""
    for cp in CHECKPOINTS:
        if not _checkpoint_approved(state, cp):
            return cp
    return None


def _object_spine(state, kind):
    return (state.get("structured_objects") or {}).get(kind) or {}


def _current_object_bytes(state, run_dir_fn, run_id, kind):
    """Load the current registered object's bytes from disk (SSOT), or None."""
    rec = (state.get("artifacts") or {}).get(kind)
    if not rec or rec.get("status", "current") != "current":
        return None
    p = rec["path"]
    rd = run_dir_fn(run_id)
    for cand in (p, os.path.join(rd, p)):
        if os.path.isabs(cand) and os.path.exists(cand):
            return yaml.safe_load(open(cand, encoding="utf-8"))
        full = cand if os.path.isabs(cand) else os.path.join(rd, cand)
        if os.path.exists(full):
            return yaml.safe_load(open(full, encoding="utf-8"))
    return None


def _revision_files(run_dir_fn, run_id, kind):
    """Every immutable revision file <kind>.rNNN.yaml on disk for this object, sorted by label."""
    rd = run_dir_fn(run_id)
    out = []
    if not os.path.isdir(rd):
        return out
    for fn in sorted(os.listdir(rd)):
        if fn.startswith(kind + ".") and fn.endswith(".yaml"):
            rev = fn[len(kind) + 1:-len(".yaml")]
            out.append((rev, os.path.join(rd, fn)))
    return out


def _session_status(state, run_dir_fn, run_id, cp):
    """Derive the interaction status for a checkpoint from state alone."""
    if _checkpoint_approved(state, cp):
        return S_APPROVED
    obj = _current_object_bytes(state, run_dir_fn, run_id, cp["object_kind"])
    if obj is None:
        return S_OPEN
    # object exists; is any of this checkpoint's approvals invalidated (owner asked for change)?
    for aid in cp["approval_ids"]:
        if aid in _invalidated(state):
            return S_REVISION_REQUESTED
    return S_OWNER_REVIEW


# ---------------------------------------------------------------------------
# QUESTION FRAMEWORK — the Wizard's structured intake per checkpoint (task §5/§6).
# Each question: stable id, type, prompt, prefilled value, provenance class, options.
# Provenance classes surfaced to the owner:
#   owner_supplied · inferred_confirm · unresolved_input · derived_info
# ---------------------------------------------------------------------------
Q_OWNER = "owner_supplied"
Q_INFER = "inferred_confirm"
Q_UNRESOLVED = "unresolved_input"
Q_DERIVED = "derived_info"

# canonical closed sets echoed from the schemas (so the GUI never invents them)
VERTICALS = ["fashion", "home_interior", "tech", "beauty", "travel", "wellness_health"]
CONVICTION_ROLES = ["lead", "supporting", "peripheral", "absent"]


def _q(qid, qtype, prompt, cls, value=None, options=None, help_text=None, path=None):
    q = {"id": qid, "type": qtype, "prompt": prompt, "provenance_class": cls,
         "value": value, "options": options or None}
    if help_text:
        q["help"] = help_text
    if path:
        q["path"] = path       # dotted path into the object this question edits (targeted revision)
    return q


def _brief_value(obj, field):
    """Read {value, provenance} material fields OR plain fields from a research_brief."""
    if not obj:
        return None, None
    v = obj.get(field)
    if isinstance(v, dict) and "value" in v:
        return v.get("value"), v.get("provenance")
    return v, None


def kickoff_questions(brief=None):
    """The Campaign Intake form (task §6). Prefilled from the current brief when one exists; the
    provenance_class of each field is driven by the brief's own provenance labels so INFERRED fields
    are visibly 'confirm or edit' and unresolved questions are surfaced as inputs needed."""
    def cls_for(field, default):
        _, prov = _brief_value(brief, field)
        if prov == "owner_supplied":
            return Q_OWNER
        if prov in ("system_inferred", "derived"):
            return Q_INFER
        return default

    qs = [
        _q("objective", "long_text", "Campaign goal / objective",
           cls_for("objective", Q_OWNER), _brief_value(brief, "objective")[0],
           path="objective.value"),
        _q("desired_behavior", "long_text", "Primary desired shopper behavior",
           cls_for("desired_behavior", Q_OWNER), _brief_value(brief, "desired_behavior")[0],
           path="desired_behavior.value"),
        _q("audience_context", "long_text", "Target audience",
           cls_for("audience_context", Q_OWNER), _brief_value(brief, "audience_context")[0],
           path="audience_context.value"),
        _q("market", "short_text", "Market / geography",
           cls_for("market", Q_OWNER), _brief_value(brief, "market")[0], path="market.value"),
        _q("campaign_window", "short_text", "Campaign timing / window",
           cls_for("campaign_window", Q_INFER), _brief_value(brief, "campaign_window")[0],
           help_text="If left to the Wizard, this is inferred and marked for your confirmation.",
           path="campaign_window.value"),
        _q("territory", "long_text", "Research breadth / vertical scope / territory",
           cls_for("territory", Q_INFER), _brief_value(brief, "territory")[0],
           path="territory.value"),
        _q("exclusions", "list", "Hard exclusions", Q_OWNER,
           (brief or {}).get("exclusions") or [], path="exclusions"),
        _q("owner_inputs", "list", "Required inclusions / known context (verbatim owner statements)",
           Q_OWNER, (brief or {}).get("owner_inputs") or [], path="owner_inputs"),
        _q("owner_notes", "long_text", "Anything else the Wizard should know (optional)",
           Q_OWNER, None),
    ]
    # surface the Wizard's inferences + open questions as read/confirm items (never hidden — task §3)
    if brief:
        for i, inf in enumerate(brief.get("inferred_inputs") or []):
            qs.append(_q("inferred_%d" % i, "confirm",
                         "Inferred: %s" % (inf if isinstance(inf, str) else json.dumps(inf)),
                         Q_INFER, True))
        for i, u in enumerate(brief.get("unresolved_questions") or []):
            qs.append(_q("unresolved_%d" % i, "short_text",
                         "Unresolved — input needed: %s"
                         % (u if isinstance(u, str) else json.dumps(u)), Q_UNRESOLVED, None))
    return qs


def direction_questions(directions=None):
    """Checkpoint 2 is a SELECTION, not a form: the question set is 'which direction', plus the
    revision affordances. Options are the current directions with the Wizard's recommendation
    flagged."""
    opts = []
    recommended = (directions or {}).get("recommended_direction_id")
    for d in (directions or {}).get("directions") or []:
        opts.append({"value": d.get("direction_id"),
                     "label": d.get("title"),
                     "recommended": d.get("direction_id") == recommended})
    return [_q("selected_direction", "radio", "Which opportunity do we pursue?",
               Q_DERIVED, recommended, options=opts,
               help_text="The Wizard's recommendation is flagged; you may select any, request a "
                         "revision, or ask for new directions.")]


def _spec_sections(spec):
    return (spec or {}).get("sections") or {}


def premise_questions(spec=None):
    """Checkpoint 3 — premise (top-level card) + per-vertical confirmation (task §8). Questions map
    to targeted paths inside the campaign_spec so a single field edit becomes a targeted revision."""
    sec = _spec_sections(spec)
    p = sec.get("premise") or {}
    qs = [
        _q("campaign_name", "short_text", "Campaign name (may be provisional)",
           Q_DERIVED, p.get("campaign_name"), path="sections.premise.campaign_name"),
        _q("dek", "short_text", "Dek / subtitle", Q_DERIVED, p.get("dek"),
           path="sections.premise.dek"),
        _q("central_tension", "long_text", "Central shopper tension", Q_DERIVED,
           p.get("central_tension"), path="sections.premise.central_tension"),
        _q("point_of_view", "long_text", "Point of view", Q_DERIVED, p.get("point_of_view"),
           path="sections.premise.point_of_view"),
        _q("why_now", "long_text", "Why now", Q_DERIVED, p.get("why_now"),
           path="sections.premise.why_now"),
        _q("shopya_role", "long_text", "Shopya's role", Q_DERIVED, p.get("shopya_role"),
           path="sections.premise.shopya_role"),
        _q("voice_summary", "long_text", "Voice", Q_DERIVED, p.get("voice_summary"),
           path="sections.premise.voice_summary"),
    ]
    # per-vertical conviction is a targeted edit on vertical_strategies (task §8 — no equal weight)
    for i, v in enumerate((sec.get("vertical_strategies") or {}).get("verticals") or []):
        vid = v.get("vertical_id")
        qs.append(_q("vertical_%s_conviction" % vid, "radio",
                     "Vertical '%s' — conviction" % vid, Q_DERIVED, v.get("conviction_role"),
                     options=[{"value": r, "label": r} for r in CONVICTION_ROLES],
                     path="sections.vertical_strategies.verticals.%d.conviction_role" % i))
    return qs


def architecture_review_sections(spec=None):
    """Checkpoint 4 is the richest REVIEW (task §9), grouped by vertical with collections/rails/
    content/default. This returns a structured review model (not questions) the GUI renders as
    tabs; owner actions are targeted (keep/drop/edit/rename/reorder/rework) via request_revision."""
    sec = _spec_sections(spec)
    selections = (sec.get("collection_selections") or {}).get("selections") or []
    rails = (sec.get("rails") or {}).get("rails") or []
    content = (sec.get("content_program") or {}).get("content") or []
    default = sec.get("default_composition") or {}
    by_vertical = {}
    for i, c in enumerate(selections):
        v = c.get("vertical") or "unassigned"
        by_vertical.setdefault(v, {"collections": [], "rails": [], "content": []})
        by_vertical[v]["collections"].append({
            "index": i, "category_id": c.get("category_id"),
            "display_name": c.get("display_name"), "campaign_role": c.get("campaign_role"),
            "why_it_earns": c.get("campaign_fit_rationale"),
            "distinct_job": c.get("distinct_shopper_product_job"),
            "path": "sections.collection_selections.selections.%d" % i})
    sel_by_cat = {c.get("category_id"): c.get("vertical") for c in selections}
    for i, r in enumerate(rails):
        srcs = r.get("source_collection_ids") or []
        v = sel_by_cat.get(srcs[0]) if srcs else "unassigned"
        by_vertical.setdefault(v or "unassigned", {"collections": [], "rails": [], "content": []})
        by_vertical[v or "unassigned"]["rails"].append({
            "index": i, "rail_id": r.get("rail_id"), "title": r.get("title"),
            "rail_type": r.get("rail_type"), "source_collection_ids": srcs,
            "editorial_job": r.get("editorial_job"),
            "renderer_capability": r.get("renderer_capability"),
            "fallback_ref": r.get("fallback_ref"),
            "path": "sections.rails.rails.%d" % i})
    for i, c in enumerate(content):
        by_vertical.setdefault("content", {"collections": [], "rails": [], "content": []})
        by_vertical["content"]["content"].append({
            "index": i, "content_id": c.get("content_id"), "target_query": c.get("target_query"),
            "seo_title": c.get("seo_title"), "card_headline": c.get("card_headline"),
            "path": "sections.content_program.content.%d" % i})
    return {
        "verticals": by_vertical,
        "default_composition": default,
        "renderer_notes": {"story_xc_present": any(r.get("rail_type") == "story_xc" for r in rails)},
    }


def build_this_review(spec=None):
    """Checkpoint 5 — the final exact spec (task §10). Structured, with technical ids/hashes carried
    but flagged secondary."""
    sec = _spec_sections(spec)
    return {
        "premise": sec.get("premise"),
        "vertical_strategies": sec.get("vertical_strategies"),
        "collection_selections": sec.get("collection_selections"),
        "rails": sec.get("rails"),
        "content_program": sec.get("content_program"),
        "naming_voice": sec.get("naming_voice"),
        "default_composition": sec.get("default_composition"),
        "seam_intent": sec.get("seam_intent"),
    }


# ---------------------------------------------------------------------------
# SEMANTIC DIFF (task §15). Structured changed/added/removed/reordered over two object revisions.
# Recursive over dicts/lists; lists of dicts keyed by a stable id when one is present.
# ---------------------------------------------------------------------------
_ID_KEYS = ("signal_id", "direction_id", "category_id", "rail_id", "content_id", "slot_id",
            "vertical_id", "object_id", "id")


def _list_key(item):
    if isinstance(item, dict):
        for k in _ID_KEYS:
            if k in item:
                return (k, item[k])
    return None


def _diff(old, new, path, out):
    if isinstance(old, dict) and isinstance(new, dict):
        for k in sorted(set(old) | set(new)):
            sub = "%s.%s" % (path, k) if path else k
            if k not in old:
                out["added"].append({"path": sub, "new": new[k]})
            elif k not in new:
                out["removed"].append({"path": sub, "old": old[k]})
            else:
                _diff(old[k], new[k], sub, out)
        return
    if isinstance(old, list) and isinstance(new, list):
        old_keys = [_list_key(x) for x in old]
        new_keys = [_list_key(x) for x in new]
        if all(old_keys) and all(new_keys):
            om = {k: v for k, v in zip(old_keys, old)}
            nm = {k: v for k, v in zip(new_keys, new)}
            for k in old_keys:
                if k not in nm:
                    out["removed"].append({"path": "%s[%s=%s]" % (path, k[0], k[1]), "old": om[k]})
            for k in new_keys:
                if k not in om:
                    out["added"].append({"path": "%s[%s=%s]" % (path, k[0], k[1]), "new": nm[k]})
                else:
                    _diff(om[k], nm[k], "%s[%s=%s]" % (path, k[0], k[1]), out)
            if old_keys != new_keys and set(old_keys) == set(new_keys):
                out["reordered"].append({"path": path, "from": [list(k) for k in old_keys],
                                         "to": [list(k) for k in new_keys]})
            return
        # positional list (no stable ids) — compare element-wise
        if old != new:
            n = max(len(old), len(new))
            for i in range(n):
                sub = "%s[%d]" % (path, i)
                if i >= len(old):
                    out["added"].append({"path": sub, "new": new[i]})
                elif i >= len(new):
                    out["removed"].append({"path": sub, "old": old[i]})
                else:
                    _diff(old[i], new[i], sub, out)
        return
    if old != new:
        out["changed"].append({"path": path, "old": old, "new": new})


def semantic_diff(old_obj, new_obj):
    """Structured, hash-free semantic diff between two object revisions. Ignores stamped hash fields
    (they are derived from content, not owner intent)."""
    out = {"changed": [], "added": [], "removed": [], "reordered": []}
    strip = {"canonical_hash", "section_hashes", "composite_hash", "signal_hash", "direction_hash"}

    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items() if k not in strip}
        if isinstance(o, list):
            return [clean(x) for x in o]
        return o

    _diff(clean(old_obj or {}), clean(new_obj or {}), "", out)
    return out


# ---------------------------------------------------------------------------
# TARGETED REVISION (semantic patch, task §14). Apply owner-scoped ops to a COPY of the current
# object, preserving every untouched field, then hand the whole new object to front_half.py to
# validate + hash + mint an immutable revision. Ops: set/replace/add/remove/edit/reorder.
# ---------------------------------------------------------------------------
def _next_revision_label(existing_labels):
    n = 0
    for lab in existing_labels:
        if lab.startswith("r") and lab[1:].isdigit():
            n = max(n, int(lab[1:]))
    return "r%03d" % (n + 1)


def _resolve_path(obj, dotted):
    """Navigate a dotted path (a.b.2.c) to (container, last_key). Numeric segments index lists."""
    parts = dotted.split(".")
    cur = obj
    for seg in parts[:-1]:
        if seg.isdigit():
            cur = cur[int(seg)]
        else:
            cur = cur[seg]
    last = parts[-1]
    return cur, (int(last) if last.isdigit() else last)


def apply_patch_ops(base_obj, ops):
    """Return a NEW object = deep copy of base_obj with ops applied. Untouched fields are preserved
    byte-for-byte (task §14). Raises CheckpointError on an op that references a missing path."""
    obj = copy.deepcopy(base_obj)
    for op in ops:
        kind = op.get("op")
        path = op.get("path")
        try:
            if kind in ("set", "replace", "edit"):
                container, key = _resolve_path(obj, path)
                if isinstance(key, int):
                    container[key] = op["value"]
                else:
                    container[key] = op["value"]
            elif kind == "add":
                # path points at a LIST; append (or insert at 'index')
                container = _get(obj, path)
                if not isinstance(container, list):
                    raise CheckpointError("patch_target_not_list",
                                          "add target %r is not a list" % path)
                idx = op.get("index")
                if idx is None:
                    container.append(op["value"])
                else:
                    container.insert(idx, op["value"])
            elif kind == "remove":
                container, key = _resolve_path(obj, path)
                if isinstance(key, int):
                    del container[key]
                else:
                    del container[key]
            elif kind == "reorder":
                lst = _get(obj, path)
                order = op["order"]     # list of indices in the new order
                if not isinstance(lst, list) or sorted(order) != list(range(len(lst))):
                    raise CheckpointError("patch_bad_reorder",
                                          "reorder %r needs a permutation of 0..n-1" % path)
                _set(obj, path, [lst[i] for i in order])
            else:
                raise CheckpointError("patch_unknown_op", "unknown op %r" % kind)
        except CheckpointError:
            raise
        except (KeyError, IndexError, TypeError) as e:
            raise CheckpointError("patch_bad_path",
                                  "op %r path %r failed: %s" % (kind, path, e))
    return obj


def _get(obj, dotted):
    cur = obj
    for seg in dotted.split("."):
        cur = cur[int(seg)] if seg.isdigit() else cur[seg]
    return cur


def _set(obj, dotted, value):
    container, key = _resolve_path(obj, dotted)
    container[key] = value


# ═══════════════════════════════════════════════════════════════════
# STATE-MUTATION ENGINE — the single implementation of object registration + typed approval that
# BOTH the CLI (run.py) and the API call. run.py's register-object/select-direction/approve-object
# and the new checkpoint verbs are thin adapters over these; the FastAPI handlers are adapters over
# the session ops below. There is exactly one place the rules live.
#
# We import run.py's PURE state helpers lazily (inside functions) to avoid an import cycle
# (run.py imports checkpoint_core only inside its command bodies).
# ═══════════════════════════════════════════════════════════════════
def _rt():
    """Lazy handle to run.py's pure helpers (run_dir/state_path/atomic_write/now/require_run/…)."""
    import run
    return run


def _run_dir(run_id):
    return _rt().run_dir(run_id)


def register_object(run_id, kind, obj):
    """Register a BUILT+validated structured object (obj already through front_half build_*), writing
    an immutable revision file, the artifact record, the spine, and running deterministic dependency
    invalidation. Returns {object_id, revision, canonical_hash, composite_hash?, invalidated:[...]}.

    This is the exact logic formerly inlined in run.cmd_register_object — now the single home."""
    rt = _rt()
    if kind not in fh_kinds():
        raise CheckpointError("bad_kind", "unknown object kind %r" % kind)
    s = rt.require_run(run_id)
    spine_prev = (s.get("structured_objects") or {}).get(kind) or {}
    prev_hash = spine_prev.get("canonical_hash")
    prev_section_hashes = spine_prev.get("section_hashes") or {}

    rev = obj["revision"]
    rd = rt.run_dir(run_id)
    os.makedirs(rd, exist_ok=True)
    rev_path = os.path.join(rd, "%s.%s.yaml" % (kind, rev))
    if os.path.exists(rev_path):
        existing = yaml.safe_load(open(rev_path, encoding="utf-8")) or {}
        if existing.get("canonical_hash") != obj["canonical_hash"]:
            raise CheckpointError(
                "campaign_spec_revision_mutated",
                "%s already exists with a different hash — a revision is write-once; mint a NEW "
                "revision label instead" % os.path.basename(rev_path))
    with open(rev_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(obj, f, sort_keys=False, default_flow_style=False, allow_unicode=True)

    import hashlib
    rel = rt._artifact_rel(run_id, rev_path)
    sha = hashlib.sha256(open(rev_path, "rb").read()).hexdigest()
    s.setdefault("artifacts", {})[kind] = {
        "path": rel, "written_at": rt.now(), "sha256": sha, "status": "current",
        "superseded_by": None, "superseded_at": None, "supersession_reason": None}

    spine = fh.spine_for_object(obj, kind)
    revisions = list(spine_prev.get("revisions") or [])
    rec = {"campaign_spec_id" if kind == "campaign_spec" else "object_id": spine["object_id"],
           "revision": rev, "canonical_hash": obj["canonical_hash"]}
    if kind == "campaign_spec":
        rec["composite_hash"] = obj["composite_hash"]
    if not any(r.get("revision") == rev and r.get("canonical_hash") == obj["canonical_hash"]
               for r in revisions):
        revisions.append(rec)
    spine["revisions"] = revisions
    s.setdefault("structured_objects", {})[kind] = spine

    changed_nodes = rt._changed_nodes(kind, prev_hash, obj, prev_section_hashes)
    invalidated = rt._invalidate_downstream(s, changed_nodes)

    rt.atomic_write(rt.state_path(run_id), s)
    out = {"object_id": spine["object_id"], "revision": rev,
           "canonical_hash": obj["canonical_hash"], "invalidated": invalidated}
    if kind == "campaign_spec":
        out["composite_hash"] = obj["composite_hash"]
        out["section_hashes"] = obj["section_hashes"]
    return out


def fh_kinds():
    return ("research_brief", "research_ledger", "campaign_directions", "campaign_spec")


def build_object(run_id, kind, payload):
    """Build (validate + hash) a structured object payload via front_half. For campaign_directions,
    resolve the current ledger for evidence-ref checking. Raises CheckpointError on invalid."""
    rt = _rt()
    s = rt.require_run(run_id)
    try:
        if kind == "research_brief":
            return fh.build_research_brief(payload)
        if kind == "research_ledger":
            return fh.build_research_ledger(payload)
        if kind == "campaign_directions":
            ledger = rt._load_current_object(s, run_id, "research_ledger")
            return fh.build_campaign_directions(payload, ledger=ledger)
        if kind == "campaign_spec":
            return fh.build_campaign_spec_revision(payload)
    except fh.FrontHalfError as e:
        raise CheckpointError("invalid_object", "not a valid %s: %s" % (kind, e))
    except (AttributeError, KeyError, TypeError, ValueError, IndexError) as e:
        # a structurally-malformed payload (e.g. a worker returned a section as a list, not a dict)
        # must be a clean REFUSAL, never an uncaught crash that could leave the run incoherent.
        raise CheckpointError("malformed_object",
                              "%s payload is structurally malformed (%s: %s)"
                              % (kind, type(e).__name__, e))
    raise CheckpointError("bad_kind", "unknown object kind %r" % kind)


# ---- typed approvals (single home; run.py adapters call these) ----
def record_direction_selection(run_id, direction_id, by="product_owner",
                               status="owner_confirmed", note=None):
    """Record direction_selected_v2 bound to the exact direction hash. Single home for the logic in
    run.cmd_select_direction."""
    rt = _rt()
    s = rt.require_run(run_id)
    dirs_obj = rt._load_current_object(s, run_id, "campaign_directions")
    if not dirs_obj:
        raise CheckpointError("no_object", "no current campaign_directions registered")
    match = next((d for d in (dirs_obj.get("directions") or [])
                  if d.get("direction_id") == direction_id), None)
    if match is None:
        raise CheckpointError("unknown_direction",
                              "direction %r is not in the current campaign_directions" % direction_id)
    if by == "product_owner" and status != "owner_confirmed":
        raise CheckpointError("decision_status_misstamped",
                              "product_owner requires status owner_confirmed")
    value = {"directions_id": dirs_obj.get("directions_id"), "revision": dirs_obj.get("revision"),
             "direction_id": direction_id, "direction_hash": match.get("direction_hash")}
    rec = {"status": status, "decided": status == "owner_confirmed", "decided_by": by,
           "decided_at": rt.now(), "value": value}
    if note:
        rec["note"] = note
    s.setdefault("owner_decisions", {})["direction_selected_v2"] = rec
    if status == "owner_confirmed" and "direction_selected_v2" in (s.get("invalidated") or []):
        s["invalidated"].remove("direction_selected_v2")
    rt.atomic_write(rt.state_path(run_id), s)
    return value


def record_object_approval(run_id, decision_id, kind, binding, section=None, sections=None,
                           by="product_owner", status="owner_confirmed", note=None):
    """Record a typed hash-bound approval (kickoff/premise/verticals/architecture/final). Single home
    for run.cmd_approve_object's logic."""
    rt = _rt()
    s = rt.require_run(run_id)
    if by == "product_owner" and status != "owner_confirmed":
        raise CheckpointError("decision_status_misstamped",
                              "product_owner requires status owner_confirmed")
    obj = rt._load_current_object(s, run_id, kind)
    spine = (s.get("structured_objects") or {}).get(kind) or {}
    if not obj or not spine:
        raise CheckpointError("no_object", "no current %s registered" % kind)
    if binding == "object":
        value = {"object_id": spine["object_id"], "revision": spine["revision"],
                 "canonical_hash": spine["canonical_hash"]}
    elif binding == "section":
        sh = (spine.get("section_hashes") or {}).get(section)
        if not sh:
            raise CheckpointError("no_section_hash", "no section_hash for %r" % section)
        value = {"object_id": spine["object_id"], "revision": spine["revision"],
                 "section": section, "section_hash": sh}
    elif binding == "composite":
        sh = spine.get("section_hashes") or {}
        missing = [x for x in (sections or []) if not sh.get(x)]
        if not sections:
            raise CheckpointError("no_sections", "composite binding requires sections")
        if missing:
            raise CheckpointError("missing_section_hashes", "missing section hashes for %s" % missing)
        value = {"object_id": spine["object_id"], "revision": spine["revision"],
                 "composite_hash": fh.composite_hash(sh, list(sections))}
    else:
        raise CheckpointError("bad_binding", "binding must be object|section|composite")
    rec = {"status": status, "decided": status == "owner_confirmed", "decided_by": by,
           "decided_at": rt.now(), "value": value}
    if note:
        rec["note"] = note
    s.setdefault("owner_decisions", {})[decision_id] = rec
    if status == "owner_confirmed" and decision_id in (s.get("invalidated") or []):
        s["invalidated"].remove(decision_id)
    rt.atomic_write(rt.state_path(run_id), s)
    return value


def record_legacy_decision(run_id, decision_id, value=None, by="product_owner",
                           status="owner_confirmed", note=None):
    """Record a plain owner_decisions entry (the legacy compatibility ids frame_accepted /
    opportunity_selected). Single home for run.cmd_record_decision's write."""
    rt = _rt()
    s = rt.require_run(run_id)
    if by == "product_owner" and status != "owner_confirmed":
        raise CheckpointError("decision_status_misstamped",
                              "product_owner requires status owner_confirmed")
    rec = {"status": status, "decided": status == "owner_confirmed", "decided_by": by,
           "decided_at": rt.now()}
    if value is not None:
        rec["value"] = value
    if note:
        rec["note"] = note
    s.setdefault("owner_decisions", {})[decision_id] = rec
    if status == "owner_confirmed" and decision_id in (s.get("invalidated") or []):
        s["invalidated"].remove(decision_id)
    rt.atomic_write(rt.state_path(run_id), s)
    return rec


# ═══════════════════════════════════════════════════════════════════
# SESSION OPERATIONS — the interaction-layer verbs the CLI + API expose.
# ═══════════════════════════════════════════════════════════════════
def _binding_for(cp, spine):
    """The approval binding descriptor(s) for a checkpoint (what hash a decision would bind)."""
    if cp["checkpoint_type"] == "kickoff":
        return [{"decision_id": "kickoff_approved", "binding": "object",
                 "would_bind": spine.get("canonical_hash")}]
    if cp["checkpoint_type"] == "direction":
        return [{"decision_id": "direction_selected_v2", "binding": "direction"}]
    if cp["checkpoint_type"] == "premise_verticals":
        sh = spine.get("section_hashes") or {}
        return [{"decision_id": "premise_approved", "binding": "section", "section": "premise",
                 "would_bind": sh.get("premise")},
                {"decision_id": "verticals_approved", "binding": "section",
                 "section": "vertical_strategies", "would_bind": sh.get("vertical_strategies")}]
    if cp["checkpoint_type"] == "architecture":
        secs = ["collection_selections", "rails", "content_program"]
        return [{"decision_id": "architecture_approved", "binding": "composite",
                 "sections": secs,
                 "would_bind": (fh.composite_hash(spine.get("section_hashes") or {}, secs)
                                if spine.get("section_hashes") else None)}]
    if cp["checkpoint_type"] == "build_this":
        secs = list(fh.CS_SECTIONS)
        return [{"decision_id": "campaign_spec_approved", "binding": "composite", "sections": secs,
                 "would_bind": (fh.composite_hash(spine.get("section_hashes") or {}, secs)
                                if spine.get("section_hashes") else None)}]
    return []


def _allowed_actions(status):
    """The interaction actions legal in a given session status (drives the GUI buttons)."""
    if status == S_OPEN:
        return ["submit_intake"]
    if status in (S_OWNER_REVIEW, S_REVISION_REQUESTED, S_DRAFT_READY):
        return ["request_revision", "approve", "run_next"]
    if status == S_APPROVED:
        return ["run_next"]
    return []


def describe_checkpoint(run_id):
    """The ONE structured checkpoint view the CLI + API + GUI render (task §5/§22, closes AF-003/004).
    Everything is recomputed from state + schema; nothing is a second SSOT. Returns a dict with the
    current checkpoint, session status, intake questions, review model, revision history + current
    diff, allowed actions, and the exact hash a decision would bind."""
    rt = _rt()
    s = rt.require_run(run_id)
    cp = current_checkpoint(s)
    header = run_header(run_id, s)
    if cp is None:
        return {"run_id": run_id, "header": header, "checkpoint": None,
                "front_half_complete": True,
                "message": "All five front-half checkpoints approved — the campaign_spec is built."}
    kind = cp["object_kind"]
    spine = _object_spine(s, kind)
    obj = _current_object_bytes(s, rt.run_dir, run_id, kind)
    status = _session_status(s, rt.run_dir, run_id, cp)

    # intake / review model per checkpoint type
    questions, review = [], None
    if cp["checkpoint_type"] == "kickoff":
        questions = kickoff_questions(obj)
    elif cp["checkpoint_type"] == "direction":
        questions = direction_questions(obj)
        review = {"directions": (obj or {}).get("directions") or [],
                  "recommended": (obj or {}).get("recommended_direction_id")}
    elif cp["checkpoint_type"] == "premise_verticals":
        questions = premise_questions(obj)
        review = {"premise": _spec_sections(obj).get("premise"),
                  "vertical_strategies": _spec_sections(obj).get("vertical_strategies")}
    elif cp["checkpoint_type"] == "architecture":
        review = architecture_review_sections(obj)
    elif cp["checkpoint_type"] == "build_this":
        review = build_this_review(obj)

    revisions = list((spine.get("revisions") or []))
    current_diff = object_diff(run_id, kind) if len(revisions) >= 2 else None

    # worker step: is a producing worker DUE now (object absent), and what is the last worker status?
    due, work_type = can_run_next(s, rt.run_dir, run_id)
    wstat = worker_status(run_id)
    actions = list(_allowed_actions(status))
    if due:
        # the object does not exist yet — the ONLY affordance is Run Next (the worker produces it),
        # unless the owner authors it directly at intake (kickoff has no producing worker).
        actions = ["run_next"] if work_type else actions
    else:
        actions = [a for a in actions if a != "run_next"]  # no re-running a completed worker step

    return {
        "run_id": run_id,
        "header": header,
        "checkpoint": {
            "checkpoint_type": cp["checkpoint_type"],
            "ordinal": cp["ordinal"],
            "title": cp["title"],
            "prompt": cp["prompt"],
            "object_kind": kind,
            "status": status,
            "object_id": spine.get("object_id"),
            "current_revision": spine.get("revision"),
            "current_hash": spine.get("canonical_hash"),
            "questions": questions,
            "review": review,
            "revision_history": revisions,
            "current_diff": current_diff,
            "allowed_actions": actions,
            "approval_binding": _binding_for(cp, spine),
            "run_next_available": bool(due and work_type),
            "pending_work_type": work_type if due else None,
            "worker_status": wstat,
        },
    }


PRODUCT_PHASES = [
    ("kickoff", "Kickoff"), ("direction", "Research + Direction"),
    ("premise_verticals", "Premise + Verticals"), ("architecture", "Architecture"),
    ("build_this", "Build This"), ("fulfillment", "Fulfillment"),
    ("execution", "Execution"), ("approved", "Approved for Implementation"),
    ("live", "Live"), ("review", "Review"),
]


def back_half_status(run_id, s=None):
    """Real back-half progression from state + on-disk artifacts (drives the timeline past Build This).
    Returns per-phase status so the Console no longer shows Fulfillment/Execution as perpetually
    'waiting' when their controls are available."""
    rt = _rt()
    s = s or rt.require_run(run_id)
    front_done = current_checkpoint(s) is None
    requests = list_requests(run_id) if front_done else []
    import receipt_ingest as ri
    store = _run_store(run_id)
    ingestions = ri.load_ingestions(store) if os.path.isdir(store) else []
    open_mx = _open_material_exceptions(s)
    arts = s.get("artifacts") or {}
    manifest = (arts.get("execution_manifest") or {})
    manifest_current = manifest.get("status", "current") == "current" and bool(manifest.get("path"))
    attempts = s.get("validation_attempts") or []
    last = attempts[-1] if attempts else {}
    validated = bool(manifest_current and last.get("result") == "passed"
                     and last.get("package_validated"))
    approved = _approval_recorded(s, "execution_package_approved") or bool(
        (s.get("owner_decisions") or {}).get("execution_package_approved", {}).get("decided"))
    verification = s.get("verification") or {}
    live = (s.get("workflow") or {}).get("state") == "LIVE" or bool(verification.get("result") == "pass")
    reviewed = (s.get("workflow") or {}).get("state") == "REVIEWED"
    # satisfied = every generated request has a satisfied ingestion
    satisfied_cats = {i.get("category_id") for i in ingestions if i.get("terminal_status") == "satisfied"}
    req_cats = {r["category_id"] for r in requests}
    fulfillment_done = bool(req_cats) and req_cats <= satisfied_cats and not open_mx
    return {
        "front_done": front_done,
        "requests_generated": bool(requests), "requests": requests,
        "ingestions": len(ingestions), "material_exceptions_open": open_mx,
        "fulfillment_done": fulfillment_done, "blocked": bool(open_mx),
        "validated": validated, "approved": approved, "live": live, "reviewed": reviewed,
    }


def run_header(run_id, s=None):
    """A product-facing run header (closes AF-004): checkpoint ladder position, current object
    id/revision, whether an owner action is required, run_mode, campaign name, internal state
    under a technical split."""
    rt = _rt()
    s = s or rt.require_run(run_id)
    cur = current_checkpoint(s)
    bh = back_half_status(run_id, s)
    timeline = []
    cur_type = cur["checkpoint_type"] if cur else None
    # the first back-half phase that is not yet done is the current one (once the front half is done)
    if cur is None:
        if not bh["requests_generated"]:
            cur_type = "fulfillment"
        elif not bh["fulfillment_done"]:
            cur_type = "fulfillment"
        elif not bh["validated"]:
            cur_type = "execution"
        elif not bh["approved"]:
            cur_type = "approved"
        elif not bh["live"]:
            cur_type = "live"
        else:
            cur_type = "review"
    back_done = {
        "fulfillment": bh["fulfillment_done"],
        "execution": bh["validated"],
        "approved": bh["approved"],
        "live": bh["live"],
        "review": bh["reviewed"],
    }
    for i, (ptype, label) in enumerate(PRODUCT_PHASES):
        cp = CHECKPOINT_BY_TYPE.get(ptype)
        if cp and _checkpoint_approved(s, cp):
            marker = "complete"
        elif ptype in back_done and back_done[ptype]:
            marker = "complete"
        elif ptype == cur_type:
            marker = "current" if not bh.get("blocked") else "blocked"
        else:
            marker = "waiting"
        timeline.append({"phase": ptype, "label": label, "status": marker})
    action_required = cur is not None and _session_status(s, rt.run_dir, run_id, cur) in (
        S_OPEN, S_OWNER_REVIEW, S_REVISION_REQUESTED)
    ident = s.get("identity") or {}
    return {
        "run_id": run_id,
        "display_name": ident.get("display_name"),
        "campaign_id": (ident.get("campaign_id") or {}).get("value"),
        "run_mode": (s.get("run") or {}).get("run_mode"),
        "internal_state": (s.get("workflow") or {}).get("state"),
        "current_checkpoint": cur_type if cur else None,
        "current_ordinal": cur["ordinal"] if cur else None,
        "owner_action_required": action_required,
        "material_exceptions_open": _open_material_exceptions(s),
        "timeline": timeline,
        "worker": worker_readiness((s.get("run") or {}).get("run_mode")),
    }


def worker_readiness(run_mode="production"):
    """The agent-worker readiness for the Console indicator (task §7/§8): Ready (with which worker) or
    Unavailable — setup required. A diagnostic run may fall back to the deterministic fake."""
    import worker as wk
    r = dict(wk.worker_readiness())
    if not r["ready"] and run_mode == "diagnostic":
        r = {"ready": True, "kind": "fake_diagnostic",
             "label": "Deterministic worker (diagnostic run)"}
    return r


def _open_material_exceptions(s):
    mx = s.get("material_exceptions") or {}
    if isinstance(mx, dict):
        return [k for k, v in mx.items() if (v or {}).get("status") == "open"]
    return []


def object_diff(run_id, kind, from_rev=None, to_rev=None):
    """Semantic diff between two immutable revisions of an object (default: previous vs current)."""
    rt = _rt()
    files = dict(_revision_files(rt.run_dir, run_id, kind))
    labels = sorted(files.keys())
    if len(labels) < 2 and not (from_rev and to_rev):
        return None
    to_rev = to_rev or labels[-1]
    if from_rev is None:
        idx = labels.index(to_rev)
        if idx == 0:
            return None
        from_rev = labels[idx - 1]
    if from_rev not in files or to_rev not in files:
        raise CheckpointError("unknown_revision", "revision not found: %r/%r" % (from_rev, to_rev))
    old = yaml.safe_load(open(files[from_rev], encoding="utf-8"))
    new = yaml.safe_load(open(files[to_rev], encoding="utf-8"))
    diff = semantic_diff(old, new)
    diff["from_revision"] = from_rev
    diff["to_revision"] = to_rev
    diff["has_changes"] = bool(diff["changed"] or diff["added"] or diff["removed"]
                               or diff["reordered"])
    # downstream effects: which approvals this change would invalidate (if it were re-registered)
    return diff


# ---- the three iterative verbs (used by CLI answer/request-revision/approve + API) ----
def request_revision(run_id, revised_payload=None, ops=None, note=None):
    """Owner-requested targeted revision (task §14). Either a whole revised payload OR a list of
    patch ops applied to the current object. Preserves untouched fields, mints a NEW immutable
    revision (auto-labelled), and triggers dependency invalidation. Returns the new revision + diff.

    A revision NEVER edits an approved revision in place; it always creates the next label."""
    rt = _rt()
    s = rt.require_run(run_id)
    cp = current_checkpoint(s)
    if cp is None:
        raise CheckpointError("front_half_complete", "no open checkpoint to revise")
    kind = cp["object_kind"]
    base = _current_object_bytes(s, rt.run_dir, run_id, kind)
    if base is None and ops:
        raise CheckpointError("no_base", "cannot apply ops with no current object; submit intake first")

    if revised_payload is not None:
        payload = revised_payload
    else:
        patched = apply_patch_ops(base, ops or [])
        payload = _strip_stamps(patched)

    # auto-mint the next revision label; preserve parent link where the object supports it
    existing = [lab for lab, _ in _revision_files(rt.run_dir, run_id, kind)]
    new_label = _next_revision_label(existing)
    prev_label = (_object_spine(s, kind).get("revision"))
    payload = dict(payload)
    payload["revision"] = new_label
    if kind == "campaign_spec":
        payload.setdefault("parent_revision", prev_label)

    obj = build_object(run_id, kind, payload)
    result = register_object(run_id, kind, obj)
    result["diff"] = object_diff(run_id, kind, from_rev=prev_label, to_rev=new_label)
    if note:
        result["note"] = note
    return result


def _strip_stamps(obj):
    """Remove derived hash stamps so front_half re-computes them on the revised object."""
    strip = {"canonical_hash", "section_hashes", "composite_hash"}
    out = {k: v for k, v in obj.items() if k not in strip}
    if "signals" in out and isinstance(out["signals"], list):
        out["signals"] = [{k: v for k, v in s.items() if k != "signal_hash"} for s in out["signals"]]
    if "directions" in out and isinstance(out["directions"], list):
        out["directions"] = [{k: v for k, v in d.items() if k != "direction_hash"}
                             for d in out["directions"]]
    return out


def submit_intake(run_id, payload):
    """Owner submits a full first draft object for the current checkpoint's object (task §5/§6). For
    kickoff this is the intake→brief. Builds + registers as the object's next revision. If an object
    already exists this is equivalent to request_revision with a whole payload."""
    rt = _rt()
    s = rt.require_run(run_id)
    cp = current_checkpoint(s)
    if cp is None:
        raise CheckpointError("front_half_complete", "no open checkpoint")
    kind = cp["object_kind"]
    existing = [lab for lab, _ in _revision_files(rt.run_dir, run_id, kind)]
    if existing:
        return request_revision(run_id, revised_payload=payload)
    obj = build_object(run_id, kind, payload)
    return register_object(run_id, kind, obj)


def approve_checkpoint(run_id, by="product_owner", note=None, direction_id=None):
    """SINGLE owner action → the whole decision set for the current checkpoint (task §16, closes
    AF-002). Emits every typed hash-bound approval AND its legacy compatibility id atomically, so the
    owner/GUI issue exactly one approval per checkpoint. Refuses if the object is missing/stale.

    Returns {approved: [decision_ids], bindings: {...}}."""
    rt = _rt()
    s = rt.require_run(run_id)
    cp = current_checkpoint(s)
    if cp is None:
        raise CheckpointError("front_half_complete", "no open checkpoint to approve")
    kind = cp["object_kind"]
    obj = _current_object_bytes(s, rt.run_dir, run_id, kind)
    if obj is None:
        raise CheckpointError("no_object",
                              "no current %s to approve — submit the checkpoint's draft first" % kind)
    approved, bindings = [], {}

    ctype = cp["checkpoint_type"]
    if ctype == "kickoff":
        bindings["kickoff_approved"] = record_object_approval(
            run_id, "kickoff_approved", "research_brief", "object", by=by, note=note)
        record_legacy_decision(run_id, "frame_accepted",
                               value={"basis": "kickoff checkpoint approval"}, by=by, note=note)
        approved = ["kickoff_approved", "frame_accepted"]
    elif ctype == "direction":
        did = direction_id
        if did is None:
            raise CheckpointError("direction_required",
                                  "approving the direction checkpoint requires a selected direction_id")
        bindings["direction_selected_v2"] = record_direction_selection(
            run_id, did, by=by, note=note)
        record_legacy_decision(run_id, "opportunity_selected",
                               value={"direction_id": did}, by=by, note=note)
        approved = ["direction_selected_v2", "opportunity_selected"]
    elif ctype == "premise_verticals":
        bindings["premise_approved"] = record_object_approval(
            run_id, "premise_approved", "campaign_spec", "section", section="premise",
            by=by, note=note)
        bindings["verticals_approved"] = record_object_approval(
            run_id, "verticals_approved", "campaign_spec", "section",
            section="vertical_strategies", by=by, note=note)
        approved = ["premise_approved", "verticals_approved"]
    elif ctype == "architecture":
        bindings["architecture_approved"] = record_object_approval(
            run_id, "architecture_approved", "campaign_spec", "composite",
            sections=["collection_selections", "rails", "content_program"], by=by, note=note)
        approved = ["architecture_approved"]
    elif ctype == "build_this":
        bindings["campaign_spec_approved"] = record_object_approval(
            run_id, "campaign_spec_approved", "campaign_spec", "composite",
            sections=list(fh.CS_SECTIONS), by=by, note=note)
        approved = ["campaign_spec_approved"]

    return {"checkpoint_type": ctype, "approved": approved, "bindings": bindings}


# ═══════════════════════════════════════════════════════════════════
# READ VIEWS — fulfillment / material-exception / execution-package (task §11/§12/§13). These are
# read-only projections the GUI renders; the Engine + the proven back half remain authority. The
# GUI NEVER computes fulfillment itself — it displays the ingested receipt records + open exceptions.
# ═══════════════════════════════════════════════════════════════════
def fulfillment_view(run_id):
    """Per-request fulfillment progress from the Wizard-side ingestion records (task §12). Achieved
    vs required, satisfied/sourcing/shortfall, receipt when terminal. Engine remains authority; we
    only read what was ingested."""
    rt = _rt()
    import receipt_ingest as ri
    store = os.path.join(rt.run_dir(run_id), "fulfillment")
    ingestions = ri.load_ingestions(store)
    exceptions = ri.load_material_exceptions(store)
    rows = []
    for ing in ingestions:
        rows.append({
            "request_id": ing.get("request_id"),
            "category_id": ing.get("category_id"),
            "required_depth": ing.get("required_depth"),
            "achieved_depth": ing.get("achieved_depth") or ing.get("eligible_count"),
            "terminal_status": ing.get("terminal_status"),
            "receipt_id": ing.get("receipt_id"),
        })
    open_mx = [m for m in exceptions if m.get("status") == "open"]
    return {
        "run_id": run_id,
        "requests": rows,
        "material_exceptions_open": len(open_mx),
        "blocked": bool(open_mx),
        "note": "Read-only projection of ingested Engine receipts; the Engine is authority for "
                "product truth and fulfillment.",
    }


def material_exceptions_view(run_id):
    """Structured Material Exception cards (task §11): required/achieved/gap, sourcing status, what
    was attempted, resolution state. Owner resolution never waives render_003."""
    rt = _rt()
    import receipt_ingest as ri
    store = os.path.join(rt.run_dir(run_id), "fulfillment")
    exceptions = ri.load_material_exceptions(store)
    cards = []
    for m in exceptions:
        cards.append({
            "material_exception_id": m.get("material_exception_id"),
            "category_id": m.get("category_id"),
            "required_depth": m.get("required_depth"),
            "achieved_depth": m.get("achieved_depth"),
            "gap": (m.get("required_depth") or 0) - (m.get("achieved_depth") or 0),
            "status": m.get("status"),
            "sourcing_policy": m.get("shortfall_policy") or "exhausted",
            "attempted": m.get("attempted") or m.get("sourcing_summary"),
            "resolution": m.get("resolution"),
        })
    return {"run_id": run_id, "material_exceptions": cards,
            "note": "Owner resolution records campaign judgment only; it never waives render_003, "
                    "never makes a shortfall satisfy completeness, never unblocks assembly."}


def execution_package_view(run_id):
    """The structured execution-package review (task §13). Reads the registered Execution Manifest +
    the staged A–G components + the validation attempt; presents them as a review model. Raw A–G
    files are available as downloads secondarily, not as the primary experience."""
    rt = _rt()
    s = rt.require_run(run_id)
    arts = s.get("artifacts") or {}
    manifest_rec = arts.get("execution_manifest")
    manifest = None
    if manifest_rec:
        rd = rt.run_dir(run_id)
        p = manifest_rec["path"]
        full = p if os.path.isabs(p) else os.path.join(rd, p)
        if not os.path.exists(full):
            full = os.path.join(rt.ROOT, p)
        if os.path.exists(full):
            manifest = yaml.safe_load(open(full, encoding="utf-8"))
    attempts = s.get("validation_attempts") or []
    last = attempts[-1] if attempts else None
    validated = bool(manifest_rec and manifest_rec.get("status", "current") == "current"
                     and last and last.get("result") == "passed"
                     and last.get("package_validated"))
    # owner-friendly component summary from the approved-spec architecture projection (secondary raw
    # A–G files stay as downloads). Product truth stays with the Engine; this is judgment structure.
    # Selected/pinned product COUNTS come from the registered execution_selection (Wizard judgment).
    summary = None
    try:
        if current_checkpoint(s) is None:
            arch = spec_architecture(run_id)
            selection = _current_object_bytes(s, rt.run_dir, run_id, "execution_selection")
            picks_by_cat, rail_picks = {}, {}
            for sel in (selection or {}).get("selections") or []:
                cat = sel.get("category_id")
                picks_by_cat[cat] = len(sel.get("picks") or [])
                for p in sel.get("picks") or []:
                    if p.get("is_rail_item"):
                        rail_picks[p.get("rail_id")] = rail_picks.get(p.get("rail_id"), 0) + 1
            summary = {
                "collections": [{"category_id": c.get("category_id"),
                                 "display_name": c.get("display_name"),
                                 "selected": picks_by_cat.get(c.get("category_id"), 0)}
                                for c in arch["collections"]],
                "rails": [{"rail_id": r.get("rail_id"), "title": r.get("rail_name"),
                           "kind": r.get("rail_kind"),
                           "pinned": rail_picks.get(r.get("rail_id"), 0)} for r in arch["rails"]],
                "content": [{"content_id": c.get("content_id"), "headline": c.get("card_headline"),
                             "seo_title": c.get("seo_title")} for c in arch["content"]],
                "default_composition": arch.get("default_composition"),
                "renderer_capabilities": arch.get("renderer_capabilities"),
                "has_selection": selection is not None,
            }
    except CheckpointError:
        summary = None
    return {
        "run_id": run_id,
        "has_manifest": manifest is not None,
        "manifest_id": (manifest or {}).get("execution_manifest_id") or (manifest or {}).get("manifest_id"),
        "manifest_sha256": manifest_rec.get("sha256") if manifest_rec else None,
        "validated": validated,
        "validation_result": (last or {}).get("result"),
        "components": (manifest or {}).get("components"),
        "validation_block": (manifest or {}).get("validation"),
        "summary": summary,
        "products_csv": (arts.get("products_csv") or {}).get("path"),
        "approved": _approval_recorded(s, "execution_package_approved") or bool(
            (s.get("owner_decisions") or {}).get("execution_package_approved", {}).get("decided")),
        "note": "Structured review of the validated, manifest-bound package. Approval binds the "
                "exact manifest id/sha. Raw A–G files are secondary downloads.",
    }


# ═══════════════════════════════════════════════════════════════════
# RUN LIST + CREATE (task §17/§20) — the campaign-list surface + new-run creation, both adapters
# over run.py so the API/CLI/GUI share one path.
# ═══════════════════════════════════════════════════════════════════
def list_runs():
    """Campaign-list cards (task §20): name, phase, checkpoint progress, owner-action flag,
    material exceptions, run_mode."""
    rt = _rt()
    out = []
    for d in rt.all_run_dirs():
        s = yaml.safe_load(open(os.path.join(d, "state.yaml"), encoding="utf-8"))
        run_id = (s.get("run") or {}).get("run_id") or os.path.basename(d)
        try:
            header = run_header(run_id, s)
        except Exception:
            header = {"current_checkpoint": None, "owner_action_required": False}
        out.append({
            "run_id": run_id,
            "display_name": (s.get("identity") or {}).get("display_name"),
            "campaign_id": ((s.get("identity") or {}).get("campaign_id") or {}).get("value"),
            "run_mode": (s.get("run") or {}).get("run_mode"),
            "internal_state": (s.get("workflow") or {}).get("state"),
            "current_checkpoint": header.get("current_checkpoint"),
            "current_ordinal": header.get("current_ordinal"),
            "owner_action_required": header.get("owner_action_required"),
            "material_exceptions_open": header.get("material_exceptions_open") or [],
        })
    return out


def create_run(note=None, diagnostic=False):
    """Create a new run (task §17 POST /runs). Adapter over run.py's NEW logic without its CLI I/O."""
    rt = _rt()
    import types
    # replicate cmd_new's state construction but return the run_id instead of printing/exiting.
    schema = yaml.safe_load(open(rt.SCHEMA, encoding="utf-8"))
    charter = yaml.safe_load(open(rt.CHARTER, encoding="utf-8"))
    rid = "cmp_" + rt.ulid()
    d = os.path.join(rt.RUNS, rt.DRAFTS, rid)
    os.makedirs(d, exist_ok=False)
    spec_v = schema["schema"]["version"]
    chart_v = charter["charter"]["version"]
    run_mode = "diagnostic" if diagnostic else "production"
    st = {
        "run": {"run_id": rid, "spec_version": spec_v, "charter_version": chart_v,
                "run_mode": run_mode, "created_at": rt.now()},
        "identity": {"campaign_id": {"value": None, "status": None, "confirmed_by_owner": False,
                                     "externally_referenced": False, "first_external_reference": None},
                     "display_name": None},
        "workflow": {"state": "NEW", "entered_at": rt.now(),
                     "history": [{"from": None, "to": "NEW", "at": rt.now(),
                                  "transition_type": "forward", "pinned_spec_version": spec_v,
                                  "pinned_charter_version": chart_v, "pinned_run_mode": run_mode,
                                  "decision_ref": None}]},
        "owner_decisions": {}, "artifacts": {}, "invalidated": [],
        "execution_tracking": {"activation_architecture_status": "not_started",
                               "seam6_execution_status": "not_started",
                               "external_handoffs_status": "not_started",
                               "external_handoffs_implemented": "unknown"},
        "capability_claims": [], "validation_attempts": [],
        "collection_freeze": {"snapshot": [], "exceptions": []}, "abandonment": None,
    }
    if note:
        st["run"]["note"] = note
    rt.atomic_write(rt.state_path(rid), st)
    return {"run_id": rid, "run_mode": run_mode, "spec_version": spec_v,
            "charter_version": chart_v, "internal_state": "NEW"}


# ═══════════════════════════════════════════════════════════════════
# WORKER ORCHESTRATION (owner-flow closeout) — the Wizard runs the research/synthesis worker BEHIND
# the interface. The owner clicks "Run Next"; the Wizard determines the work, supplies the approved
# context + output contract, invokes the configured WorkerAdapter, VALIDATES the returned structured
# artifact via the front_half builders, and REGISTERS it (immutable revision). The owner-facing layer
# never receives responsibility for generating the object. A worker failure leaves a coherent,
# retryable state and NEVER registers a partial artifact.
# ═══════════════════════════════════════════════════════════════════
def _worker_context(state, run_id, work_type):
    """Build the approved context the worker is given for a work type (READ-ONLY refs to the exact
    approved upstream objects). The worker gets what it needs to bind correctly — never authority."""
    rt = _rt()
    ctx = {"run_id": run_id, "work_type": work_type}
    brief_spine = _object_spine(state, "research_brief")
    if brief_spine:
        ctx["brief_id"] = brief_spine.get("object_id")
        ctx["brief_revision"] = brief_spine.get("revision")
        ctx["brief_hash"] = brief_spine.get("canonical_hash")
        brief = _current_object_bytes(state, rt.run_dir, run_id, "research_brief")
        if brief:
            # pass the approved brief content the worker researches from (read-only)
            ctx["brief"] = brief
    # research also needs the ledger + directions the worker binds to, once they exist
    for kind, key in (("research_ledger", "ledger"), ("campaign_directions", "directions")):
        obj = _current_object_bytes(state, rt.run_dir, run_id, kind)
        if obj:
            ctx[key] = obj
    if work_type == "spec":
        dsel = (state.get("owner_decisions") or {}).get("direction_selected_v2") or {}
        val = dsel.get("value") or {}
        if val:
            ctx["selected_direction_ref"] = {
                "directions_id": val.get("directions_id"), "revision": val.get("revision"),
                "direction_id": val.get("direction_id"), "direction_hash": val.get("direction_hash")}
        # carry the current spec forward so architecture/finalize amend rather than start fresh
        spec = _current_object_bytes(state, rt.run_dir, run_id, "campaign_spec")
        if spec:
            ctx["current_spec"] = spec
        # architecture judgment selects from the CAMPAIGN-NEUTRAL taxonomy (task §5, AF-008): the
        # worker must never see historical Almost Fall selection markers.
        try:
            import taxonomy as tx
            ctx["neutral_taxonomy"] = tx.neutral_registry()
        except Exception:
            pass
    return ctx


WORK_PHASE_LABEL = {
    "research": "Researching",
    "spec": "Developing premise, verticals, architecture",
}


def _record_worker_run(run_id, work_type, status, detail=None, error=None):
    """Record a worker-run status entry (for the Working/error/retry UX). Append-only; the newest
    entry drives the UI. Never carries campaign truth — it is orchestration status only."""
    rt = _rt()
    s = rt.require_run(run_id)
    runs = s.setdefault("worker_runs", [])
    rec = {"work_type": work_type, "status": status, "at": rt.now(),
           "phase": WORK_PHASE_LABEL.get(work_type, work_type)}
    if detail:
        rec["detail"] = detail
    if error:
        rec["error"] = error
    runs.append(rec)
    # keep the list bounded (status history, not an audit ledger)
    if len(runs) > 40:
        del runs[:-40]
    rt.atomic_write(rt.state_path(run_id), s)
    return rec


def worker_status(run_id):
    """The latest worker-run status (drives the Working/failed banner). None if no worker has run."""
    rt = _rt()
    s = rt.require_run(run_id)
    runs = s.get("worker_runs") or []
    return runs[-1] if runs else None


def can_run_next(state, run_dir_fn, run_id):
    """Whether a worker step is DUE, and its work type.

    The checkpoint ladder advances by approval; `current_checkpoint` is the first UNAPPROVED
    checkpoint, which guarantees every prior checkpoint is already approved. A worker step is due when
    the current checkpoint's authoritative object is NOT yet present and a producer exists for it
    (research produces the direction object; the spec work produces the campaign_spec). If the object
    is already present, the owner reviews/approves it — no worker step. Returns (due, work_type)."""
    import worker as wk
    cp = current_checkpoint(state)
    if cp is None:
        return False, None
    wt = wk.CHECKPOINT_PRODUCER.get(cp["checkpoint_type"])
    if wt is None:
        return False, None
    obj = _current_object_bytes(state, run_dir_fn, run_id, cp["object_kind"])
    return (obj is None), wt


def pending_work_type(state, run_dir_fn=None, run_id=None):
    """The work type a Run Next would dispatch now, or None if the current checkpoint awaits an owner
    action (object present) or the front half is complete."""
    rt = _rt()
    due, wt = can_run_next(state, run_dir_fn or rt.run_dir, run_id or (state.get("run") or {}).get("run_id"))
    return wt if due else None


def run_checkpoint_work(run_id, worker=None):
    """Execute the worker for the current checkpoint's pending work (owner-flow closeout).

    Lifecycle: determine work → build approved context → invoke worker → validate output (front_half
    builders are the gate) → register the immutable object(s) in dependency order → advance. On ANY
    failure a WORK FAILED status is recorded and NO partial artifact is registered; the run is left
    coherent + retryable. Returns {work_type, registered: [...], next_checkpoint}.
    """
    import worker as wk
    rt = _rt()
    s = rt.require_run(run_id)
    due, wt = can_run_next(s, rt.run_dir, run_id)
    cp = current_checkpoint(s)
    if wt is None:
        raise CheckpointError("no_work",
                              "the current checkpoint has no producing worker step "
                              "(its object is authored by the owner or already present)")
    if not due:
        raise CheckpointError(
            "object_already_present",
            "the %s object is already present — review/approve it (or request a revision) "
            "rather than re-running the worker" % (cp["object_kind"] if cp else "?"))

    # FAIL-CLOSED worker selection (task §6): a production run with no real worker raises
    # worker_unavailable — never a silent fake. The fake is used only for an explicit diagnostic run
    # or when a caller passes one in (tests). run_mode is the run-level identity set once at NEW.
    run_mode = (s.get("run") or {}).get("run_mode") or "production"
    if worker is None:
        try:
            worker = wk.get_worker(run_mode=run_mode, allow_fake=(run_mode == "diagnostic"))
        except wk.WorkerError as e:
            _record_worker_run(run_id, wt, "unavailable", detail=e.message, error=e.code)
            raise CheckpointError("worker_unavailable", e.message)
    ctx = _worker_context(s, run_id, wt)
    _record_worker_run(run_id, wt, "working", detail="invoking worker for %s" % wt)

    # 1) invoke — any worker error is a clean, retryable failure (no state mutation happened yet).
    try:
        result = worker.run({"work_type": wt, "context": ctx,
                             "output_contract": wk.WORK_TYPES[wt]})
    except wk.WorkerError as e:
        _record_worker_run(run_id, wt, "failed", detail=e.message, error=e.code)
        raise CheckpointError("work_failed", "worker failed on %s: %s" % (wt, e.message))

    # 2) VALIDATE every returned object BEFORE registering ANY of them (all-or-nothing coherence).
    built = []
    try:
        for o in result["objects"]:
            kind = o["kind"]
            expected = wk.WORK_TYPES[wt]["produces"]
            if kind not in expected:
                raise CheckpointError("worker_wrong_object",
                                      "worker returned %r; %s produces %s" % (kind, wt, expected))
            payload = _prepare_worker_payload(s, rt, run_id, kind, o["payload"])
            obj = build_object(run_id, kind, payload)   # front_half validators gate here
            built.append((kind, obj))
    except CheckpointError as e:
        _record_worker_run(run_id, wt, "failed", detail=e.message, error=e.code)
        raise CheckpointError("work_output_invalid",
                              "worker output for %s was rejected: %s" % (wt, e.message))

    # 3) register the validated objects in dependency order. Registration is immutable + idempotent
    #    (same id/rev/hash is a no-op), so a retry after a mid-sequence crash is safe.
    registered = []
    for kind, obj in built:
        res = register_object(run_id, kind, obj)
        registered.append({"kind": kind, "object_id": res["object_id"], "revision": res["revision"]})

    _record_worker_run(run_id, wt, "done", detail="registered %s"
                       % ", ".join(r["kind"] for r in registered))
    nxt = describe_checkpoint(run_id).get("checkpoint")
    return {"work_type": wt, "registered": registered,
            "next_checkpoint": (nxt or {}).get("checkpoint_type")}


def _prepare_worker_payload(state, rt, run_id, kind, payload):
    """Bind a worker payload to the run's real upstream objects + mint the correct revision label.

    The worker returns candidate content; the Wizard fixes the identity so the object binds to THIS
    run's approved brief/ledger/direction and lands as the next immutable revision. This keeps
    campaign-judgment content from the worker while identity/immutability stays Wizard-owned.
    """
    payload = dict(payload)
    if kind == "research_ledger":
        bspine = _object_spine(state, "research_brief")
        if bspine:
            payload["brief_ref"] = bspine.get("object_id")
    elif kind == "campaign_directions":
        lspine = _object_spine(state, "research_ledger")
        if lspine:
            payload["ledger_ref"] = lspine.get("object_id")
    elif kind == "campaign_spec":
        dsel = (state.get("owner_decisions") or {}).get("direction_selected_v2") or {}
        val = dsel.get("value") or {}
        if val:
            payload["selected_direction_ref"] = {
                "directions_id": val.get("directions_id"), "revision": val.get("revision"),
                "direction_id": val.get("direction_id")}
    # mint the next immutable revision label for this kind
    existing = [lab for lab, _ in _revision_files(rt.run_dir, run_id, kind)]
    prev = _object_spine(state, kind).get("revision")
    payload["revision"] = _next_revision_label(existing)
    if kind == "campaign_spec" and prev:
        payload["parent_revision"] = prev
    return payload


# ═══════════════════════════════════════════════════════════════════
# BACK-HALF OWNER FLOW (full-lifecycle closeout) — the Wizard→Engine handoff driven from the Console.
# These are THIN wrappers over the EXISTING proven back-half operations (generate_curation_request,
# receipt_ingest, execution_package) so the CLI and the Console share one path. NO Engine change, NO
# duplicated Engine business logic, NO product truth authored here — the worker/GUI stay judgment-only
# and product truth stays with the Engine. Each function returns structured data / raises
# CheckpointError; the API handlers and CLI are adapters over them.
# ═══════════════════════════════════════════════════════════════════
def _run_store(run_id):
    return os.path.join(_rt().run_dir(run_id), "fulfillment")


def _requests_dir(run_id):
    return os.path.join(_rt().run_dir(run_id), "requests")


def _package_dir(run_id):
    return os.path.join(_rt().run_dir(run_id), "package")


def generate_requests(run_id):
    """Generate the Request v2 SET from the EXACT approved campaign_spec (task §22/§23). Thin wrapper
    over generate_curation_request: refuses unless a CURRENT non-stale campaign_spec_approved exists
    (a stale/unapproved spec never generates). One immutable, canonically-hashed request per durable
    collection_selection. Returns {requests:[{request_id, category_id, required_depth, request_hash,
    path}], spec_ref}."""
    import generate_curation_request as gcr
    rt = _rt()
    run_state = rt.require_run(run_id)
    spec_ref, spine, errors = gcr.approved_spec_binding(run_state)
    if errors:
        raise CheckpointError("no_build_this_authority",
                              "cannot generate requests: " + " ; ".join(errors))
    spec_doc = _current_object_bytes(run_state, rt.run_dir, run_id, "campaign_spec")
    sections = (spec_doc or {}).get("sections") or {}
    pairs = gcr.selections_from_spec(sections)
    if not pairs:
        raise CheckpointError("no_selections", "the approved spec has no collection_selections")
    base = _requests_dir(run_id)
    os.makedirs(base, exist_ok=True)
    out, errs_all = [], []
    for cat, depth in pairs:
        art, errs = gcr.build_request(run_state, cat, depth, spec_ref=spec_ref)
        if errs:
            errs_all += ["%s: %s" % (cat, e) for e in errs]
            continue
        p = os.path.join(base, "request_%s.json" % str(cat).replace(".", "_"))
        with open(p, "w", encoding="utf-8") as f:
            json.dump(art, f, ensure_ascii=False, indent=2)
        out.append({"request_id": art["request_id"], "category_id": art["category_id"],
                    "required_depth": art["required_depth"],
                    "request_hash": art["integrity"]["request_hash"], "path": p})
    if errs_all:
        raise CheckpointError("request_generation_failed", " ; ".join(errs_all))
    return {"requests": out, "spec_ref": spec_ref}


def list_requests(run_id):
    """The generated Request v2 set on disk (read-only summary for the Console)."""
    base = _requests_dir(run_id)
    out = []
    if os.path.isdir(base):
        for fn in sorted(os.listdir(base)):
            if fn.endswith(".json"):
                try:
                    art = json.load(open(os.path.join(base, fn), encoding="utf-8"))
                except Exception:
                    continue
                out.append({"request_id": art.get("request_id"),
                            "category_id": art.get("category_id"),
                            "required_depth": art.get("required_depth"),
                            "request_hash": (art.get("integrity") or {}).get("request_hash"),
                            "path": os.path.join(base, fn)})
    return out


def ingest_receipt(run_id, receipt_path, request_path, snapshot_dir=None,
                   fulfillment_exception_path=None, no_run_check=False, no_campaign_check=False):
    """Ingest ONE immutable Engine Curation Receipt v1 mechanically (task §12) — thin wrapper over
    receipt_ingest.ingest_receipt. Independently verifies + binds to the exact Request v2, recomputes
    the eligible SET, distinguishes satisfied vs shortfall (opening a Material Exception on shortfall),
    records an immutable ingestion. Refuses a diagnostic receipt in a production run + tampered/
    mismatched artifacts. Returns the structured ingestion outcome.

    no_run_check / no_campaign_check mirror the CLI's cross-repo-fixture flags; production ingestion
    from the Console always keeps both binding checks ON (the API never passes them)."""
    import receipt_ingest as ri
    rt = _rt()
    s = rt.require_run(run_id)
    run_mode = (s.get("run") or {}).get("run_mode") or "production"
    campaign_id = ((s.get("identity") or {}).get("campaign_id") or {}).get("value")
    run_ref = (s.get("run") or {}).get("run_id")
    try:
        res = ri.ingest_receipt(
            receipt_path, request_path, snapshot_dir=snapshot_dir, store_dir=_run_store(run_id),
            fulfillment_exception_path=fulfillment_exception_path,
            expected_run_mode=run_mode,
            expected_campaign_id=None if no_campaign_check else campaign_id,
            expected_run_ref=None if no_run_check else run_ref, generated_at=rt.now())
    except ri.ReceiptIngestError as e:
        raise CheckpointError("receipt_ingest_refused", str(e))
    # PERSIST the exact bound Truth Export v2 snapshot into the run store (task §2) so package build
    # loads it AUTOMATICALLY by the receipt's binding — the owner never re-supplies a truth-export
    # path. Keyed by export_id (content-addressed); a copy, never re-verified as authority here (the
    # ingestion already verified export_id + export_sha256 against the receipt).
    _persist_bound_snapshot(run_id, receipt_path, snapshot_dir)
    return res


def _snapshots_dir(run_id):
    return os.path.join(_run_store(run_id), "snapshots")


def _persist_bound_snapshot(run_id, receipt_path, snapshot_dir):
    """Copy the receipt's bound Truth Export v2 snapshot into <store>/snapshots/<export_id>.jsonl."""
    import receipt_ingest as ri
    try:
        receipt = json.load(open(receipt_path, encoding="utf-8")) \
            if not isinstance(receipt_path, dict) else receipt_path
    except Exception:
        return
    tex = (receipt or {}).get("truth_export") or {}
    eid = tex.get("export_id")
    if not eid:
        return
    src = ri._resolve_snapshot_path(receipt, snapshot_dir)
    if not src or not os.path.exists(src):
        return
    dst_dir = _snapshots_dir(run_id)
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, "%s.jsonl" % eid)
    if not os.path.exists(dst):
        import shutil
        shutil.copyfile(src, dst)


def bound_snapshot_path(run_id, export_id):
    """The persisted bound Truth Export snapshot for an export_id, or None (task §2)."""
    p = os.path.join(_snapshots_dir(run_id), "%s.jsonl" % export_id)
    return p if os.path.exists(p) else None


def resolve_material_exception(run_id, mx_id, resolution, by="product_owner"):
    """Record an owner JUDGMENT on an open Material Exception (open -> resolved). DECISION RECORD ONLY
    (task §13): never unblocks assembly, waives render_003, or makes a shortfall satisfy completeness.
    Thin wrapper over receipt_ingest.resolve_material_exception."""
    import receipt_ingest as ri
    if by != "product_owner":
        raise CheckpointError("owner_required", "a Material Exception resolution is an owner judgment")
    resolution = dict(resolution or {})
    resolution.setdefault("resolved_by", by)
    try:
        return ri.resolve_material_exception(_run_store(run_id), mx_id, resolution,
                                             generated_at=_rt().now())
    except ri.ReceiptIngestError as e:
        raise CheckpointError("resolve_refused", str(e))


def spec_architecture(run_id):
    """The current-adapter architecture object the A–G producers consume, projected from the approved
    campaign_spec (JUDGMENT ONLY — no product truth; front_half.campaign_spec_to_architecture).

    Backfills each collection's request_id from the GENERATED Request v2 set on disk, so the package
    coherence check (expected-request set) matches the ingested receipts. request_id stays None until
    its request is generated (assembly then refuses, correctly)."""
    import front_half as fh
    rt = _rt()
    s = rt.require_run(run_id)
    spec = _current_object_bytes(s, rt.run_dir, run_id, "campaign_spec")
    if not spec:
        raise CheckpointError("no_spec", "no current campaign_spec to project")
    arch = fh.campaign_spec_to_architecture(spec)
    req_by_cat = {r["category_id"]: r["request_id"] for r in list_requests(run_id)}
    for c in arch.get("collections") or []:
        if req_by_cat.get(c.get("category_id")):
            c["request_id"] = req_by_cat[c["category_id"]]
    return arch


def build_and_validate_package(run_id, judgment=None, truth_export=None, engine=None, campaign=None,
                               campaign_name=None, build=None, package_revision=1):
    """Build the COMPLETE A–G package, validate it, and (only after validation passes) emit + register
    the immutable F Execution Manifest — the frozen, non-self-attesting order (task §17–§19). Thin
    orchestration over execution_package (+ the v2 Master-CSV builder subprocess).

    Two distinct inputs (as the proven CLI requires): the ARCHITECTURE (collections/rails/content),
    auto-projected from the approved spec, drives B–G; the JUDGMENT rows (the curated per-product
    launch set) drive A (the Master CSV), hydrated read-only from the Engine truth export. The
    judgment rows are a curation artifact (which products, which rail, which position) that is not
    derivable from the spec's collection selections alone — the owner supplies the curated file. If
    it is missing, this refuses with a clear message rather than fabricating product rows.
    Returns {validated, manifest_id, manifest_sha256, checks} or raises CheckpointError."""
    import hashlib
    import subprocess
    import execution_package as ep
    import receipt_ingest as ri
    rt = _rt()
    s = rt.require_run(run_id)
    run_mode = (s.get("run") or {}).get("run_mode") or "production"
    campaign_id = ((s.get("identity") or {}).get("campaign_id") or {}).get("value")
    run_ref = (s.get("run") or {}).get("run_id")
    campaign = campaign or campaign_id or run_ref
    campaign_name = campaign_name or (s.get("identity") or {}).get("display_name") or campaign
    build = build or run_ref

    if not judgment or not os.path.exists(judgment):
        raise CheckpointError(
            "judgment_required",
            "the Master CSV (A) needs the curated product-launch judgment rows (which products, in "
            "which rail, at which position) hydrated from the Engine truth export — supply the "
            "curated judgment file. It is not fabricated from the spec's collection selections.")

    arch = spec_architecture(run_id)
    store = _run_store(run_id)
    ingestions = ri.load_ingestions(store)
    if not ingestions:
        raise CheckpointError("no_ingestions",
                              "no accepted receipt ingestions — ingest receipts before building")
    fview = ep.build_fulfillment_view(ingestions, ri.load_material_exceptions(store))

    pkg_dir = _package_dir(run_id)
    os.makedirs(pkg_dir, exist_ok=True)
    # write the architecture the manifest binds (spec projection) for reference
    arch_path = os.path.join(pkg_dir, "architecture.json")
    with open(arch_path, "w", encoding="utf-8") as f:
        json.dump(arch, f, ensure_ascii=False, indent=2)

    # A (Master CSV) via the sanctioned v2 builder (real subprocess; Engine truth hydration). The
    # builder consumes the CURATED JUDGMENT ROWS (not the architecture) + the read-only truth export.
    out_csv = os.path.join(pkg_dir, "A_master.csv")
    builder = os.path.join(rt.HERE, "build_execution_csv.py")
    cmd = [sys.executable, builder, "--campaign", str(campaign), "--campaign-name",
           str(campaign_name), "--build", str(build), "--judgment", judgment, "--out", out_csv]
    if engine:
        cmd += ["--engine", engine]
    if truth_export:
        cmd += ["--truth", truth_export]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    blob = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0 or not os.path.exists(out_csv):
        _record_failed_package(run_id, [{"predicate": "master_csv_builds", "detail": blob[-800:]}])
        raise CheckpointError("master_csv_failed",
                              "Master CSV (A) build failed — the package cannot stage")
    csv_sha = hashlib.sha256(open(out_csv, "rb").read()).hexdigest()

    try:
        staged = ep.stage_components(arch, fview, out_dir=pkg_dir, master_csv_path=out_csv,
                                     master_csv_sha256=csv_sha)
    except ep.PackageError as e:
        _record_failed_package(run_id, [{"predicate": "staging", "detail": str(e)}])
        raise CheckpointError("staging_failed", str(e))

    result = ep.validate_package(arch, fview, pkg_dir, staged, run_mode)
    if not result["ok"]:
        failures = [{"predicate": "validate_package", "detail": p} for p in result["problems"]]
        _record_failed_package(run_id, failures)
        raise CheckpointError("package_validation_failed", " ; ".join(result["problems"]))

    arch_sha = hashlib.sha256(open(arch_path, "rb").read()).hexdigest()
    try:
        emitted = ep.emit_manifest(
            arch, fview, out_dir=pkg_dir, staged=staged, campaign_id=campaign_id,
            run_id=run_ref, run_mode=run_mode, validation_result=result,
            package_revision=package_revision,
            architecture_ref=rt._artifact_rel(run_id, arch_path),
            architecture_sha256=arch_sha, generated_at=rt.now())
    except ep.PackageError as e:
        _record_failed_package(run_id, [{"predicate": "emit_manifest", "detail": str(e)}])
        raise CheckpointError("emit_manifest_failed", str(e))

    manifest = emitted["manifest"]
    manifest_sha = hashlib.sha256(open(emitted["manifest_path"], "rb").read()).hexdigest()
    s = rt.require_run(run_id)
    s.setdefault("artifacts", {})["execution_manifest"] = {
        "path": rt._artifact_rel(run_id, emitted["manifest_path"]), "written_at": rt.now(),
        "sha256": manifest_sha, "status": "current", "superseded_by": None,
        "superseded_at": None, "supersession_reason": None}
    s.setdefault("artifacts", {})["products_csv"] = {
        "path": rt._artifact_rel(run_id, out_csv), "written_at": rt.now(), "sha256": csv_sha,
        "status": "current", "superseded_by": None, "superseded_at": None,
        "supersession_reason": None}
    s.setdefault("validation_attempts", []).append({
        "attempted_at": rt.now(), "result": "passed", "allow_stale_used": False,
        "legacy_replay_used": False, "production": run_mode == "production",
        "package_validated": True, "package_manifest_sha256": manifest_sha,
        "output_sha256": csv_sha, "manifest_id": manifest["manifest_id"],
        "validated_checks": result["checks"], "builder_stdout_tail": blob[-1500:], "failures": []})
    s.setdefault("execution_tracking", {})["seam6_execution_status"] = "validated"
    rt.atomic_write(rt.state_path(run_id), s)
    return {"validated": True, "manifest_id": manifest["manifest_id"],
            "manifest_sha256": manifest_sha, "checks": result["checks"],
            "products_csv_sha256": csv_sha}


def _record_failed_package(run_id, failures):
    rt = _rt()
    s = rt.require_run(run_id)
    s.setdefault("validation_attempts", []).append({
        "attempted_at": rt.now(), "result": "failed", "allow_stale_used": False,
        "legacy_replay_used": False, "production": False, "package_validated": False,
        "package_manifest_sha256": None, "output_sha256": None, "failures": failures})
    rt.atomic_write(rt.state_path(run_id), s)


def approve_package(run_id, by="product_owner", note=None):
    """Record the owner EXECUTION-PACKAGE approval bound to the EXACT current Execution Manifest
    (task §23). Thin wrapper over run.py's manifest-bound approval so the CLI + Console share it. A
    stale/superseded manifest invalidates the approval exactly as the core already enforces."""
    import run as _run
    if by != "product_owner":
        raise CheckpointError("owner_required", "execution-package approval is an owner action")

    class _A:
        pass
    a = _A()
    a.run, a.by, a.note = run_id, by, note
    try:
        _run.cmd_approve_package(a)   # sanctioned single writer of execution_package_approved
    except SystemExit as e:
        raise CheckpointError("approve_package_refused", str(e) or "approval refused")
    return execution_package_view(run_id)


# ═══════════════════════════════════════════════════════════════════
# POST-FULFILLMENT MERCHANDISING (automation closeout) — the missing seam that removes the manual
# truth-export / curated-product-row form. After fulfillment, the Wizard mechanically:
#   1. loads the approved spec + satisfied receipts + the PERSISTED bound Truth Export snapshots;
#   2. independently verifies each request's eligible sellable SET from the bound snapshot;
#   3. invokes the post_fulfillment_merchandising worker with BOUNDED input (eligible sets + product
#      facts + the rail/collection architecture) — the worker performs CAMPAIGN JUDGMENT only;
#   4. VALIDATES the returned selections (only eligible UIDs, right category, floor-eligible, present
#      in the bound snapshot, no duplicate identity, no product-fact mutation) and registers the
#      immutable execution_selection artifact;
#   5. materializes the selections into the existing CSV builder's judgment rows;
#   6. stages A–G, validates, emits F — no owner-supplied product rows or truth export.
# Product truth stays with the Engine (referenced by UID/export_id); the worker never authors it.
# ═══════════════════════════════════════════════════════════════════
def _load_bound_eligibility(run_id):
    """For each SATISFIED ingestion, load the persisted bound Truth Export snapshot and independently
    verify the eligible sellable SET + collect the per-UID product facts. Returns
    {category_id: {request_id, receipt_id, truth_export_id, eligible:set, rows_by_uid, snap_path}}.
    Raises CheckpointError if a bound snapshot is missing (the automatic path requires it)."""
    import receipt_ingest as ri
    import truth_export_v2 as tev2
    rt = _rt()
    store = _run_store(run_id)
    ingestions = [i for i in ri.load_ingestions(store) if i.get("terminal_status") == "satisfied"]
    if not ingestions:
        raise CheckpointError("no_satisfied_receipts",
                              "no satisfied receipts ingested — fulfillment is not complete")
    reqs = {r["category_id"]: r for r in list_requests(run_id)}
    out = {}
    for ing in ingestions:
        cat = ing.get("category_id")
        eid = ing.get("truth_export_id")
        snap_path = bound_snapshot_path(run_id, eid) if eid else None
        if not snap_path:
            raise CheckpointError(
                "bound_snapshot_missing",
                "the bound Truth Export snapshot for %s (export %s) is not in the run store — it is "
                "persisted automatically at ingestion; re-ingest the receipt" % (cat, eid))
        try:
            snap = tev2.load_snapshot(snap_path, expect_export_id=eid,
                                      expect_export_sha256=ing.get("truth_export_sha256"))
        except tev2.TruthExportError as e:
            raise CheckpointError("bound_snapshot_refused", "bound snapshot %s refused: %s" % (eid, e))
        # map each eligible sellable → a representative engine product_uid (the CSV builder's grain).
        rows_by_uid = snap.get("rows_by_uid") or {}
        eligible = set(ing.get("eligible_sellable_set") or [])
        sellable_to_puid = {}
        for puid, rec in rows_by_uid.items():
            sp = rec.get("sellable_product_uid")
            if sp in eligible and sp not in sellable_to_puid and bool(rec.get("floor_eligible")):
                sellable_to_puid[sp] = puid
        out[cat] = {
            "request_id": ing.get("request_id"), "receipt_id": ing.get("receipt_id"),
            "truth_export_id": eid, "eligible": eligible,
            "rows_by_uid": rows_by_uid, "snap_path": snap_path,
            "sellable_to_puid": sellable_to_puid,
            "confirmed_by_sellable": snap.get("confirmed_by_sellable") or {},
        }
    return out


def _sellable_uids_in_snapshot(bound):
    """The set of sellable_product_uids the bound snapshot vouches for (product-fact presence)."""
    uids = set()
    for rec in (bound.get("rows_by_uid") or {}).values():
        if rec.get("sellable_product_uid"):
            uids.add(rec["sellable_product_uid"])
    return uids


def _merchandising_worker_input(run_id):
    """Assemble the BOUNDED worker input (task §3/§10): per satisfied request, the verified eligible
    sellable set + the rail ids that source that collection, plus product facts for context. The
    worker may select/order/bind from the eligible set ONLY; it gets no Engine access."""
    rt = _rt()
    arch = spec_architecture(run_id)
    spec_ref = None
    try:
        import generate_curation_request as gcr
        sr, _, errs = gcr.approved_spec_binding(rt.require_run(run_id))
        spec_ref = sr if not errs else None
    except Exception:
        spec_ref = None
    bound = _load_bound_eligibility(run_id)
    rails_by_cat = {}
    for r in arch.get("rails") or []:
        for src in r.get("source_collection_ids") or []:
            rails_by_cat.setdefault(src, []).append(r.get("rail_id"))
    requests = []
    for cat, b in bound.items():
        # product facts for the eligible uids only (bounded; UID-referenced, not authored)
        facts = {}
        for uid, rec in (b["rows_by_uid"] or {}).items():
            sp = rec.get("sellable_product_uid")
            if sp in b["eligible"]:
                facts[sp] = {"product_name": rec.get("product_name"), "brand": rec.get("brand"),
                             "colorway": rec.get("colorway"), "price_usd": rec.get("price_usd"),
                             "url": rec.get("url")}
        requests.append({
            "category_id": cat, "request_id": b["request_id"], "receipt_id": b["receipt_id"],
            "truth_export_id": b["truth_export_id"],
            "eligible": sorted(b["eligible"]), "rails": rails_by_cat.get(cat, []),
            "product_facts": facts,
        })
    return {"run_id": (rt.require_run(run_id).get("run") or {}).get("run_id"),
            "spec_ref": spec_ref, "requests": requests, "architecture": arch}


EXECUTION_SELECTION_KIND = "execution_selection"


def build_execution_selection(run_id, payload):
    """Validate + canonically hash the worker's execution_selection (task §4/§5). SELECTION AUTHORITY:
    every picked sellable UID must be in the corresponding request's independently-verified eligible
    set AND vouched for by the bound snapshot; wrong-category/arbitrary/non-eligible/duplicate/absent
    are refused; the worker may carry NO product-fact authority (price/availability/name/taxonomy).
    Returns the canonical object (with canonical_hash)."""
    import front_half as fh
    bound = _load_bound_eligibility(run_id)
    for f in ("execution_selection_id", "revision", "selections"):
        if f not in payload:
            raise CheckpointError("invalid_selection", "execution_selection missing %r" % f)
    PRODUCT_FACT_KEYS = {"price", "price_usd", "currency", "stock_status", "availability",
                         "product_name", "brand", "colorway", "url", "taxonomy", "collection_ids",
                         "floor_eligible", "confidence"}
    out_selections = []
    for sel in payload["selections"]:
        cat = sel.get("category_id")
        b = bound.get(cat)
        if not b:
            raise CheckpointError("selection_wrong_category",
                                  "selection references category %r with no satisfied receipt" % cat)
        snapshot_sellables = _sellable_uids_in_snapshot(b)
        seen = set()
        for p in sel.get("picks") or []:
            uid = p.get("sellable_product_uid")
            if uid not in b["eligible"]:
                raise CheckpointError(
                    "selection_not_eligible",
                    "%s: %r is not in the independently-verified eligible sellable set" % (cat, uid))
            if uid not in snapshot_sellables:
                raise CheckpointError("selection_absent_from_truth",
                                      "%s: %r is not vouched for by the bound Truth Export" % (cat, uid))
            if uid in seen:
                raise CheckpointError("selection_duplicate",
                                      "%s: duplicate sellable identity %r cannot inflate selection"
                                      % (cat, uid))
            seen.add(uid)
            leaked = PRODUCT_FACT_KEYS & set(p.keys())
            if leaked:
                raise CheckpointError(
                    "selection_authors_product_truth",
                    "%s: a merchandising pick may not carry product facts %s — product truth is the "
                    "Engine's, referenced by UID (task §5)" % (cat, sorted(leaked)))
        out_selections.append(sel)
    obj = dict(payload)
    obj["object_kind"] = EXECUTION_SELECTION_KIND
    obj["selections"] = out_selections
    obj.pop("canonical_hash", None)
    obj["canonical_hash"] = fh.canonical_hash(obj)
    return obj


def _selection_to_judgment_rows(run_id, selection):
    """Materialize the validated execution_selection into the CSV builder's judgment rows (campaign
    fields ONLY: product_uid resolved from the bound snapshot for the selected sellable identity,
    collection_name, is_rail_item, rail_name, rail_position, collection_position, annotation).
    Product FACTS are hydrated by the builder from truth — never authored here."""
    bound = _load_bound_eligibility(run_id)
    rows = []
    for sel in selection.get("selections") or []:
        coll = sel.get("category_id")
        s2p = (bound.get(coll) or {}).get("sellable_to_puid") or {}
        for p in sel.get("picks") or []:
            sp = p.get("sellable_product_uid")
            puid = s2p.get(sp)
            if not puid:
                raise CheckpointError("selection_unresolvable",
                                      "%s: no floor-eligible product_uid for sellable %r" % (coll, sp))
            rows.append({
                "product_uid": puid,
                "collection_name": coll,
                "is_rail_item": bool(p.get("is_rail_item")),
                "rail_name": (p.get("rail_id") or "") if p.get("is_rail_item") else None,
                "rail_position": p.get("rail_position") if p.get("is_rail_item") else None,
                "collection_position": p.get("collection_position"),
                "annotation": p.get("annotation") or "",
            })
    return rows


def _register_execution_selection(run_id, obj):
    """Write the immutable execution_selection revision + spine + artifact (task §4)."""
    import hashlib
    rt = _rt()
    s = rt.require_run(run_id)
    rev = obj["revision"]
    rd = rt.run_dir(run_id)
    path = os.path.join(rd, "execution_selection.%s.yaml" % rev)
    if os.path.exists(path):
        existing = yaml.safe_load(open(path, encoding="utf-8")) or {}
        if existing.get("canonical_hash") != obj["canonical_hash"]:
            # mint the next revision label rather than overwrite (immutable)
            labels = [fn[len("execution_selection."):-len(".yaml")]
                      for fn in os.listdir(rd)
                      if fn.startswith("execution_selection.") and fn.endswith(".yaml")]
            rev = _next_revision_label(labels)
            obj = dict(obj); obj["revision"] = rev
            path = os.path.join(rd, "execution_selection.%s.yaml" % rev)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(obj, f, sort_keys=False, default_flow_style=False, allow_unicode=True)
    sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
    s.setdefault("artifacts", {})["execution_selection"] = {
        "path": rt._artifact_rel(run_id, path), "written_at": rt.now(), "sha256": sha,
        "status": "current", "superseded_by": None, "superseded_at": None,
        "supersession_reason": None}
    s.setdefault("structured_objects", {})["execution_selection"] = {
        "object_kind": "execution_selection", "object_id": obj["execution_selection_id"],
        "revision": rev, "canonical_hash": obj["canonical_hash"], "artifact_key": "execution_selection"}
    rt.atomic_write(rt.state_path(run_id), s)
    return {"object_id": obj["execution_selection_id"], "revision": rev, "path": path,
            "canonical_hash": obj["canonical_hash"]}


def generate_execution_package(run_id, worker=None, engine=None, revision_instruction=None):
    """THE mechanical post-fulfillment path (automation closeout §8): from the approved spec +
    satisfied receipts + persisted bound snapshots, run the merchandising worker, validate + register
    the execution_selection, materialize the curated judgment rows, and build → validate → emit the F
    Manifest. NO owner-supplied truth export or product rows. Returns the execution-package result.

    A worker failure (or an invalid selection) records WORK FAILED, registers no package, and leaves
    the run coherent + retryable. revision_instruction scopes a re-merchandising request (task §9)."""
    import worker as wk
    rt = _rt()
    s = rt.require_run(run_id)
    if current_checkpoint(s) is not None:
        raise CheckpointError("front_half_incomplete", "the campaign_spec is not yet approved")
    if not list_requests(run_id):
        raise CheckpointError("no_requests", "generate the Request set first")
    bh = back_half_status(run_id, s)
    if bh["blocked"]:
        raise CheckpointError("blocked_by_material_exception",
                              "an open Material Exception blocks assembly — resolve fulfillment first")

    run_mode = (s.get("run") or {}).get("run_mode") or "production"
    if worker is None:
        try:
            worker = wk.get_worker(run_mode=run_mode, allow_fake=(run_mode == "diagnostic"))
        except wk.WorkerError as e:
            _record_worker_run(run_id, "post_fulfillment_merchandising", "unavailable",
                               detail=e.message, error=e.code)
            raise CheckpointError("worker_unavailable", e.message)

    ctx = _merchandising_worker_input(run_id)
    if revision_instruction:
        ctx["revision_instruction"] = revision_instruction
    _record_worker_run(run_id, "post_fulfillment_merchandising", "working",
                       detail="merchandising %d request(s)" % len(ctx["requests"]))
    try:
        result = worker.run({"work_type": "post_fulfillment_merchandising", "context": ctx,
                             "output_contract": wk.WORK_TYPES["post_fulfillment_merchandising"]})
    except wk.WorkerError as e:
        _record_worker_run(run_id, "post_fulfillment_merchandising", "failed",
                           detail=e.message, error=e.code)
        raise CheckpointError("merchandising_failed", "merchandising worker failed: %s" % e.message)

    objs = [o for o in result["objects"] if o.get("kind") == "execution_selection"]
    if not objs:
        _record_worker_run(run_id, "post_fulfillment_merchandising", "failed",
                           detail="no execution_selection returned")
        raise CheckpointError("no_selection", "worker returned no execution_selection")
    try:
        obj = build_execution_selection(run_id, objs[0]["payload"])   # SELECTION AUTHORITY gate
    except CheckpointError as e:
        _record_worker_run(run_id, "post_fulfillment_merchandising", "failed",
                           detail=e.message, error=e.code)
        raise
    reg = _register_execution_selection(run_id, obj)

    # materialize the curated judgment rows + build the package (no owner inputs)
    try:
        rows = _selection_to_judgment_rows(run_id, obj)
    except CheckpointError as e:
        _record_worker_run(run_id, "post_fulfillment_merchandising", "failed", detail=e.message)
        raise
    pkg_dir = _package_dir(run_id)
    os.makedirs(pkg_dir, exist_ok=True)
    judgment_path = os.path.join(pkg_dir, "curated_judgment.json")
    with open(judgment_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    # the bound Truth Export snapshot(s) are already persisted; the builder needs the engine dir OR a
    # truth export. We resolve the single persisted snapshot as the truth input (satisfied set shares
    # the engine's export in the common single-engine case). Pass the persisted snapshot for A.
    truth = _resolve_truth_for_build(run_id)
    _record_worker_run(run_id, "post_fulfillment_merchandising", "done",
                       detail="selection %s registered; building package" % reg["revision"])
    return build_and_validate_package(run_id, judgment=judgment_path, truth_export=truth,
                                      engine=engine)


def _resolve_truth_for_build(run_id):
    """The persisted bound Truth Export snapshot to hydrate the Master CSV (task §2) — chosen
    automatically, never owner-supplied. When multiple exports are bound, the builder validates each
    product against the passed snapshot; the common case is one engine export across the satisfied
    set."""
    bound = _load_bound_eligibility(run_id)
    paths = {b["snap_path"] for b in bound.values() if b.get("snap_path")}
    return sorted(paths)[0] if paths else None
