# Revenue Recovery Intelligence Agent

## 1. Project overview

Revenue Recovery Intelligence Agent is a policy-gated AI system for recovering overdue B2B invoice payments.

It helps a merchant answer:

> “This invoice is overdue. Why is it stuck, what should we do next, is that action allowed, and did it actually recover money?”

Rather than treating every overdue invoice with the same reminder sequence, the system diagnoses the payment situation, predicts the most valuable recovery action, applies safety rules, executes only permitted actions, verifies the result, and keeps a complete audit trail.

The project is designed for the Razorpay AI Buildathon’s AI Revenue Recovery track.

---

# 2. Problem statement

## The business problem

Businesses lose revenue across multiple payment-failure surfaces:

- Failed one-time payments
- Subscription renewal failures
- Checkout abandonment
- Overdue B2B invoices and receivables

The project specifically focuses on overdue B2B invoices.

B2B invoice recovery is difficult because an overdue payment can have many different causes:

- The buyer disputes the invoice.
- A payment approver has not completed an internal process.
- The payment link was lost or expired.
- The company has a temporary cash-flow problem.
- The buyer repeatedly delays or breaks promises to pay.
- The invoice is genuinely unlikely to be recovered without a human relationship manager.

Traditional receivables systems commonly use fixed dunning rules, such as:

- Day 1: send reminder
- Day 7: send another reminder
- Day 15: escalate
- Day 30: hand off to collections

This is inefficient because every customer and invoice receives the same treatment, regardless of amount, history, dispute status, payment behavior, or likelihood of recovery.

## The core problem

The problem is not simply identifying an overdue invoice.

The real problem is:

> For each overdue invoice, choose the next safe action that maximizes expected recovery value while respecting customer-contact limits, disputes, approvals, and audit requirements.

---

# 3. Our solution

The Revenue Recovery Intelligence Agent follows this decision loop:

```text
Observe invoice data
        ↓
Diagnose why it is overdue
        ↓
Predict recovery probability per action
        ↓
Calculate expected recovery value
        ↓
Apply policy and safety guardrails
        ↓
Execute only approved actions
        ↓
Verify outcome
        ↓
Record everything in audit trail
        ↓
Retry, escalate, or stop
```

The central design principle is:

> AI can recommend; deterministic policy decides what is allowed; only approved tools can execute actions.

This prevents an AI model from inventing discounts, contacting disputed customers incorrectly, or repeatedly sending reminders without controls.

---

# 4. Target users

The system is intended for:

- Finance and accounts receivable teams
- B2B merchants using Razorpay invoices or payment links
- Collections and revenue-operations teams
- Account managers responsible for high-value customers
- Merchant owners who need visibility into revenue at risk

---

# 5. Main user journey

A merchant uploads or syncs overdue invoices.

For every invoice, the system:

1. Reads the invoice and customer-payment context.
2. Determines why it is probably overdue.
3. Estimates which allowed action has the best chance of recovery.
4. Calculates the expected recovered amount.
5. Checks whether that action is permitted.
6. Executes the approved action through a payment workflow.
7. Tracks the result.
8. Escalates or stops when appropriate.
9. Shows the complete reasoning and action history in the dashboard.

Example:

```text
Invoice: ₹2,50,000
Days overdue: 45
Customer history: 3 prior late payments, 1 broken promise
Diagnosis: Cash-flow risk
Best predicted action: Offer payment plan
Predicted recovery probability: 42%
Expected recovery: ₹1,05,000
Policy result: Requires human approval because amount exceeds threshold
Final action: Human approval requested
Audit log: Recorded
```

---

# 6. Project architecture

```text
                    ┌──────────────────────────┐
                    │ Merchant / Dashboard UI  │
                    └────────────┬─────────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │      FastAPI Backend     │
                    └────────────┬─────────────┘
                                 │
      ┌───────────────┬──────────┼───────────┬───────────────┐
      │               │          │           │               │
┌─────▼─────┐  ┌──────▼─────┐ ┌──▼────────┐ ┌▼────────────┐ ┌▼───────────┐
│ Data      │  │ Diagnosis  │ │ Prediction│ │ Policy       │ │ Execution  │
│ Foundation│  │ Engine     │ │ & Ranking │ │ Engine       │ │ Tools      │
└─────┬─────┘  └──────┬─────┘ └──┬────────┘ └┬────────────┘ └┬───────────┘
      │               │          │           │               │
      └───────────────┴──────────┴───────────┴───────────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │ SQLite / PostgreSQL       │
                    │ Invoices + Audit Events   │
                    └──────────────────────────┘
```

---

# 7. Layer-by-layer project design

## Layer 1: Data foundation

### Purpose

Create reliable, realistic receivables data and store it safely.

### What it contains

- Synthetic overdue invoices
- Customer payment-history attributes
- Promise-to-pay records
- Invoice lifecycle status
- Audit events
- Batch-level summary data

### Invoice fields

Each invoice contains fields such as:

- Invoice ID
- Batch ID
- Invoice number
- Customer name
- Customer email
- Industry
- Customer segment
- Invoice amount in paise
- Due date
- Days overdue
- Invoice status
- Dispute flag
- Number of prior invoices
- Historical late-payment rate
- Number of previously broken promises
- Contact count
- Whether a payment link was previously sent
- Created timestamp

### Customer segments

The synthetic generator creates customers across:

- SMB
- Mid-market
- Enterprise

### Industries

The generated portfolio includes industries such as:

- SaaS
- Manufacturing
- Logistics
- Healthcare
- Retail
- Education

### Why synthetic data is needed

We do not have real merchant receivables data for the buildathon. Therefore, the project uses a synthetic dataset generator.

However, it does not generate unrelated random values.

For example:

- A customer with a higher prior late-payment rate is more likely to have broken promises.
- A customer with repeated broken promises is more likely to have payment risk.
- A healthcare invoice can have a higher dispute probability.
- Larger or enterprise invoices can behave differently from SMB invoices.
- Days overdue, customer history, and invoice amount influence recovery likelihood.

This produces data that is useful for demonstration, training, and evaluation.

### Promise-to-pay data

A promise-to-pay record represents a customer commitment to pay by a particular date.

Fields include:

- Promise ID
- Invoice ID
- Promised payment date
- Promised amount
- Whether it was kept
- Created timestamp

The system generates both:

- `kept=True`
- `kept=False`

This is important because a future model must see both successful and broken promises.

### Current completion status

Completed.

---

## Layer 2: Deterministic diagnosis engine

### Purpose

Explain why an invoice is likely overdue before deciding what action to recommend.

### Why it is deterministic

This layer is not an LLM and not a machine-learning model.

It uses transparent, testable rules based only on observable invoice facts. This makes the result explainable and safe.

### Diagnosis categories

#### 1. Disputed

Triggered when:

```text
dispute_flag = true
```

Meaning:

The invoice should not be treated as normal non-payment. It requires a human dispute-resolution path.

#### 2. Likely process delay

Triggered when:

```text
days_overdue <= 14
prior_late_payment_rate < 0.2
prior_broken_promises = 0
```

Meaning:

The customer is historically reliable and the invoice is only recently overdue. The likely cause may be internal approval, invoice processing, or payment-link friction.

#### 3. Cash-flow risk

Triggered when:

```text
prior_late_payment_rate >= 0.4
OR
prior_broken_promises >= 1
```

Meaning:

The customer’s history suggests financial pressure or unreliable payment behavior.

#### 4. Chronic non-payment

Triggered when:

```text
days_overdue > 60
AND
prior_broken_promises >= 2
```

Meaning:

The invoice has been overdue for a long period and the buyer has repeatedly failed to keep commitments.

#### 5. Standard overdue

Fallback classification.

Meaning:

The invoice is overdue, but the system does not have sufficient evidence for a stronger diagnosis category.

### Output

The diagnosis layer returns:

- Machine-readable diagnosis code
- Human-readable explanation
- Supporting evidence/signals

Example:

```json
{
  "code": "cash_flow_risk",
  "explanation": "Payment history indicates elevated cash-flow or payment-reliability risk.",
  "signals": [
    "prior_late_payment_rate=0.48",
    "prior_broken_promises=1"
  ]
}
```

### Current completion status

Completed.

---

## Layer 3: Training-data generation

### Purpose

Create labeled historical action-outcome data to train the prediction model.

### Why this layer is needed

We have synthetic invoices, but a prediction model needs examples like:

```text
Invoice features + action taken → recovered or not recovered
```

For example:

```text
₹80,000 invoice
18 days overdue
SMB customer
High historical late-payment rate
Action: resend payment link
Outcome: recovered = yes
```

### How labels will be generated

A hidden outcome simulator will define recovery probabilities internally.

Example concept:

```text
Reminder: 24% recovery probability
Payment-link resend: 30% recovery probability
Payment plan: higher probability for long-overdue cash-flow cases
Account-manager escalation: higher probability for enterprise cases
```

The simulator will use this probability only to sample a binary outcome:

```text
recovered = true
or
recovered = false
```

The training model never receives the hidden probability.

### Why this avoids leakage

The model will only see:

- Invoice fields
- Diagnosis code
- Candidate action
- Binary historical outcome

It will not see:

- Hidden simulator formulas
- Hidden recovery probability
- Any oracle-only variables

This avoids directly teaching the model the answer.

### Dataset splitting

We will use separate data splits:

- Training dataset: generated with seed A
- Validation/calibration dataset: generated with seed B
- Final demonstration evaluation dataset: generated with seed C

The final evaluation batch will never be used during training.

### Current completion status

Planned.

---

## Layer 4: Recovery prediction model

### Purpose

Estimate the probability that a particular action will recover an invoice.

### Candidate revenue actions

The model will estimate recovery probability for:

- Send reminder
- Resend payment link
- Offer payment plan
- Escalate to account manager

### Input features

Possible model inputs:

- Invoice amount
- Days overdue
- Industry
- Customer segment
- Dispute status
- Prior invoice count
- Prior late-payment rate
- Prior broken promises
- Contact count
- Payment-link status
- Diagnosis code
- Candidate action

### Model choice

A lightweight interpretable model is sufficient:

- Logistic regression
- Gradient boosting
- Calibrated classifier

The intended approach is a calibrated classifier, likely logistic regression first.

### Why calibration matters

A model may rank actions correctly but still produce unreliable probability values.

For example:

```text
Model says 80% recovery chance
Actual historical success rate is 35%
```

That is unacceptable because expected recovery calculations would be misleading.

Calibration aligns predicted probabilities with observed outcomes.

For example:

```text
Invoices predicted at 40% recovery should recover roughly 40% of the time.
```

### Current completion status

Planned.

---

## Layer 5: Expected-value ranking

### Purpose

Choose the action that produces the highest expected recovered value.

### Formula

```text
Expected recovery value = predicted recovery probability × invoice amount
```

Example:

| Action | Predicted recovery probability | Invoice amount | Expected recovery |
|---|---:|---:|---:|
| Reminder | 35% | ₹1,00,000 | ₹35,000 |
| Payment-link resend | 42% | ₹1,00,000 | ₹42,000 |
| Payment plan | 38% | ₹1,00,000 | ₹38,000 |
| Account-manager escalation | 30% | ₹1,00,000 | ₹30,000 |

The ranking recommends:

```text
Resend payment link
```

because it has the highest expected recovered amount.

### Important constraint

The following are not revenue-ranking actions:

- Request human approval
- Stop
- Route to dispute resolution

These are policy outcomes, not direct recovery tactics. They must not compete in the same expected-value ranking.

### Current completion status

Planned.

---

## Layer 6: Policy and guardrail engine

### Purpose

Decide whether a recommended action is actually allowed.

This is one of the most important parts of the project.

The prediction model may recommend an action, but the policy engine has final authority.

### Example policy rules

#### Dispute policy

```text
If dispute_flag = true:
    do not send normal dunning outreach
    route to human dispute resolution
```

#### Contact cap

```text
If contact_count >= allowed maximum:
    stop automatic contact
```

#### High-value invoice policy

```text
If invoice amount exceeds threshold:
    require human approval before payment-plan offer or escalation
```

#### Broken-promise policy

```text
If customer has repeated broken promises:
    avoid endless reminders
    escalate or stop based on policy
```

#### Retry policy

```text
Do not retry the same action beyond the configured number of attempts.
```

#### Payment-plan policy

```text
The AI cannot invent discounts, installments, or settlement terms.
Only preconfigured payment-plan offers are permitted.
```

### Output examples

```text
Recommendation: resend payment link
Policy result: approved
```

```text
Recommendation: offer payment plan
Policy result: human approval required
Reason: invoice amount exceeds ₹5,00,000
```

```text
Recommendation: reminder
Policy result: blocked
Reason: invoice is dispute-flagged
```

### Current completion status

Planned.

---

## Layer 7: Execution tools

### Purpose

Perform approved recovery actions.

### Planned tool registry

- Send reminder
- Resend payment link
- Offer payment plan
- Escalate to account manager
- Request human approval
- Stop workflow

### Razorpay integration

For the buildathon, actions can integrate with Razorpay test-mode APIs, such as:

- Payment Links API
- Invoice API
- Payment status polling or webhook handling

### Idempotency

Every action will have an idempotency key.

This prevents duplicate execution caused by:

- Webhook retries
- Network timeouts
- Repeated button clicks
- Worker retries
- Process restarts

Example:

```text
invoice_123 + resend_payment_link + attempt_1
```

If the same execution request appears again, the system should return the original action result instead of resending the payment link.

### Current completion status

Planned.

---

## Layer 8: Verification and outcome tracking

### Purpose

Determine whether an action actually worked.

### Possible outcomes

- Invoice paid
- Payment link opened
- Payment link expired
- Promise-to-pay received
- Promise kept
- Promise broken
- No response
- Dispute raised
- Escalation required
- Workflow stopped

### Verification methods

- Razorpay webhook
- Payment status polling
- Simulated outcomes for the hackathon dataset
- Manual account-manager update

### Important transparency rule

For the demo:

```text
Razorpay test-mode API execution is real test-mode execution.
Financial recovery outcome is simulated unless connected to real merchant transactions.
```

The dashboard must never claim simulated recovery as actual merchant cash collection.

### Current completion status

Planned.

---

## Layer 9: Audit trail

### Purpose

Provide a complete, tamper-resistant operational history of the system.

### Audit events

The audit log will eventually include:

- Invoice ingested
- Diagnosis generated
- Prediction generated
- Candidate actions scored
- Policy rule evaluated
- Recommendation approved or blocked
- Human approval requested
- Tool/API action executed
- Payment outcome received
- Retry scheduled
- Escalation created
- Stop decision taken

### Stored audit details

Each event can include:

- Event ID
- Invoice ID
- Action type
- Idempotency key
- Timestamp
- Reasoning details
- Policy result
- API response metadata
- Outcome result

### Current completion status

Partially complete.

Currently completed:

- Invoice ingestion events
- Audit-event table
- Unique idempotency-key field
- API to retrieve audit events

Still planned:

- Decision, policy, execution, and outcome audit events

---

## Layer 10: Dashboard

### Purpose

Give merchants a clear operational and financial view of recovery performance.

### Batch-level metrics

The dashboard will show:

- Total overdue invoice count
- Revenue at risk
- Expected recoverable revenue
- Simulated/actual recovered revenue
- Recovery rate
- Escalation rate
- Broken-promise rate
- Dispute rate
- Amount recovered by action type
- Recovery by customer segment
- Recovery by overdue-age bucket

### Invoice-level view

For each invoice:

- Customer details
- Amount
- Days overdue
- Diagnosis
- Recommended action
- Predicted recovery probability
- Expected recovery amount
- Policy decision
- Action status
- Payment status
- Full audit timeline

### Current completion status

The backend summary endpoint is complete.

Frontend dashboard is planned.

---

# 8. Current API endpoints

The backend currently exposes:

| Endpoint | Purpose |
|---|---|
| `GET /health` | Confirms backend service is running |
| `POST /batches?size=250&seed=42` | Generates and stores a synthetic invoice batch |
| `GET /invoices?batch_id=<id>` | Lists invoices in a batch |
| `GET /invoices/{invoice_id}` | Returns one invoice |
| `GET /invoices/{invoice_id}/diagnosis` | Returns deterministic overdue diagnosis |
| `GET /invoices/{invoice_id}/audit` | Returns audit events for one invoice |
| `GET /batches/{batch_id}/summary` | Returns batch-level receivables summary |

---

# 9. Technology stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI |
| Language | Python |
| Database | SQLite now; PostgreSQL later |
| Synthetic entities | Faker |
| Data behavior and simulation | NumPy + custom rules |
| Validation/models | Pydantic |
| ML model | scikit-learn, planned |
| Payment execution | Razorpay test-mode APIs, planned |
| Frontend | React + Tailwind, planned |
| Testing | Pytest |

---



# 11. What remains to be built
- FastAPI backend scaffold
- Dependency and test setup
- Synthetic correlated invoice generator
- Seeded/reproducible data generation
- Synthetic promise-to-pay data with both kept and broken outcomes
- SQLite invoice storage
- SQLite promise-to-pay storage
- Append-only ingestion audit events
- Explicit SQLite transaction and connection lifecycle handling
- Foreign-key enforcement
- Idempotency-key database support
- Deterministic diagnosis engine
- Batch, invoice, summary, audit, and diagnosis APIs
- Unit and API-level tests


In order:

1. Synthetic historical action-outcome dataset generator  
2. Calibrated recovery-probability model  
3. Expected-value action ranking  
4. Recommendation API endpoint  
5. Policy and guardrail engine  
6. Action state machine and idempotency enforcement  
7. Razorpay test-mode payment-link/invoice execution  
8. Outcome verification loop  
9. Full audit logging for all decisions and actions  
10. React/Tailwind dashboard  
11. Fixed-cadence baseline strategy  
12. Batch evaluation comparing baseline versus intelligent policy  
13. Demo scenario where the agent safely stops or escalates  
14. Final architecture diagram, pitch narrative, and demo video  

---

# 12. Differentiation

The project is not just:

> “An AI bot sends payment reminders.”

Its differentiators are:

- Focus on B2B receivables rather than generic payment retries.
- Deterministic explanation of why an invoice is overdue.
- Action-level recovery probability prediction.
- Expected-value ranking based on invoice amount.
- Policy guardrails that override model recommendations.
- Human approval for sensitive or high-value decisions.
- Idempotency and auditability from the start.
- Honest synthetic-data evaluation with a hidden outcome simulator.
- Explicit comparison against a simple fixed-cadence reminder baseline.

The intended final message is:

> A policy-gated recovery decision engine that chooses the safest, highest-value next action for each overdue B2B invoice and proves its performance against measured simulated outcomes.