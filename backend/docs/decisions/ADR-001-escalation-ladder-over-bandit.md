# ADR-001: Escalation ladder over a contextual bandit

## Status
Accepted.

## Context
Greedy argmax on expected value re-picks the same top-ranked action every
cycle forever — send the same reminder indefinitely if it's the highest-EV
choice, never escalating even as an invoice ages. The theoretically
correct fix for this kind of sequential decision problem is a contextual
bandit or a finite-horizon Markov decision process: something that learns
or plans over the whole trajectory, not just the current tick.

## Decision
We use a fixed escalation ladder instead:
`send_reminder → resend_payment_link → send_upi_payment_link →
schedule_call → offer_payment_plan → escalate_to_am`. An invoice may move
at most one rung forward per cycle, never backward, subject to a per-action
cooldown and a hard cap of two executions of the same action ever.

## Why
A bandit or MDP would likely capture more of the available sequential
value in principle. But on this track, three other properties matter more
than that marginal optimality:

- **Explainability.** "You're on rung 3 because rungs 1 and 2 didn't work
  and their cooldowns have passed" is a sentence a finance team can verify
  by hand. A learned policy's action isn't.
- **Auditability.** The ladder's state (current rung, cooldown remaining,
  execution count) is three plain facts you can show on a dashboard and
  reconstruct after the fact from the audit log. A bandit's internal state
  is a set of parameters, not a fact.
- **Bounded behaviour.** The "never skip more than one rung" and "max two
  executions ever" rules are the literal implementation of the track
  brief's word "bounded" — a hard ceiling on what the agent can do without
  a human, independent of the ranking or policy layers.

## Consequences
This is a deliberately simpler answer than the field's state of the art,
chosen because the track rewards auditability and explainability over
squeezed-out optimality. If a real deployment later wanted to close that
gap, the ladder could become the *initial* policy an actual bandit is
initialized from — the ladder captures most of the value; naming that
trade-off out loud here is the point of this record.
