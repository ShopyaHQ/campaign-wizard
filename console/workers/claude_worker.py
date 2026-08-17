#!/usr/bin/env python3
"""claude_worker.py — the REAL Claude cognitive worker adapter for the Campaign Wizard.

This is the production worker behind the Wizard. It is invoked by the Wizard's WorkerAdapter seam
(SubprocessWorker → this script) with a structured work-request JSON on stdin, and it writes ONLY a
valid WorkerAdapter envelope on stdout:

    {"objects": [ {"kind": "...", "payload": {...}}, ... ]}

All diagnostics go to STDERR (never stdout). The Wizard remains responsible for validation, hashing,
immutable registration and state advancement — Claude is a worker only.

INVOCATION (proven against the local claude CLI v2.1.195; see the reference memory):
  claude -p --output-format stream-json --verbose --permission-mode bypassPermissions
         --add-dir <neutral-context-dir> [--model ...]
  • stream-json + --verbose lets us SEE tool_use events (to prove real research actually ran —
    the usage.server_tool_use counters are unreliable and stay 0 even when WebFetch fires).
  • Web tools (WebSearch/WebFetch) are DEFERRED in the default set; the model self-loads them via
    ToolSearch when a genuine current-data task needs them. We do NOT hard-restrict tools to a list
    that excludes them (that would block research); we run in a NEUTRAL cwd with only the neutral
    context dir added, so repo CLAUDE.md / Almost Fall material is never in scope.

CONTAMINATION PROTECTION (task §5, AF-008):
  • The subprocess cwd is a fresh temp dir, NOT the repo — so CLAUDE.md auto-discovery + the repo
    tree (golden benchmark, historical runs, review books) are out of scope.
  • Only the campaign-neutral context (from the Wizard work-request) is passed, via the prompt.
  • --add-dir points ONLY at that temp neutral dir. No unrestricted repo Read during generation.

STRICT OUTPUT (task §9):
  • The prompt demands a single fenced ```json block containing exactly the required envelope.
  • We extract the LAST JSON object/array from the model's final result; prose around it is tolerated
    only insofar as a single valid JSON block is present — anything else is refused (nonzero exit).
"""
import json
import os
import re
import subprocess
import sys
import tempfile

# work-type → (produced kinds, whether it needs live external research, phase label)
WORK_PROFILE = {
    "research": {"produces": ["research_ledger", "campaign_directions"], "research": True,
                 "phase": "Researching"},
    "spec": {"produces": ["campaign_spec"], "research": False,
             "phase": "Developing the campaign spec"},
    "post_fulfillment_merchandising": {"produces": ["execution_selection"], "research": False,
                                       "phase": "Merchandising the fulfilled products"},
}


def log(msg):
    sys.stderr.write("[claude_worker] %s\n" % msg)
    sys.stderr.flush()


# ---------------------------------------------------------------------------
# prompt construction — bounded, neutral, strict-output.
# ---------------------------------------------------------------------------
def _object_contract(kind):
    """A compact shape reminder so the model returns registrable payloads (the Wizard re-validates)."""
    if kind == "research_ledger":
        return ("research_ledger payload: {ledger_id, revision:'r001', brief_ref, signals:[{signal_id, "
                "family in [cultural,behavioral,commercial,competitive,seasonal_temporal,platform_surface], "
                "claim, source(real url), source_type, captured_at(ISO), market_time_relevance, "
                "confidence in [low,medium,high], evidence_strength in [weak,moderate,strong], "
                "supports:[], contradicts:[], limitations:[...], provenance}]}. >=3 signals, each with a "
                "REAL current source URL you actually retrieved. source_type MUST NOT be 'golden_benchmark'.")
    if kind == "campaign_directions":
        return ("campaign_directions payload: {directions_id, revision:'r001', ledger_ref, "
                "recommended_direction_id, directions:[{direction_id, title, evidence_refs:[signal_ids from "
                "the ledger], shopper_tension, why_now, shopya_role, desired_behavior, campaign_opportunity, "
                "vertical_implications_summary, risks_counterevidence, confidence}]}. 2-4 genuinely distinct "
                "directions; every evidence_ref MUST be a signal_id present in your ledger.")
    if kind == "campaign_spec":
        return ("campaign_spec payload MUST match this EXACT nested shape (every section is an OBJECT "
                "with the named list inside — NEVER a bare list):\n" + _CAMPAIGN_SPEC_SKELETON + "\n"
                "Rules: use ONLY category_ids from the provided campaign-neutral taxonomy; "
                "requested_depth>=50; fulfillment_state MUST be 'not_yet_requested'; base_1c rails "
                "reference EXACTLY ONE selected collection; story_xc reference >=2 collections and carry "
                "a non-empty editorial_job; every content piece has DISTINCT seo_title AND card_headline; "
                "default_composition.ordered_slots reference only rails/content defined above; provide "
                ">=2 collection_selections and >=1 content piece.")
    if kind == "execution_selection":
        return ("execution_selection payload: {execution_selection_id:'es_<slug>', revision:'r001', "
                "selections:[{category_id, request_id, receipt_id, truth_export_id, picks:[{"
                "sellable_product_uid (MUST be from this request's eligible list below), "
                "collection_position:int, is_rail_item:bool, rail_id (a rail that sources this "
                "collection, when is_rail_item), rail_position:int, annotation}]}]}. You are doing "
                "MERCHANDISING JUDGMENT: choose/order/pin actual fulfilled products. Rules that MUST "
                "hold or the package is rejected: (1) include EVERY sellable_product_uid from the "
                "eligible list as a pick (the whole collection ships — the collection-depth floor "
                "needs all eligible members; do NOT drop any); (2) collection_position is a unique "
                "1..N over ALL picks in the collection, contiguous; (3) mark EXACTLY 12 picks as "
                "is_rail_item=true with rail_position 1..12 (the rail is the 12 hero pins) and the "
                "REST is_rail_item=false with no rail_position; (4) pick ONLY from the eligible list; "
                "(5) NEVER include price/availability/name/url or any product fact — product truth is "
                "the Engine's, referenced by UID only. annotation is your short merchandising note.")
    return ""


_CAMPAIGN_SPEC_SKELETON = """{
  "campaign_spec_id": "cs_<slug>", "revision": "r001", "parent_revision": null,
  "selected_direction_ref": {"directions_id":"...","revision":"r001","direction_id":"..."},
  "sections": {
    "premise": {"campaign_name":"...","dek":"...","central_tension":"...","point_of_view":"...",
                "why_now":"...","shopya_role":"...","desired_behavior":"...","exclusions":[],
                "voice_summary":"...","evidence_refs":["<direction_id or signal_id>"]},
    "vertical_strategies": {"verticals":[{"vertical_id":"home_interior","conviction_role":"lead",
        "interpretation":"...","shopper_job":"...","why_it_belongs":"...","distinct_mechanism":"...",
        "evidence_refs":[],"risks_limits":"...","content_role":"...","collection_role":"lead",
        "default_role":"hero"}]},
    "collection_selections": {"selections":[{"category_id":"<from neutral taxonomy>","display_name":"...",
        "vertical":"home_interior","campaign_role":"hero","campaign_fit_rationale":"...",
        "distinct_shopper_product_job":"...","durable_infrastructure_consideration":"...",
        "evidence_refs":[],"requested_depth":50,"charter_rule_ref":"render_003",
        "fulfillment_state":"not_yet_requested"}]},
    "rails": {"rails":[{"rail_id":"r_1","rail_type":"base_1c","title":"...","hook_dek":"...",
        "source_collection_ids":["<one selected category_id>"],"vertical_surface":"home_interior",
        "editorial_job":"...","placement_role":"top","renderer_capability":"supported",
        "fallback_ref":null,"status":"intended"}]},
    "content_program": {"content":[{"content_id":"c1","target_query":"...","evidence_refs":[],
        "search_intent":"informational","seo_title":"...","card_headline":"...","premise":"...",
        "outline_brief":"...","linked_collection_ids":["<category_id>"],"linked_rail_ids":["r_1"],
        "placement":"explore","priority":1,"status":"to_produce"}]},
    "naming_voice": {"campaign_name":"...","dek":"...","voice_principles":["..."],
        "positive_examples":["..."],"negative_patterns":["generic abstraction"],
        "collection_naming_constraints":"...","rail_voice_constraints":"...",
        "content_voice_constraints":"..."},
    "default_composition": {"ordered_slots":[
        {"slot_id":"s1","object_type":"base_rail","object_id":"r_1","rationale":"...","fallback_ref":null},
        {"slot_id":"s2","object_type":"content","object_id":"c1","rationale":"...","fallback_ref":null}]},
    "seam_intent": {"collection_rail_relationships":{"<category_id>":["r_1"]},
        "rail_content_relationships":{"r_1":["c1"]},"default_bindings":["s1","s2"],
        "renderer_capability_notes":"...","fallback_intent":"...","production_human_notes":"..."}
  }
}"""


def build_prompt(work_request):
    wt = work_request.get("work_type")
    profile = WORK_PROFILE.get(wt)
    if not profile:
        raise ValueError("unknown work_type %r" % wt)
    ctx = work_request.get("context") or {}
    produces = profile["produces"]

    lines = []
    lines.append("You are a merchandising RESEARCH/SYNTHESIS worker for the Shopya Campaign Wizard.")
    lines.append("You are a worker behind a system: your ONLY output is a single machine-readable "
                 "JSON result. No conversation, no explanation outside the JSON block.")
    lines.append("")
    lines.append("TASK: %s" % profile.get("phase"))
    if profile["research"]:
        lines.append("You MUST ground each evidence signal in REAL, CURRENT external sources you "
                     "actually retrieve from the web (use your web research tools). Do NOT invent "
                     "URLs or rely on possibly-stale training memory for market claims. Each signal "
                     "must carry a real source URL, a captured_at date, confidence, and limitations.")
    else:
        lines.append("Develop the campaign judgment from the APPROVED CONTEXT below only.")
    lines.append("")
    lines.append("APPROVED / NEUTRAL CONTEXT (this is all you may use as campaign input):")
    lines.append(json.dumps(_neutral_context(ctx), indent=2, ensure_ascii=False))
    lines.append("")
    lines.append("Do NOT look for, read, or use any prior 'Almost Fall' campaign material, golden "
                 "benchmark, historical runs or review books. Generate independently from the "
                 "context above.")
    lines.append("")
    lines.append("REQUIRED OUTPUT — a SINGLE ```json fenced block, nothing after it, matching EXACTLY:")
    lines.append("```json")
    lines.append('{"objects": [')
    for i, kind in enumerate(produces):
        comma = "," if i < len(produces) - 1 else ""
        lines.append('  {"kind": "%s", "payload": { ... }}%s' % (kind, comma))
    lines.append(']}')
    lines.append("```")
    lines.append("")
    for kind in produces:
        lines.append("- " + _object_contract(kind))
    return "\n".join(lines)


def _neutral_context(ctx):
    """Pass ONLY campaign-neutral fields to the worker (contamination boundary). Strips anything that
    could carry historical campaign identity; keeps the approved brief content, selected direction and
    the campaign-neutral taxonomy the Wizard supplies."""
    out = {"run_id": ctx.get("run_id"), "work_type": ctx.get("work_type")}
    if ctx.get("brief"):
        out["research_brief"] = ctx["brief"]
    if ctx.get("selected_direction_ref"):
        out["selected_direction_ref"] = ctx["selected_direction_ref"]
    if ctx.get("current_spec"):
        out["current_spec"] = ctx["current_spec"]
    if ctx.get("neutral_taxonomy"):
        out["campaign_neutral_taxonomy"] = ctx["neutral_taxonomy"]
    # post-fulfillment merchandising: the BOUNDED eligible sets + rails + product facts (UID-keyed).
    # This is verified Engine truth the worker MERCHANDISES over — never authors.
    if ctx.get("requests"):
        out["requests"] = ctx["requests"]
    if ctx.get("architecture"):
        out["architecture"] = ctx["architecture"]
    return out


# ---------------------------------------------------------------------------
# claude CLI invocation + strict parsing
# ---------------------------------------------------------------------------
CLAUDE_BIN = os.environ.get("SHOPYA_CLAUDE_BIN", "claude")


def invoke_claude(prompt, model=None, timeout=1200):
    """Run the claude CLI non-interactively in a NEUTRAL temp cwd. Returns (final_text, tool_names).

    Uses stream-json + --verbose so we can observe tool_use events (real-research detection). The cwd
    is a throwaway temp dir with nothing from the repo, so no CLAUDE.md/Almost Fall material is in
    scope; --add-dir points only at that same neutral dir."""
    neutral_cwd = tempfile.mkdtemp(prefix="shopya_worker_ctx_")
    argv = [CLAUDE_BIN, "-p", "--output-format", "stream-json", "--verbose",
            "--permission-mode", "bypassPermissions", "--add-dir", neutral_cwd]
    if model:
        argv += ["--model", model]
    log("invoking: %s (cwd=%s)" % (" ".join(argv), neutral_cwd))
    try:
        proc = subprocess.run(argv, input=prompt, capture_output=True, text=True,
                              timeout=timeout, cwd=neutral_cwd)
    except subprocess.TimeoutExpired:
        raise RuntimeError("claude CLI timed out after %ds" % timeout)
    except (OSError, ValueError) as e:
        raise RuntimeError("could not launch claude CLI (%s): %s" % (CLAUDE_BIN, e))
    finally:
        try:
            os.rmdir(neutral_cwd)
        except OSError:
            pass
    if proc.returncode != 0:
        raise RuntimeError("claude CLI exited %d: %s" % (proc.returncode, (proc.stderr or "")[-1500:]))

    final_text, tools, is_error, err_result = _parse_stream(proc.stdout)
    if is_error:
        raise RuntimeError("claude reported an error result: %s" % (err_result or "")[:500])
    if final_text is None:
        raise RuntimeError("no final result event in claude output")
    return final_text, tools


def _parse_stream(stdout):
    """Parse stream-json lines. Return (final_result_text, [tool_names], is_error, error_text)."""
    final_text, tools, is_error, err = None, [], False, None
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = ev.get("type")
        if t == "assistant":
            for c in (ev.get("message", {}) or {}).get("content", []) or []:
                if c.get("type") == "tool_use":
                    tools.append(c.get("name"))
        elif t == "result":
            is_error = bool(ev.get("is_error"))
            final_text = ev.get("result")
            if is_error:
                err = ev.get("result")
    return final_text, tools, is_error, err


_JSON_BLOCK = re.compile(r"```json\s*(.*?)\s*```", re.DOTALL)


def extract_envelope(text):
    """Extract the WorkerAdapter envelope from the model's final text. Prefers a ```json fenced block;
    else the last balanced JSON object. Refuses if none parses to {objects:[...]}. Prose AROUND a
    single valid JSON block is tolerated; anything that does not yield the envelope is refused."""
    candidates = []
    for m in _JSON_BLOCK.finditer(text or ""):
        candidates.append(m.group(1))
    if not candidates:
        # fall back to the last {...} that parses
        depth, start = 0, None
        for i, ch in enumerate(text or ""):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start is not None:
                    candidates.append(text[start:i + 1])
    env = None
    for cand in reversed(candidates):
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("objects"), list):
            env = obj
            break
    if env is None:
        raise ValueError("no valid {'objects': [...]} JSON envelope found in worker output")
    # shape-check (the Wizard re-validates payloads; this catches gross contract violations early)
    for o in env["objects"]:
        if not isinstance(o, dict) or "kind" not in o or not isinstance(o.get("payload"), dict):
            raise ValueError("each object must be {kind, payload:{...}}; got %r" % o)
    return env


def run(work_request):
    """Full worker: prompt → claude → strict envelope. Verifies real research actually ran for a
    research work type (a tool_use of a web tool), else refuses (do not fake research — task §3)."""
    wt = work_request.get("work_type")
    profile = WORK_PROFILE.get(wt)
    if not profile:
        raise ValueError("unknown work_type %r" % wt)
    prompt = build_prompt(work_request)
    model = (work_request.get("options") or {}).get("model")
    final_text, tools = invoke_claude(prompt, model=model)
    log("tool_use during run: %s" % tools)
    if profile["research"]:
        used_web = any(tn in ("WebSearch", "WebFetch") for tn in tools)
        if not used_web:
            raise ValueError("research work_type produced no real web research (no WebSearch/WebFetch "
                             "tool_use observed) — refusing to register memory-only 'research'")
    env = extract_envelope(final_text)
    env["_worker_meta"] = {"tools_used": tools, "phase": profile["phase"], "engine": "claude_cli"}
    return env


def main():
    raw = sys.stdin.read()
    try:
        work_request = json.loads(raw)
    except json.JSONDecodeError as e:
        log("bad work request: %s" % e)
        sys.exit(2)
    try:
        env = run(work_request)
    except Exception as e:  # any failure → nonzero exit + stderr detail; NO stdout envelope
        log("WORKER FAILED: %s" % e)
        sys.exit(1)
    sys.stdout.write(json.dumps(env))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
