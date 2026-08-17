#!/usr/bin/env python3
"""worker.py — the Wizard-owned WORKER BOUNDARY (owner-flow closeout).

The owner operates the campaign entirely from the Console; the research/synthesis worker runs BEHIND
the Wizard. This module is that boundary. The Wizard decides WHAT work is needed and supplies the
exact structured input + the allowed output contract; the worker returns a structured artifact ONLY;
the Wizard validates + registers it. The worker never touches state, never approves, never decides
campaign judgment authority — it only produces a candidate object the Wizard then validates.

Design (kept lean — no queue/DB/redis/celery/cloud, task §3):
  • WorkerAdapter is the interface. SubprocessWorker is the default real adapter: it invokes a
    CONFIGURED local command (SHOPYA_WIZARD_WORKER_CMD) with a structured work request as JSON on
    stdin and reads a structured result as JSON on stdout. That command may wrap the current Claude
    CLI / agent mechanism; no business authority is hard-coded into it and no credentials live here.
  • FakeWorker is a deterministic adapter used by automated tests (and as a safe default when no
    worker command is configured, so the system is inspectable without a live agent).

Work types (one per checkpoint transition):
  research        → produces research_ledger + campaign_directions from the approved brief
  premise         → produces the campaign_spec premise + vertical_strategies from the selected direction
  architecture    → fills collection_selections + rails + content_program on the spec
  finalize        → fills naming_voice + default_composition + seam_intent on the spec

Each work type has a WorkSpec: the object kind(s) it must return and the approved context it is given.
The worker returns {"objects": [{"kind": ..., "payload": {...}}, ...]}; the Wizard builds+registers
each in order (front_half validators are the gate — an invalid payload is REFUSED, never registered).
"""
import json
import os
import shlex
import subprocess
import sys


class WorkerError(Exception):
    """A worker failed (bad output, nonzero exit, timeout, contract violation). The orchestrator
    turns this into a coherent, retryable WORK FAILED — no partial artifact is ever registered."""

    def __init__(self, code, message, detail=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail


# ---------------------------------------------------------------------------
# work-type contracts — what the worker must return, and the allowed output shape.
# ---------------------------------------------------------------------------
WORK_TYPES = {
    "research": {
        "produces": ["research_ledger", "campaign_directions"],
        "for_checkpoint": "direction",
        "desc": "run research from the approved brief; produce the ledger + 2–4 directions",
    },
    "spec": {
        "produces": ["campaign_spec"],
        "for_checkpoint": "premise_verticals",
        "desc": "develop the complete campaign_spec (premise + verticals + architecture + naming/"
                "default/seam) from the selected direction; reviewed section-by-section downstream",
    },
    "post_fulfillment_merchandising": {
        "produces": ["execution_selection"],
        "for_checkpoint": None,   # post-fulfillment, not a front-half checkpoint
        "research": False,
        "desc": "materialize the fulfilled eligible products into the campaign's rail/collection "
                "structure — Wizard merchandising JUDGMENT over verified Engine truth (select/order/"
                "pin/bind from the bounded eligible sellable set ONLY; never author product facts)",
    },
}

# the work type that PRODUCES each checkpoint's authoritative object, when that object is not yet
# present. A campaign_spec revision is authored WHOLE (front_half requires all 8 sections in every
# revision), so a single "spec" work step produces the complete spec once a direction is selected;
# the Architecture and Build-This checkpoints then review/approve sections of that same spec (and the
# owner may request targeted revisions). Kickoff's brief is authored by the owner at intake, so
# kickoff has no producing worker.
CHECKPOINT_PRODUCER = {
    "direction": "research",          # research produces research_ledger + campaign_directions
    "premise_verticals": "spec",      # produces the complete campaign_spec (all 8 sections)
    # architecture + build_this reuse that spec — no new producing work unless the owner revises.
}


# ---------------------------------------------------------------------------
# adapters
# ---------------------------------------------------------------------------
class WorkerAdapter:
    """Interface. run(work_request) -> {"objects": [{"kind", "payload"}, ...]}."""

    def run(self, work_request):  # pragma: no cover - interface
        raise NotImplementedError


class SubprocessWorker(WorkerAdapter):
    """Invoke a configured local command with the work request as JSON on stdin; parse JSON stdout.

    The command is read from SHOPYA_WIZARD_WORKER_CMD (or passed explicitly). It is the ONE place the
    real cognitive worker (e.g. a Claude-CLI wrapper) is plugged in. The Wizard supplies structured
    input + the output contract; the command returns a structured artifact only.
    """

    def __init__(self, command=None, timeout=900):
        self.command = command or os.environ.get("SHOPYA_WIZARD_WORKER_CMD")
        self.timeout = timeout

    def available(self):
        return bool(self.command)

    def run(self, work_request):
        if not self.command:
            raise WorkerError("no_worker_configured",
                              "no worker command configured (set SHOPYA_WIZARD_WORKER_CMD)")
        argv = shlex.split(self.command)
        try:
            proc = subprocess.run(argv, input=json.dumps(work_request), capture_output=True,
                                  text=True, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            raise WorkerError("worker_timeout",
                              "worker did not return within %ds" % self.timeout)
        except (OSError, ValueError) as e:
            raise WorkerError("worker_launch_failed", "could not launch worker: %s" % e)
        if proc.returncode != 0:
            raise WorkerError("worker_nonzero_exit",
                              "worker exited %d" % proc.returncode,
                              detail=(proc.stderr or "")[-2000:])
        out = (proc.stdout or "").strip()
        if not out:
            raise WorkerError("worker_empty_output", "worker produced no output",
                              detail=(proc.stderr or "")[-2000:])
        try:
            result = json.loads(out)
        except json.JSONDecodeError as e:
            raise WorkerError("worker_bad_json", "worker output was not valid JSON: %s" % e,
                              detail=out[-2000:])
        return _validate_result_shape(result)


class FakeWorker(WorkerAdapter):
    """Deterministic worker for AUTOMATED TESTS and explicit diagnostic runs ONLY — never a silent
    production fallback (task §6/§11). Builds minimal valid payloads for the requested work type from
    self-contained builders, deriving ids/refs from the work request's approved context so the objects
    bind correctly to the run's real upstream objects.

    A FakeWorker configured with fail_on=<work_type> raises WorkerError to exercise failure/retry.
    """

    def __init__(self, fail_on=None, produce_invalid=False):
        self.fail_on = fail_on
        self.produce_invalid = produce_invalid

    def run(self, work_request):
        wt = work_request["work_type"]
        if self.fail_on == wt:
            raise WorkerError("fake_failure", "fake worker was told to fail on %s" % wt)
        ctx = work_request.get("context") or {}
        objs = _fake_objects(wt, ctx, invalid=self.produce_invalid)
        return _validate_result_shape({"objects": objs})


def _validate_result_shape(result):
    if not isinstance(result, dict) or "objects" not in result \
            or not isinstance(result["objects"], list) or not result["objects"]:
        raise WorkerError("worker_contract_violation",
                          "worker result must be {'objects': [ {kind, payload}, ... ]} with >=1 object")
    for o in result["objects"]:
        if not isinstance(o, dict) or o.get("kind") not in \
                ("research_ledger", "campaign_directions", "campaign_spec", "execution_selection") \
                or not isinstance(o.get("payload"), dict):
            raise WorkerError("worker_contract_violation",
                              "each worker object must be {kind, payload:{...}}; got %r" % o)
    return result


# ---------------------------------------------------------------------------
# deterministic fake payloads (mirror tests/front_half_fixture, but self-contained so the worker
# module has no test dependency). Derive refs from the approved context.
# ---------------------------------------------------------------------------
def _sig(sid, fam="cultural"):
    return {"signal_id": sid, "family": fam, "claim": "c-" + sid, "source": "https://x/" + sid,
            "source_type": "editorial", "captured_at": "2026-08-10",
            "market_time_relevance": "current", "confidence": "medium",
            "evidence_strength": "moderate", "supports": [], "contradicts": [],
            "limitations": ["single source"], "provenance": "system_inferred"}


def _dir(did):
    return {"direction_id": did, "title": "t-" + did, "evidence_refs": ["s1", "s2"],
            "shopper_tension": "x", "why_now": "x", "shopya_role": "x", "desired_behavior": "x",
            "campaign_opportunity": "x", "vertical_implications_summary": "x",
            "risks_counterevidence": "x", "confidence": "medium"}


def _spec_sections(depth=50):
    return {
        "premise": {"campaign_name": "Worked", "dek": "d", "central_tension": "x",
                    "point_of_view": "x", "why_now": "x", "shopya_role": "x",
                    "desired_behavior": "x", "exclusions": [], "voice_summary": "restrained",
                    "evidence_refs": ["d1"]},
        "vertical_strategies": {"verticals": [
            {"vertical_id": "fashion", "conviction_role": "lead", "interpretation": "x",
             "shopper_job": "x", "why_it_belongs": "x", "distinct_mechanism": "x",
             "evidence_refs": ["s1"], "risks_limits": "x", "content_role": "x",
             "collection_role": "lead", "default_role": "hero"},
            {"vertical_id": "tech", "conviction_role": "absent", "interpretation": "n/a",
             "shopper_job": "n/a", "why_it_belongs": "n/a", "distinct_mechanism": "n/a",
             "evidence_refs": [], "risks_limits": "n/a", "content_role": "none",
             "collection_role": "none", "default_role": "none"}]},
        "collection_selections": {"selections": [
            {"category_id": "w.coats", "display_name": "Coats", "vertical": "fashion",
             "campaign_role": "hero", "campaign_fit_rationale": "core",
             "distinct_shopper_product_job": "outerwear",
             "durable_infrastructure_consideration": "reusable", "evidence_refs": ["s1"],
             "requested_depth": depth, "charter_rule_ref": "render_003",
             "fulfillment_state": "not_yet_requested"},
            {"category_id": "w.knitwear", "display_name": "Knitwear", "vertical": "fashion",
             "campaign_role": "support", "campaign_fit_rationale": "layering",
             "distinct_shopper_product_job": "mid layers",
             "durable_infrastructure_consideration": "reusable", "evidence_refs": ["s2"],
             "requested_depth": depth, "charter_rule_ref": "render_003",
             "fulfillment_state": "not_yet_requested"}]},
        "rails": {"rails": [
            {"rail_id": "r_coats", "rail_type": "base_1c", "title": "The Coats", "hook_dek": "x",
             "source_collection_ids": ["w.coats"], "vertical_surface": "fashion",
             "editorial_job": "anchor", "placement_role": "top",
             "renderer_capability": "supported", "fallback_ref": None, "status": "intended"},
            {"rail_id": "r_layers", "rail_type": "story_xc", "title": "Layer Up", "hook_dek": "x",
             "source_collection_ids": ["w.coats", "w.knitwear"], "vertical_surface": "fashion",
             "editorial_job": "a layering story", "placement_role": "mid",
             "renderer_capability": "xc_rails_unsupported", "fallback_ref": None,
             "status": "intended"}]},
        "content_program": {"content": [
            {"content_id": "c1", "target_query": "how to layer", "evidence_refs": ["s1"],
             "search_intent": "informational", "seo_title": "How to Layer",
             "card_headline": "Master the in-between", "premise": "x", "outline_brief": "x",
             "linked_collection_ids": ["w.coats"], "linked_rail_ids": ["r_coats"],
             "placement": "explore", "priority": 1, "status": "to_produce"}]},
        "naming_voice": {"campaign_name": "Worked", "dek": "d",
                         "voice_principles": ["concrete"], "positive_examples": ["x"],
                         "negative_patterns": ["generic abstraction"],
                         "collection_naming_constraints": "x", "rail_voice_constraints": "x",
                         "content_voice_constraints": "x"},
        "default_composition": {"ordered_slots": [
            {"slot_id": "s1", "object_type": "base_rail", "object_id": "r_coats",
             "rationale": "anchor", "fallback_ref": None},
            {"slot_id": "s2", "object_type": "content", "object_id": "c1", "rationale": "teach",
             "fallback_ref": None}]},
        "seam_intent": {"collection_rail_relationships": {"w.coats": ["r_coats"]},
                        "rail_content_relationships": {"r_coats": ["c1"]},
                        "default_bindings": ["s1", "s2"],
                        "renderer_capability_notes": "xc unsupported",
                        "fallback_intent": "base only", "production_human_notes": "coats first"},
    }


def _fake_merchandising(ctx, invalid=False):
    """Deterministic post-fulfillment merchandising: materialize eligible sellables into the rails/
    collections the architecture describes. Selects ONLY from each request's bounded eligible set."""
    requests = ctx.get("requests") or []   # [{category_id, request_id, receipt_id, truth_export_id,
                                           #   eligible: [sellable_uid...], rails: [rail_id...]}]
    selections = []
    for req in requests:
        elig = list(req.get("eligible") or [])
        rails = req.get("rails") or []
        picks = []
        for i, uid in enumerate(elig, 1):
            picks.append({
                "sellable_product_uid": uid,
                "collection_position": i,
                "is_rail_item": i <= 12,
                "rail_id": (rails[0] if rails else None) if i <= 12 else None,
                "rail_position": i if i <= 12 else None,
                "annotation": "auto-merchandised",
            })
        if invalid and picks:
            picks[0]["sellable_product_uid"] = "sp:not:eligible"   # not in the eligible set
        selections.append({
            "category_id": req.get("category_id"),
            "request_id": req.get("request_id"),
            "receipt_id": req.get("receipt_id"),
            "truth_export_id": req.get("truth_export_id"),
            "picks": picks,
        })
    payload = {
        "execution_selection_id": "es_" + (ctx.get("run_id") or "fx"),
        "revision": "r001",
        "spec_ref": ctx.get("spec_ref"),
        "selections": selections,
        "worker_provenance": {"engine": "fake", "work_type": "post_fulfillment_merchandising"},
    }
    return [{"kind": "execution_selection", "payload": payload}]


def _fake_objects(work_type, ctx, invalid=False):
    if work_type == "post_fulfillment_merchandising":
        return _fake_merchandising(ctx, invalid=invalid)
    if work_type == "research":
        brief_id = ctx.get("brief_id") or "rb_fx"
        ledger = {"ledger_id": "rl_" + (ctx.get("run_id") or "fx"), "revision": "r001",
                  "brief_ref": brief_id,
                  "signals": [_sig("s1", "cultural"), _sig("s2", "commercial"),
                              _sig("s3", "seasonal_temporal")]}
        directions = {"directions_id": "cd_" + (ctx.get("run_id") or "fx"), "revision": "r001",
                      "ledger_ref": ledger["ledger_id"],
                      "directions": [_dir("d1"), _dir("d2"), _dir("d3")],
                      "recommended_direction_id": "d1"}
        if invalid:
            directions["directions"] = [_dir("d1")]  # <2 directions -> front_half refuses
        return [{"kind": "research_ledger", "payload": ledger},
                {"kind": "campaign_directions", "payload": directions}]

    # the "spec" work type: build a full spec revision (front_half requires all 8 sections present;
    # the worker supplies a coherent whole, reviewed section-by-section at the downstream checkpoints).
    spec = {"campaign_spec_id": "cs_" + (ctx.get("run_id") or "fx"), "revision": "r001",
            "parent_revision": None,
            "selected_direction_ref": ctx.get("selected_direction_ref")
            or {"directions_id": "cd_fx", "revision": "r001", "direction_id": "d1"},
            "sections": _spec_sections()}
    if invalid:
        # break CB-1: a selection missing its distinct-job -> front_half refuses
        spec["sections"]["collection_selections"]["selections"][0].pop("distinct_shopper_product_job")
    return [{"kind": "campaign_spec", "payload": spec}]


# ---------------------------------------------------------------------------
# worker discovery + FAIL-CLOSED selection (real Claude worker closeout §6/§7/§11)
# ---------------------------------------------------------------------------
import shutil as _shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CLAUDE_WORKER = os.path.join(ROOT, "console", "workers", "claude_worker.py")


def claude_cli_available():
    """Is the local Claude CLI on PATH (or SHOPYA_CLAUDE_BIN set)?"""
    binname = os.environ.get("SHOPYA_CLAUDE_BIN", "claude")
    return _shutil.which(binname) is not None or (os.path.isabs(binname) and os.path.exists(binname))


def default_worker_command():
    """The auto-detected real worker command, or None. Prefers an explicit SHOPYA_WIZARD_WORKER_CMD;
    else the bundled Claude worker when the claude CLI is available."""
    cmd = os.environ.get("SHOPYA_WIZARD_WORKER_CMD")
    if cmd:
        return cmd
    if claude_cli_available() and os.path.exists(CLAUDE_WORKER):
        return "%s %s" % (sys.executable, CLAUDE_WORKER)
    return None


def worker_readiness():
    """Structured readiness for the Console indicator (task §7/§8). Distinguishes an explicitly
    configured command from the auto-detected bundled Claude worker from unavailable."""
    if os.environ.get("SHOPYA_WIZARD_WORKER_CMD"):
        return {"ready": True, "kind": "configured",
                "label": "Configured worker (SHOPYA_WIZARD_WORKER_CMD)"}
    if claude_cli_available() and os.path.exists(CLAUDE_WORKER):
        return {"ready": True, "kind": "claude_cli", "label": "Claude CLI"}
    return {"ready": False, "kind": "unavailable",
            "label": "Unavailable — setup required (install/authenticate the Claude CLI, or set "
                     "SHOPYA_WIZARD_WORKER_CMD)"}


def get_worker(command=None, run_mode="production", allow_fake=False, force_fake=False):
    """Select the worker, FAIL-CLOSED for production (task §6).

    Precedence:
    • force_fake → the deterministic FakeWorker (tests only).
    • an EXPLICITLY configured real worker ALWAYS wins (explicit `command`, else
      SHOPYA_WIZARD_WORKER_CMD, else the auto-detected bundled Claude worker) — even for a diagnostic
      run, so a diagnostic run still exercises the real worker when one is configured.
    • only when NO real worker is available: `allow_fake` (a diagnostic run) → the FakeWorker;
      PRODUCTION → raise WORKER_UNAVAILABLE. There is NO silent fake-worker fallback in production;
      the fake is never selected implicitly when a real worker exists.
    """
    if force_fake:
        return FakeWorker()
    cmd = command or default_worker_command()
    if cmd:
        return SubprocessWorker(command=cmd)
    if allow_fake:
        return FakeWorker()
    raise WorkerError(
        "worker_unavailable",
        "no real cognitive worker is available. Install + authenticate the Claude CLI, or set "
        "SHOPYA_WIZARD_WORKER_CMD. (The deterministic fake worker is for tests / explicit diagnostic "
        "runs only and is never a silent production fallback.)")
