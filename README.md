# Revenue Recovery Intelligence Agent

Razorpay AI Buildathon 2026 — Track 03, AI Revenue Recovery.

> Fixed dunning ladders send the same four emails to every overdue invoice,
> whether it's a reliable customer a day late or a repeat defaulter three
> months in. This agent diagnoses *why* each invoice is stuck, scores every
> permitted action by time-discounted expected value net of the cost of
> acting, and submits that recommendation to a deterministic policy engine
> that has final authority — it can block, gate, or substitute the action,
> and it does. Approved actions execute through Razorpay's real API under
> idempotency keys, and every step lands in a hash-chained, tamper-evident
> audit ledger. When a customer replies, the agent reads it: a
> promise-to-pay suppresses outreach until the promised date, a dispute
> halts dunning entirely within one cycle. We measure ourselves against a
> no-contact holdout, so the number we report is *incremental* recovery
> with a confidence interval — not raw recovery, which would silently take
> credit for customers who'd have paid anyway.

**The model ranks. The policy decides. The tools execute.** That one
sentence is this project's whole architecture — everything else exists to
make it true in code, not just in a pitch.

## Where everything lives

| | |
|---|---|
| **Full design rationale, defect log, day-by-day build history** | [`plan.md`](plan.md) |
| **Setup, quick start, verified numbers, API surface** | [`backend/README.md`](backend/README.md) |
| **As-built architecture, layer by layer** | [`backend/docs/architecture.md`](backend/docs/architecture.md) |
| **Why we didn't train a model, use a framework, or use Claude** | [`backend/docs/decisions/`](backend/docs/decisions/) |
| **Pitch video script** | [`video_script.md`](video_script.md) |

## In one breath

- Six deterministic diagnosis rules, not a black box — every decision comes
  with an evidence trail.
- Ranking by risk-adjusted expected value against a **published** decision
  environment, not a trained model hiding what it learned.
- A policy engine, evaluated from YAML, that can override the model's own
  top-ranked action — and does, on camera, in the demo.
- Real Razorpay payment links, real HMAC-verified webhooks, real
  idempotency — verified live, not assumed from reading the code.
- Reply understanding via Gemini, schema-constrained, with a
  verbatim-quote check as a hard anti-hallucination guarantee, PII-redacted
  before any call leaves the system.
- A three-arm measurement (agent / fixed-cadence baseline / no-contact
  holdout) so the headline number is incremental recovery, not raw
  recovery inflated by customers who'd have paid anyway.
- 27 real defects found by actually running the system — not by code
  review — each documented with root cause and fix in `plan.md`, including
  a silent break in the audit chain's tamper-evidence guarantee found
  while proving a real Razorpay webhook closes the loop end to end, and
  turning "offer_payment_plan drafts an email" into a real computed
  installment schedule after direct user feedback, and building a real
  autonomous orchestrator (`/simulate/advance` + `/simulate/tick`) that
  runs the full loop across an entire portfolio with no human clicking
  each invoice, after feedback the demo "feels like a chatbot, not an
  agent."
- 196/196 tests passing, confirmed inside a genuine cold-clone check: a
  fresh `git clone` into an isolated Docker environment, from zero.

Start with [`backend/README.md`](backend/README.md) to run it yourself.
