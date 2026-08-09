---
name: new-campaign
description: >
  Plan a Shopya campaign end to end and produce the Seam 6 execution package. Use when the user
  says "new campaign", asks to start or plan a campaign, asks to populate /explore rails, asks
  for a campaign concept, or invokes /new-campaign.
---

# New Campaign

**This skill deliberately contains no stage list.** The process is defined in
`schemas/workflow_state.schema.yaml` and it changes. Any stage list written here would be stale
within a pass — that is exactly what happened to the version now in `docs/archive/`.

## Do this

1. **Read `CLAUDE.md`.** It sets the authority order and the two rules that are always true.
2. **Read `schemas/workflow_state.schema.yaml`.** It is the only process authority: the states,
   their entry prerequisites, the legal transitions, the predicate vocabulary, `settable_paths`,
   and the refusals. Do not infer the process from anywhere else.
3. **Start or resume a run.**
   - `python3 scripts/run.py new` — a fresh campaign
   - `python3 scripts/run.py status --run <run_id>` — where an existing run stands and which
     transitions are legal from here
4. **Mutate state only through supported commands.** `record-decision`, `register-artifact`,
   `set`, `transition`. Never edit `state.yaml`.
5. **Stop at genuine owner-decision gates.** A transition whose prerequisites include
   `owner_decision_recorded` needs a human. Present what they need to decide, then stop. Do not
   record it for them, and do not treat agreement in passing as a decision.
6. **Use `SHOPYA_CONTENT_CHARTER.yaml` for editorial and merchandising rules** — voice, naming,
   the three-object model, collection roles, product selection logic, content quality. It is
   approved and binding; numeric technical requirements are referenced to the campaign charter.

## When a transition is refused

Report the failed predicates verbatim, with their paths and expected values. A refusal is
information about the work, not an obstacle to route around. The canonical state is untouched
by a refusal, so nothing is lost by stopping.

## Scope reminder

You author across seams; you execute Seam 6 only. Everything else produces a handoff brief that
is never described as implemented.
