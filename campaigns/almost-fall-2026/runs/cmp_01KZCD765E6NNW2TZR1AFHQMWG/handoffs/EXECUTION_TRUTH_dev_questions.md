# HANDOFF · Execution-path truth questions (owner -> dev/live-system owner), 2026-08-07
Purpose: establish whether the 27 non-Shopify-capturable Almost Fall pins are POTENTIAL or
CONFIRMED ingest blockers. Do not infer from repo plans; answers must come from the live system.

1. Are the 36 Almost Fall pinned products already present in Shopya's live/staging product catalog or DB?
2. If a product is not present, what is the supported ingestion path today?
3. Can admin create/import a product using PDP URL, retailer external ID, SKU, or another identifier?
4. Is `products_catalog.jsonl -> shopya_feed.ndjson -> DB upsert` an implemented production workflow or only a planned/unexecuted pipeline?
5. If implemented, what command/service actually performs the DB upsert?
6. What fields are minimally required for an ingest-ready product?
7. What identifier does feed creation ultimately reference: internal product ID, external ID, URL, or something else?
8. Where are image, price/currency and variants hydrated during that process?

Classification on answers: already in catalog | supported ingest path exists | missing ingest capability (true launch blocker).
