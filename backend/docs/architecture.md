# Architecture

Razorpay AI Buildathon 2026 — Track 03, AI Revenue Recovery. Full design
history and defect log: `plan.md`, one level up. This document is the
as-built map of the system.

## The invariant

```text
The model produces a RANKING.
The policy engine produces a DECISION.
The tool registry produces an EFFECT.

A model can never produce a decision. A decision can never produce an
uncontracted effect. Every effect is idempotent. Every transition is
logged.
```

Every layer below exists to make this true structurally — not just true by
convention. Three concrete examples: `app/domain/features.py`'s
`to_feature_vector()` has a function signature that physically cannot
accept an environment parameter, so the ranking model cannot see the
oracle even by accident. `app/domain/policy/types.py`'s `SubstitutionTarget`
is a plain string specifically so policy can redirect execution to a
target (`route_to_dispute`) that was never a candidate for the AI's
ranking in the first place. `app/db/models.py::Action`'s
`idempotency_key` carries a real database `UNIQUE` constraint, not an
application-level check — a duplicate insert fails at the database, it
doesn't get caught and ignored later.

## The loop

```text
  RISK SOURCE                    ┌──────────────────────────────┐
  (overdue invoice,              │  1. OBSERVE                  │
   abandoned checkout,           │  normalise → RiskEvent       │
   ...)                          └──────────────┬───────────────┘
                                 ┌──────────────▼───────────────┐
                                 │  2. DIAGNOSE                 │
                                 │  R01-R06 ordered cascade      │
                                 └──────────────┬───────────────┘
                                 ┌──────────────▼───────────────┐
                                 │  3. PREDICT                  │
                                 │  prior_v1 — published table   │
                                 └──────────────┬───────────────┘
                                 ┌──────────────▼───────────────┐
                                 │  4. RANK                     │
                                 │  time-discounted EV + ladder  │
                                 └──────────────┬───────────────┘
                                 ┌──────────────▼───────────────┐
                                 │  5. GOVERN   ← FINAL AUTHORITY│
                                 │  policy YAML: allow / gate /  │
                                 │  block / substitute           │
                                 └──────────────┬───────────────┘
                                 ┌──────────────▼───────────────┐
                                 │  6. EXECUTE                  │
                                 │  Razorpay, idempotency-keyed  │
                                 └──────────────┬───────────────┘
                                 ┌──────────────▼───────────────┐
                                 │  7. LISTEN                   │
                                 │  Gemini extraction, verified  │
                                 └──────────────┬───────────────┘
                                 ┌──────────────▼───────────────┐
                                 │  8. VERIFY                   │
                                 │  outcome vs. holdout; audit   │
                                 └───────────────────────────────┘
```

Every arrow writes an audit event. There are no unlogged transitions.

## Layer-by-layer, as built

### Risk sources — `app/sources/`

`RiskSource` (`base.py`) is a `Protocol`: `key: str` and
`async def detect(session, now) -> list[RiskEvent]`. `RiskEvent`
(`app/domain/types.py`) is deliberately generic — `reference_id`, not
`invoice_id` — so a surface that isn't an invoice at all can satisfy the
same shape.

- `ReceivablesSource` — real, DB-backed. Verified live against the running
  Postgres: 5 repeated calls against unchanged data return the identical
  set of 540 invoices every time, proving idempotent emission (no
  duplicate `RiskEvent`s from repeated polling).
- `CheckoutAbandonmentSource` — a genuine ~30-line stub over a declared,
  fixed list, proving the protocol generalizes to a domain object with no
  due date, no dispute flag, no payment history.
- `RISK_SOURCES` (`registry.py`) — one dict. Adding the stub cost one line
  here plus the 30-line adapter, with zero changes anywhere else in the
  pipeline.

### Diagnosis — `app/domain/diagnosis.py`

Six mutually-exclusive, ordered rules (R01–R06), first match wins, every
`InvoiceFacts` maps to exactly one `Diagnosis`. The order is a business
call, not alphabetical — disputed dominates everything; chronic outranks
channel-failure and cash-flow because it changes the action set, not just
the wording; channel-failure outranks cash-flow because an unopened
payment link tells you nothing about a customer's finances. Property-tested
(every input produces exactly one code) and table-tested (one fixture per
threshold boundary).

### The declared environment — `app/simulation/environment.py`,
`docs/environment.md`

Every probability this project's evaluation depends on is published, not
hidden — the fix for the classic failure mode where a model trained on a
simulator is then evaluated against the same simulator and "wins" by
construction. Three declared worlds: `E_train` (the base belief),
`E_shift` (a fixed, checked-in alternate belief — action effectiveness
perturbed, one ranking partially inverted), `E_adversarial` (fatigue
tripled, escalation actively backfires for SMB — tests whether the
*policy* layer, not the model, is what keeps the system safe when its
beliefs are confidently wrong).

`p_self_cure()` is the holdout arm's ground truth — an independent
estimate of "what happens with no action at all," declining with days
overdue and a worse payment history, varying by segment. Verified: mean
11.3% across a 3,000-invoice portfolio, inside the declared 8–25%
plausible band, stable within 0.2pp across three seeds and all three
environments.

`Outcome(recovered, days_to_cash)` gives every sampled outcome a time
axis — `Gamma(shape=2, scale=mean/2)` per action, a realistic right tail
around a declared mean (2 days for a UPI link, 60 for a payment plan).

### Prediction — `app/ml/priors.py`

`prior_v1`: the environment's own action ordering, per diagnosis,
deliberately perturbed by a fixed ±15% (seeded, reproducible) — not equal
to the environment's true table, because equal would make it an oracle.
No trained model exists in this codebase; see the README's "deliberately
not used" section for why that's a considered choice, not a gap.

### Ranking — `app/domain/ranking.py`, `config/actions.yaml`

```text
value = p × collectible × time_discount × (1 − fatigue) − cost
```

`fatigue = min(0.6, 0.15 × contact_count_30d)` — soft, never zeroes an
action; hard stops are policy's job. The escalation ladder
(`send_reminder → resend_payment_link → send_upi_payment_link →
schedule_call → offer_payment_plan → escalate_to_am`) constrains
*sequential* choice: no more than one rung forward per cycle, never
backward, cooldowns per action, max two executions of the same action
ever. A contextual bandit or finite-horizon MDP would be the theoretically
correct answer; the ladder was chosen instead because it's explainable to
a finance team and auditable, which matter more on this track than
optimality (ADR-001).

### Policy — `app/domain/policy/`, `policies/default.yaml`

Policy is data, not code — a YAML file with ten rules (`P01`–`P10`, minus
`P04`/`P07`, cut under this build's compressed schedule per the plan's own
pre-decided cut ladder), evaluated by `simpleeval`'s
`EvalWithCompoundTypes` over a fixed, whitelisted fact namespace
(`diagnosis`, `customer`, `invoice`, `action`, `batch`) — never `eval()`,
verified empirically: `__import__(...)` raises `FunctionNotDefined`,
`().__class__.__bases__[0].__subclasses__()` raises `FeatureNotAvailable`.
Every rule is evaluated; every match is collected; conflicts resolve by
severity (`block > substitute > require_approval > allow`) — "blocked for
three reasons" is a better audit record than "blocked."

### Execution — `app/tools/`, `app/api/invoices.py::act_on_invoice`,
`app/api/webhooks.py`

`create_payment_link()` is raw `httpx` against Razorpay's documented
contract, not the `razorpay` SDK's unverified method names — proven live,
not assumed: a real test-mode link (`plink_TWR8Y8WeMFwpxV`) was created
before any wrapper code existed. Idempotency is a real database `UNIQUE`
constraint on `Action.idempotency_key`; a successfully `executed` action
is returned unconditionally on any later call, `attempt_no` only
increments on a prior *failure* — found and fixed live after an earlier
version double-executed on a second call (F9 in `plan.md`). The webhook
receiver verifies `X-Razorpay-Signature` via `hmac.compare_digest` before
parsing JSON at all, and dedups by the `x-razorpay-event-id` *header*
(verified against Razorpay's own docs — not, as an earlier draft assumed,
a body field).

### Reply intelligence — `app/llm/`

One LLM seat in the entire system: reading a customer's reply, nothing
else. `redact.py` strips emails/phones/GSTIN/long digit runs before any
text leaves the process — verified against the real template corpus, zero
leaks. `reply_extraction.py` calls Gemini via `client.interactions.create()`
with a schema-constrained `response_format`, requires the model's
`evidence_quote` to be a verified verbatim substring of what it actually
saw (rejected otherwise — a cheap, hard anti-hallucination guarantee), and
routes anything under 0.6 confidence to a human queue instead of acting.
Real spot-check against the live API: 90.6% intent accuracy, 100% date
exact-match, 0 PII leaks (`plan.md` §6.8 — including the two real bugs
found and fixed to get there).

`chaos.py` / `app/tools/registry.py`'s `is_razorpay_down()` are the
graceful-degradation switch (`POST /demo/chaos`): either a deliberate
toggle or a genuine unexpected failure degrades extraction to
`fallback.py`'s keyword classifier at a fixed confidence of 0.5 —
deliberately below the 0.6 acting threshold, so a fallback classification
is *never* acted on automatically, and Razorpay failures transition an
action to `failed` rather than raising, ready for the state machine's
retry path.

### Audit — `app/audit/`

Per-invoice SHA-256 hash chain: `hash = sha256(prev_hash +
canonical_json(payload))`. `verify_chain()` recomputes every link;
mutating one payload row anywhere in the chain makes `/audit/verify`
return `intact: false` — demonstrated live by editing a row directly in
Postgres.

### Measurement — `app/evaluation/`

Three arms, assigned by `sha256(invoice_id + salt) % 100` — deterministic,
not RNG, so the split can't be re-rolled until it looks good. Both the
agent and the fixed-cadence baseline get the *same* four scripted
touchpoints (day 1, 7, 15, 30); the agent's choice at each is real
diagnosis-and-ladder-informed ranking, the baseline's is a fixed script
regardless of diagnosis. This equal-opportunity design replaced an earlier
version that gave the agent one decision and the baseline four — which
made the agent look 33 points worse for having fewer chances, not worse
judgement (a defect caught before it could become a false claim in a
report). `reports/evaluation.md` is regenerated by `make evaluate`, with a
bootstrap 95% CI on every reported metric, across all three declared
environments.

### Dashboard — `app/templates/dashboard.html`

One server-rendered HTML file, vanilla JS, no build step. Four things on
screen at once, each mapped to a scored criterion: the highest-EV action
shown struck through next to whatever policy actually chose (compliant
escalation); the action-budget meter (bounded workflow); the live 3-arm
recovery chart with CI whiskers (measured recovery); the chain-verified
audit timeline (audit trail). The DEGRADED banner polls `/demo/chaos`
every 3 seconds so flipping the switch from a terminal shows up live with
no page reload.

## Data model

See `app/db/models.py` for the authoritative schema. The two tables worth
calling out specifically: `AuditEvent` (`prev_hash`/`hash`, the tamper-
evident chain) and `Action` (`idempotency_key` with a real `UNIQUE`
constraint — the mechanism, not just the policy, that prevents a
double-send).

## Honest gaps

See the README's "Known, honest gaps" section — not duplicated here to
avoid the two documents drifting out of sync with each other.

## Decision records

`docs/decisions/` — ADR-001 (escalation ladder over a contextual bandit),
ADR-002 (published priors over a trained model), ADR-003 (no broker, no
framework, no vector DB), ADR-004 (Gemini over Claude for the one LLM
seat — a pragmatic constraint, not a technical judgment that one is better
suited than the other).
