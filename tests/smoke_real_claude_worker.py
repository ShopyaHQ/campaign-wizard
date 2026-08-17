#!/usr/bin/env python3
"""smoke_real_claude_worker.py — MANDATORY real Claude worker smoke (task §10). NOT in the automated
suite (it needs the live Claude CLI + network). Disposable run, NOT Almost Fall.

Flow through the SAME core the browser/API uses:
  create disposable diagnostic run → owner authors a small generic merchandising brief → approve
  kickoff → RUN NEXT (real ClaudeWorker does actual current web research) → verify a real external
  source + provenance in the registered research_ledger → reach Direction Review → select a direction
  → RUN NEXT (real synthesis) → reach Premise + Vertical Review.

Run:  python3 tests/smoke_real_claude_worker.py
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def field(v, prov="owner_supplied"):
    return {"value": v, "provenance": prov}


def brief(run_id):
    return {
        "brief_id": "rb_smoke", "revision": "r001", "campaign_id": None, "run_id": run_id,
        "objective": field("Grow discovery-led saves for everyday reusable drinkware among "
                           "sustainability-minded US shoppers"),
        "desired_behavior": field("Save a reusable bottle/tumbler to a list for later"),
        "market": field("United States"),
        "audience_context": field("US shoppers who care about sustainability + daily hydration",
                                  "system_inferred"),
        "campaign_window": field("Q4 2026", "system_inferred"),
        "territory": field("Everyday reusable drinkware (bottles, tumblers, insulated flasks)",
                           "derived"),
        "exclusions": ["No single-use plastic framing", "No discount/cheapness framing"],
        "owner_inputs": ["Lead with everyday utility + sustainability, not novelty"],
        "inferred_inputs": ["Audience skews sustainability-minded"],
        "assumptions": [], "unresolved_questions": ["Which drinkware sub-types lead?"],
        "provenance": {"objective": "owner_supplied"},
    }


def main():
    import worker as wk
    if not wk.claude_cli_available():
        print("SKIP: claude CLI not available on PATH — cannot run the real smoke.")
        sys.exit(2)

    tmp = tempfile.mkdtemp(prefix="smoke_claude_")
    runs = os.path.join(tmp, "campaigns")
    os.makedirs(os.path.join(runs, "_drafts"))
    os.environ["SHOPYA_CAMPAIGN_RUNS"] = runs
    # force the REAL bundled Claude worker
    os.environ["SHOPYA_WIZARD_WORKER_CMD"] = "%s %s" % (
        sys.executable, os.path.join(ROOT, "console", "workers", "claude_worker.py"))
    for m in ("run", "checkpoint_core", "front_half", "worker"):
        sys.modules.pop(m, None)
    import checkpoint_core as cc
    fails = []
    try:
        # a disposable PRODUCTION run (proves the real production worker path; NOT Almost Fall)
        rid = cc.create_run()["run_id"]
        print("disposable production run:", rid)
        cc.submit_intake(rid, brief(rid))
        cc.approve_checkpoint(rid, by="product_owner")
        print("kickoff approved. Running REAL research worker (live Claude, real web research)…")

        r = cc.run_checkpoint_work(rid)   # real ClaudeWorker via SHOPYA_WIZARD_WORKER_CMD
        print("research registered:", [x["kind"] for x in r["registered"]], "→ next:", r["next_checkpoint"])
        if r["next_checkpoint"] != "direction":
            fails.append("did not reach Direction Review")

        # verify a REAL external source + provenance in the registered ledger
        s = cc._rt().require_run(rid)
        ledger = cc._current_object_bytes(s, cc._rt().run_dir, rid, "research_ledger")
        sigs = (ledger or {}).get("signals") or []
        real_sourced = [sg for sg in sigs if str(sg.get("source", "")).startswith("http")]
        print("ledger signals:", len(sigs), "| with a real URL source:", len(real_sourced))
        for sg in real_sourced[:3]:
            print("   -", sg.get("source"), "| captured_at:", sg.get("captured_at"),
                  "| confidence:", sg.get("confidence"))
        if not real_sourced:
            fails.append("no signal carried a real external (http) source")

        # reach Direction Review, select a direction
        view = cc.describe_checkpoint(rid)["checkpoint"]
        dirs = (cc._current_object_bytes(s, cc._rt().run_dir, rid, "campaign_directions") or {}).get("directions") or []
        print("directions produced:", [d.get("direction_id") for d in dirs])
        if not dirs:
            fails.append("no directions produced")
        else:
            did = dirs[0]["direction_id"]
            cc.approve_checkpoint(rid, by="product_owner", direction_id=did)
            print("selected direction:", did, "→ running REAL synthesis worker…")
            r2 = cc.run_checkpoint_work(rid)
            print("spec registered:", [x["kind"] for x in r2["registered"]], "→ next:", r2["next_checkpoint"])
            if r2["next_checkpoint"] != "premise_verticals":
                fails.append("did not reach Premise + Vertical Review")
            else:
                view2 = cc.describe_checkpoint(rid)["checkpoint"]
                print("reached checkpoint:", view2["checkpoint_type"], "with premise present:",
                      bool((view2.get("review") or {}).get("premise")))

        print()
        if fails:
            print("REAL SMOKE FAILED:")
            for f in fails:
                print("  -", f)
            sys.exit(1)
        print("REAL CLAUDE SMOKE PASSED: live research → Direction Review → live synthesis → "
              "Premise + Vertical Review, with real external provenance.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        for k in ("SHOPYA_CAMPAIGN_RUNS", "SHOPYA_WIZARD_WORKER_CMD"):
            os.environ.pop(k, None)


if __name__ == "__main__":
    main()
