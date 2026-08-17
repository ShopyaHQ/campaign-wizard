#!/usr/bin/env python3
"""test_worker_flow.py — the Wizard-owned worker boundary (owner-flow closeout §10).

Proves the owner can operate the campaign entirely from the interface while the research/synthesis
worker runs BEHIND the Wizard: correct work-type derivation, worker receives the exact approved
context, invalid/partial output is refused and cannot advance state, worker failure leaves a coherent
retryable state, retry works, successful output registers the correct immutable object/revision, the
checkpoint advances, and the owner NEVER supplies a generated artifact directly.

Uses a deterministic FakeWorker (no live agent). Runs directly:
    python3 tests/test_worker_flow.py
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

PASS, FAIL = [], []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %s %s%s" % ("PASS " if cond else "FAIL ", name, "" if cond else "  << " + str(detail)))


class SpyWorker:
    """Wraps FakeWorker to capture the exact work_request the Wizard passed (context assertions)."""
    def __init__(self, inner):
        self.inner = inner
        self.last_request = None

    def run(self, work_request):
        self.last_request = work_request
        return self.inner.run(work_request)


def main():
    tmp = tempfile.mkdtemp(prefix="worker_flow_")
    runs = os.path.join(tmp, "campaigns")
    os.makedirs(os.path.join(runs, "_drafts"))
    os.environ["SHOPYA_CAMPAIGN_RUNS"] = runs
    for m in ("run", "checkpoint_core", "front_half", "worker"):
        sys.modules.pop(m, None)
    import checkpoint_core as cc
    import worker as wk
    import front_half_fixture as fx
    try:
        rid = cc.create_run()["run_id"]
        S = lambda: cc._rt().require_run(rid)

        # ── owner authors kickoff intake (the ONLY object the owner supplies), approves ──
        cc.submit_intake(rid, fx.brief_payload(bid="rb_1", run_id=rid))
        cc.approve_checkpoint(rid, by="product_owner")

        # (1) correct work type derived at the current checkpoint
        due, wt = cc.can_run_next(S(), cc._rt().run_dir, rid)
        ok("work-type derivation: research is due after kickoff approval", due and wt == "research", wt)

        # (2) worker receives the EXACT approved context (brief id/hash + brief content)
        spy = SpyWorker(wk.FakeWorker())
        res = cc.run_checkpoint_work(rid, worker=spy)
        req = spy.last_request
        bspine = cc._object_spine(S(), "research_brief")
        ok("worker received work_type=research", req["work_type"] == "research")
        ok("worker received the approved brief id + hash in context",
           req["context"]["brief_id"] == bspine["object_id"]
           and req["context"]["brief_hash"] == bspine["canonical_hash"], req["context"].get("brief_id"))
        ok("worker received the approved output contract (produces ledger+directions)",
           req["output_contract"]["produces"] == ["research_ledger", "campaign_directions"])

        # (3) successful output registered the correct immutable objects + advanced
        ok("research registered ledger + directions",
           {r["kind"] for r in res["registered"]} == {"research_ledger", "campaign_directions"},
           res["registered"])
        ok("checkpoint advanced to direction review", res["next_checkpoint"] == "direction")
        ok("worker_status recorded done", cc.worker_status(rid)["status"] == "done")

        # (4) owner NEVER supplied the generated artifact: directions came from the worker, and the
        # checkpoint now offers a SELECTION (not an intake form for the object)
        view = cc.describe_checkpoint(rid)["checkpoint"]
        ok("owner is asked to SELECT a direction (not author one)",
           view["questions"][0]["id"] == "selected_direction", view["questions"][0]["id"])
        ok("run_next no longer available (object present, awaiting owner action)",
           view["run_next_available"] is False and "run_next" not in view["allowed_actions"])

        # ── owner selects a direction; spec work becomes due ──
        cc.approve_checkpoint(rid, by="product_owner", direction_id="d1")
        due, wt = cc.can_run_next(S(), cc._rt().run_dir, rid)
        ok("work-type derivation: spec is due after direction selection", due and wt == "spec", wt)

        # (5) worker gets the selected-direction ref as approved context
        spy2 = SpyWorker(wk.FakeWorker())
        res2 = cc.run_checkpoint_work(rid, worker=spy2)
        ok("spec worker received the selected_direction_ref",
           (spy2.last_request["context"].get("selected_direction_ref") or {}).get("direction_id") == "d1",
           spy2.last_request["context"].get("selected_direction_ref"))
        ok("spec work registered the campaign_spec",
           [r["kind"] for r in res2["registered"]] == ["campaign_spec"], res2["registered"])
        spec_rev = cc._object_spine(S(), "campaign_spec")["revision"]
        ok("registered spec is an immutable r001 revision on disk",
           os.path.exists(os.path.join(cc._rt().run_dir(rid), "campaign_spec.%s.yaml" % spec_rev)))

        # (6) INVALID worker output is refused + cannot advance state
        # fresh run to a clean pre-research point
        rid2 = cc.create_run()["run_id"]
        cc.submit_intake(rid2, fx.brief_payload(bid="rb_2", run_id=rid2))
        cc.approve_checkpoint(rid2, by="product_owner")
        try:
            cc.run_checkpoint_work(rid2, worker=wk.FakeWorker(produce_invalid=True))
            ok("invalid worker output refused", False, "expected error")
        except cc.CheckpointError as e:
            ok("invalid worker output is refused (front_half gate)",
               e.code == "work_output_invalid", e.code)
        s2 = cc._rt().require_run(rid2)
        ok("partial/invalid output did NOT register any object (state coherent)",
           "campaign_directions" not in (s2.get("artifacts") or {})
           and "research_ledger" not in (s2.get("artifacts") or {}), list((s2.get("artifacts") or {}).keys()))
        ok("failed worker status recorded, checkpoint unchanged",
           cc.worker_status(rid2)["status"] == "failed"
           and cc.describe_checkpoint(rid2)["checkpoint"]["checkpoint_type"] == "direction")

        # (7) worker FAILURE leaves a coherent retryable state; RETRY works
        rid3 = cc.create_run()["run_id"]
        cc.submit_intake(rid3, fx.brief_payload(bid="rb_3", run_id=rid3))
        cc.approve_checkpoint(rid3, by="product_owner")
        try:
            cc.run_checkpoint_work(rid3, worker=wk.FakeWorker(fail_on="research"))
        except cc.CheckpointError as e:
            ok("worker failure surfaces as work_failed", e.code == "work_failed", e.code)
        ok("after failure, run is still retryable at the same checkpoint",
           cc.can_run_next(cc._rt().require_run(rid3), cc._rt().run_dir, rid3) == (True, "research"))
        retry = cc.run_checkpoint_work(rid3, worker=wk.FakeWorker())   # good worker
        ok("retry with a working worker succeeds + advances",
           retry["next_checkpoint"] == "direction"
           and {r["kind"] for r in retry["registered"]} == {"research_ledger", "campaign_directions"})

        # (8) no worker step when the object is already present (owner reviews, not re-run)
        try:
            cc.run_checkpoint_work(rid3, worker=wk.FakeWorker())
            ok("re-running when the object is present is refused", False, "expected error")
        except cc.CheckpointError as e:
            ok("no worker re-run when the object is already present",
               e.code == "object_already_present", e.code)

        # (9) worker returning the WRONG object kind is refused
        class WrongKind:
            def run(self, wr):
                return {"objects": [{"kind": "campaign_spec", "payload": {}}]}
        rid4 = cc.create_run()["run_id"]
        cc.submit_intake(rid4, fx.brief_payload(bid="rb_4", run_id=rid4))
        cc.approve_checkpoint(rid4, by="product_owner")
        try:
            cc.run_checkpoint_work(rid4, worker=WrongKind())
            ok("wrong-kind worker output refused", False, "expected error")
        except cc.CheckpointError as e:
            ok("worker returning the wrong object kind is refused",
               e.code in ("work_output_invalid", "worker_wrong_object"), e.code)

        print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
        sys.exit(1 if FAIL else 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("SHOPYA_CAMPAIGN_RUNS", None)


if __name__ == "__main__":
    main()
