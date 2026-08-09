#!/usr/bin/env python3
"""One-time backfill: add governance_003 `status` to a run's owner_decisions ledger.

    python3 scripts/migrate_decision_status.py --run <run_id>            # DRY RUN (default)
    python3 scripts/migrate_decision_status.py --run <run_id> --apply    # mutate after review

Owner ruling 2026-08-09: an entry is backfilled `owner_confirmed` ONLY when it carries
concrete evidence of explicit owner confirmation — a quoted/basis text AND a date/session
reference. Anything ambiguous is FLAGGED (status left unset, needs_owner=True), never
inferred from the legacy `decided_by: product_owner` stamp alone.

Prints a table of every entry: old stamp -> evidence basis -> proposed new status. The state
file is otherwise never hand-edited; this is a schema backfill, applied only with --apply and
written atomically through the same helper run.py uses.
"""
import argparse, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run as runner  # reuse require_run / atomic_write / state_path

# Evidence of an explicit owner confirmation: a basis/owner marker AND a date/session anchor.
BASIS_RX = re.compile(r"\b(basis|owner|publish|approved|locked|confirmed|selected|directive|"
                      r"ruling|message|answers|verbatim)\b", re.I)
DATE_RX = re.compile(r"20\d\d-\d\d-\d\d|this session|kickoff|checkpoint")


def classify(key, rec):
    """Return (proposed_status, needs_owner, reason)."""
    note = (rec.get("note") or "").replace("\n", " ").strip()
    has_basis = bool(BASIS_RX.search(note))
    has_anchor = bool(DATE_RX.search(note)) or bool(rec.get("decided_at"))
    if note and has_basis and has_anchor:
        return "owner_confirmed", False, "explicit owner basis + date/session anchor"
    if not note:
        return None, True, "no note — cannot confirm explicit owner basis"
    return None, True, "note lacks a clear owner-confirmation basis or anchor"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--apply", action="store_true", help="mutate; default is dry-run")
    a = ap.parse_args()

    s = runner.require_run(a.run)
    od = s.get("owner_decisions") or {}
    rows, flagged = [], []
    for k, rec in od.items():
        if not isinstance(rec, dict):
            continue
        if rec.get("status"):  # already migrated
            rows.append((k, rec.get("decided_by"), "status=%s (kept)" % rec["status"], rec["status"]))
            continue
        status, needs, reason = classify(k, rec)
        old = "decided=%s by=%s" % (rec.get("decided"), rec.get("decided_by"))
        rows.append((k, old, reason, status or "FLAG:needs_owner"))
        if needs:
            flagged.append(k)

    w = max(len(r[0]) for r in rows) if rows else 10
    print("%-*s  %-28s  %-42s  %s" % (w, "entry", "old stamp", "evidence basis", "-> proposed"))
    print("-" * (w + 80))
    for k, old, reason, prop in rows:
        print("%-*s  %-28s  %-42s  %s" % (w, k, old[:28], reason[:42], prop))
    print("\n%d entries; %d flagged for owner (left unset)." % (len(rows), len(flagged)))
    if flagged:
        print("FLAGGED (need explicit owner ruling, not migrated): " + ", ".join(flagged))

    if not a.apply:
        print("\nDRY RUN. Re-run with --apply to write status: owner_confirmed on the "
              "evidenced entries (flagged entries are left untouched).")
        return

    n = 0
    for k, rec in od.items():
        if not isinstance(rec, dict) or rec.get("status"):
            continue
        status, needs, _ = classify(k, rec)
        if status == "owner_confirmed":
            rec["status"] = "owner_confirmed"
            n += 1
    runner.atomic_write(runner.state_path(a.run), s)
    print("\nAPPLIED: %d entries set to owner_confirmed; %d left flagged." % (n, len(flagged)))


if __name__ == "__main__":
    main()
