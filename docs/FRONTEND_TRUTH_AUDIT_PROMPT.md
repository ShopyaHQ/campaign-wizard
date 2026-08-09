# FRONTEND/SANITY TRUTH AUDIT — run this prompt in the shopya-frontend repo (+ Sanity studio)
# Purpose: establish implementation truth for the Phase 1 multi-surface + content requirement.
# Method: same provenance discipline as the 2026-08-06 audit — every claim cites file+lines or
# a live probe; unknown is an acceptable answer; never infer from docs alone.

Report, with citations:
1. sub_group enum: exact location(s) (types, validation, DB constraint?). Cost of adding
   `outdoors_sports`: frontend-only change, or backend/API/DB migration too? What breaks if a
   feed carries an unknown sub_group today?
2. Per-surface rail capacity: is there ANY hard limit on feeds per group or per sub_group
   (query limits, pagination, layout)? What is the practical maximum before UX degrades?
3. Default/All composition: does any mechanism exist for prominence beyond global sort_order
   (featured flags, hero slots, per-surface ordering)? Is sort_order per-group only, or can
   ordering differ between All and a vertical view?
4. Content rails: can the feed system carry a non-product entity today (exact enum of feed
   entity types + what the renderer does with each)? What exactly renders an S5 editorial
   injection (component, position on page, cap enforcement location)? Is the cap of 2 code,
   config, or Sanity query?
5. Sanity `post` schema: FULL field list (title, dek/standfirst, body, cover image, campaign
   tag, category/vertical fields, publish state, anything else). Can one post target multiple
   surfaces/verticals? What field would carry a vertical assignment today?
6. Content cards: which fields does the rendered card actually display (title/image/dek/...)?
   Where do card cover images come from?
7. Per-vertical editorial slots: does the package/skin model (S1) support per-sub_group
   variants of header/dek/editorial content anywhere in SurfacePackage or its consumers?
8. For each Phase 1 output (product rails per vertical, default composition, content rails on
   default, content rails per vertical, vertical headers): classify execution-capable today /
   handoff-capable today / required — technically blocked, and name the SMALLEST
   implementation change that unblocks each blocked item (per owner rulings R1-R4:
   no arbitrary feed cap, outdoors_sports as new sub_group, multi-placement collections,
   content beyond S5 cap 2).
9. Collection multi-placement (R3): what today ties a feed to "its" collection? Could two
   feeds (different sub_groups/titles) legitimately present the same collection's products —
   what breaks (view-all, analytics, dedupe)?
10. include_ids order survival (pending_validation include_ids_order_survives): any new
    evidence path — can a staging feed be created and read back to verify order?
