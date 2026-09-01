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
- **150/150 tests pass**, and 12 real defects (F1-F12 in `plan.md` §1.1)
  were found by actually running the system — not by code review — and are
  documented with root cause and fix, including two that would have
  produced financially or diagnostically wrong behaviour in production.
  F11 was found by a genuine cold-clone check (a fresh `git clone` into an
  isolated Docker environment, from zero); F12 was found by rehearsing the
  judge demo itself, clicking through the dashboard rather than reading
  the CSS.

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

- **The measurement is a multi-touchpoint simulation, not a live
  orchestrator.** Both the agent and the baseline get the same four
  scripted touchpoints and the agent's choice at each is real
  diagnosis-and-ladder-informed ranking — but there's no scheduler
  advancing real elapsed time yet. `app/evaluation/simulate.py`'s module
  docstring says so directly.
- **Reply extraction has no HTTP endpoint yet.** `app/llm/reply_extraction.py`
  is real and tested, but nothing exposes `POST /invoices/{id}/replies`
  to trigger it on a live invoice — only the offline spot-check
  (`python -m app.llm.spot_check`) exercises it end to end today.
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

POST /webhooks/razorpay                  HMAC-verified, deduped by x-razorpay-event-id

GET  /evaluation/summary?seed=&size=&env=

GET  /demo/chaos
POST /demo/chaos?llm=&razorpay=          the graceful-degradation switch
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
