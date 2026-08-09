# NAMING CONVENTIONS — owner-locked SSOT, 2026-08-07
# Three separate identities; no filename ever does more than one job.
#   campaign_id  human identity      almost-fall-2026
#   run_id       machine identity    cmp_01KZ... (immutable ULID, unchanged — identity_002)
#   build_id     execution revision  b001, b002, ... (sequential per run, immutable)

## Locked rules
| Object            | Convention                                          | Example |
|-------------------|-----------------------------------------------------|---------|
| Display name      | human editorial name                                | Almost Fall |
| Campaign ID       | lowercase kebab-case ASCII, usually year-qualified  | almost-fall-2026 |
| Campaign folder   | exactly campaign_id                                 | campaigns/almost-fall-2026/ |
| Run ID            | immutable cmp_<ULID>                                | cmp_01KZ... |
| Run folder        | run_id, nested under campaign                       | runs/cmp_01KZ.../ |
| Working artifacts | stable concise names, no campaign/date prefixes     | stage4_brief.yaml |
| Build ID          | sequential per campaign/run                         | b001 |
| Portable asset    | <campaign_id>__<asset>__<build>__<UTC ts>.<ext>     | almost-fall-2026__products__b001__20260807T091753Z.csv |
| latest/final      | NEVER in filenames — build identity handles it      | — |
| Rebuild behavior  | immutable new build; b001 is never overwritten      | b002 |

## Campaign ID formation
Never the display name directly (punctuation, drift). Lowercase, kebab-case, ASCII,
hyphens only, year suffix when time-bound: almost-fall-2026, holiday-hosting-2026.

## Directory model (LOCKED; implementation is next-pass — see NEXT_PASS_SCOPE)
campaigns/<campaign_id>/campaign.yaml + runs/<run_id>/... expresses the real domain model
(campaign -> one or more runs -> artifacts/builds). Unnamed kickoffs live in
campaigns/_drafts/<run_id>/ and are PROMOTED once campaign_id locks — a controlled
lifecycle operation, not a rename. Prerequisite: artifact registration stores paths
relative to the RUN ROOT (path: stage1_signals.yaml) so moving the container invalidates
nothing. campaign.yaml carries campaign_id, display_name, created_at, current_run_id,
status, and the runs list with purpose (original | revision | ...).

## Working artifacts
Keep boring. The path provides identity. Never almost-fall-2026_stage1_signals_2026-08-07.yaml.

## Execution / exported assets
Self-describing and immutable. Never export bare products.csv as the durable artifact.
Build id answers "which approved build" (admin imported b002); timestamp answers "exactly
when produced". Every build emits a manifest:
<campaign_id>__execution-manifest__<build>__<ts>.yaml with campaign_id, display_name,
run_id, build_id, built_at, products_file, products_sha256, rails, products, validation,
and later execution.executed_build.

## Handoffs
Working copy inside the run keeps its concise seam name (handoffs/S1_campaign_header.md).
Anything leaving the project gets a portable release name:
almost-fall-2026__campaign-header__b001.md.

## Controlled asset vocabulary (agents never invent labels)
execution (the master worklist — canonical since b003) · products (retired at b003) ·
curated (internal) · execution-manifest · campaign-header · activation-brief ·
collection-handoff (retired at b003 — folded into execution) · verification-report ·
review-book (the per-campaign line-by-line review document)
Banned label words: final, latest, new, revised, use-this.

## Review book (added 2026-08-09 — owner catch: recurring deliverable, needs identity)
Every campaign has one review book. Two forms, per the working-vs-portable rule:
- WORKING copy: runs/<run_id>/review_book.md — boring canonical name, always the current state.
- REVIEW ROUNDS: immutable snapshots per round in runs/<run_id>/review/ named
  <campaign_id>__review-book__r001__<UTC ts>.md — r-series is the REVIEW revision counter
  (parallel to but distinct from b-series execution builds: r = what the owner reviewed,
  b = what execution built). A round snapshot is cut when the book goes to the owner; the
  owner's annotated copy joins the same round. Never overwrite a round; next review = r002.
