#!/usr/bin/env python3
"""console/api.py — the Interaction API + thin Campaign Console (task §17/§19).

FastAPI handlers are ADAPTERS ONLY. Every rule lives below, in scripts/checkpoint_core.py, which the
CLI (run.py) also calls — there is no business logic here and none duplicated from the CLI. The app
serves both:
  • a JSON API under /api/... (task §17) — the seam a richer GUI or the agent-worker would call;
  • server-rendered HTML pages (Jinja2) — the thin local Campaign Console (task §19–§24).

Single owner, local only, no auth, no DB, no deploy. Launched by scripts/run.py serve on 127.0.0.1.
"""
import os
import sys

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

ROOT = os.environ.get("SHOPYA_CAMPAIGN_ROOT",
                      os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import checkpoint_core as cc            # the single business-logic home
import json as _json

HERE = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(HERE, "templates"))

app = FastAPI(title="Shopya Campaign Console", docs_url="/api/docs")
app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")


# ---------------------------------------------------------------------------
# adapter helper — turn a CheckpointError into a structured error (task §17/§31)
# ---------------------------------------------------------------------------
def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except cc.CheckpointError as e:
        raise HTTPException(status_code=422, detail={"code": e.code, "message": e.message})


def _parse_body_json(raw, field):
    if not raw:
        return None
    try:
        return _json.loads(raw)
    except Exception as e:
        raise HTTPException(status_code=400,
                            detail={"code": "bad_json", "message": "%s: %s" % (field, e)})


# ═══════════════════════════════════════════════════════════════════
# JSON API (task §17) — handlers are adapters over checkpoint_core.
# ═══════════════════════════════════════════════════════════════════
@app.get("/api/worker")
def api_worker_readiness():
    """Agent-worker readiness (Console indicator): Ready (which worker) or Unavailable."""
    import worker as wk
    return wk.worker_readiness()


@app.get("/api/runs")
def api_list_runs():
    return {"runs": cc.list_runs()}


@app.post("/api/runs")
def api_create_run(body: dict = None):
    body = body or {}
    return _guard(cc.create_run, note=body.get("note"), diagnostic=bool(body.get("diagnostic")))


@app.get("/api/runs/{run_id}")
def api_get_run(run_id: str):
    return {"header": cc.run_header(run_id)}


@app.get("/api/runs/{run_id}/checkpoint")
def api_get_checkpoint(run_id: str):
    return _guard(cc.describe_checkpoint, run_id)


@app.post("/api/runs/{run_id}/checkpoint/answers")
def api_submit_answers(run_id: str, body: dict):
    payload = (body or {}).get("payload")
    if payload is None:
        raise HTTPException(400, detail={"code": "no_payload", "message": "payload required"})
    return _guard(cc.submit_intake, run_id, payload)


@app.post("/api/runs/{run_id}/checkpoint/revision")
def api_request_revision(run_id: str, body: dict):
    body = body or {}
    return _guard(cc.request_revision, run_id, revised_payload=body.get("payload"),
                  ops=body.get("ops"), note=body.get("note"))


@app.post("/api/runs/{run_id}/checkpoint/approve")
def api_approve(run_id: str, body: dict = None):
    body = body or {}
    return _guard(cc.approve_checkpoint, run_id, by=body.get("by", "product_owner"),
                  note=body.get("note"), direction_id=body.get("direction_id"))


@app.post("/api/runs/{run_id}/checkpoint/run-next")
def api_run_next(run_id: str):
    """RUN NEXT — the Wizard executes the research/synthesis worker BEHIND the interface, validates
    the returned structured artifact, and registers it. Thin adapter over run_checkpoint_work; the
    worker is the configured WorkerAdapter (SHOPYA_WIZARD_WORKER_CMD, else the deterministic fake).
    A worker failure returns a structured, retryable error — never a partial artifact."""
    return _guard(cc.run_checkpoint_work, run_id)


@app.get("/api/runs/{run_id}/objects/{kind}/diff")
def api_object_diff(run_id: str, kind: str, from_rev: str = None, to_rev: str = None):
    return {"diff": _guard(cc.object_diff, run_id, kind, from_rev=from_rev, to_rev=to_rev)}


@app.get("/api/runs/{run_id}/fulfillment")
def api_fulfillment(run_id: str):
    return cc.fulfillment_view(run_id)


@app.get("/api/runs/{run_id}/material-exceptions")
def api_material_exceptions(run_id: str):
    return cc.material_exceptions_view(run_id)


@app.get("/api/runs/{run_id}/execution-package")
def api_execution_package(run_id: str):
    return cc.execution_package_view(run_id)


# ── BACK-HALF owner actions (thin adapters over checkpoint_core; existing proven ops) ──
@app.post("/api/runs/{run_id}/generate-requests")
def api_generate_requests(run_id: str):
    return _guard(cc.generate_requests, run_id)


@app.post("/api/runs/{run_id}/ingest-receipt")
def api_ingest_receipt(run_id: str, body: dict):
    body = body or {}
    if not body.get("receipt_path") or not body.get("request_path"):
        raise HTTPException(400, detail={"code": "missing_paths",
                                         "message": "receipt_path and request_path required"})
    return _guard(cc.ingest_receipt, run_id, body["receipt_path"], body["request_path"],
                  snapshot_dir=body.get("snapshot_dir"),
                  fulfillment_exception_path=body.get("fulfillment_exception_path"))


@app.post("/api/runs/{run_id}/material-exceptions/{mx_id}/resolve")
def api_resolve_mx(run_id: str, mx_id: str, body: dict = None):
    body = body or {}
    return _guard(cc.resolve_material_exception, run_id, mx_id,
                  body.get("resolution") or {"note": body.get("note", "")},
                  by=body.get("by", "product_owner"))


@app.post("/api/runs/{run_id}/generate-execution-package")
def api_generate_execution_package(run_id: str, body: dict = None):
    """The MECHANICAL production path: Wizard merchandises the fulfilled eligible products into the
    package (worker → validate selections → build → validate → F manifest). No owner product inputs."""
    body = body or {}
    return _guard(cc.generate_execution_package, run_id, engine=body.get("engine"),
                  revision_instruction=body.get("revision_instruction"))


@app.post("/api/runs/{run_id}/build-package")
def api_build_package(run_id: str, body: dict = None):
    """DIAGNOSTIC/TEST-ONLY: explicit curated judgment + truth export inputs. The normal production
    path is /generate-execution-package (mechanical). Kept for fixtures/operators."""
    body = body or {}
    return _guard(cc.build_and_validate_package, run_id, judgment=body.get("judgment"),
                  truth_export=body.get("truth_export"), engine=body.get("engine"),
                  campaign=body.get("campaign"), campaign_name=body.get("campaign_name"),
                  build=body.get("build"))


@app.post("/api/runs/{run_id}/execution-package/approve")
def api_approve_package(run_id: str, body: dict = None):
    # execution-package approval is a distinct back-half owner action; the sanctioned writer lives in
    # run.py (approve_package binds the exact manifest). The API returns the current view; the GUI
    # posts the approval through the CLI-equivalent path below to keep one writer.
    import run as _run
    body = body or {}
    class _A:  # minimal args shim for the existing cmd
        run = run_id
        by = body.get("by", "product_owner")
        note = body.get("note")
    try:
        _run.cmd_approve_package(_A())
    except SystemExit as e:
        raise HTTPException(422, detail={"code": "approve_package_refused", "message": str(e)})
    return cc.execution_package_view(run_id)


# ═══════════════════════════════════════════════════════════════════
# HTML CONSOLE (task §19–§24) — Jinja2 server-rendered pages. Thin.
# ═══════════════════════════════════════════════════════════════════
@app.get("/", response_class=HTMLResponse)
def page_home(request: Request):
    import worker as wk
    return templates.TemplateResponse("home.html",
                                      {"request": request, "runs": cc.list_runs(),
                                       "worker": wk.worker_readiness()})


@app.post("/ui/runs/new")
def ui_new_run():
    res = cc.create_run()
    return RedirectResponse(url="/ui/runs/%s" % res["run_id"], status_code=303)


@app.get("/ui/runs/{run_id}", response_class=HTMLResponse)
def page_run(request: Request, run_id: str, err: str = None):
    view = cc.describe_checkpoint(run_id)
    fulfillment = cc.fulfillment_view(run_id)
    mx = cc.material_exceptions_view(run_id)
    pkg = cc.execution_package_view(run_id)
    back = cc.back_half_status(run_id)
    return templates.TemplateResponse("run.html", {
        "request": request, "run_id": run_id, "view": view,
        "fulfillment": fulfillment, "material_exceptions": mx, "package": pkg,
        "back": back, "err": err,
        "worker": (view.get("header") or {}).get("worker"),
        "json": _json,
    })


@app.post("/ui/runs/{run_id}/intake")
def ui_intake(run_id: str, payload_json: str = Form(...)):
    payload = _parse_body_json(payload_json, "payload_json")
    _guard(cc.submit_intake, run_id, payload)
    return RedirectResponse(url="/ui/runs/%s" % run_id, status_code=303)


@app.post("/ui/runs/{run_id}/revision")
def ui_revision(run_id: str, ops_json: str = Form(None), payload_json: str = Form(None),
                note: str = Form(None)):
    ops = _parse_body_json(ops_json, "ops_json") if ops_json else None
    payload = _parse_body_json(payload_json, "payload_json") if payload_json else None
    _guard(cc.request_revision, run_id, revised_payload=payload, ops=ops, note=note)
    return RedirectResponse(url="/ui/runs/%s" % run_id, status_code=303)


@app.post("/ui/runs/{run_id}/approve")
def ui_approve(run_id: str, direction_id: str = Form(None), note: str = Form(None)):
    _guard(cc.approve_checkpoint, run_id, by="product_owner",
           direction_id=direction_id or None, note=note)
    return RedirectResponse(url="/ui/runs/%s" % run_id, status_code=303)


@app.post("/ui/runs/{run_id}/run-next")
def ui_run_next(run_id: str):
    """RUN NEXT from the browser: the Wizard runs the worker behind the interface and registers the
    result, then redirects to the next checkpoint. A worker failure is recorded as a WORK FAILED
    status and rendered on the run page (safe to retry) — never a raw stack trace."""
    try:
        cc.run_checkpoint_work(run_id)
    except cc.CheckpointError:
        pass  # the failure is recorded in worker_status and rendered on the page; retry is safe
    return RedirectResponse(url="/ui/runs/%s" % run_id, status_code=303)


# ── BACK-HALF owner actions from the browser (redirect back to the run page; errors flashed) ──
def _flash(run_id, err):
    return RedirectResponse(url="/ui/runs/%s?err=%s" % (run_id, err), status_code=303)


@app.post("/ui/runs/{run_id}/generate-requests")
def ui_generate_requests(run_id: str):
    try:
        cc.generate_requests(run_id)
    except cc.CheckpointError as e:
        return _flash(run_id, "%s: %s" % (e.code, e.message))
    return RedirectResponse(url="/ui/runs/%s" % run_id, status_code=303)


@app.post("/ui/runs/{run_id}/generate-execution-package")
def ui_generate_execution_package(run_id: str, revision_instruction: str = Form(None)):
    """The one browser action: Generate Execution Package (mechanical). No product-row form."""
    try:
        cc.generate_execution_package(run_id, revision_instruction=revision_instruction or None)
    except cc.CheckpointError as e:
        return _flash(run_id, "%s: %s" % (e.code, e.message))
    return RedirectResponse(url="/ui/runs/%s" % run_id, status_code=303)


@app.post("/ui/runs/{run_id}/approve-package")
def ui_approve_package(run_id: str):
    try:
        cc.approve_package(run_id, by="product_owner")
    except cc.CheckpointError as e:
        return _flash(run_id, "%s: %s" % (e.code, e.message))
    return RedirectResponse(url="/ui/runs/%s" % run_id, status_code=303)


@app.post("/ui/runs/{run_id}/material-exceptions/{mx_id}/resolve")
def ui_resolve_mx(run_id: str, mx_id: str, note: str = Form(None)):
    try:
        cc.resolve_material_exception(run_id, mx_id, {"note": note or ""}, by="product_owner")
    except cc.CheckpointError as e:
        return _flash(run_id, "%s: %s" % (e.code, e.message))
    return RedirectResponse(url="/ui/runs/%s" % run_id, status_code=303)


@app.get("/healthz")
def healthz():
    return {"ok": True}
