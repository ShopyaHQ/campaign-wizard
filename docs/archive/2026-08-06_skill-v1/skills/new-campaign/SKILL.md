---
name: new-campaign
description: >
  Run the Shopya new-campaign wizard: a slow, checkpoint-gated process that surveys what is
  happening in the world, works a chosen angle into a locked brief, and only then builds the
  structure and curates the products underneath it. Use whenever the user says "new campaign",
  asks to start or plan a campaign, asks to populate /explore rails, asks for a campaign
  concept, or invokes /new-campaign.
---

# New Campaign

Orchestration only. The rules live in `CLAUDE.md` (always true); the stage references evolve.

## What Shopya is — read before writing a single line

**Shopya is discovery. Trend-led, visual — Pinterest meets fashion.** People come to browse, to
see what is moving, to find something they did not know to look for. They are not arriving with a
purchase intent to fulfil.

So: **we are never "selling" anything.** A campaign is a lens on what is happening, not an offer.
The unit of value is the find, not the transaction. Copy that reads like a retailer's seasonal
push is off-brand even when it is well written. If a line would sit comfortably in a department
store email, it is wrong here.

## The cardinal rule — one step at a time

This process is deliberately slow, and its order is the whole point. **Every run goes through the
same stages in the same order, every single time.** Do not compress two stages into one output
because the answer feels obvious. Do not front-run a later stage "just to show where this goes."
Laying out steps and then not respecting them is worse than having no steps.

### Structure silence

**Until the brief is locked at Stage 3, structure does not exist.** Never mention, imply or
plan: how many collections · how many rails · `sub_group` or vertical tagging · `sort_order` ·
render caps, the ≥12 floor, the >50 target · the CSV · admin execution · what is already in the
product library.

These are all real and all downstream. Raising them during concept work collapses the work into
merchandising, which is this wizard's most common and most expensive failure. If a structural
question is genuinely blocking, record it as an open question — do not answer it.

## Read first, every run

- `CLAUDE.md` — identity, ownership map, non-goals, delivery paths
- `references/landscape.md` — Stage 1: how to survey angles
- `references/plain_statement.md` — the format and voice every concept output is written in
- `references/brief.md` — Stage 3: what a locked brief must answer
- `references/naming_and_seo.md` — the quality bar and the three-layer naming model.
  **Stage 3 only, and only after the six are agreed**
- `references/interview.md` — the fixed question set
- `references/render_rules.md` and `references/csv_contract.md` — **Stage 4 and later. Do not
  open these during concept work**
- the canonical contract at the path named in `CLAUDE.md` — **if it disagrees with anything
  here, the contract wins**

---

## The stages

Each ends in a gate. Do not cross a gate without the human. Do not merge stages.

### 1 · Landscape — what is happening
Per `references/landscape.md`. Survey the world our users are in, from several angles at once.
Return **six to eight candidate angles**, flat and unranked, each with its evidence labelled by
type. No names. No structure. No reference to the existing library.

→ **GATE: the human reacts to the spread** — kills, merges, redirects, or picks. Expect several
rounds. Never push toward a pick.

### 2 · Interview — the human's context
Once an angle is chosen, run `references/interview.md` against it: window, audience, what it must
never be, first-party data. This is where `avoid_terms` comes from, and it must exist before any
line of copy is generated.

→ **GATE: answers captured.**

### 3 · Brief — the locked concept
Per `references/brief.md`, written in the `plain_statement.md` format: bulleted outline, plain
language, no campaign voice. Answer WHO · WHAT · WHY · WHEN · WHERE · HOW, with evidence and
explicit assumption flags.

**This is a workshop, over as many rounds as it takes.** Present, take the cuts, re-present.
Locked means the human said the word, not that a round went un-objected-to.

**The name comes last, inside this stage**, derived from the agreed brief's own prose per
`naming_and_seo.md`. Then `campaign_id` = `<slug>-<year>`, immutable, confirmed by the human.
This is the first moment anything is written to `campaigns/<campaign-id>/`.

→ **GATE: the brief is locked in words by the human.**

### 4 · Structure — collections, rails, tags
**Only now.** Read `render_rules.md`. Propose the shape: which collections, which rails, how
many, `sub_group`, `sort_order` slotted against the live probe, tags. Rail count N comes with its
evidence split — what is fillable from the library today versus what needs a fresh scrape.
Names woven with the confirmed `seo_targets`: collection names editorial, rail names preview
hooks, sharing keyword territory and differing.

Instantiate the seam ledger: you produce seam 6. Name the five seams someone else must dress.

→ **GATE: structure approved.**

### 5 · Probe & scope
`python3 scripts/probe_feeds.py --group explore` — play the live catalog back. Never ask what is
live; never cache it. Confirm the additivity check: campaign rails stay under roughly a third of
the resulting slice.

→ **GATE: scope agreed.**

### 6 · Scrape & curate
Zero questions. **Invoke the sibling curation engine** — do not write a new scraper. Consult its
`brand_fetch_config.yaml` and climb its fetch ladder; observations append to its log. Curate to
target depth, never below the render floor. Lint every generated line against `avoid_terms`.

→ **GATE: curation reviewed.**

### 7 · Assemble
One question: pin depth past the render cap, and tail policy. Write the CSV to
`campaigns/<campaign-id>/products.csv` per `references/csv_contract.md`.

→ **GATE: CSV delivered.**

### 8 · Execute & verify
**Re-probe first** — the Stage 5 probe may be days stale and `sort_order` collisions surface
on-page, not in the CSV. The HUMAN executes in admin: create collection → add products → create
the feed. After the cache window (~10 min) verify the live surface. Emit `handoff.md` for the
five seams this tool does not own — a first-class deliverable, not a courtesy.

→ **GATE: run closed.** Freeze `campaigns/<campaign-id>/`; a revision is a new campaign id.

---

## Hard gates

- no agreed angle → no interview
- no `avoid_terms` → no generated copy, and the lint has nothing to enforce
- no locked brief → no name, no `campaign_id`, no structure
- no `campaign_id` → nothing is written to `campaigns/`
- no approved structure → no scraping
- any rail below the render floor → flagged before delivery, never discovered on-page
- a rail without exactly one source collection, or a collection without a rail → authoring error

## What you work out yourself — never ask

The live state of the page (probe it), `sort_order` slotting, slug derivation, and the
`campaign_id` format. Derive, then have the human confirm.

## Scope boundary

This skill covers the concept and the CSV. Product-library metadata maintenance — real-time
inventory, sizing, colours — is a **separate tool and a separate effort**. Do not build, plan,
or absorb any of it here.
