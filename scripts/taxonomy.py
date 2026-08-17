#!/usr/bin/env python3
"""taxonomy.py — the CAMPAIGN-NEUTRAL taxonomy view (task §25, closes AF-008).

docs/CATEGORY_TAXONOMY.md is the platform SSOT category registry, but each node line ends in a
historical Almost Fall selection marker (`SEL` = selected that campaign · `avail` = not selected ·
plus split-note annotations). Reading the registry for a legitimate campaign-neutral purpose
(enumerating verticals / requestable category_ids for a fresh brief) unavoidably exposed the
operator to the historical Almost Fall selection set — a real isolation gap for a run whose whole
purpose is proving INDEPENDENT generation.

This module produces the registry a FRESH campaign generates against, with the per-node campaign
selection markers REMOVED. Canonical ids + durable metadata (display · boundary/exclusions ·
rationale · strength · coverage · season) are preserved; the historical AF selection state is
available ONLY through `historical_selection()`, never mixed into the generation input.

`neutral_registry()` is the sanctioned generation input. It carries NO `SEL`/`avail` marker on any
node. The regression tests assert that.

Node line format (docs/CATEGORY_TAXONOMY.md):
    <id> · <display> · <boundary -> exclusions> · <why-durable> · <strength> · <coverage> · <season> · <AF marker>
The AF marker is the LAST ` · ` field. A split-note annotation may follow the SEL/avail word in
parentheses; that whole trailing field is campaign-specific and is stripped from the neutral view.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("SHOPYA_CAMPAIGN_ROOT", os.path.dirname(HERE))
TAXONOMY_MD = os.path.join(ROOT, "docs", "CATEGORY_TAXONOMY.md")

SEP = " · "
# the campaign-specific trailing markers (case-insensitive first token of the last field)
_AF_MARKER_TOKENS = ("sel", "avail", "avail-candidate")

# vertical header -> canonical vertical_id (schema surface_006 closed set + men's fashion)
_VERTICAL_HEADERS = {
    "WOMEN'S FASHION": "fashion",
    "MEN'S FASHION": "fashion",
    "HOME & INTERIOR": "home_interior",
    "TECH & ELECTRONICS": "tech",
    "BEAUTY & GROOMING": "beauty",
    "TRAVEL & LUGGAGE": "travel",
    "OUTDOORS & SPORTS": "wellness_health",
}


def _is_node_line(line):
    """A node line starts with an id token (letters/dot) then ` · `."""
    if SEP not in line:
        return False
    head = line.split(SEP, 1)[0].strip()
    return bool(head) and all(c.isalnum() or c in "._-" for c in head) and "." in head


def _looks_like_marker(field):
    """Is this trailing field an Almost Fall selection marker (possibly annotated)?"""
    token = field.strip().split()[0].lower() if field.strip() else ""
    token = token.strip("().,")
    return token in _AF_MARKER_TOKENS


def _parse_nodes(text):
    """Parse the registry into structured nodes, capturing the raw AF marker separately."""
    nodes = []
    current_vertical = None
    current_header = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            header = line[3:].strip()
            # strip a trailing "(N nodes)" count
            header_key = header.split("(")[0].strip().rstrip(",").strip()
            current_header = header_key
            current_vertical = _VERTICAL_HEADERS.get(header_key)
            continue
        if line.startswith("#") or not line.strip():
            continue
        if not _is_node_line(line):
            continue
        fields = [f.strip() for f in line.split(SEP)]
        af_marker = None
        if fields and _looks_like_marker(fields[-1]):
            af_marker = fields[-1]
            fields = fields[:-1]
        node = {
            "category_id": fields[0],
            "display_name": fields[1] if len(fields) > 1 else None,
            "boundary": fields[2] if len(fields) > 2 else None,
            "why_durable": fields[3] if len(fields) > 3 else None,
            "strength": fields[4] if len(fields) > 4 else None,
            "coverage": fields[5] if len(fields) > 5 else None,
            "season": fields[6] if len(fields) > 6 else None,
            "vertical": current_vertical,
            "source_header": current_header,
            "_af_marker": af_marker,      # historical only — NEVER in the neutral view
        }
        nodes.append(node)
    return nodes


def _load_text(path=None):
    p = path or TAXONOMY_MD
    with open(p, encoding="utf-8") as f:
        return f.read()


def neutral_registry(path=None):
    """The SANCTIONED campaign-neutral generation input (task §25). Every node carries canonical id +
    durable metadata and NO campaign selection marker. Fresh generation reads THIS."""
    nodes = _parse_nodes(_load_text(path))
    neutral = []
    for n in nodes:
        neutral.append({k: v for k, v in n.items() if k != "_af_marker"})
    return {
        "registry_kind": "campaign_neutral",
        "note": "Canonical durable-collection registry with per-node campaign selection markers "
                "REMOVED. Historical Almost Fall selection state is NOT present. This is the fresh-"
                "generation input (task §25 / AF-008).",
        "verticals": sorted({n["vertical"] for n in neutral if n["vertical"]}),
        "nodes": neutral,
    }


def requestable_category_ids(vertical=None, path=None):
    """The canonical category_ids a fresh campaign may select from, optionally scoped to a vertical.
    No selection markers — availability is 'in the registry', not 'selected in some past campaign'."""
    nodes = neutral_registry(path)["nodes"]
    if vertical:
        nodes = [n for n in nodes if n["vertical"] == vertical]
    return [n["category_id"] for n in nodes]


def historical_selection(campaign="almost_fall", path=None):
    """The historical AF selection state, kept SEPARATE from the generation input (task §25). This is
    evidence/audit only; it must never be passed into fresh generation. Returns {category_id: marker}.
    """
    nodes = _parse_nodes(_load_text(path))
    return {n["category_id"]: n["_af_marker"] for n in nodes if n["_af_marker"]}


def assert_neutral(registry):
    """Guard used by generation paths + tests: raise if any node still carries a selection marker or
    the raw marker key leaked into a neutral registry."""
    for n in registry.get("nodes") or []:
        if "_af_marker" in n:
            raise ValueError("taxonomy contamination: node %r still carries _af_marker"
                             % n.get("category_id"))
        # defensive: no value field may equal a bare marker token
        for k, v in n.items():
            if isinstance(v, str) and v.strip().lower() in _AF_MARKER_TOKENS:
                raise ValueError("taxonomy contamination: node %r field %r == marker %r"
                                 % (n.get("category_id"), k, v))
    return True


if __name__ == "__main__":
    import json
    reg = neutral_registry()
    assert_neutral(reg)
    print("campaign-neutral registry: %d nodes across %s"
          % (len(reg["nodes"]), reg["verticals"]))
    print("sample:", json.dumps(reg["nodes"][0], indent=2, ensure_ascii=False))
    hist = historical_selection()
    print("\nhistorical AF selection (SEPARATE, audit-only): %d marked nodes" % len(hist))
