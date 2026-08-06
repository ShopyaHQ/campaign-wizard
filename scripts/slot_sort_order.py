#!/usr/bin/env python3
"""slot_sort_order.py — assign collision-free sort_orders against the LIVE catalog.

    python3 scripts/probe_feeds.py --group explore --json > /tmp/live.json
    python3 scripts/slot_sort_order.py --live /tmp/live.json --rails "Rail A,Rail B" [--after 3]

sort_order is global across the group. Never hand-pick numbers against a remembered page.
"""
import argparse, json, sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from probe_feeds import flatten

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", required=True, help="JSON from probe_feeds.py --json")
    ap.add_argument("--rails", required=True, help="comma-separated rail names, in intended page order")
    ap.add_argument("--after", type=int, help="slot new rails after this sort_order (default: append)")
    a = ap.parse_args()

    feeds = flatten(json.load(open(a.live)))
    taken = sorted({f.get("sort_order") for f in feeds if isinstance(f.get("sort_order"), int)})
    rails = [r.strip() for r in a.rails.split(",") if r.strip()]

    start = (a.after + 1) if a.after is not None else ((taken[-1] + 1) if taken else 0)
    assigned, n = [], start
    for r in rails:
        while n in taken: n += 1
        assigned.append((n, r)); taken.append(n); n += 1

    print(f"taken before: {sorted(set(taken) - {s for s, _ in assigned})}")
    print("assigned:")
    for s, r in assigned: print(f"  sort_order {s:>3}  {r}")
    if a.after is not None:
        print("\nNOTE: inserting mid-page does not renumber existing feeds. Existing rails keep")
        print("their sort_orders; verify the resulting page order is what you intended.")

if __name__ == "__main__":
    main()
