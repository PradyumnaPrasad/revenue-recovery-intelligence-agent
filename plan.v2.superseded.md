# Revenue Recovery Intelligence Agent — Implementation Plan (v2)

> Supersedes `project.md`. This document is the single source of truth for
> implementation. It is written to be executed top-to-bottom by an AI coding
> agent (Claude Sonnet) with a human reviewing each milestone gate.
>
> **Target:** Razorpay AI Buildathon 2026 — *AI Revenue Recovery* track.
> **Track brief:** "Build an agent that detects revenue at risk, determines the
> right intervention, and executes a **bounded** recovery workflow."
> **Judged on:** measured recovery amounts, explainable money actions, audit trails.
> **Deliverables:** public repo + 5-minute pitch video + architecture doc.

---

## 0. How to use this document

Each layer below has three fixed sections:

- **Contract** — the exact types/signatures to implement. Do not improvise these.
- **Rules** — the logic, stated unambiguously.
- **Done when** — the acceptance criteria. A layer is not complete until every
  bullet passes. Write the test *before* claiming the layer is done.

Build in milestone order (§11). Do not start a milestone until the previous
milestone's gate passes. Do not add features not in this document — scope creep
is the primary failure mode for a hackathon build.

---

## 1. Critique of `project.md` — what changes and why

The original design is unusually strong for a hackathon: the deterministic
diagnosis layer, policy-over-model authority, idempotency-from-day-one, and the
explicit honesty rule about simulated outcomes are all correct instincts that
most submissions will not have. Keep all of them.

These are the defects that would cost marks, ordered by severity.

| # | Defect | Why it matters | Fix (layer) |
|---|---|---|---|
| **C1** | **Circular evaluation.** Training labels are sampled from a hidden simulator with hardcoded per-action probabilities; the model then learns those probabilities; then the "intelligent policy beats baseline" claim is evaluated against *the same simulator*. The agent is guaranteed to win by construction. | This is the single biggest threat. A judge with ML background spots it immediately, and it invalidates the headline number the track is scored on. | §6.4 — reframe the simulator as a **declared decision environment**, publish its generative model, and add **environment-shift stress tests** (train on env A, evaluate on mis-specified env B/C). Claim only what is true. |
| **C2** | **No incrementality measurement.** The plan measures recovery rate, not *incremental* recovery. Some invoices get paid regardless of what the agent does. | The track scores **measured recovery amounts**. Attributing self-cure to the agent is the classic recovery-product lie, and it is the easiest thing for a judge to attack. | §6.11 — mandatory **holdout control arm** (10–20% no-action / fixed-cadence). Headline metric becomes **incremental ₹ recovered**, with a confidence interval. |
| **C3** | **No LLM anywhere in the architecture.** The system is logistic regression + if-statements. | This is an **AI** buildathon on an **agentic** track. A rules engine is defensible engineering but does not read as an agent. | §6.3 + §7 — add three LLM roles that are genuinely better than rules and all sit **off the money path**: inbound-reply understanding, grounded message generation, novel-case diagnosis fallback. |
| **C4** | **Inbound replies are ignored entirely.** The loop only sends; it never listens. Outcomes are limited to "paid / no response". | Real B2B receivables fail because replies ("we'll pay after PO approval on the 15th", "wrong GST number") land in a black hole. This is the highest-value missing capability and it is exactly where an LLM earns its place. | §6.3 — new **Reply Intelligence** layer: extract promise-to-pay, dispute signal, objection class, and requested-doc from free text, as structured output. |
| **C5** | **Expected-value formula is wrong.** `EV = p × invoice_amount` ignores action cost, that a payment plan does not collect the full amount now, time-value of cash, relationship/annoyance cost, and the fact that this is a *sequential* decision, not a one-shot one. | Greedy argmax on this formula will spam the single highest-EV action forever, and will over-value payment plans. | §6.6 — corrected EV with `expected_collected_amount`, time discounting, action cost, and a **contact-fatigue penalty**; plus an **escalation ladder** constraint so greedy cannot loop. |
| **C6** | **Scope declared as "B2B invoices only"** while the track brief spans failures, abandonment, and receivables. | Narrow depth is right for a hackathon, but a single-surface demo under-reads against the brief. | §3 — keep B2B receivables as the **deep vertical**, but build a generic **risk-event spine** so failed payments and subscription dunning plug in as additional sources with zero pipeline change. Demo one deep, two shallow. |
| **C7** | **SQLite now, Postgres "later".** | A background worker writing concurrently will hit SQLite lock contention, and the JSON/`ARRAY`/`UPSERT` semantics differ enough to force a painful mid-build migration. | §8 — **Postgres 16 from commit one** via `docker compose`. One container. No migration ever. |
| **C8** | **No clock, no scheduler, no worker.** The loop requires time to pass (retry in 3 days, promise due date arrives, payment link expires), but nothing advances time. | Without this there is no *workflow*, only a recommendation API. The track says "executes a bounded recovery **workflow**". | §6.9 — **virtual clock** + `scheduled_actions` table + in-process poller. No Redis, no Celery, no extra infra. |
| **C9** | **Diagnosis rules overlap and have no stated priority.** `cash_flow_risk` and `chronic_non_payment` can both fire; a disputed invoice that is also chronic has two labels. | Non-deterministic "deterministic" layer. Undermines the explainability claim. | §6.2 — explicit ordered, mutually exclusive rule cascade + `confidence` + `matched_rule_id`. |
| **C10** | **Policy rules live in Python.** | Policy is the *product*. Hardcoded rules can't be shown, diffed, versioned, or explained to a judge, and every tuning change is a code change. | §6.7 — **policy-as-data** (`policies/*.yaml`), versioned, hot-loadable, with the policy version stamped into every audit record. |
| **C11** | **Razorpay integration is one line ("Payment Links API, planned").** | On an agentic payments track, depth of platform integration is a scored differentiator, and Razorpay ships an official MCP server with 40+ tools. | §6.8 — typed **tool registry** mirroring Razorpay MCP tool names, real test-mode execution, HMAC webhook verification, UPI payment links + QR. |
| **C12** | **No cost model.** | Project constraint is to minimise implementation cost. | §7 + §8 — LLM only on two paths, small model default, **decision cache** on a bounded key space, zero paid infra, free-tier deploy. |

**One thing to explicitly *not* change:** the "AI recommends, deterministic
policy decides, only approved tools execute" principle. That sentence is the
spine of the pitch. Everything below reinforces it rather than diluting it.

---

## 2. Problem statement (reframed)

### 2.1 The loss surface

Merchants lose revenue at four points in the money lifecycle:

| Surface | Loss mechanism | Who owns it |
|---|---|---|
| Failed one-time payments | Issuer decline, expired card, insufficient funds, auth drop-off | Payments ops |
| Subscription renewals | Involuntary churn after mandate/card failure | Growth + billing |
| Checkout abandonment | Intent existed, payment never attempted | Growth |
| **Overdue B2B receivables** | Invoice raised, cash never arrives | Finance / AR |

All four share one shape: **a known amount of money is at risk, a bounded set of
interventions exists, and someone must choose which intervention to apply, when,
to whom, under what constraints.** That shared shape is why this system is built
as one engine with pluggable risk sources rather than four products.

### 2.2 Why receivables is the chosen depth

Two reasons, both defensible on stage:

1. **The platform already solves the easy half of the others.** Razorpay
   auto-retries failed subscription charges on a T+1 / T+2 / T+3 cadence and
   moves the subscription `pending → halted`, emitting `subscription.pending`
   and `subscription.halted`. A project whose core contribution is "retry
   harder" is rebuilding platform behaviour that ships for free.
2. **Receivables has no automated decision layer at all.** The industry default
   is a fixed dunning ladder — reminder at D+1, D+7, D+15, hand to collections at
   D+30 — applied identically to a reliable ₹40k SaaS customer and a
   thrice-defaulted ₹8L manufacturing account. Every invoice gets the same
   treatment regardless of amount, history, dispute status, or recoverability.

### 2.3 The actual problem

Not "which invoices are overdue" — that is a `WHERE due_date < now()` query.

> **For each at-risk amount, choose the next action that maximises expected
> incremental recovered cash, subject to hard constraints on customer contact,
> disputes, financial authority, and auditability — and prove the choice
> mattered.**

Three words carry the weight: **incremental** (§6.11), **constraints** (§6.7),
**prove** (§6.11).

---

## 3. Solution architecture

### 3.1 The recovery loop

```text
  RISK SOURCE                    ┌──────────────────────────────┐
  (invoice overdue,              │  1. OBSERVE                  │
   payment failed,               │  normalise → RiskEvent       │
   subscription halted,          └──────────────┬───────────────┘
   checkout abandoned)                          │
                                 ┌──────────────▼───────────────┐
                                 │  2. DIAGNOSE                 │
                                 │  deterministic cascade       │
                                 │  (LLM fallback on unknown)   │
                                 └──────────────┬───────────────┘
                                 ┌──────────────▼───────────────┐
                                 │  3. PREDICT                  │
                                 │  calibrated p(recover|action)│
                                 │  for each candidate action   │
                                 └──────────────┬───────────────┘
                                 ┌──────────────▼───────────────┐
                                 │  4. RANK                     │
                                 │  risk-adjusted expected value│
                                 └──────────────┬───────────────┘
                                 ┌──────────────▼───────────────┐
                                 │  5. GOVERN   ← FINAL AUTHORITY│
                                 │  policy YAML: allow / gate /  │
                                 │  block / substitute           │
                                 └──────────────┬───────────────┘
                                 ┌──────────────▼───────────────┐
                                 │  6. EXECUTE                  │
                                 │  typed tool registry         │
                                 │  Razorpay test mode          │
                                 │  idempotency-keyed           │
                                 └──────────────┬───────────────┘
                                 ┌──────────────▼───────────────┐
                                 │  7. LISTEN                   │
                                 │  webhooks + inbound replies  │
                                 │  → promise / dispute /       │
                                 │    objection extraction      │
                                 └──────────────┬───────────────┘
                                 ┌──────────────▼───────────────┐
                                 │  8. VERIFY & LEARN           │
                                 │  outcome attribution vs      │
                                 │  holdout; audit close-out    │
                                 └──────────────┬───────────────┘
                                                │
                                    retry ▸ escalate ▸ stop
                                                │
                                                └──▶ back to 2
```

Every arrow writes an audit event. There are no unlogged transitions.

### 3.2 The core invariant

```text
The model produces a RANKING.
The policy engine produces a DECISION.
The tool registry produces an EFFECT.
A model can never produce a decision. A decision can never produce an
uncontracted effect. Every effect is idempotent and reversible-or-logged.
```

This is the sentence to put on slide 2 of the pitch.

### 3.3 Risk sources (C6 fix)

A `RiskSource` normalises anything into a common `RiskEvent`. Adding a surface
is one adapter class — the rest of the pipeline is untouched.

| Source | Adapter | Demo depth |
|---|---|---|
| `receivables` | Overdue invoice from synthetic portfolio + Razorpay Invoices API | **Deep** — full loop, model, policy, measurement |
| `payment_failure` | `payment.failed` webhook → decline-reason taxonomy | Shallow — diagnose + one action (retry-window / rail-switch) |
| `subscription_dunning` | `subscription.pending` / `subscription.halted` webhooks | Shallow — diagnose + card-update link, explicitly *deferring* to Razorpay's native T+1/T+2/T+3 retry rather than duplicating it |
| `checkout_abandonment` | Order created, no payment within N minutes | Stub adapter + tests only (proves extensibility, not demoed live) |

**Say the deferral out loud in the video.** "Razorpay already retries three
times; we don't rebuild that — we decide what happens on day four, and which
rail to move to." Knowing what *not* to build is a maturity signal.

---

## 4. Domain model

### 4.1 Entities

```text
Customer ──< Invoice ──< RiskEvent ──< Decision ──< Action ──< Outcome
                │                          │           │
                ├──< PromiseToPay           │           └──< AuditEvent
                └──< InboundMessage ────────┘
```

### 4.2 Tables (Postgres)

```sql
-- Reference / portfolio
customers            (id, name, email, industry, segment, created_at)
customer_history     (customer_id PK, prior_invoice_count, prior_late_rate,
                      prior_broken_promises, avg_days_to_pay, relationship_tier)

invoices             (id, batch_id, customer_id, invoice_number,
                      amount_paise BIGINT, issued_at, due_date, status,
                      dispute_flag, razorpay_invoice_id, razorpay_payment_link_id,
                      created_at)

-- Experiment control (C2)
batches              (id, seed, size, created_at, notes)
arm_assignments      (invoice_id PK, arm ENUM('agent','baseline','holdout'),
                      assigned_at, assignment_hash)

-- Pipeline
risk_events          (id, source, invoice_id, detected_at, amount_at_risk_paise,
                      payload JSONB)

diagnoses            (id, risk_event_id, code, confidence, rule_id, explanation,
                      signals JSONB, produced_by ENUM('rules','llm_fallback'),
                      created_at)

predictions          (id, risk_event_id, action_key, p_recover, p_calibrated,
                      model_version, features_hash, created_at)

decisions            (id, risk_event_id, ranked JSONB, chosen_action_key,
                      expected_value_paise, policy_version, policy_result,
                      policy_reasons JSONB, requires_approval, created_at)

actions              (id, decision_id, invoice_id, action_key, idempotency_key UNIQUE,
                      state ENUM('pending','approved','executing','executed',
                                 'failed','cancelled'),
                      tool_name, request JSONB, response JSONB,
                      cost_paise, scheduled_for, executed_at)

scheduled_actions    (id, invoice_id, fire_at, kind, payload JSONB,
                      state ENUM('scheduled','fired','cancelled'))

outcomes             (id, action_id, invoice_id, kind, amount_recovered_paise,
                      observed_at, source ENUM('webhook','poll','simulator','manual'))

promises_to_pay      (id, invoice_id, promised_date, promised_amount_paise,
                      source ENUM('reply_llm','manual','simulator'),
                      state ENUM('open','kept','broken'), created_at)

inbound_messages     (id, invoice_id, channel, raw_text_redacted, received_at,
                      extraction JSONB, llm_model, llm_cost_micros)

-- Governance
audit_events         (id, invoice_id, risk_event_id, kind, actor, payload JSONB,
                      policy_version, idempotency_key, prev_hash, hash, created_at)

llm_cache            (key PK, response JSONB, model, created_at, hits)
```

### 4.3 Two non-obvious columns worth defending

- **`audit_events.prev_hash` / `hash`** — each audit row stores
  `sha256(prev_hash || canonical_json(payload))`, forming a per-invoice hash
  chain. Cheap to implement (~15 lines), and it converts "we have logs" into
  "we have a tamper-evident ledger". The track asks for audit trails; this is
  how you exceed the bar rather than meet it.
- **`arm_assignments.assignment_hash`** — arm is assigned by
  `sha256(invoice_id + experiment_salt) % 100`, not by RNG. Deterministic,
  reproducible, and immune to the accusation that arms were re-rolled until the
  numbers looked good.

### 4.4 Money and time conventions

- **All money is `BIGINT` paise.** No floats anywhere in the money path. Format
  to ₹ only at the API boundary.
- **All timestamps are `TIMESTAMPTZ` in UTC.** Business-day logic uses
  `Asia/Kolkata` and an Indian holiday list.
- **"Now" is never `datetime.now()` in domain code.** It is always
  `clock.now()` (§6.9), so the demo can advance 45 days in one second.

---

## 5. What is real vs simulated (honesty contract)

This table goes **in the README and on a slide**. Volunteering it is worth more
than hoping nobody asks.

| Component | Status in demo |
|---|---|
| Portfolio, customer history, replies | **Synthetic** — seeded generator |
| Diagnosis, prediction, ranking, policy, audit | **Real code**, deterministic and reproducible |
| Razorpay payment links / invoices / QR | **Real API calls**, test mode |
| Webhook receipt + HMAC verification | **Real** |
| Whether a customer pays | **Simulated** by a declared environment (§6.4) |
| Reported ₹ recovered | **Simulated cash, real decisions** — never described as merchant cash |

> The dashboard renders every simulated figure with a `SIM` chip. The word
> "recovered" never appears without it in demo mode.

---

## 6. Layer specifications

### 6.0 — Layer 0: Risk event spine

**Contract**

```python
class RiskEvent(BaseModel):
    id: UUID
    source: Literal["receivables", "payment_failure",
                    "subscription_dunning", "checkout_abandonment"]
    invoice_id: UUID | None
    detected_at: datetime
    amount_at_risk_paise: int
    payload: dict

class RiskSource(Protocol):
    key: str
    def detect(self, session: AsyncSession, now: datetime) -> list[RiskEvent]: ...
```

**Rules**

- Sources are registered in a dict; the scheduler polls each on tick.
- Emission is idempotent: one open `RiskEvent` per `(source, invoice_id)`.
  Re-detection updates `amount_at_risk_paise`, it does not insert a duplicate.

**Done when**

- `ReceivablesSource` emits exactly one event per overdue invoice across
  repeated ticks (test asserts no duplicates after 5 ticks).
- A second source can be registered in <20 lines with no pipeline edits
  (proven by the `checkout_abandonment` stub).

---

### 6.1 — Layer 1: Data foundation

Largely as in `project.md` — the correlated generator is good. Four changes.

**Change 1 — correlation is declared, not incidental.** Ship
`docs/generative_model.md` stating the exact structural equations:

```text
late_rate        ~ Beta(a(segment), b(segment))
broken_promises  ~ Poisson(λ = 0.4 + 2.1 × late_rate)
dispute_flag     ~ Bernoulli(p = base(industry) + 0.05 × 1[amount > ₹5L])
days_overdue     ~ Gamma(k(late_rate), θ(segment))
amount_paise     ~ LogNormal(μ(segment), σ(segment))
```

Publishing the DGP is what separates "honest synthetic evaluation" from
"numbers we made up". It also makes C1 defensible instead of fatal.

**Change 2 — add fields the corrected EV and policy need:**
`relationship_tier`, `avg_days_to_pay`, `preferred_channel`, `last_contacted_at`,
`contact_count_30d` (rolling, not lifetime — a lifetime cap silently freezes
long-tenured accounts forever).

**Change 3 — inbound reply corpus.** For each invoice, pre-generate 0–3
realistic reply texts spanning: promise-to-pay with a date, dispute with a
reason, PO/approval blocker, wrong-invoice-details, request-for-payment-plan,
hostile/stop-contacting, and pure noise ("out of office"). ~60 templates ×
Faker slotting is plenty. This is the fuel for §6.3.

**Change 4 — three seeds are not enough.** Generate a **fold set**: seeds
`{101..110}` train, `{201..205}` calibration, `{301..310}` evaluation. Single-
seed evaluation produces a headline number with no error bar, and an uplift
claim without a CI is not a measurement.

**Done when**

- `POST /batches` with the same seed twice produces byte-identical rows
  (test asserts hash equality).
- Correlation assertions pass: `corr(late_rate, broken_promises) > 0.4`;
  `P(dispute | healthcare) > P(dispute | saas)`.
- Every invoice has ≥1 reply candidate and the label distribution across the
  seven reply classes is within ±5pp of target.

---

### 6.2 — Layer 2: Diagnosis (C9 fix)

**Contract**

```python
class Diagnosis(BaseModel):
    code: Literal["disputed", "chronic_non_payment", "cash_flow_risk",
                  "process_delay", "channel_failure", "standard_overdue"]
    confidence: float          # 0..1
    rule_id: str               # e.g. "R03.cash_flow.late_rate"
    explanation: str
    signals: list[str]
    produced_by: Literal["rules", "llm_fallback"]
```

**Rules — ordered cascade, first match wins, mutually exclusive**

| Order | Code | Condition | Confidence |
|---|---|---|---|
| R01 | `disputed` | `dispute_flag` OR an inbound reply classified `dispute` | 1.00 |
| R02 | `chronic_non_payment` | `days_overdue > 60 AND prior_broken_promises >= 2` | 0.90 |
| R03 | `cash_flow_risk` | `prior_late_rate >= 0.4 OR prior_broken_promises >= 1` | 0.75 |
| R04 | `channel_failure` | payment link sent AND never opened AND `contact_count >= 2` | 0.70 |
| R05 | `process_delay` | `days_overdue <= 14 AND prior_late_rate < 0.2 AND broken_promises == 0` | 0.65 |
| R06 | `standard_overdue` | fallback | 0.40 |

Ordering matters and is deliberate: **disputed dominates everything** (a
disputed invoice must never enter dunning, regardless of how bad the history
looks), and **chronic outranks cash-flow** (both fire on a bad account; chronic
is the more actionable label because it changes the action set from "help them
pay" to "escalate or write off").

`channel_failure` (new, R04) is worth adding for one reason: it is the only
diagnosis whose correct response is *mechanical rather than persuasive* — resend
via a different rail, not send a firmer email. It gives the ranking layer a
genuinely different action to choose and makes the demo more interesting than
"which email do we send".

**LLM fallback (bounded):** when R06 fires *and* the invoice has ≥1 inbound
reply, call the LLM to propose one of the five real codes with evidence. It may
**never** invent a code, and its output is stamped `produced_by="llm_fallback"`
and rendered differently in the UI. Rules-only remains the default path.

**Done when**

- Table-driven test: 40 fixtures, one per boundary condition, exact code match.
- Property test: no input produces two codes; every input produces exactly one.
- A disputed + chronic + high-late-rate invoice returns `disputed`.

---

### 6.3 — Layer 3: Reply Intelligence (NEW — C4 fix)

This is the layer that turns the project from a scoring engine into an agent.
It is also the strongest single addition relative to `project.md`.

**Why an LLM here and nowhere near the money.** Free-text customer replies are
genuinely unstructured — regex on "we will pay" fails on "cheque is being
couriered Tuesday", "released in the next payment run", "post GST correction".
But the LLM's output is **evidence, not a decision**: it produces structured
facts that feed the deterministic layers, which retain authority.

**Contract**

```python
class ReplyExtraction(BaseModel):
    intent: Literal["promise_to_pay", "dispute", "approval_blocker",
                    "details_incorrect", "requests_payment_plan",
                    "stop_contact", "acknowledgement", "unrelated"]
    promised_date: date | None
    promised_amount_paise: int | None
    dispute_reason: str | None
    blocker_owner: str | None            # "PO approval", "finance head", ...
    sentiment: Literal["cooperative", "neutral", "hostile"]
    confidence: float
    evidence_quote: str                  # verbatim span, ≤200 chars
```

**Rules**

- Structured output enforced by schema (`instructor` / `pydantic-ai`), never
  free-text parsing.
- **PII redaction before the call** — emails, phones, GSTIN, bank digits, names
  replaced with typed placeholders. Restore only for display. Redaction is
  covered by unit tests.
- `confidence < 0.6` → route to human queue, do not act.
- `intent == "dispute"` → set `dispute_flag`, which forces R01 and halts dunning
  on the next tick. **A hostile or disputing customer stops receiving automated
  contact within one cycle.** State this in the video; it is the clearest
  demonstration of "bounded".
- `intent == "stop_contact"` → hard suppression, permanent, policy-enforced.
- `promise_to_pay` → create `promises_to_pay`, schedule a check for
  `promised_date + 1` (§6.9), and **suppress all outreach until then**. Nothing
  destroys a receivables relationship faster than chasing a customer who already
  committed to a date.
- `evidence_quote` is mandatory and must be a verbatim substring of the input —
  verified programmatically, not trusted. If it isn't a substring, the
  extraction is rejected. This is a cheap, hard anti-hallucination guarantee.

**Done when**

- 60 labelled fixtures; intent accuracy ≥0.85, date extraction exact-match ≥0.80.
- Every accepted extraction's `evidence_quote` verifies as a substring.
- Redaction test: no raw email/phone/GSTIN in any outbound LLM payload.
- Cache hit rate >0 on repeated identical text.

---

### 6.4 — Layer 4: Declared decision environment (C1 fix — the critical one)

**The problem, stated plainly.** If a hidden simulator defines
`P(recover | action)`, a model trained on its samples will recover those
probabilities, and evaluating the resulting policy against the same simulator
proves only that the pipeline has no bugs. It does not prove the agent recovers
money. The original framing ("hidden outcome simulator", "avoids leakage")
protects against *label leakage* but not against *environment circularity*,
which is the bigger hole.

**The fix is honesty plus stress-testing, not concealment.**

**Change 1 — rename and publish.** It is not a "hidden simulator". It is a
**declared decision environment** `E`, fully published in
`docs/environment.md`, with parameters cited to public dunning/collections
benchmarks where any exist and marked `ASSUMED` where none do.

**Change 2 — state the claim you can actually defend.**

> We do not claim "this agent recovers X% more money in the real world." We
> claim: **given a stated environment, the decision layer captures Y% of the
> available uplift over a fixed-cadence baseline, and it degrades gracefully
> when the environment is mis-specified.**

That is a smaller claim and a much stronger one, because it is true and
falsifiable. A judge who tries to poke the first claim finds nothing to poke in
the second.

**Change 3 — environment-shift stress test (the differentiator).** Define three
environments:

| Env | Definition | Purpose |
|---|---|---|
| `E_train` | Baseline parameters | Model is trained here |
| `E_shift` | Action effects perturbed ±40%, action ordering partially inverted | Tests robustness to wrong beliefs |
| `E_adversarial` | Contact fatigue tripled; escalation *reduces* recovery for SMB | Tests whether policy guardrails save the agent when the model is confidently wrong |

Report uplift in all three. **`E_adversarial` is where the pitch lands:** the
model's recommendations get worse, and the policy engine — contact caps,
cooldowns, escalation ladder — limits the damage. That is a live demonstration
that "policy overrides model" is a real safety property and not a slogan.

Most submissions will show one number on one environment. Showing a degradation
curve across three is the kind of thing that wins a track judged on rigour.

**Change 4 — oracle hygiene, preserved from the original.** Model sees invoice
features + diagnosis code + candidate action only. Never environment
parameters, never latent propensity. Enforced by a feature-allowlist in code,
with a test asserting no environment symbol appears in the feature vector.

**Done when**

- `docs/environment.md` fully specifies all three environments.
- One CLI command regenerates every dataset from seeds.
- Feature-allowlist test passes.
- The evaluation harness reports uplift on all three environments.

---

### 6.5 — Layer 5: Prediction model

**Contract**

```python
class Predictor(Protocol):
    version: str
    def predict(self, features: FeatureVector,
                actions: list[ActionKey]) -> dict[ActionKey, float]: ...
```

**Rules**

- **Baseline first:** `LogisticRegression` on one-hot + scaled numerics inside a
  `Pipeline`. Commit this and its metrics before trying anything else. A
  gradient-boosted model is permitted **only if** it beats logistic on held-out
  Brier score by >0.01 — and if it does not, say so in the writeup. Reporting a
  negative result is a credibility gain, not a loss.
- **Calibration is mandatory**, on a *separate* seed fold:
  `CalibratedClassifierCV(method="isotonic", cv="prefit")`. Ship the reliability
  diagram in the repo and the deck. The original doc correctly identifies why
  calibration matters — this makes it a visible artifact rather than a claim.
- Report **Brier score and ECE, not accuracy.** Accuracy is meaningless here:
  the decision consumes the probability, so calibration quality *is* model
  quality.
- **Version everything.** `model_version = sha256(training_seed + feature_spec +
  hyperparams)[:12]`, stamped on every `predictions` row so any historical
  decision is reproducible.
- Cold start: if no model artifact exists, fall back to a hand-set prior table
  by `(diagnosis, action)` and stamp `model_version="prior_v1"`. The system must
  never fail because the model hasn't been trained yet.

**Done when**

- Brier and ECE reported per action on the evaluation fold.
- Reliability diagram committed to `reports/`.
- Predictions reproducible from `model_version` + `features_hash`.
- Cold-start path tested with the artifact deleted.

---

### 6.6 — Layer 6: Risk-adjusted expected value (C5 fix)

**The original formula and why it breaks**

`EV = p × invoice_amount` fails four ways:
1. A payment plan that recovers ₹1L over six months is scored as ₹1L today.
2. Sending an email and escalating to a named account manager cost the same (₹0).
3. Nothing penalises the eleventh contact in a month.
4. Argmax is myopic — it re-picks the same top action every tick forever.

**Corrected contract**

```python
def expected_value_paise(
    p: float,                      # calibrated P(recover | action)
    collectible_paise: int,        # amount this action can actually collect
    days_to_cash: float,           # expected delay to cash-in-hand
    action_cost_paise: int,        # marginal cost of the action
    fatigue_penalty: float,        # 0..1, from recent contact density
    annual_discount_rate: float = 0.12,
) -> int:
    tvm = 1.0 / (1.0 + annual_discount_rate) ** (days_to_cash / 365.0)
    return int(p * collectible_paise * tvm * (1.0 - fatigue_penalty)
               - action_cost_paise)
```

**Per-action parameters** (illustrative; tune in `config/actions.yaml`):

| Action | `collectible` | `days_to_cash` | `action_cost` | Notes |
|---|---|---|---|---|
| `send_reminder` | full | 5 | ₹2 | Email send cost |
| `resend_payment_link` | full | 3 | ₹2 | New rail available |
| `send_upi_payment_link` | full | 2 | ₹2 | Fastest rail in India |
| `offer_payment_plan` | full × (1 − concession) | 60 | ₹5 | **Concession is policy-fixed, never model-chosen** |
| `escalate_to_am` | full | 12 | ₹1,200 | ~40 min of a human's time |
| `schedule_call` | full | 8 | ₹400 | |

Two consequences fall straight out of the corrected formula, and both are worth
narrating in the demo because they are *counter-intuitive but obviously right*:

- **Escalation is correctly expensive.** At ₹1,200 of human time it can never
  win on a ₹15k invoice — which is exactly the real-world rule that AR teams
  apply by instinct and that fixed-cadence software ignores.
- **Payment plans stop being over-picked.** Time-discounting a 60-day plan plus
  the concession haircut prices it honestly against a link resend.

**Fatigue penalty**

```python
fatigue_penalty = min(0.6, 0.15 * contact_count_30d)
```

Caps at 0.6 so fatigue suppresses but never fully zeroes an action — the hard
stop is policy's job (§6.7), not the scorer's. Keeping soft economics and hard
constraints in separate layers is what keeps the system explainable.

**Sequential correction — the escalation ladder**

Greedy argmax on a per-tick basis will re-choose `send_reminder` indefinitely.
Constrain it:

```yaml
ladder: [send_reminder, resend_payment_link, send_upi_payment_link,
         schedule_call, offer_payment_plan, escalate_to_am]
rules:
  - an action may not repeat within its cooldown_days
  - the agent may not move more than one rung per cycle
  - the agent may not move down the ladder
  - max 2 executions of the same action per invoice, ever
```

This is a deliberate engineering choice over the theoretically-correct answer
(a contextual bandit or finite-horizon MDP). The ladder captures ~most of the
sequential value, is fully explainable to a finance team, and is auditable —
all of which matter more on this track than optimality. **Say that trade-off out
loud;** naming the sophisticated alternative and justifying the simpler pick
reads as judgement, whereas silence reads as ignorance.

**Excluded from ranking** (unchanged from `project.md`, and correct):
`request_human_approval`, `stop`, `route_to_dispute` are policy outcomes and
must not compete on EV.

**Done when**

- Unit tests for each formula term in isolation.
- Test: `escalate_to_am` never wins on an invoice below ₹50k.
- Test: no action repeats inside its cooldown across a 90-day simulated run.
- Ladder monotonicity property test.

---

### 6.7 — Layer 7: Policy engine (C10 fix)

**Policy is the product.** It gets its own versioned, human-readable file.

**Contract**

```python
class PolicyResult(BaseModel):
    outcome: Literal["allow", "require_approval", "block", "substitute"]
    substituted_action: ActionKey | None
    reasons: list[PolicyReason]      # rule_id, rule_text, matched_facts
    policy_version: str
```

**`policies/default.yaml`**

```yaml
version: "1.3.0"
rules:
  - id: P01_dispute_freeze
    when: "diagnosis.code == 'disputed'"
    then: substitute
    with: route_to_dispute
    reason: "Disputed invoices exit automated dunning entirely."

  - id: P02_stop_contact
    when: "customer.suppressed == true"
    then: block
    reason: "Customer requested no further contact."

  - id: P03_contact_cap
    when: "customer.contact_count_30d >= 4"
    then: block
    reason: "Rolling 30-day contact cap reached."

  - id: P04_quiet_hours
    when: "not clock.is_business_hours(customer.timezone)"
    then: block
    reason: "Outside 09:00–19:00 IST business hours."

  - id: P05_open_promise
    when: "invoice.has_open_promise and clock.today <= promise.promised_date"
    then: block
    reason: "Customer has an open promise-to-pay; suppress until due."

  - id: P06_high_value_approval
    when: "invoice.amount_paise > 50000000"     # ₹5,00,000
      and: "action.key in ['offer_payment_plan','escalate_to_am']"
    then: require_approval
    reason: "Financial authority threshold exceeded."

  - id: P07_concession_whitelist
    when: "action.key == 'offer_payment_plan'"
    then: allow
    constraints:
      plan_must_be_in: ["plan_3x_30d", "plan_6x_30d"]
    reason: "Only pre-approved plans. The model cannot author terms."

  - id: P08_chronic_ladder_skip
    when: "diagnosis.code == 'chronic_non_payment'"
    then: substitute
    with: escalate_to_am
    reason: "Chronic non-payment does not respond to further reminders."

  - id: P09_daily_action_budget
    when: "batch.actions_today >= batch.action_budget"
    then: block
    reason: "Daily action budget exhausted (blast-radius cap)."

  - id: P10_novel_case
    when: "diagnosis.produced_by == 'llm_fallback' and diagnosis.confidence < 0.7"
    then: require_approval
    reason: "Low-confidence LLM diagnosis requires human confirmation."
```

**Rules**

- Evaluate **all** rules and collect **all** matches. Never short-circuit —
  "blocked for 3 reasons" is a better audit record than "blocked".
- Severity ordering when rules conflict: `block > substitute > require_approval > allow`.
- Condition strings are evaluated by a **restricted evaluator over a whitelisted
  fact namespace** (`simpleeval` with no builtins), not `eval()`. Never execute
  arbitrary strings from a config file, even your own.
- `policy_version` is stamped on every `decisions` row. Changing policy does not
  rewrite history.
- Ship `POST /policy/simulate` — run a candidate policy YAML over a past batch
  and diff the decisions. Being able to say *"here is what this policy change
  would have done to last month's portfolio, without touching a customer"* is a
  genuinely enterprise-grade feature and costs almost nothing to build on top of
  what already exists.

Rules **P04 (quiet hours)**, **P05 (open promise)**, and **P09 (daily budget)**
are additions to the original set. P09 in particular is the literal
implementation of the word "**bounded**" in the track brief — a hard ceiling on
how much the agent can do before a human looks at it. Give it a visible dial in
the dashboard.

**Done when**

- Every rule has a passing positive and negative test.
- Conflict-resolution test: dispute + high-value + cap → `block`, 3 reasons.
- `POST /policy/simulate` returns a decision diff for a stored batch.
- No `eval()` / `exec()` anywhere in the codebase (grep test in CI).

---

### 6.8 — Layer 8: Execution (C11 fix)

**Contract**

```python
class Tool(Protocol):
    name: str
    cost_paise: int
    requires_approval: bool
    async def execute(self, ctx: ActionContext) -> ToolResult: ...
```

**Registry**

| Tool | Razorpay surface | Real in demo |
|---|---|---|
| `send_reminder` | Email (SMTP / console sink) | Console sink |
| `resend_payment_link` | `payment_links.create` + `send` | **Yes, test mode** |
| `send_upi_payment_link` | `payment_links.create` (UPI) | **Yes, test mode** |
| `create_invoice_qr` | `qr_codes.create` | **Yes, test mode** |
| `offer_payment_plan` | Payment link per instalment | **Yes, test mode** |
| `escalate_to_am` | Internal task record | Yes (internal) |
| `route_to_dispute` | Internal queue | Yes (internal) |
| `request_human_approval` | Approval queue + UI | Yes |
| `stop` | Terminal state | Yes |

Tool names deliberately mirror the [official Razorpay MCP server](https://github.com/razorpay/razorpay-mcp-server)
(`create_payment_link`, `create_qr_code`, `fetch_payment`, …). Two payoffs:
the agent can be pointed at the real MCP server with a config flag instead of a
rewrite, and it demonstrates fluency with Razorpay's own agent tooling on an
agentic track.

**Idempotency**

```python
idempotency_key = sha256(f"{invoice_id}:{action_key}:{attempt_no}:{policy_version}")
```

`UNIQUE` constraint on the column. On collision, return the stored
`ToolResult` — never re-execute. Include `policy_version` in the key so a
deliberate post-policy-change retry is a *different* action, not a silently
swallowed duplicate.

**Action state machine**

```text
pending ──▶ approved ──▶ executing ──▶ executed ──▶ (outcome)
   │            │            │
   └──▶ cancelled            └──▶ failed ──▶ (retry w/ backoff, max 3)
```

Illegal transitions raise. Test every edge.

**Webhook security (non-negotiable)**

- Verify `X-Razorpay-Signature` = `HMAC_SHA256(body, webhook_secret)` using
  `hmac.compare_digest`. Reject unverified with 400 **before parsing JSON**.
- Store `event.id`; drop duplicates (Razorpay retries).
- Respond 200 fast; process asynchronously.

Handled events: `payment_link.paid`, `payment.failed`, `payment.captured`,
`invoice.paid`, `invoice.expired`, `subscription.pending`, `subscription.halted`,
`refund.created`.

**Done when**

- Duplicate execution test: same key twice → one API call, identical result.
- Signature test: tampered body → 400, nothing written.
- Replay test: same `event.id` twice → one outcome row.
- A real test-mode payment link is created, paid in the Razorpay test dashboard,
  and the webhook closes the loop end-to-end. **Record this once and keep the
  screen capture — it is the money shot of the pitch video.**

---

### 6.9 — Layer 9: Clock, scheduler, verification (C8 fix)

**Why a virtual clock.** The workflow is inherently temporal — a reminder
today, a promise due in 9 days, a link expiring in 14. A 5-minute demo cannot
wait. And `datetime.now()` scattered through domain code is untestable.

**Contract**

```python
class Clock(Protocol):
    def now(self) -> datetime: ...
    def is_business_hours(self, tz: str) -> bool: ...

class RealClock(Clock): ...
class VirtualClock(Clock):        # demo/test — advanceable
    def advance(self, days: float) -> None: ...
```

Inject via FastAPI dependency. **`datetime.now()` in `app/domain/**` is a CI
failure** (grep test). Small rule, disproportionate payoff.

**Scheduler**

Deliberately boring: one `AsyncIOScheduler` (APScheduler) inside the FastAPI
process, ticking every 30s:

1. Poll risk sources → new `RiskEvent`s
2. Fire due `scheduled_actions`
3. Run the loop for open events (respecting the daily budget)
4. Poll Razorpay for actions awaiting outcome past their SLA
5. Resolve promises past `promised_date + 1` → `kept` / `broken`

**No Celery, no Redis, no RabbitMQ.** At this scale a Postgres table plus an
in-process scheduler is strictly better: zero extra containers, zero extra
cost, trivially debuggable, and one `docker compose up` for a judge. Adding a
broker would be resume-driven architecture. If it ever needs to scale out,
`SELECT … FOR UPDATE SKIP LOCKED` on `scheduled_actions` makes the table a
real queue without changing the schema.

**Demo endpoint:** `POST /simulate/advance?days=7` — advances the virtual clock,
runs ticks, returns a timeline diff. This is what makes a 45-day recovery
journey fit in a 5-minute video.

**Done when**

- 90-day simulated run completes with no duplicate actions and no orphaned events.
- Promise resolution correct across kept and broken paths.
- Clock injection test: two clocks, two independent timelines, no bleed.
- `grep -r "datetime.now()" app/domain/` returns nothing.

---

### 6.10 — Layer 10: Audit and explainability

Extend `project.md`'s partial audit to a complete hash-chained ledger.

**Every event kind:** `risk_detected`, `diagnosis_produced`,
`prediction_produced`, `actions_ranked`, `policy_evaluated`, `approval_requested`,
`approval_granted`, `approval_denied`, `action_scheduled`, `action_executed`,
`action_failed`, `webhook_received`, `reply_received`, `reply_extracted`,
`promise_created`, `promise_resolved`, `outcome_observed`, `escalated`, `stopped`.

**Hash chain**

```python
payload_json = canonical_json(payload)          # sorted keys, no whitespace
hash = sha256(f"{prev_hash}{payload_json}".encode()).hexdigest()
```

Ship `GET /invoices/{id}/audit/verify` → recomputes the chain, returns
`{"intact": true, "events": n}`. Roughly 15 lines that upgrade the audit story
from adequate to distinctive.

**The explanation object** — every decision must render as one paragraph a
finance person reads without training:

```json
{
  "invoice": "INV-2291", "amount": "₹2,50,000", "days_overdue": 45,
  "diagnosis": {
    "code": "cash_flow_risk",
    "because": ["late payment rate 0.48 (threshold 0.40)", "1 broken promise"],
    "rule": "R03.cash_flow.late_rate"
  },
  "considered": [
    {"action": "offer_payment_plan",  "p": 0.42, "ev": "₹94,300", "rank": 1},
    {"action": "resend_payment_link", "p": 0.38, "ev": "₹91,200", "rank": 2},
    {"action": "escalate_to_am",      "p": 0.51, "ev": "₹1,26,300", "rank": 0,
     "note": "highest EV but gated"}
  ],
  "policy": {
    "outcome": "require_approval",
    "version": "1.3.0",
    "because": ["P06: ₹2,50,000 under review threshold for payment plans"]
  },
  "final": "Awaiting human approval — requested 2026-08-23T14:02:11Z",
  "chain_verified": true
}
```

Note that the *highest-EV action is shown even when it was gated*. Showing the
option the policy took away is far more persuasive than showing only what was
allowed — it makes the governance layer visible instead of invisible, which is
precisely what "explainable money actions" asks for.

**Done when**

- Chain verification passes over a 500-invoice batch.
- Mutating one payload row makes `/verify` return `intact: false`.
- Every decision has a renderable explanation object.

---

### 6.11 — Layer 11: Measurement (C2 fix — the headline number)

**Three arms**, assigned deterministically by hash at batch creation:

| Arm | Share | Behaviour |
|---|---|---|
| `agent` | 70% | Full loop |
| `baseline` | 20% | Fixed cadence: D+1 reminder, D+7 reminder, D+15 link, D+30 escalate |
| `holdout` | 10% | **No contact at all** — measures natural self-cure |

**The holdout is the whole point.** Without it, "we recovered ₹18L" includes
every invoice that would have been paid anyway. With it:

```text
incremental_recovery = (recovery_rate_agent − recovery_rate_holdout) × portfolio_value
agent_uplift_vs_baseline = recovery_rate_agent − recovery_rate_baseline
```

**Report with error bars.** Across 10 evaluation seeds, report mean ± 95% CI
(bootstrap, 1000 resamples). A number without a CI is an anecdote.

**Also report — and this is the honest part most submissions omit:**

- **Cost of recovery**: `total_action_cost / incremental_recovered`. An agent
  that recovers 3% more by escalating everything to humans is not a good agent.
- **Contacts per recovery** — the customer-experience cost.
- **Suppression precision**: of invoices where the agent stopped, how many were
  genuinely unrecoverable? Knowing when to *stop* is a first-class result.
- **Uplift under `E_shift` and `E_adversarial`** (§6.4) — the robustness curve.

**Scoreboard artifact:** `reports/evaluation.md`, regenerated by one command,
with a table per environment and a bootstrap distribution plot. Committed to
the repo so a judge can read the numbers without running anything.

**Done when**

- `make evaluate` regenerates the full report from seeds.
- Arm assignment is stable across re-runs (hash test).
- CIs present on every reported metric.
- Cost-of-recovery and suppression-precision reported.

---

### 6.12 — Layer 12: Dashboard

Single-page **Recovery Command Center**. Optimise for the 5-minute video: a
judge should understand the system from one screen.

**Layout**

```text
┌────────────────────────────────────────────────────────────────────┐
│  Revenue at Risk  ₹1.84 Cr   │  Incremental Recovered  ₹22.4 L SIM │
│  Portfolio 500 invoices      │  vs holdout +8.2pp (CI 6.1–10.3)    │
│  Actions today 43/120 ▓▓▓░░  │  Cost of recovery ₹1.02 per ₹100    │
├──────────────────┬─────────────────────────────────────────────────┤
│ QUEUE            │  DECISION DETAIL                                │
│ ● Approvals (4)  │  INV-2291 · Acme Mfg · ₹2,50,000 · 45d overdue  │
│ ● Disputes (2)   │  ┌────────────────────────────────────────────┐ │
│ ● Promises (11)  │  │ DIAGNOSIS  cash_flow_risk       conf 0.75  │ │
│ ● Suppressed (7) │  │ late rate 0.48 · 1 broken promise · R03     │ │
│                  │  ├────────────────────────────────────────────┤ │
│ FILTERS          │  │ RANKED ACTIONS                              │ │
│ [diagnosis ▾]    │  │ 1 payment_plan   0.42 → ₹94,300            │ │
│ [arm ▾]          │  │ 2 resend_link    0.38 → ₹91,200            │ │
│ [status ▾]       │  │ ⊘ escalate_am    0.51 → ₹1,26,300  GATED   │ │
│                  │  ├────────────────────────────────────────────┤ │
│                  │  │ POLICY v1.3.0   REQUIRE_APPROVAL           │ │
│                  │  │ P06 amount > ₹5,00,000 threshold           │ │
│                  │  │        [ Approve ]  [ Deny ]                │ │
│                  │  ├────────────────────────────────────────────┤ │
│                  │  │ AUDIT TIMELINE      🔒 chain verified       │ │
│                  │  │ ●─●─●─●─● 5 events                          │ │
│                  │  └────────────────────────────────────────────┘ │
├──────────────────┴─────────────────────────────────────────────────┤
│ [⏩ Advance 7 days]   [Recovery curve: agent / baseline / holdout]  │
└────────────────────────────────────────────────────────────────────┘
```

**Four things that must be on screen** — these map 1:1 to the judging criteria:

1. The **gated** action shown struck through next to the chosen one → *explainable money actions*
2. The **action budget meter** → *bounded workflow*
3. The **three-arm recovery curve** → *measured recovery amounts*
4. The **chain-verified audit timeline** → *audit trails*

`Advance 7 days` is the demo's hero control: the curves move live, promises
resolve, approvals appear.

**Aesthetic direction** — dark slate base, one accent for money-in (emerald),
one for risk (amber), red reserved exclusively for blocked/disputed. Tabular
numerals for all currency. No gradients, no glass, no emoji. Data-dense and
calm; it should look like a finance tool, not a startup landing page.

**Done when**

- One screen carries all four judging criteria without scrolling.
- `Advance 7 days` visibly moves the curves.
- Approve/deny writes an audit event and unblocks the action.

---

## 7. LLM usage and cost control (C3, C12)

**Where the LLM is used — exactly three places, all off the money path:**

| Use | Why not rules | Guardrail |
|---|---|---|
| Reply extraction (§6.3) | Free text is genuinely unstructured | Schema-constrained; verbatim quote verified as substring; `conf<0.6` → human |
| Message generation | Tone must adapt to diagnosis + relationship tier | Only policy-approved offers may appear; post-generation validator rejects any unapproved number, date, or concession |
| Novel-case diagnosis fallback (§6.2) | Long tail beyond R01–R05 | May only select from the five existing codes; gated by P10 |

**Where the LLM is never used:** choosing an action, setting a probability,
authoring financial terms, deciding policy, computing any number that reaches
the dashboard. Every one of these has a deterministic owner.

**Cost controls**

1. **Decision cache.** Key on
   `(diagnosis_code, segment, industry, amount_bucket, days_bucket, tier)` —
   a bounded space of roughly 6×3×6×5×4×3 ≈ 6,480 cells. After warm-up, a
   500-invoice batch is nearly all cache hits. Stored in `llm_cache`; hit rate
   shown in the dashboard footer (a nice detail for a cost-conscious judge).
2. **Small model by default**, escalating to a larger model only when
   `confidence < 0.6`. Log `llm_cost_micros` per call and show total spend per
   batch — *demonstrating* cost discipline beats claiming it.
3. **Batch offline work.** Reply extraction for a generated portfolio runs once
   at generation time, not per request.
4. **Templates for the 80% case.** Reminder emails for `process_delay` and
   `standard_overdue` are Jinja templates with zero LLM calls. The LLM is
   reserved for `disputed`, `chronic_non_payment`, and enterprise tier.
5. **Hard per-batch spend ceiling** in config; exceeding it degrades to
   templates rather than failing.

**Realistic budget:** a 500-invoice demo batch should cost well under $1 in LLM
spend. Put the actual measured figure in the README.

**Infra cost: ₹0.** One Postgres container, one FastAPI process, one Vite dev
server. Deploy target is a free tier (Railway / Fly / Render) or purely local
with a recorded video — nothing in the design requires paid infrastructure.

---

## 8. Technology stack (final)

| Concern | Choice | Rationale |
|---|---|---|
| Language | Python 3.12 | Your primary stack |
| API | FastAPI + Pydantic v2 | Your primary stack; async, typed, free OpenAPI docs |
| ORM | SQLAlchemy 2.0 async + Alembic | Typed `Mapped[]`; migrations from day one |
| DB | **Postgres 16** (docker compose) | C7 — JSONB, real concurrency, `SKIP LOCKED`, no migration later |
| Scheduler | APScheduler in-process | C8 — zero extra infra vs Celery/Redis |
| ML | scikit-learn | Logistic + isotonic calibration is the right size |
| Data | NumPy, pandas, Faker | Generator + evaluation |
| LLM | `instructor` or `pydantic-ai` + small model | Schema-enforced structured output |
| Payments | `razorpay` Python SDK, test mode | Real API calls; tool names mirror Razorpay MCP |
| Rule eval | `simpleeval` | Safe restricted evaluation — never `eval()` |
| Logging | `structlog` (JSON) | Machine-readable audit correlation |
| Testing | pytest + pytest-asyncio + hypothesis | Property tests on policy and ladder |
| Frontend | Vite + React + TS + Tailwind + shadcn/ui | Fast, clean, minimal custom CSS |
| Charts | Recharts | Recovery curves, reliability diagram |
| Data fetching | TanStack Query | Polling during `advance` without hand-rolled state |
| Container | docker compose (db + api) | One command for a judge |

**Deliberately not used, and why** — worth a line in the README, because
restraint is a signal:

- **Celery / Redis / RabbitMQ** — a Postgres table and a 30s tick is sufficient
  and strictly cheaper to run and debug.
- **Vector DB / RAG** — there is no corpus to retrieve over. Adding one would be
  decoration.
- **LangChain / agent frameworks** — the control flow here is a 6-step state
  machine that the code should state plainly. A framework would obscure the
  auditability that is the project's main claim.
- **Deep learning** — ~5k rows and ~14 features. Logistic regression with
  isotonic calibration is the correct model, and saying so is a stronger signal
  than reaching for something bigger.

---

## 9. Repository layout

```text
revenue-recovery-agent/
├── docker-compose.yml
├── Makefile                       # dev, test, seed, train, evaluate, demo
├── README.md                      # incl. honesty contract (§5) + cost figures
├── .env.example
├── docs/
│   ├── architecture.md            # buildathon deliverable
│   ├── generative_model.md        # §6.1 — declared DGP
│   ├── environment.md             # §6.4 — E_train / E_shift / E_adversarial
│   └── decisions/ADR-00x.md       # key trade-offs, incl. ladder vs bandit
├── policies/
│   ├── default.yaml               # v1.3.0
│   └── conservative.yaml          # for /policy/simulate diffing
├── config/
│   ├── actions.yaml               # costs, days_to_cash, cooldowns, ladder
│   └── plans.yaml                 # whitelisted payment plans
├── reports/                       # committed evaluation artifacts
│   ├── evaluation.md
│   ├── reliability.png
│   └── uplift_bootstrap.png
├── app/
│   ├── main.py
│   ├── settings.py
│   ├── deps.py                    # clock, session, registries
│   ├── db/
│   │   ├── models.py
│   │   ├── session.py
│   │   └── migrations/
│   ├── domain/                    # PURE — no I/O, no datetime.now()
│   │   ├── types.py
│   │   ├── diagnosis.py           # §6.2 cascade
│   │   ├── features.py            # allowlist enforced
│   │   ├── ranking.py             # §6.6 EV + ladder
│   │   ├── policy/
│   │   │   ├── engine.py
│   │   │   └── evaluator.py       # simpleeval sandbox
│   │   └── clock.py
│   ├── sources/
│   │   ├── base.py
│   │   ├── receivables.py
│   │   ├── payment_failure.py
│   │   ├── subscription_dunning.py
│   │   └── checkout_abandonment.py   # stub, proves extensibility
│   ├── ml/
│   │   ├── train.py
│   │   ├── calibrate.py
│   │   ├── predictor.py
│   │   └── priors.py              # cold start
│   ├── llm/
│   │   ├── client.py              # cache + cost meter + model routing
│   │   ├── redact.py              # PII scrubbing (tested)
│   │   ├── reply_extraction.py    # §6.3
│   │   ├── message_gen.py
│   │   └── validators.py          # rejects unapproved numbers/terms
│   ├── tools/
│   │   ├── registry.py
│   │   ├── razorpay_client.py
│   │   ├── payment_links.py
│   │   ├── qr.py
│   │   ├── email.py
│   │   └── internal.py            # escalate, dispute, approval, stop
│   ├── orchestrator/
│   │   ├── loop.py                # the 8-step cycle
│   │   ├── scheduler.py           # APScheduler wiring
│   │   └── state_machine.py       # action transitions
│   ├── audit/
│   │   ├── writer.py
│   │   ├── chain.py               # hash chain + verify
│   │   └── explain.py             # §6.10 explanation object
│   ├── simulation/
│   │   ├── generator.py           # portfolio + replies
│   │   ├── environment.py         # E_train / E_shift / E_adversarial
│   │   └── outcomes.py
│   ├── evaluation/
│   │   ├── arms.py                # deterministic assignment
│   │   ├── baseline.py            # fixed cadence
│   │   ├── metrics.py             # uplift, CI, cost-of-recovery
│   │   └── report.py
│   └── api/
│       ├── batches.py  invoices.py  decisions.py  approvals.py
│       ├── webhooks.py  simulate.py  policy.py  evaluation.py
├── tests/
│   ├── unit/  integration/  property/  fixtures/
└── web/
    └── src/{App.tsx,api/,components/,hooks/}
```

**The `app/domain/` purity rule matters most.** No I/O, no clock, no network.
It makes the entire decision core testable in milliseconds and is what allows
the property tests in §6.6 and §6.7 to exist at all.

---

## 10. API surface

**Existing (keep, from `project.md`)**

```text
GET  /health
POST /batches?size=&seed=
GET  /invoices?batch_id=
GET  /invoices/{id}
GET  /invoices/{id}/diagnosis
GET  /invoices/{id}/audit
GET  /batches/{id}/summary
```

**New**

```text
# Pipeline
POST /invoices/{id}/evaluate           → diagnosis + ranking + policy (no execution)
POST /invoices/{id}/act                → execute the policy-approved action
GET  /invoices/{id}/explanation        → §6.10 explanation object
GET  /invoices/{id}/audit/verify       → hash-chain integrity

# Approvals (bounded autonomy)
GET  /approvals                        → pending queue
POST /approvals/{id}/approve
POST /approvals/{id}/deny

# Replies
POST /invoices/{id}/replies            → ingest text → extraction → facts

# Policy
GET  /policy                           → active YAML + version
POST /policy/simulate                  → dry-run candidate policy over a batch, diff

# Simulation / demo
POST /simulate/advance?days=           → advance virtual clock, run ticks
POST /simulate/run-batch?batch_id=&env= → full run under E_train|E_shift|E_adversarial

# Measurement
GET  /evaluation/{batch_id}            → arms, uplift, CIs, cost-of-recovery
GET  /evaluation/{batch_id}/curve      → recovery curve by arm over time

# Webhooks
POST /webhooks/razorpay                → HMAC-verified, deduped
```

---

## 11. Milestone plan

`project.md` lists Layer 1, 2 and parts of 9 as complete. Milestone 0 migrates
that work onto the corrected foundations before anything new is built.

| M | Milestone | Deliverables | Gate |
|---|---|---|---|
| **M0** | Foundation migration | Postgres + Alembic + docker compose; port existing invoice/diagnosis/audit code; `Clock` injected; hash chain; arm assignment; generator extended (replies, rolling contacts, tier); ordered diagnosis cascade (C9) | `docker compose up` → seed 500 invoices → `/verify` intact; diagnosis property tests pass |
| **M1** | Environment + training data | `docs/generative_model.md`, `docs/environment.md`; three environments; fold seeds; feature allowlist | Datasets regenerate byte-identically; allowlist test passes |
| **M2** | Model + calibration | Logistic + isotonic; Brier/ECE per action; reliability diagram; `prior_v1` cold start | Reliability diagram committed; ECE < 0.05; cold start works with artifact deleted |
| **M3** | Ranking + policy | Corrected EV (C5); ladder + cooldowns; `policies/default.yaml`; simpleeval sandbox; `/policy/simulate` | Every policy rule has ±tests; no-repeat-in-cooldown property test passes; no `eval()` in CI grep |
| **M4** | Execution + webhooks | Tool registry; Razorpay test-mode links/QR; idempotency; state machine; HMAC webhooks | **End-to-end: link created → paid in test dashboard → webhook → outcome recorded. Record this.** |
| **M5** | Clock, scheduler, workflow | APScheduler tick; `scheduled_actions`; promise resolution; `/simulate/advance` | 90-day run: no dupes, no orphans, promises resolve both ways |
| **M6** | Reply intelligence | Redaction; schema-constrained extraction; quote verification; dispute → suppression; cache + cost meter | 60 fixtures ≥0.85 intent accuracy; redaction test passes; dispute halts dunning within one tick |
| **M7** | Measurement | Three arms; baseline cadence; bootstrap CIs; `reports/evaluation.md` across all 3 environments | `make evaluate` regenerates the report; every metric has a CI |
| **M8** | Dashboard | Command Center; gated-action display; budget meter; three-arm curve; audit timeline; advance control | All four judging criteria visible on one screen |
| **M9** | Submission | `docs/architecture.md`; README honesty contract + cost figures; ADRs; 5-min video; public repo | Cold clone → `docker compose up` → working demo, verified on a second machine |

**If time runs short, cut in this order** (and cut *before* you run out, not
after): `checkout_abandonment` stub → `create_invoice_qr` → `E_adversarial` →
message generation (keep templates) → `schedule_call`.

**Never cut:** the holdout arm (M7), the audit chain (M0), HMAC verification
(M4), or the honesty contract (M9). Those four are what the track is scored on.

---

## 12. Demo video beat sheet (5 minutes)

| Time | Beat | On screen |
|---|---|---|
| 0:00–0:30 | **The problem.** Fixed dunning ladders treat a reliable ₹40k SaaS account and a thrice-defaulted ₹8L manufacturer identically. | Baseline cadence diagram |
| 0:30–1:00 | **The invariant.** "Model ranks. Policy decides. Tools execute. Everything is logged." | Architecture slide |
| 1:00–2:00 | **One invoice, end to end.** ₹2.5L, 45 days. Diagnosis with evidence → ranked actions → *escalation is highest-EV and the policy gates it* → approval queue. | Command Center detail pane |
| 2:00–2:45 | **Real execution.** UPI payment link created in Razorpay test mode → paid → webhook → outcome closes the loop. | Split screen: app + Razorpay dashboard |
| 2:45–3:15 | **The agent listens.** Paste "we dispute this, wrong GST" → extraction → dispute flag → dunning halts within one cycle. | Reply panel + audit timeline |
| 3:15–4:00 | **The measurement.** Advance 30 days. Three-arm curve separates. Incremental uplift with CI. Cost of recovery. | Recovery curve + scoreboard |
| 4:00–4:30 | **Bounded, provably.** Budget meter; approval gate; chain-verified audit; tamper a row → `intact: false`. | Live verify call |
| 4:30–5:00 | **The honest close.** "Decisions are real, cash is simulated under a published environment. Here is uplift under three environments, including one where the model is deliberately wrong — the policy layer contains the damage." | Robustness table |

The final 30 seconds is the highest-leverage part of the video. Most
submissions end on their best number. Ending on *the limits of your own claim,
plus evidence you stress-tested it* is far more memorable to a technical panel —
and it inoculates you against the exact question they were about to ask.

---

## 13. Risks

| Risk | Mitigation |
|---|---|
| Circular-evaluation challenge (C1) | Pre-empt it: publish the environment, state the narrow claim, show the robustness curve. Raise it before the judge does. |
| Razorpay test-mode friction | Complete M4 early. Record the working webhook loop the day it works — do not rely on live demo. |
| LLM extraction flaky in demo | Cache all demo replies; `conf<0.6` routes to human, which is a *feature* to narrate, not a failure. |
| Scope creep | The cut list in §11 is pre-decided. Cut early. |
| Dashboard eats the last two days | M8 is one screen. Build it against fixture JSON in parallel with M5–M7 if possible. |
| "Only synthetic data" objection | The honesty contract (§5) is on a slide. Volunteering the limitation converts an attack into a credibility signal. |

---

## 14. The pitch, in one paragraph

> Fixed dunning ladders send the same four emails to every overdue invoice.
> This agent diagnoses *why* each invoice is stuck, predicts calibrated recovery
> probability for each permitted action, ranks them by time-discounted expected
> value net of the cost of acting, and then submits that recommendation to a
> deterministic policy engine that has final authority — it can block, gate, or
> substitute the action, and it does. Approved actions execute through
> Razorpay's API under idempotency keys and a daily action budget, and every
> step lands in a hash-chained audit ledger. When a customer replies, the agent
> reads it: a promise-to-pay suppresses outreach until the promised date, a
> dispute halts dunning entirely within one cycle. We measure ourselves against
> a no-contact holdout, so the number we report is *incremental* recovery, with
> a confidence interval — and we report it under an environment where our own
> model is deliberately wrong, to show that the guardrails, not the model, are
> what make it safe to let this thing touch money.
