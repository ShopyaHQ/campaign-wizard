#!/usr/bin/env python3
"""probe_feeds.py — read the LIVE feed catalog. Never cache the result.

    python3 scripts/probe_feeds.py --group explore [--base URL] [--json]

sort_order is global across the group, so new rails must slot into the live order.
This is Stage 2's first action and MUST be re-run immediately before Stage 6 execution —
the Stage 2 probe goes stale and collisions surface on-page, not in the CSV.
"""
import argparse, json, sys, urllib.request, urllib.error
from collections import defaultdict

DEFAULT_BASE = "https://api-staging.shopya.app/api/v1"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

def fetch(url, timeout=20):
    # A 403 here is a Cloudflare edge rule, not auth — CF bot scoring commonly keys on UA.
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": UA,
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def flatten(payload):
    """The catalog is entity -> group -> [feeds]. Return a flat list of feed dicts."""
    out = []
    def walk(node, entity=None, group=None):
        if isinstance(node, dict):
            if "sort_order" in node and ("slug" in node or "name" in node):
                out.append({**node, "_entity": entity, "_group": group}); return
            for k, v in node.items():
                walk(v, entity if entity else k, group if entity else None) if not isinstance(v, list) \
                    else walk(v, entity or k, group or k)
        elif isinstance(node, list):
            for x in node: walk(x, entity, group)
    walk(payload)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", default="explore")
    ap.add_argument("--sub-group")
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--json", action="store_true", help="emit raw JSON instead of the playback")
    a = ap.parse_args()

    url = f"{a.base}/feeds?group={a.group}" + (f"&sub_group={a.sub_group}" if a.sub_group else "")
    try:
        payload = fetch(url)
    except urllib.error.HTTPError as e:
        hint = ("\n  403 = Cloudflare edge rule, not auth. The API is public and returns 200\n"
                "  from a normal dev machine. Either allowlist this egress IP in Cloudflare, or\n"
                "  run `curl '" + url + "'` on the dev machine and pass the JSON to\n"
                "  slot_sort_order.py --live." ) if e.code == 403 else ""
        sys.exit(f"PROBE FAILED {e.code} — {url}{hint}\nDo not proceed on a stale or assumed catalog.")
    except Exception as e:
        sys.exit(f"PROBE FAILED — {url}\n{e}\nDo not proceed on a stale or assumed catalog.")

    if a.json:
        print(json.dumps(payload, indent=1)); return

    feeds = flatten(payload)
    print(f"=== LIVE CATALOG — group={a.group} ({len(feeds)} feeds) ===")
    print(f"    {url}\n")
    by_order = sorted(feeds, key=lambda f: (f.get("sort_order", 10**6), str(f.get("slug"))))
    seen = defaultdict(list)
    for f in by_order:
        seen[f.get("sort_order")].append(f.get("slug") or f.get("name"))
        vert = f.get("sub_group") or "— (All only)"
        print(f"  {str(f.get('sort_order')):>4}  {str(f.get('_entity') or ''):<11} "
              f"{str(f.get('name'))[:44]:<44} {vert}")
    dupes = {k: v for k, v in seen.items() if len(v) > 1}
    print()
    if dupes:
        print("  !! SORT_ORDER COLLISIONS — authoring errors, not features:")
        for k, v in sorted(dupes.items(), key=lambda x: (x[0] is None, x[0])):
            print(f"     sort_order {k}: {', '.join(map(str, v))}")
    else:
        print("  sort_order: no collisions")
    taken = sorted({f.get("sort_order") for f in feeds if isinstance(f.get("sort_order"), int)})
    print(f"  taken slots: {taken}")
    verts = sorted({f.get("sub_group") for f in feeds if f.get("sub_group")})
    print(f"  verticals live (pills showing): {verts or 'none — All landing only'}")

if __name__ == "__main__":
    main()
