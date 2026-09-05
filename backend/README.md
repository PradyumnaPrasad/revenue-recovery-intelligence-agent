# Revenue Recovery Intelligence Agent

Razorpay AI Buildathon 2026 — Track 03, AI Revenue Recovery.

> Fixed dunning ladders send the same four emails to every overdue invoice.
> This agent diagnoses *why* each invoice is stuck, scores every permitted
> action by time-discounted expected value net of the cost of acting, and
> submits that recommendation to a deterministic policy engine that has
> final authority — it can block, gate, or substitute the action, and it
> does. Approved actions execute through Razorpay's API under idempotency
> keys, and every step lands in a hash-chained audit ledger. When a
> customer replies, the agent reads it: a promise-to-pay suppresses
> outreach until the promised date, a dispute halts dunning entirely within
> one cycle. We measure ourselves against a no-contact holdout, so the
> number we report is *incremental* recovery with a confidence interval —
> not raw recovery, which would silently take credit for customers who'd
> have paid anyway.

Full design rationale, defect log, and day-by-day build history:
[`plan.md`](../plan.md) (one level up).

## The one sentence that matters

**The model ranks. The policy decides. The tools execute.** A model can
never produce a decision; a decision can never cause an uncontracted
effect; every effect is idempotent; every transition is logged. Everything
below exists to make that sentence true in code, not just in a pitch deck.

## What's real vs. simulated

Volunteered here, not discovered by a judge — it's the single most
dangerous question this kind of project invites, and the honest answer is
also the strongest one.

| Component | Status |
|---|---|
| Portfolio, customer history, inbound replies | **Synthetic** — seeded generator, every distribution published in `docs/generative_model.md` |
| Diagnosis, ranking, policy, audit, measurement | **Real code** — deterministic and reproducible |
| Reply understanding | **Real Gemini API calls**, schema-constrained, PII-redacted before every call |
| Razorpay payment links | **Real API calls**, test mode — a real link was created and paid in the Razorpay test dashboard |
| Webhook receipt + HMAC verification | **Real** |
| Whether a customer pays | **Simulated**, by a declared environment (`docs/environment.md`) — not hidden, published |
| Recovery probabilities | **Published priors** (`prior_v1`), not a trained model — see "Deliberately not used" below |
| Reported ₹ recovered | **Simulated cash, real decisions** — never described as merchant cash |

## Quick start

```bash
cp .env.example .env
# then fill in: GEMINI_API_KEY (free, aistudio.google.com), RAZORPAY_KEY_ID,
# RAZORPAY_KEY_SECRET (test mode), RAZORPAY_WEBHOOK_SECRET (any string you
# choose). Confirm your free-tier Gemini model at
# aistudio.google.com/rate-limit and set LLM_MODEL_SMALL/LLM_MODEL_LARGE —
# the ones in .env.example are what worked on 31 Aug 2026, but Google's
# free-tier lineup moves fast; re-verify if this is much later.

docker compose up -d
curl -X POST "http://localhost:8000/batches?size=500&seed=42"
python -m app.simulation.demo_batch   # the curated batch with all six diagnoses, for demos
open http://localhost:8000/            # the Recovery Command Center
```

No migration step — `create_all()` runs on startup (`make reset` for a
clean slate). See "Deliberately not used" for why.

```bash
make test       # 145 tests, pure Python + one live-DB-verified layer
make evaluate    # regenerates reports/evaluation.md from the declared seeds
```

## The eight-step loop

```text
OBSERVE  -> money is at risk (a RiskEvent — see app/sources/)
DIAGNOSE -> why is it stuck (six deterministic rules, R01-R06)
PREDICT  -> P(recover | action), from a published table, not a trained model
RANK     -> expected value: probability x collectible x time-discount x
            (1 - fatigue) - cost, plus an escalation ladder so it can't
            just re-pick the same top action every cycle forever
GOVERN   -> policy YAML has final authority: allow / block / substitute /
            require_approval, every matching rule collected, not just the
            first one
EXECUTE  -> real Razorpay calls, idempotency-keyed, or an internal record
LISTEN   -> a customer's reply goes through Gemini, schema-constrained,
            with a verbatim-quote check as a hard anti-hallucination
            guarantee
VERIFY   -> outcome vs. a no-contact holdout; every step already landed in
            the hash chain on the way past
```

The whole loop runs per-invoice via `/evaluate`+`/act`, or autonomously
across an entire batch via `POST /simulate/advance` + `POST /simulate/tick`
— the same decision code either way, just looped in the second case, with
`block`/`require_approval` outcomes still never auto-executed.

## What's actually been verified, not just claimed

- **Reply extraction accuracy: 90.6%** on 64 real fixtures against the live
  Gemini API (target was 85%), **100% exact-match** on date extraction,
  zero PII leaks. First run scored 81.2%/0% — both gaps were real bugs
  (a fixture bug and an underspecified category boundary), fixed, not
  worked around. See `plan.md` §6.8.
- **A real payment link created and paid** in the Razorpay test dashboard,
  closing the loop through a real HMAC-verified webhook.
- **Idempotency actually works** — verified by calling `/act` three times
  in a row and confirming the identical Razorpay link comes back every
  time, after catching and fixing a real bug where it didn't (two links
  were created from two calls before the fix — see `plan.md` F9).
- **The audit chain is genuinely tamper-evident** — edit a payload row
  directly in Postgres, `/invoices/{id}/audit/verify` flips to
  `intact: false`.
- **The holdout arm measures something real**: a 3-arm simulation (agent /
  fixed-cadence baseline / no-contact holdout) reports incremental recovery
  with a bootstrap 95% confidence interval, across three declared
  environments including one where the agent's own beliefs are
  deliberately wrong. `reports/evaluation.md` is regenerated from seeds,
  not hand-edited.
- **192/192 tests pass**, and 23 real defects (F1-F23 in `plan.md` §1.1)
  were found by actually running the system — not by code review — and are
  documented with root cause and fix, including several that would have
  produced financially, diagnostically, or evidentially wrong behaviour in
  production. F11 was found by a genuine cold-clone check (a fresh
  `git clone` into an isolated Docker environment, from zero); F12 was
  found by rehearsing the judge demo itself, clicking through the
  dashboard rather than reading the CSS; F13 was reported directly by a
  user clicking "Execute" and seeing no visible proof anything happened —
  the dashboard was silently wiping its own execution result before it
  could render; F14 followed immediately when the same user noticed the
  drafted messages F13 introduced had no recipient at all, despite real
  customer name/email already sitting in the DB; F15 and F16 were found
  while proving the Razorpay webhook loop closes end to end with a real
  test-mode payment — the webhook arrived but never actually updated the
  invoice (F15), and fixing that exposed the audit hash chain's
  tamper-evidence guarantee silently breaking under this project's frozen
  demo clock (F16), fixed with a genuine monotonic sequence column; F17
  was a wording fix on demo day — a failed real Razorpay call (this test
  account's amount cap) was mislabeled "Internal record only," confused
  with a genuinely internal, no-external-call action; F18 was the sharpest
  critique of the whole build — "offer_payment_plan drafts an email, but
  there is no plan" — fixed with `app/tools/plan_builder.py`: a real
  computed installment schedule, a real call slot, and a real account-
  manager assignment with an SLA, all flowing through to the dashboard as
  structured data, not just prose; F19 was the root cause behind F18 and
  behind "it feels like a chatbot, not an agent" — the process ran on a
  clock frozen at one instant forever, and the only way anything ever
  happened was a human clicking "Execute" per invoice. Fixed with a real
  autonomous orchestrator: `POST /simulate/advance` moves the clock,
  `POST /simulate/tick` runs diagnose→rank→govern→execute across an
  entire portfolio with no human touching each one — the exact same
  decision code `/act` uses, just looped, with `block`/`require_approval`
  outcomes still never auto-executed.

## Deliberately not used

Restraint is a signal, not an omission — this project's track explicitly
scores whether AI and infrastructure were applied appropriately rather than
forced.

- **A trained model.** The decision environment (`docs/environment.md`) is
  published to defeat circular evaluation. Training a classifier on
  samples drawn from an environment whose formulas are already printed in
  this repo would just be re-estimating numbers we wrote down — real
  engineering effort for zero new information. `prior_v1` is a published,
  deliberately-perturbed table behind the same `Predictor` interface a
  real model could later fill without changing any caller.
- **Alembic / a migration chain.** The demo always seeds from scratch;
  `create_all()` plus `make reset` is sufficient and a migration history
  would be pure ceremony with nothing to migrate.
- **APScheduler / Celery / Redis.** The "tick" that would drive a live
  scheduler is a plain function, invoked on demand — a Postgres table and
  an explicit call is strictly cheaper to run and easier to debug at this
  scale, and adding a broker here would be resume-driven architecture.
- **An LLM anywhere near the money.** It reads replies. It never chooses
  an action, sets a probability, authors financial terms, or computes a
  number that reaches the dashboard. Every one of those has a
  deterministic owner.
- **A frontend framework.** The dashboard is one server-rendered HTML file
  with vanilla JS — no build step, no second process, one URL for a judge.

## Known, honest gaps

- **The offline *measurement* report (`app/evaluation/simulate.py`,
  behind `reports/evaluation.md`) is a multi-touchpoint simulation, not
  driven by the live orchestrator** — it generates its own scripted
  touchpoints for statistical comparison across seeds, independent of
  `/simulate/advance`+`/simulate/tick`. The *live* system, by contrast,
  now has a real orchestrator (F19): `POST /simulate/advance` moves the
  process clock and `POST /simulate/tick` runs the full loop
  autonomously across an entire batch, no human clicking each invoice —
  built in direct response to "I want an end-to-end agent." F20 was found during a pre-submission verification sweep: the
  exact `make reset` + reseed sequence this README documents crashed a
  live API server (`asyncpg` prepared-statement cache holding stale type
  OIDs from before the reset) — fixed at the connection level
  (`statement_cache_size: 0`), not with a note nobody reads. F21 added
  real SMTP sending for `send_reminder`/`offer_payment_plan` (redirected
  to the operator's own inbox, gated so the autonomous tick can never
  spam it) after direct feedback to "make it real." F22 — the most
  severe live bug found in this build — was surfaced by wiring up
  `POST /invoices/{id}/replies`: a synchronous Gemini call inside an
  `async def` endpoint with no timeout froze the ENTIRE server, not just
  that request, for every user, for minutes. Fixed with
  `asyncio.to_thread` and a bounded `HttpOptions(timeout=15000)`.
- ~~Reply extraction has no HTTP endpoint yet~~ **Resolved (F22):**
  `POST /invoices/{id}/replies` now runs a real Gemini call on live input,
  applying real domain effects (`Invoice.dispute_flag`, a real
  `PromiseToPay` row, `Customer.suppressed`) so the next `/evaluate` on
  that invoice genuinely reflects what the customer said. The dashboard
  has a live "Customer reply" box wired to it.
- **`checkout_abandonment` is a genuine stub, not a live surface.** It
  proves the `RiskSource` protocol generalizes beyond invoices (a
  different domain object, ~30 lines, zero pipeline changes) but returns a
  fixed declared list, not a real query. `payment_failure` and
  `subscription_dunning` are named in the architecture but not built at
  all.
- **The chaos switch is real and demoable** (`POST /demo/chaos`, a live
  DEGRADED banner on the dashboard) but only covers the LLM and Razorpay
  paths — there's no equivalent for, say, a database outage.

## API surface

```text
GET  /health
GET  /                                   the Recovery Command Center

POST /batches?size=&seed=
GET  /batches
GET  /batches/{id}/summary
GET  /invoices?batch_id=
GET  /invoices/{id}
GET  /invoices/{id}/diagnosis
POST /invoices/{id}/evaluate             diagnose + rank + govern, no execution
POST /invoices/{id}/act                  execute the policy-approved action, idempotent
GET  /invoices/{id}/audit
GET  /invoices/{id}/audit/verify
POST /invoices/{id}/replies              real Gemini extraction on live input; applies
                                          dispute_flag/PromiseToPay/suppression for real

POST /webhooks/razorpay                  HMAC-verified, deduped by x-razorpay-event-id

GET  /evaluation/summary?seed=&size=&env=

GET  /demo/chaos
POST /demo/chaos?llm=&razorpay=          the graceful-degradation switch

POST /simulate/advance?days=&hours=      moves the process clock forward
POST /simulate/tick?batch_id=            runs the full loop autonomously across every
                                          open invoice in a batch -- no human clicks
```

## Running the test suite yourself

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

145 tests, almost all pure Python with no database — the one exception
(`app/sources/receivables.py`) is verified live against the running
Postgres container instead of through pytest, since it uses JSONB/enum
columns pytest's usual sqlite fallback doesn't support; the live
verification (5 repeated ticks, zero duplication) is recorded in `plan.md`.
