#!/usr/bin/env python3
"""test_real_worker.py — real Claude worker adapter + fail-closed production + adversarial output.

Deterministic + network-free (no live Claude). Proves:
  • strict output enforcement in the claude_worker adapter (prose-around-JSON tolerated; malformed,
    wrong-shape, wrong-kind, missing-object all refused; research-without-real-web-tools refused);
  • the SubprocessWorker + Wizard reject bad output from a REAL subprocess (stub scripts emitting
    prose / malformed / nonzero-exit / one-valid-one-invalid) and never register partial authority;
  • PRODUCTION fails closed with no real worker (never silently selects the fake); the fake is
    selectable only for tests / explicit diagnostic runs.

Run: python3 tests/test_real_worker.py
"""
import json
import os
import shutil
import stat
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "console", "workers"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

PASS, FAIL = [], []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %s %s%s" % ("PASS " if cond else "FAIL ", name, "" if cond else "  << " + str(detail)))


def _stub(tmp, name, body):
    """Write an executable python stub worker that reads stdin JSON and emits `body` behavior."""
    p = os.path.join(tmp, name)
    with open(p, "w") as f:
        f.write("#!/usr/bin/env python3\nimport sys, json\nraw=sys.stdin.read()\n" + body)
    os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)
    return "%s %s" % (sys.executable, p)


def main():
    tmp = tempfile.mkdtemp(prefix="real_worker_")
    runs = os.path.join(tmp, "campaigns")
    os.makedirs(os.path.join(runs, "_drafts"))
    os.environ["SHOPYA_CAMPAIGN_RUNS"] = runs
    for m in ("run", "checkpoint_core", "front_half", "worker", "claude_worker"):
        sys.modules.pop(m, None)
    import claude_worker as cw
    import worker as wk
    import checkpoint_core as cc
    import front_half_fixture as fx
    try:
        # ── (A) adapter strict output enforcement (unit) ──
        env = cw.extract_envelope('prose before\n```json\n{"objects":[{"kind":"research_ledger",'
                                  '"payload":{"x":1}}]}\n```\nprose after')
        ok("adapter: tolerates prose around a single valid JSON block",
           env["objects"][0]["kind"] == "research_ledger")
        for bad, label in (("no json at all", "malformed/no-json"),
                           ('```json\n{"foo":1}\n```', "wrong-shape (no objects)"),
                           ('```json\n{"objects":[{"payload":{}}]}\n```', "object missing kind")):
            try:
                cw.extract_envelope(bad)
                ok("adapter: refuses %s" % label, False, "should have raised")
            except ValueError:
                ok("adapter: refuses %s" % label, True)

        # ── (B) adapter refuses research with NO real web tool_use (no faked research) ──
        # simulate the parse path: run() checks tool_use for a research work type. We call run()'s
        # research-gate by monkeypatching invoke_claude to return a valid envelope but NO web tools.
        orig = cw.invoke_claude
        cw.invoke_claude = lambda prompt, model=None, timeout=1200: (
            '```json\n{"objects":[{"kind":"research_ledger","payload":{"a":1}},'
            '{"kind":"campaign_directions","payload":{"b":1}}]}\n```', [])  # no tools
        try:
            cw.run({"work_type": "research", "context": {"run_id": "x"}})
            ok("adapter: research with no web tool_use is refused (no faked research)", False, "raised?")
        except ValueError as e:
            ok("adapter: research with no web tool_use is refused (no faked research)",
               "no real web research" in str(e), str(e)[:50])
        # with a WebFetch tool_use it passes the research gate
        cw.invoke_claude = lambda prompt, model=None, timeout=1200: (
            '```json\n{"objects":[{"kind":"research_ledger","payload":{"a":1}},'
            '{"kind":"campaign_directions","payload":{"b":1}}]}\n```', ["ToolSearch", "WebFetch"])
        env = cw.run({"work_type": "research", "context": {"run_id": "x"}})
        ok("adapter: research WITH real web tool_use passes the research gate",
           env["_worker_meta"]["tools_used"] == ["ToolSearch", "WebFetch"])
        cw.invoke_claude = orig

        # ── (C) SubprocessWorker + Wizard reject bad output from a REAL subprocess ──
        def fresh_run_at_research():
            rid = cc.create_run()["run_id"]
            cc.submit_intake(rid, fx.brief_payload(bid="rb", run_id=rid))
            cc.approve_checkpoint(rid, by="product_owner")
            return rid

        cases = [
            ("prose only (no json)", 'sys.stdout.write("I did the research! Here are results.")'),
            ("malformed json", 'sys.stdout.write("{objects: [broken")'),
            ("wrong shape", 'sys.stdout.write(json.dumps({"foo": 1}))'),
            ("nonzero exit", 'sys.stderr.write("boom"); sys.exit(3)'),
            ("empty output", 'pass'),
        ]
        for label, body in cases:
            rid = fresh_run_at_research()
            cmd = _stub(tmp, "stub_%s.py" % abs(hash(label)), body)
            w = wk.SubprocessWorker(command=cmd)
            try:
                cc.run_checkpoint_work(rid, worker=w)
                ok("subprocess: %s refused" % label, False, "should have failed")
            except cc.CheckpointError as e:
                s = cc._rt().require_run(rid)
                registered = "campaign_directions" in (s.get("artifacts") or {})
                ok("subprocess: %s refused + nothing registered" % label,
                   e.code in ("work_failed", "work_output_invalid") and not registered, e.code)

        # ── (C2) structurally-malformed section (real-worker shape drift) is a clean refusal, not a
        #        crash. A worker returned a spec section as a LIST instead of an object. ──
        def run_to_spec():
            rid = cc.create_run()["run_id"]
            cc.submit_intake(rid, fx.brief_payload(bid="rb", run_id=rid))
            cc.approve_checkpoint(rid, by="product_owner")
            cc.run_checkpoint_work(rid, worker=wk.FakeWorker())     # produce ledger+directions
            cc.approve_checkpoint(rid, by="product_owner", direction_id="d1")
            return rid
        rid = run_to_spec()
        malformed_spec = json.dumps({"objects": [{"kind": "campaign_spec", "payload": {
            "campaign_spec_id": "cs_bad", "revision": "r001", "parent_revision": None,
            "selected_direction_ref": {"directions_id": "cd_fx", "revision": "r001", "direction_id": "d1"},
            "sections": {"collection_selections": ["not", "an", "object"]}}}]})
        cmd = _stub(tmp, "stub_malformed.py", "sys.stdout.write(%r)" % malformed_spec)
        try:
            cc.run_checkpoint_work(rid, worker=wk.SubprocessWorker(command=cmd))
            ok("subprocess: structurally-malformed section refused (no crash)", False, "should fail")
        except cc.CheckpointError as e:
            s = cc._rt().require_run(rid)
            ok("subprocess: structurally-malformed section is a clean refusal, not a crash",
               e.code in ("work_output_invalid", "malformed_object")
               and "campaign_spec" not in (s.get("artifacts") or {}), e.code)

        # ── (D) one valid + one invalid object → NONE registered (all-or-nothing) ──
        rid = fresh_run_at_research()
        # research must produce ledger+directions; emit a VALID ledger but an INVALID directions
        good_ledger = json.dumps(fx.ledger_payload(lid="rl_z", brief_ref="rb"))
        body = ('objs=[{"kind":"research_ledger","payload":%s},'
                '{"kind":"campaign_directions","payload":{"directions_id":"cd_z","revision":"r001",'
                '"ledger_ref":"rl_z","directions":[{"direction_id":"d1"}],'
                '"recommended_direction_id":"d1"}}];'
                'sys.stdout.write(json.dumps({"objects":objs}))') % good_ledger
        cmd = _stub(tmp, "stub_partial.py", body)
        try:
            cc.run_checkpoint_work(rid, worker=wk.SubprocessWorker(command=cmd))
            ok("subprocess: one-valid+one-invalid refused", False, "should fail")
        except cc.CheckpointError as e:
            s = cc._rt().require_run(rid)
            none_reg = ("research_ledger" not in (s.get("artifacts") or {})
                        and "campaign_directions" not in (s.get("artifacts") or {}))
            ok("subprocess: one-valid+one-invalid registers NEITHER (all-or-nothing)",
               none_reg, list((s.get("artifacts") or {}).keys()))

        # ── (E) retry after a bad worker succeeds with a good one ──
        good = json.dumps({"objects": [
            {"kind": "research_ledger", "payload": fx.ledger_payload(lid="rl_ok", brief_ref="rb")},
            {"kind": "campaign_directions",
             "payload": fx.directions_payload(did="cd_ok", ledger_ref="rl_ok")}]})
        good_cmd = _stub(tmp, "stub_good.py", "sys.stdout.write(%r)" % good)
        r = cc.run_checkpoint_work(rid, worker=wk.SubprocessWorker(command=good_cmd))
        ok("subprocess: retry with a good worker succeeds after failures",
           {x["kind"] for x in r["registered"]} == {"research_ledger", "campaign_directions"})

        # ── (F) PRODUCTION fails closed with no real worker (never silent fake) ──
        os.environ.pop("SHOPYA_WIZARD_WORKER_CMD", None)
        os.environ["SHOPYA_CLAUDE_BIN"] = "/nonexistent/claude_xyz"
        sys.modules.pop("worker", None)
        import worker as wk2
        rid = fresh_run_at_research()   # a production run
        # run_checkpoint_work with NO explicit worker → must raise worker_unavailable
        try:
            cc.run_checkpoint_work(rid)
            ok("production: no real worker → worker_unavailable (no silent fake)", False, "should raise")
        except cc.CheckpointError as e:
            s = cc._rt().require_run(rid)
            ok("production: no real worker → worker_unavailable + nothing registered",
               e.code == "worker_unavailable"
               and "campaign_directions" not in (s.get("artifacts") or {}), e.code)
        ok("production: get_worker refuses to return a fake implicitly",
           _raises(lambda: wk2.get_worker(run_mode="production", allow_fake=False), wk2.WorkerError))
        ok("test/diagnostic: fake is selectable explicitly",
           type(wk2.get_worker(force_fake=True)).__name__ == "FakeWorker")
        os.environ.pop("SHOPYA_CLAUDE_BIN", None)

        print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
        sys.exit(1 if FAIL else 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        for k in ("SHOPYA_CAMPAIGN_RUNS", "SHOPYA_WIZARD_WORKER_CMD", "SHOPYA_CLAUDE_BIN"):
            os.environ.pop(k, None)


def _raises(fn, exc):
    try:
        fn()
        return False
    except exc:
        return True


if __name__ == "__main__":
    main()
