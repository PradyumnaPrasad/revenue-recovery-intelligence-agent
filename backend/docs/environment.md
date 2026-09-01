# Declared decision environment

This document mirrors `app/simulation/environment.py` exactly — every
number here is a number in that file. This is the fix for what plan.md
calls C1 (circular evaluation): the original design trained a model on a
hidden simulator and then evaluated it against the same simulator, which
proves the pipeline runs without crashing and proves nothing about whether
the resulting decisions recover money. Publishing the environment converts
"trust us" into "here is exactly what we assumed — check it yourself, and
watch what happens when we deliberately assume wrong" (see E_shift and
E_adversarial below).

## The claim this lets us honestly make

> Given this declared environment, the decision layer captures Y% of the
> available uplift over a fixed-cadence baseline, and it degrades gracefully
> when the environment is mis-specified.

Not: "this agent recovers X% more money in the real world." That claim
would require real merchant data we don't have. The claim above is smaller,
true, and falsifiable by anyone who reads this file.

## What the model is never allowed to see

`app/domain/features.py::ALLOWED_FEATURE_KEYS` is a closed set: invoice
facts + diagnosis code + candidate action, nothing else. No environment
name, no base probability, no segment multiplier, no self-cure rate.
`sample_outcome()` returns an `Outcome(recovered, days_to_cash)` — the
probability that produced `recovered`, and the delay distribution that
produced `days_to_cash`, are both discarded, not logged, not returned.
`tests/property/test_no_leakage.py` asserts this structurally, not just by
convention.

## The recovery-probability formula (every environment uses this shape)

```text
p_effective = base_prob[diagnosis][action]
              * segment_multiplier[segment]
              * amount_factor(amount_paise)
              * fatigue_factor(contact_count_30d)
              * (escalation_smb_penalty if action == escalate_to_am and segment == "smb" else 1.0)

amount_factor(amount)   = clip(1 - amount_decay_coefficient * max(0, log10(amount_rupees) - 4), 0.55, 1.0)
fatigue_factor(contacts) = max(0.35, 1 - fatigue_coefficient * contacts)

p_effective is clipped to [0.02, 0.95] and used as a Bernoulli parameter.
```

## E_train — the base environment

The model is trained and calibrated on samples from this environment only
(`TRAIN_SEEDS` = 101-110, `CALIBRATION_SEEDS` = 201-205). `segment_multiplier`
= `{smb: 0.90, mid_market: 1.00, enterprise: 1.10}` (bigger, more
process-driven customers pay a bit more reliably once contacted).
`fatigue_coefficient = 0.08`. `escalation_smb_penalty = 1.0` (no penalty).

Base table (`_BASE_RECOVERY_PROB` in code) — the "declared belief" about
which action works best for which diagnosis:

| Diagnosis | reminder | resend_link | upi_link | payment_plan | escalate | call |
|---|---:|---:|---:|---:|---:|---:|
| process_delay | 0.45 | 0.50 | 0.52 | 0.30 | **0.55** | 0.48 |
| cash_flow_risk | 0.18 | 0.22 | 0.24 | **0.40** | 0.35 | 0.30 |
| chronic_non_payment | 0.05 | 0.06 | 0.07 | 0.15 | **0.28** | 0.20 |
| channel_failure | 0.10 | 0.15 | **0.38** | 0.12 | 0.30 | 0.33 |
| standard_overdue | 0.28 | 0.33 | **0.35** | 0.25 | 0.32 | 0.30 |
| disputed | 0.05 | 0.05 | 0.05 | 0.05 | 0.10 | 0.08 |

(Disputed rows exist only so the environment is total — the policy engine
routes disputed invoices away from all of these actions before the ranking
layer ever runs.)

## Self-cure — the holdout arm's ground truth (fix for F2)

The table above answers "what happens if we take this action." It has no
answer for "what happens if we do nothing" — and without one, a no-contact
holdout arm recovers exactly 0% by construction, which silently collapses
"incremental recovery" back into raw recovery: precisely the inflated number
a holdout exists to prevent. `p_self_cure()` is that missing number.

```text
p_self_cure = clip(self_cure_base[segment]
                    * exp(-days_overdue / self_cure_halflife_days)
                    * (1 - 0.6 * prior_late_payment_rate),
                    0.01, 0.60)

self_cure_base        = {smb: 0.30, mid_market: 0.23, enterprise: 0.15}
self_cure_halflife_days = 32.0
```

Three declared beliefs, in order: larger, more process-driven accounts
self-cure *less* often (not because they're less reliable, but because
release is a slower, less discretionary internal process, and they need
proactive cash-flow help less than they need the invoice to reach the top
of a queue); the longer nothing happens the less likely a spontaneous
payment becomes (exponential decay); and a worse payment history lowers the
odds regardless of segment. Measured across a 3,000-invoice portfolio
(seed 42), mean self-cure lands at **11.3%**, comfortably inside the
declared plausible band of 8–25%, and stable within 0.2pp across three
independent seeds. As a sanity check (not a hard guarantee — see the code
comment), self-cure sits below the best available action's probability for
97.8% of a sampled portfolio: acting should usually beat doing nothing, and
mostly does.

This is a deliberately independent estimate, not derived from the action
table above by subtraction (an earlier design decomposed every action cell
into "self-cure plus lift," but retuning all 36 cells by hand added
mechanical risk this build's schedule didn't have room for, for no gain in
what the holdout arm actually needs — a plausible, non-zero, sensibly-
varying no-action baseline).

## The time axis — when does recovered cash actually land? (fix for F3)

`sample_outcome()` no longer returns a bare boolean. Every recovery also
samples **when**:

```text
days_to_cash ~ Gamma(shape=2, scale=mean_days[action] / 2), clipped [1, 180]
              (only sampled when recovered = True; None otherwise)

mean_days[action]:
  send_upi_payment_link   2
  resend_payment_link     3
  send_reminder           5
  schedule_call           8
  escalate_to_am         12
  offer_payment_plan     60
```

Gamma(2, ·) puts most outcomes near the mean with a realistic right tail — a
few invoices pay very late even on the fastest rail. This is the
environment's **true** generative delay, deliberately a separate object
from whatever the (not-yet-built) ranking layer *believes* about
`days_to_cash` in its own expected-value formula: the environment is
ground truth, the ranker's belief is an input the agent works from, and
keeping them as two objects that happen to be initialised similarly is what
makes the E_shift/E_adversarial robustness tests mean anything. The holdout
arm's own delay (`sample_no_action_outcome`) reuses the slowest action's
delay shape (`offer_payment_plan`'s mean of 60 days) rather than inventing a
second, unjustified distribution for "nothing happened, then it resolved
anyway."

## E_shift — a mis-specified world (`EVALUATION_SEEDS` only, never trained on)

Every base-probability cell is multiplied by a **fixed, declared** per-action
factor (not sampled at runtime — this is a checked-in alternate world, not
noise):

| Action | Multiplier | Direction |
|---|---:|---|
| send_reminder | ×1.40 | reminders work much better than E_train assumed |
| resend_payment_link | ×0.85 | slightly worse |
| send_upi_payment_link | ×1.10 | slightly better |
| offer_payment_plan | ×0.60 | notably worse |
| escalate_to_am | ×0.65 | **inverted** — the model was trained believing this is the best action for chronic cases; here it's mediocre |
| schedule_call | ×1.15 | slightly better |

`segment_multiplier` also flips direction: `{smb: 1.05, mid_market: 0.95,
enterprise: 0.90}` — small accounts respond better here, the opposite of
E_train. `amount_decay_coefficient` raised to `0.05` (larger invoices decay
faster).

## E_adversarial — model is confidently wrong; policy has to save it

Same base table as E_train, but:

- `fatigue_coefficient = 0.24` (tripled) — repeated contact suppresses
  recovery far faster than the model was trained to expect.
- `escalation_smb_penalty = 0.45` — escalating to an account manager
  **actively hurts** recovery for SMB customers (reads as disproportionate),
  the opposite of what E_train taught the model (escalation is usually
  good).

**What we expect, and what we report:** under E_adversarial, the model's
recommendations get measurably worse. The question this environment answers
is whether the *policy engine* — contact caps (P03), the action ladder's
cooldowns, the daily action budget (P09) — limits the damage regardless.
If it does, "policy overrides model" is a demonstrated safety property, not
a slogan on a slide.

## Regenerating the datasets

```bash
python -m app.simulation.build_datasets
```

Produces `data/train.jsonl`, `data/calibration.jsonl`, and
`data/eval_{E_train,E_shift,E_adversarial}.jsonl`. Deleting `data/` and
rerunning reproduces byte-identical files, because every random draw in the
pipeline — portfolio generation, historical-policy action sampling, and
outcome sampling — is seeded, never wall-clock.
