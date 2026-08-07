# Deliverable 2 — the CSV

One row per product. **Critical = the minimum that lets the human execute the three admin
steps and QA a row at a glance.** Join keys are `collection_name` and `product_url` — records
are created in workflow order, so ids never appear.

| Column | Role |
|---|---|
| `campaign_id` | join label, from Deliverable 1 |
| `collection_name` | which collection this product belongs to — join key for admin steps 1 + 2 |
| `rail_name` | reference to the rail block in Deliverable 1 |
| `collection_rank` | **curation ranking -> rail order.** Drives `include_ids` order, which IS what shoppers see on the rail. It does NOT control collection-page display order — no rank field or reorder endpoint exists in the public API today |
| `pinned` | is this row in the rail's top set (the feed's `rules.include_ids`) |
| `product_url` | direct link — creation input, and the dedupe/lookup key against the library |
| `product_name` | creation input |
| `brand` · `price` · `currency` · `image_url` | QA-at-a-glance |

Optional tail: `notes` for QA context. Raw scrape JSON-LD is kept **alongside** the CSV, never
inside it.

**Do not grow these columns.** Anything richer belongs to the separate metadata/inventory
tool. A CSV that drifts toward a full product-enrichment payload has absorbed scope that isn't
this tool's.

`sort_order` is a property of the RAIL, not of a product. It lives in Deliverable 1 and is
never repeated per row — repeating it invites contradiction between rows.

## The admin endpoints these map onto

Confirmed from `openapi.json`:

- `POST /collections` — name required
- `POST /collections/{id}/items` — product_id
- `POST /products` — url + name required
- `POST /admin/feeds` — `FeedCreate`: entity / group / slug / name, plus `rules.include_ids`
  for pins, `sort_order`, and the window fields
- `POST /admin/feeds/preview` — dry-run before committing

Execution order in admin: **create collection → add products to it → create the feed.**

## Verifies — resolved 2026-08 against shopya-frontend + admin-develop

1. **Collection item ordering — NO rank mechanism.** `CollectionItemUpdate` has no position
   field, the items listing takes `page`/`size` only, and no reorder endpoint exists. So
   `collection_rank` is a curation ranking that drives rail order, not collection-page order.
   **Tell the human not to hand-sequence collection inserts expecting on-page order.**
2. **`include_ids` order SURVIVES.** Pinned items float to the top in array order (CASE on the
   array index), then the tail follows `sort_field`. Pinning is real; keep `rail_position`.
3. **`is_active` DOES gate the public catalog** — admin needs `include_inactive=true` to see
   inactive feeds. Windowed scheduling (`active_from`/`active_until`) is **unverified** — the
   evaluating logic is backend-side and unreadable. One throwaway-feed test settles it.
4. **View-all destination** — no `source_collection_id` on the feed model; hardcoded to
   `/feeds/{feedId}`. Filed ask. Do not promise collection linking.
