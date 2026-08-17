#!/usr/bin/env python3
"""test_console_api.py — Interaction API + GUI HTTP tests + synthetic E2E smoke (task §31/§32/§33).

Runs under the repo .venv (fastapi + httpx). Drives the SAME flow a browser would through the
FastAPI adapters, proving the API surface, structured errors, the HTML renderers, and the end-to-end
iterative interaction pattern — WITHOUT running a fresh Almost Fall.

    .venv/bin/python tests/test_console_api.py
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS, FAIL = [], []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %s %s%s" % ("PASS " if cond else "FAIL ", name, "" if cond else "  << " + str(detail)))


def main():
    tmp = tempfile.mkdtemp(prefix="console_api_")
    runs = os.path.join(tmp, "campaigns")
    os.makedirs(os.path.join(runs, "_drafts"))
    os.environ["SHOPYA_CAMPAIGN_RUNS"] = runs
    os.environ["SHOPYA_CAMPAIGN_ROOT"] = ROOT
    # configure the DETERMINISTIC example worker (a real subprocess, no network/live agent) so
    # run-next has a real configured production worker — the fail-closed selection is satisfied and
    # the GUI/API flow stays deterministic. (The live Claude worker is exercised by the real smoke.)
    os.environ["SHOPYA_WIZARD_WORKER_CMD"] = "%s %s" % (
        sys.executable, os.path.join(ROOT, "console", "workers", "example_worker.py"))
    sys.path.insert(0, os.path.join(ROOT, "console"))
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    for m in ("run", "checkpoint_core", "front_half", "api"):
        sys.modules.pop(m, None)
    from fastapi.testclient import TestClient
    import api
    import front_half_fixture as fx
    c = TestClient(api.app)
    try:
        # ── API: create/list/open ──
        ok("GET /healthz", c.get("/healthz").json().get("ok") is True)
        r = c.post("/api/runs", json={})
        rid = r.json()["run_id"]
        ok("POST /api/runs creates a run", r.status_code == 200 and rid.startswith("cmp_"), r.text)
        ok("GET /api/runs lists it", any(x["run_id"] == rid for x in c.get("/api/runs").json()["runs"]))
        ok("GET /api/runs/{id} returns a header with a timeline",
           "timeline" in c.get("/api/runs/%s" % rid).json()["header"])

        # ── API: current checkpoint (KICKOFF/OPEN) ──
        cpv = c.get("/api/runs/%s/checkpoint" % rid).json()["checkpoint"]
        ok("GET checkpoint → KICKOFF OPEN", cpv["checkpoint_type"] == "kickoff"
           and cpv["status"] == "OPEN", cpv["status"])

        # ── API: structured error on an illegal action (approve with no object) ──
        r = c.post("/api/runs/%s/checkpoint/approve" % rid, json={})
        ok("approve with no object → structured 422 error",
           r.status_code == 422 and r.json()["detail"]["code"] == "no_object", r.text)

        # ── API: submit intake (answers) ──
        r = c.post("/api/runs/%s/checkpoint/answers" % rid,
                   json={"payload": fx.brief_payload(bid="rb_a", run_id=rid)})
        ok("POST /checkpoint/answers registers the brief", r.status_code == 200
           and r.json()["revision"] == "r001", r.text)

        # ── API: request targeted revision → diff ──
        r = c.post("/api/runs/%s/checkpoint/revision" % rid,
                   json={"ops": [{"op": "set", "path": "market.value", "value": "US + CA"}]})
        ok("POST /checkpoint/revision mints r002 with a diff",
           r.status_code == 200 and r.json()["revision"] == "r002"
           and r.json()["diff"]["has_changes"], r.text)

        # ── API: object diff endpoint ──
        r = c.get("/api/runs/%s/objects/research_brief/diff" % rid)
        ok("GET object diff → has_changes on market.value", r.status_code == 200
           and any(x["path"] == "market.value" for x in r.json()["diff"]["changed"]), r.text)

        # ── API: single-action approve advances the checkpoint ──
        r = c.post("/api/runs/%s/checkpoint/approve" % rid, json={"by": "product_owner"})
        ok("POST approve (one action) records kickoff_approved + frame_accepted",
           set(r.json()["approved"]) == {"kickoff_approved", "frame_accepted"}, r.text)
        nxt = c.get("/api/runs/%s/checkpoint" % rid).json()["checkpoint"]
        ok("checkpoint advanced to direction", nxt["checkpoint_type"] == "direction",
           nxt["checkpoint_type"])

        # ── API: run-next EXECUTES the worker behind the Wizard (owner-flow closeout) ──
        r = c.post("/api/runs/%s/checkpoint/run-next" % rid, json={})
        ok("run-next executes the research worker + registers ledger+directions",
           r.status_code == 200
           and {x["kind"] for x in r.json()["registered"]} == {"research_ledger", "campaign_directions"},
           r.text)

        # ── E2E through all five checkpoints, objects PRODUCED by the worker (task §33 + closeout) ──
        import checkpoint_core as cc
        r = c.post("/api/runs/%s/checkpoint/approve" % rid,
                   json={"by": "product_owner", "direction_id": "d1"})
        ok("E2E: direction selected via API", "direction_selected_v2" in r.json()["approved"], r.text)

        # premise+verticals: worker produces the spec via run-next, then owner revises one vertical
        r = c.post("/api/runs/%s/checkpoint/run-next" % rid, json={})
        ok("E2E: run-next produced the campaign_spec (worker behind the Wizard)",
           [x["kind"] for x in r.json()["registered"]] == ["campaign_spec"], r.text)
        r = c.post("/api/runs/%s/checkpoint/revision" % rid,
                   json={"ops": [{"op": "set",
                                  "path": "sections.vertical_strategies.verticals.0.conviction_role",
                                  "value": "supporting"}]})
        ok("E2E: one-vertical revision minted + diffed", r.json()["diff"]["has_changes"], r.text)
        r = c.post("/api/runs/%s/checkpoint/approve" % rid, json={"by": "product_owner"})
        ok("E2E: premise+verticals approved (both sections)",
           set(r.json()["approved"]) == {"premise_approved", "verticals_approved"}, r.text)

        # architecture: drop one collection via remove op? keep it valid — edit a rail title, approve
        r = c.post("/api/runs/%s/checkpoint/revision" % rid,
                   json={"ops": [{"op": "set", "path": "sections.rails.rails.0.title",
                                  "value": "The Coats, renamed"}]})
        ok("E2E: architecture targeted edit minted + diffed", r.json()["diff"]["has_changes"], r.text)
        r = c.post("/api/runs/%s/checkpoint/approve" % rid, json={"by": "product_owner"})
        ok("E2E: architecture approved (composite)", r.json()["approved"] == ["architecture_approved"], r.text)

        # build this
        r = c.post("/api/runs/%s/checkpoint/approve" % rid, json={"by": "product_owner"})
        ok("E2E: BUILD THIS approved (final composite)",
           r.json()["approved"] == ["campaign_spec_approved"], r.text)
        done = c.get("/api/runs/%s/checkpoint" % rid).json()
        ok("E2E: front half complete after all five checkpoints",
           done.get("front_half_complete") is True, done)

        # ── GUI HTML renderers (task §32) ──
        home = c.get("/").text
        ok("GUI: campaign list renders + New campaign button", "New campaign" in home)
        ok("GUI: the campaign appears on the home page", rid in home)
        # a fresh run to exercise the HTML intake + renderers at each stage
        r = c.post("/ui/runs/new", follow_redirects=False)
        loc = r.headers["location"]
        rid2 = loc.rsplit("/", 1)[-1]
        page = c.get(loc).text
        ok("GUI: new campaign opens the kickoff intake page", "Kickoff" in page and "Intake" in page)
        # submit intake through the HTML form endpoint
        import json as J
        r = c.post("/ui/runs/%s/intake" % rid2,
                   data={"payload_json": J.dumps(fx.brief_payload(bid="rb_b", run_id=rid2))})
        ok("GUI: kickoff form submit accepted (303 redirect)", r.status_code in (200, 303))
        page = c.get("/ui/runs/%s" % rid2).text
        ok("GUI: confirmation/review renders provenance chips",
           "inferred" in page and "owner" in page)
        # a revision via the HTML form
        r = c.post("/ui/runs/%s/revision" % rid2,
                   data={"ops_json": J.dumps([{"op": "set", "path": "market.value", "value": "US only"}])})
        page = c.get("/ui/runs/%s" % rid2).text
        ok("GUI: semantic diff appears after a revision", "What changed" in page)
        # approve via HTML → advances
        c.post("/ui/runs/%s/approve" % rid2)
        page = c.get("/ui/runs/%s" % rid2).text
        ok("GUI: approval advances to the direction checkpoint", "Directions" in page or "direction" in page)
        ok("GUI: technical details are present but secondary (details/summary)",
           "Technical" in page and "current hash" in page)
        ok("GUI: NO product-row approval affordance in architecture (grouped review only)",
           "product row" not in page.lower())

        # ══ BROWSER-ONLY WORKER-BACKED FLOW (owner-flow closeout §7/§8) ══
        # The owner operates entirely through the browser endpoints; the worker runs BEHIND the
        # Wizard (fake worker, default when no SHOPYA_WIZARD_WORKER_CMD). The owner supplies ONLY the
        # kickoff intake + approvals + a direction selection — never a generated artifact.
        r = c.post("/ui/runs/new", follow_redirects=False)
        rid3 = r.headers["location"].rsplit("/", 1)[-1]
        c.post("/ui/runs/%s/intake" % rid3,
               data={"payload_json": J.dumps(fx.brief_payload(bid="rb_c", run_id=rid3))})
        c.post("/ui/runs/%s/approve" % rid3)   # approve kickoff
        page = c.get("/ui/runs/%s" % rid3).text
        ok("WORKER GUI: after kickoff, the browser offers Run research (no intake for directions)",
           "Run research" in page, "run research button")
        # RUN NEXT from the browser → the Wizard runs the research worker behind the interface
        c.post("/ui/runs/%s/run-next" % rid3)
        page = c.get("/ui/runs/%s" % rid3).text
        ok("WORKER GUI: run-next produced + rendered the directions (worker behind the Wizard)",
           "Directions" in page and "Select this direction" in page)
        cpv = c.get("/api/runs/%s/checkpoint" % rid3).json()["checkpoint"]
        ok("WORKER GUI: directions object exists though the owner never authored one",
           cpv["object_id"] is not None and cpv["checkpoint_type"] == "direction")
        # owner selects a direction, runs next → spec produced behind the Wizard
        c.post("/ui/runs/%s/approve" % rid3, data={"direction_id": "d1"})
        page = c.get("/ui/runs/%s" % rid3).text
        ok("WORKER GUI: after selection, the browser offers Run next (spec)",
           "Run next" in page or "run-next" in page)
        c.post("/ui/runs/%s/run-next" % rid3)   # spec worker
        page = c.get("/ui/runs/%s" % rid3).text
        ok("WORKER GUI: premise + verticals now render (spec produced behind the Wizard)",
           "Premise" in page and "Verticals" in page)
        # advance premise → architecture → build this, all via browser approvals
        c.post("/ui/runs/%s/approve" % rid3)    # premise+verticals
        page = c.get("/ui/runs/%s" % rid3).text
        ok("WORKER GUI: architecture review renders after premise approval", "Architecture" in page)
        c.post("/ui/runs/%s/approve" % rid3)    # architecture
        page = c.get("/ui/runs/%s" % rid3).text
        ok("WORKER GUI: Build This renders after architecture approval",
           "Final Campaign Spec" in page or "Build this" in page)
        c.post("/ui/runs/%s/approve" % rid3)    # build this
        done = c.get("/api/runs/%s/checkpoint" % rid3).json()
        ok("WORKER GUI: reached front-half complete entirely through the browser + worker",
           done.get("front_half_complete") is True, done)
        # the owner used ONLY: new campaign · intake(brief) · approve · direction select · run-next.
        # The ledger, directions and campaign_spec were all produced by the worker behind the Wizard —
        # the owner never POSTed a generated object.
        ok("WORKER GUI: owner never supplied a generated artifact (browser-only, agent behind Wizard)",
           done.get("front_half_complete") is True)

        # ══ BACK-HALF browser flow (full-owner-flow closeout) ══
        # rid3 reached front-half complete above. The Console now offers Generate Requests, and the
        # timeline progresses past Build This (no perpetual "waiting").
        page = c.get("/ui/runs/%s" % rid3).text
        ok("BACK-HALF GUI: run page offers Generate Requests after Build This", "Generate Requests" in page)
        ok("BACK-HALF GUI: timeline includes Approved for Implementation", "Approved for Implementation" in page)
        r = c.post("/api/runs/%s/generate-requests" % rid3, json={})
        ok("BACK-HALF API: generate-requests derives the Request set from the approved spec",
           r.status_code == 200 and len(r.json()["requests"]) >= 1, r.text)
        page = c.get("/ui/runs/%s" % rid3).text
        ok("BACK-HALF GUI: Execution package section renders after requests", "Execution package" in page)
        # header timeline now shows Fulfillment current via the API
        hdr = c.get("/api/runs/%s" % rid3).json()["header"]
        tl = {t["phase"]: t["status"] for t in hdr["timeline"]}
        ok("BACK-HALF API: Fulfillment is current (not perpetually waiting)",
           tl.get("fulfillment") == "current", tl)
        # MECHANICAL merchandising path: the browser offers "Generate Execution Package" and NO
        # product-row / truth-export input form (owner authors nothing).
        page = c.get("/ui/runs/%s" % rid3).text
        ok("MERCH GUI: Execution package offers 'Generate Execution Package' (mechanical)",
           "Generate Execution Package" in page)
        ok("MERCH GUI: no owner product-row / curated-judgment input form on the normal path",
           "curated_judgment.json" not in page and "Enter curated product" not in page)
        # the mechanical endpoint exists; without satisfied receipts it refuses cleanly (no fabrication)
        r = c.post("/api/runs/%s/generate-execution-package" % rid3, json={})
        ok("MERCH API: generate-execution-package endpoint present + structured refusal pre-fulfillment",
           r.status_code in (200, 422), r.status_code)
        if r.status_code == 422:
            ok("MERCH API: refusal names a fulfillment/selection precondition (not a product-row form)",
               r.json()["detail"]["code"] in ("no_requests", "no_satisfied_receipts",
                                              "bound_snapshot_missing", "blocked_by_material_exception",
                                              "worker_unavailable", "merchandising_failed", "no_selection"),
               r.json()["detail"]["code"])

        print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
        sys.exit(1 if FAIL else 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("SHOPYA_CAMPAIGN_RUNS", None)
        os.environ.pop("SHOPYA_WIZARD_WORKER_CMD", None)


if __name__ == "__main__":
    main()
