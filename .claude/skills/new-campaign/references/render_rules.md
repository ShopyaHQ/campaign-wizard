# Render + planning rules

Contract §3 is authoritative. If this file disagrees with it, the contract wins.

## Where rails land

**`/explore` only, today.** Campaign *identity* (skin, hero, copy) can dress `/explore`,
`/home` and `/discover` together — but `/home` and `/discover` are pre-migration and cannot
receive authored rails. A rail plan for them has nowhere to land.

## The feed fields, and what each one means on the page

| Field | Meaning |
|---|---|
| `name` | rendered **verbatim** as the rail's on-page title. Display-grade editorial copy only — never an internal label |
| `sort_order` | vertical position, sorted **globally across all entities** in the group. Unique and deliberate. Duplicates fall back to an arbitrary-but-stable id tie-break — treat that as an authoring error. Re-sorted within a filtered vertical view; relative order preserved, no gaps |
| `entity` | `products` · `collections` · `brands`. Determines the card type |
| `sub_group` | the vertical axis. Closed set: `fashion` · `home_interior` · `tech` · `beauty` · `travel` · `wellness_health` |
| `slug` | stable, kebab-case. **No semantics in suffixes** — no `trending--fashion--v2`. The other fields carry all meaning |

## Sub-group semantics

**Tagging adds a home; it does not scope away from All.** A tagged rail shows on its vertical
*and* on the All landing. An untagged rail shows on All only. Toolbar pills are derived from
the sub_groups present — authoring the first feed for a vertical makes its pill appear.

## Rail count invariants

1. **Floor** — ≥12 products per rail, all from that rail's own source collection.
2. **Identity** — one rail = one collection = one curation run.
3. **Additivity** — rails are additive to a live page. `sort_order` is global and the frontend
   renders every feed in the catalog, so nothing stops a 6-rail campaign doubling the page. The
   Stage-2 probe must state the resulting total; campaign rails stay under ~a third of the S6 slice.
4. **Band** — 1–4 campaign rails **per `/explore`**, default 2–3. **Not per vertical.**

**Surface = `/explore`. Settled 2026-08 against the frontend.** Pills are URL writes that
re-query the server (`?category_slug` -> `sub_group`); the vertical fetch is EXCLUSIVE and
returns only feeds tagged that sub_group, re-sorted within the filtered set. The unfiltered
"All" landing returns everything, tagged and untagged.

Consequence: **the All landing IS the page.** Every rail you author appears there, so the band
and the one-third check both run against All. A `sub_group` tag does not spend extra budget —
it makes the same rail *also* appear on its vertical view, where it competes only with that
vertical's feeds. **Never plan 1-4 rails per vertical; that is 24 rails and it is wrong.**

N is proposed by the wizard with evidence and approved at the `seo_targets` gate. Availability
informs N; it is never N. These are **S6-only numbers** — the rendered page also carries
editorial rails, banners and modules this tool does not touch.

## Membership floor

**12 products per rail.** Below the render cap the feed resolves empty and is **silently
dropped** from the page — no error, no gap, it just isn't there. If a rail is missing on the
live surface, check membership before anything else.

Count only members that are actually available. Twelve members of which four are dead links or
sold out is a rail that ships broken.

Render caps by entity: products 12 · collections 10 · brands 12.

## The rail ↔ collection convention

Every product rail has **exactly one source collection** and all its items come from that
collection. One rail = one collection = one curation run.

**View-all does NOT open the collection today — not implemented.** The feed model carries no
`source_collection_id` (public wire shape is `{id, slug, name, sort_order, sub_group}`), and the
destination is hardcoded to `/feeds/{feedId}` in `CatalogRails.tsx` — the same products in a
plain grid. A filed backend + frontend ask.

**Do not describe rail -> collection linking as working.** The authoring convention still holds
in full; only the link destination lags. Say "view all opens `/feeds/{feedId}`" until the field
ships.

## Naming

Both the rail name and its collection name are built from the same `seo_targets`. Neither is
"the SEO one."

- **Collection name** — the editorial title AND the SEO asset. The collection page is the
  rankable unit: one page, one subject, its own H1. Keywords live here.
- **Rail name** — the preview hook. A heading on `/explore`, which carries twenty headings about
  twenty things and will not rank for any of them. Its job is **CTR**, not ranking. Voice lives here.

See `naming_and_seo.md` for the three-layer model and the keyword-in-the-noun formula.
- They must differ, even subtly. A character-for-character duplicate is an authoring error; a
  deliberately unrelated pair is equally wrong.

## Campaign

Campaign never appears in a user-facing axis — not in a slug, not in a group, not in a
sub_group. The `campaign` param on `GET /feeds` is backend-blocked and not built. Author
untagged default feeds; do not simulate campaigns through any other field.

## Delivery paths

| Path | Available | Mechanism |
|---|---|---|
| `evergreen` | **now** | no window; standing content |
| `dark-author -> flip` | **now** | feeds are born `is_active: false` (admin create form default). Author dark, human flips live. `is_active` provably gates the public catalog — admin must pass `include_inactive=true` to see inactive feeds |
| `scheduled` | **pending one test** | `active_from`/`active_until` exist end-to-end, but no readable code proves the PUBLIC catalog evaluates the window (that logic is backend-side). **Verify first:** author a throwaway feed with `active_until` in the past and `is_active: true`; if the public catalog omits it, `scheduled` is real. Timezone unverified — assume UTC and confirm in the same test |
| `registry` | future | Sanity campaign-registry resolve; frontend build not started |
| `tagged` | future | `campaign` param on `GET /feeds`; backend-blocked |

Offer `evergreen` and `dark-author -> flip` as the certain paths. Offer `scheduled` only as
pending-one-test, and say so. `registry` and `tagged` remain unbuilt — never put them in front
of the human.

## Pinning is real — `include_ids` order survives to the render

The pinned array's ORDER is the manual display order. The API's `build_order_by` floats pinned
items to the top of the public feed in exactly that sequence (a CASE on the array index), then
the rule-matched tail follows `sort_field`. Reorder the array, reorder the feed.

So `rail_position` maps 1:1 onto `include_ids` order. Pinned items lead; `sort_field` governs
only what comes after them.
