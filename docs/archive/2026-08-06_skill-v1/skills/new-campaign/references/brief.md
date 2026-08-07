# Stage 3 · The Brief — the locked concept, in full

Begins only after the human has picked an angle from the Stage 1 landscape.

This is the artifact everything downstream is built from. It is **iterated, not approved** —
expect several rounds of the human cutting, correcting and adding. It is locked when the human
says it is locked, and not before.

---

## It is written as a Plain Statement

Every round of the brief is presented in the format defined in `plain_statement.md`: an outline
of bullets, plain language, no campaign voice. That format is not a preamble to the brief — it
IS the brief's format, at every round, including the final locked one.

---

## What the brief must answer

The six, each earning its place with evidence or an explicit assumption flag:

- **WHO** — who this is for, what they already know, what they are tired of, who it is not for
- **WHAT** — the condition and the tension, stated flatly. What is happening in the world
- **WHY** — why now, why it is real, and why it is ours rather than something any platform could
  run unchanged. **The test: could a competitor run this unaltered? If yes, keep working**
- **WHEN** — the window, and whether it stands or expires. What it hands off to afterwards
- **WHERE** — the territories in the world it touches, in plain nouns. Not collections
- **HOW** — the editorial approach: the point of view, what we would be saying, what the
  discovery experience feels like. Not the mechanics

Plus, always:

- **Evidence** — the data, each item labelled by type, with the unavailable things named as
  unavailable
- **Avoid** — banned words, banned concepts, territory a competitor owns
- **Open questions** — what is unresolved and what had to be assumed

---

## The name comes LAST, inside this stage

Only once the six are agreed. Derive it from the brief's own prose — the naming conventions and
the calibration bar live in `plain_statement.md`. Never generate a name cold.

Once the human confirms the name, derive `campaign_id` as `<slug>-<year>`. It is immutable from
that moment, and it is the first point at which anything is written to `campaigns/`.

---

## Still banned in the brief

No collections, no rails, no counts, no `sub_group`, no `sort_order`, no caps or floors, no CSV,
no reference to existing library contents. Structure is Stage 4. A brief that specifies structure
has skipped the argument it exists to have.

→ **GATE: the brief is locked, by the human, in words.** Only then does structure begin.
