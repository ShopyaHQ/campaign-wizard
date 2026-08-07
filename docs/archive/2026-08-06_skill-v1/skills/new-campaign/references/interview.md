# Stage 1 · Define — the locked interview

Run this verbatim, in order, every run. Five questions, then the recon.

Open by stating what you will NOT ask, so the human doesn't waste effort on it:

> **What I won't ask you:** the current state of the page (I probe `GET /feeds?group=explore`
> fresh), `sort_order` slotting against the live order, slug derivation, and the `campaign_id`
> format — I derive `<slug>-<year>` and you confirm it.

---

## 1 · Surfaces & territory

**1a. Campaign identity.** The skin, hero and copy can dress `/explore`, `/home` and
`/discover` together. Which do you want it on?

**1b. Rails — state, do not ask.** Rails land on **`/explore` only** today. `/home` and
`/discover` are pre-migration and cannot receive authored rails, so there is nothing to
decide. Say this; never offer rail placement elsewhere.

**1c. Verticals.** Default **"All"** (untagged), or vertical-tagged from the closed set —
`fashion` · `home_interior` · `tech` · `beauty` · `travel` · `wellness_health`?

Carry this semantic explicitly: **tagging adds a home, it doesn't scope away from All.**
A tagged rail shows on its vertical *and* on the All landing. Untagged shows on All only.

**1d. Rail count — do NOT ask this cold.** You propose N in the recon output, not here.
Ask only what you cannot derive: is there a reason this campaign should sit at the top or the
bottom of the band? Otherwise say nothing and bring a number with evidence after the recon.

Guardrails you are proposing inside (state them if the human asks):
floor ≥12 products per rail from its own collection · one rail = one collection = one curation
run · campaign rails no more than ~a third of the S6 slice, made concrete by the Stage-2 probe ·
band 1–4 per surface, default 2–3.

---

## 2 · Moment & window

- What's the moment — a season, a holiday, a cultural event, or standing content?
- Which delivery path:
  - **`evergreen`** — no window, stands until retired. Certain.
  - **`dark-author -> flip`** — feeds are born inactive; you flip them live when ready. Certain.
  - **`scheduled`** — `active_from`/`active_until` set in admin. **Pending one verification test**;
    say so rather than offering it as settled.
- If scheduled or windowed: live dates.
- Is there a phase after this one it should hand off to?

> `registry` and `tagged` are unbuilt — never put them in front of the human.
> Budget note for 1c: the band is 1-4 rails **per `/explore`**, not per vertical. Tagging a rail
> to a vertical does not buy extra budget; it gives the same rail a second home.

---

## 3 · The idea, in one line

- What is this campaign actually about — the feeling or the behaviour, not the category list.
- What should a shopper *do differently* because they saw it?
- Any line you already like? Say it even if it's rough — **locked copy beats copy I invent.**

---

## 4 · Audience

- Who is shopping this?
- Taste level and price posture — aspirational, accessible, or a ladder across both?
- What do they already own or already know, **so we're not selling them the obvious**?
- Anyone this is explicitly *not* for?

---

## 5 · What it must never be

- Banned **words and phrases** — these are grepped against every generated line, so **stems
  help** ("school", "dorm").
- Banned **concepts** — tonal traps a word list cannot catch.
- Anything a competitor owns that we should stay off?

---

## Then: the SEO recon

**Strictly after Q5.** The avoid-list must exist first so it constrains what you propose —
never bring back keyword territory that sits on the banned list.

Read `naming_and_seo.md` first — the method, what counts as real data, and the quality bar.

**A campaign is never built on a search query.** Keyword findings are evidence that a tension is
real; the campaign is a point of view. Do not hand back a filter label dressed as a concept.

**Ask before assuming:** does the client have first-party search data — site search logs, Search
Console? That beats every external proxy.

Posture: **marketing & SEO expert.** Research live what is actually trending in this
territory right now — current keywords and search phrases, rising products, editorial
roundups, what is selling out, what has cultural traction. Build the concept FROM that
signal rather than decorating it afterwards.

---

## Then: the Plain Statement — the first thing the human sees

Read `plain_statement.md` and write it before anything else leaves your hands.

Stage 1 hands back **three** things, in this order:

1. **The Plain Statement** — the concept in flat language, as an outline of bullets, six required
   sections. **No name, no tagline, no rail or collection title anywhere in it.**
2. **`seo_targets`** — keywords and phrases, each carrying its evidence, folded into section 3 of
   the statement. Evidence that a tension is real, never the idea and never a keyword dump.
3. **Proposed N** — the rail count, with the evidence split: how many are fillable ≥12 from the
   existing library today, how many need a fresh scrape, and the estimated effort. Inside the
   1–4 band, default 2–3. Never inflated to make the campaign feel bigger — the other five seams
   do that job.

**Not returned at Stage 1: the campaign name, `campaign_id`, or any rail or collection name
candidate.** The id is `<slug>-<year>` derived from the name, and the name is derived from the
agreed statement — so all of it belongs to Stage 3. Do not front-run it, and do not slip a
"just as an example" name into the statement.

→ **GATE: the human reacts to the Plain Statement.** Not "approves" — *reacts*. Cut the bullets
they argue with, add what is missing, re-present. It is agreed when the thinking is right, not
when it sounds good. Close every presentation by saying plainly that no name has been chosen
yet, and asking whether the thinking holds.
