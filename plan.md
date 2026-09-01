# Revenue Recovery Intelligence Agent — Ship Plan (v4)

> **Supersedes `plan.v2.superseded.md` and `project.md`** (v3 was edited
> in place to become this version — no separate v3 snapshot was kept). This
> is the single source of truth. v2 was a 10-milestone
> architecture written without a deadline; v3 rescoped it to eight days and
> folded in the five defects found in the code audit. **v4 re-sequences v3
> for a solo builder with no slack**, after Day 1's actual execution (below)
> surfaced two more defects and consumed a full calendar day on its own —
> the original per-day gates all held, but "Day 1" landed on the calendar
> day after the one it was named for.
>
> **Deadline: Thursday 3 September 2026. Today: Friday 28 August (evening).**
> Day 1 (foundation fixes) is **done** — it ran today, Friday 28 August, not
> Thursday 27 as v3's calendar assumed. That leaves **exactly six calendar
> days — Sat 29 through Thu 3 — for six remaining milestones**, solo, at
> 6–8 hours/day. §9 below is the reconciliation: two of the highest-
> uncertainty tasks (the Razorpay spike, an LLM accuracy spot-check) move
> forward into Day 2, and the Razorpay *execution* build moves from its own
> day into Day 4, next to the state machine it's an extension of, rather
> than two artificially separated concerns three days apart. Day 7 absorbs
> what was two separate days (dashboard, then ship) because documentation is
> written incrementally through the week instead of saved for the end.
> Nothing in the system architecture changed from v3 — only the calendar.
>
> **Amended the same evening: the LLM vendor switched from Anthropic to
> Google Gemini (ADR-004, §12).** The Anthropic Console's free trial credit
> never materialized after signup; rather than lose D2 morning to account
> troubleshooting, the one LLM seat (§6.8) moves to Gemini's free tier,
> which is free on an ongoing basis rather than a one-time credit. Nothing
> else changed — same one seat, same job (reply extraction only), same
> evidence-not-decisions design.
>
> **Target:** Razorpay AI Buildathon 2026 — **Track 03, AI Revenue Recovery**.
> **Track brief (verbatim):** *"Find revenue that's slipping away and win it
> back. Build an agent that detects revenue at risk, determines the right
> intervention, and executes a bounded recovery workflow: from payment failures
> and checkout abandonment to overdue receivables."*
> **The bar (verbatim):** *"measured money recovered across a batch, with
> compliant escalation, stopping rules, and an audit trail."*
> **Deliverables:** public repo + 5-minute pitch video + architecture doc.

---

## 0. How to use this document

Each layer has three fixed sections: **Contract** (exact types — do not
improvise), **Rules** (the logic), **Done when** (acceptance criteria; write the
test before claiming the layer is done).

Build in day order (§9). Do not start a day until the previous day's gate
passes. If a gate slips past its day, go to §10 and cut — do not extend the day
and compress a later one.

**The scope in this document is already the cut version.** Adding anything to
it is the failure mode that loses the submission.

---

## 1. What changed from v2, and why

### 1.1 The fifteen defects found in the code audit and real execution

The v2 plan was sound; the code did not match it. The original audit found
five (F1–F5); actually running the stack and, later, actually clicking
through the browser — not just reading the code — surfaced five more (F6
through F10) that no amount of code review would have caught. A genuine
cold-clone check (fresh rsync copy, isolated Docker Compose project, remapped
ports, no shared state with the working tree) found one more (F11), specific
to the gap between "works in my dev checkout" and "works from a stranger's
`git clone`." A pre-recording rehearsal of the actual judge demo — clicking
through the dashboard the way a presenter would, not reading the CSS — found
a twelfth (F12). A thirteenth (F13) came directly from the user clicking
"Execute" and reporting that nothing visible happened — the single most
demo-critical defect on this list, since it undermined the exact claim
("actions execute for real") the whole system exists to prove. A
fourteenth (F14) followed immediately: the user noticed the drafted
messages F13 introduced had no recipient at all. A fifteenth (F15) —
arguably the most serious defect on this list, since it silently broke
the tamper-evidence guarantee this project treats as non-negotiable — was
found while proving the Razorpay webhook loop closes end to end with a
real test-mode payment. All fifteen are fixed and verified live.

| # | Defect | Evidence | Fixed on |
|---|---|---|---|
| **F1** | **No database schema exists.** `app/db/migrations/versions/` has zero files and there is no `create_all` anywhere. Every DB endpoint 500s. v2's M0 gate could never pass. | `ls -A app/db/migrations/versions/ \| wc -l` → `0`; `grep -rn "create_all" app/ \| wc -l` → `0` | **D1** |
| **F2** | **The holdout arm measures nothing.** The environment defines `P(recover \| action)` but has no self-cure path — `ActionKey` has six members, all of them actions. Holdout recovers 0% by construction, so "incremental recovery" silently collapses back to raw recovery: the exact inflated number the holdout exists to prevent. | No `no_action` / `self_cure` symbol anywhere in `app/` or `docs/` | **D2** |
| **F3** | **The environment has no time axis.** `sample_outcome()` returns a bare `bool`. But the EV formula takes `days_to_cash`, the workflow runs 90 simulated days, and the dashboard's hero is a recovery *curve*. | `app/simulation/environment.py:sample_outcome` returns `bool` | **D2** |
| **F4** | **Portfolio composition breaks the demo.** Measured on n=3,000: `cash_flow_risk` 56.8%, `disputed` 19.7% (real B2B is ~2–5%), `channel_failure` 1.4%, `chronic_non_payment` 2.7%. Root cause is **rule design, not the generator** — R03 fires on `broken_promises >= 1`, which 72.7% of customers have, so it swallows the portfolio and steals 74% of R04's natural population before R04 is even evaluated. Also: 20% disputed means a fifth of the portfolio exits at P01 and never contributes to measured uplift. | Diagnosis cascade + threshold sweep over `generate_portfolio(6000, seed=7)` | **D1** |
| **F5** | **Reproducibility gate fails; one test asserts the wrong rule.** `generate_portfolio()` defaults `now = datetime.now(timezone.utc)` and `due_date`/`issued_at` derive from it, so the same seed twice differs. Separately, `test_diagnosis.py` case 7 expects `process_delay` for `late_rate=0.39`, but R05 requires `< 0.2` — the code is right, the test is wrong. | Two-call fingerprint mismatch; `pytest` → 40 passed, 1 failed | **D1** |
| **F6** | **Found during D1 verification, not in the original audit.** The process clock defaulted to `RealClock`, but every generated portfolio is anchored to a fixed reference instant (2026-01-01). Downstream code recomputes `days_overdue` from `clock.now() - due_date` — so as real wall-clock time drifts past the anchor (by August, ~240 days), every invoice looks catastrophically overdue regardless of what the generator intended. The live diagnosis mix came back 44% chronic / 0% process-delay against declared bands of 7–14% / 16–24%. | 500-invoice batch, diagnosis mix measured via 500 live API calls, before vs after the fix | **D1** |
| **F7** | **Found during D1 verification.** `ArmAssignment` holds a raw foreign key to `invoices.id` with no ORM `relationship()` linking the two mapper classes, so SQLAlchemy's unit-of-work has no edge to infer insert ordering and batched the tables in a sequence that violated the FK constraint at 500 rows. Every seed of the standard batch crashed. | `POST /batches?size=500` → 500 Internal Server Error, `ForeignKeyViolationError` in the API logs | **D1** |
| **F8** | **Found live while testing the new `/evaluate` endpoint, not by code review.** `_AMOUNT_LOGNORMAL`'s (mu, sigma) pairs were tuned assuming the raw lognormal draw represents rupees (the code comments say so explicitly — "median ~ Rs 54k"), but the generator stored that raw number directly as `amount_paise` with no ×100 conversion. Every invoice amount was ~100x too small: no invoice in a 500-batch ever exceeded ~Rs 1L, so P06's Rs 5,00,000 approval gate could never fire, and every "revenue at risk" figure — including the plan's own dashboard mockup number — would have been off by two orders of magnitude. | Segment medians measured against the documented DGP: smb showed ₹5,000 (the clip floor) instead of the documented ~₹54k | **D2 (compressed)** |
| **F9** | **Found live while manually testing `/act` twice in a row — the exact scenario idempotency exists to prevent.** `attempt_no` was computed as "count of ALL existing Action rows for this (invoice, action)," which increments on every call including successful ones — so every repeat call to `/act` produced a genuinely different idempotency key and re-executed for real. Two distinct Razorpay payment links were created from two calls that should have collapsed to one. Fixed: a successfully `executed` action is now returned unconditionally on any later call; `attempt_no` counts only prior `failed` attempts, so a retry only produces a new key when the previous one actually failed. | `POST /invoices/{id}/act` called 3 times: before the fix, 2 different `plink_...` IDs came back; after, all 3 calls returned the identical ID with `idempotent_replay: true` on calls 2 and 3 | **D4 (compressed)** |
| **F10** | **Found live while browser-testing the dashboard's "gated action" display.** `/evaluate` and `/act` called `rank_actions()` with `history=[]` unconditionally — so the escalation ladder's cooldown/rung constraints could never actually apply, even moments after a real action had been executed on the same invoice. Fixed: `_decide()` now queries the invoice's real executed `Action` rows and builds genuine `ActionHistoryEntry` objects with `days_ago` computed from each action's real `executed_at`. Two more, smaller bugs surfaced and were fixed in the same browser-testing pass: `format_rupees()` used Python's `:,` (Western digit grouping) while the dashboard's frontend used `toLocaleString("en-IN")` (Indian grouping), so the same amount showed "Rs 362,554" in one place and "Rs 3,62,554" in another on one screen; and inserting the evaluation chart as a DOM sibling inside the dashboard's CSS Grid broke the grid's auto-placement, silently collapsing the detail pane to the queue's width three rows down the page. | Re-evaluating an invoice right after executing `send_upi_payment_link` on it now correctly shows that action `ladder_eligible: false` with a "highest EV but gated" note, and a lower-ranked action becomes the real recommendation — verified both via the API response and visually in the browser (struck-through row, GATED label) | **D7 (compressed)** |
| **F11** | **Found only by a real cold-clone check** (rsync to `/tmp`, isolated Docker Compose project name, remapped host ports — genuinely fresh containers/volumes/network, no shared state with the dev checkout). `tests/unit/test_policy_engine.py::test_no_eval_or_exec_in_app` computed its `grep` working directory via `__file__.rsplit("/backend/", 1)[0] + "/backend"` — a string match on the literal path segment `"/backend/"`. That segment exists in a local checkout (`.../Revenue Recovery Intelligence Agent/backend/tests/...`) but not inside the Docker image, where the same file lives at `/code/tests/unit/test_policy_engine.py` with no `"backend"` segment at all — `rsplit` silently found nothing to split on and produced a garbage path, crashing the test with `NotADirectoryError`. A second, related discovery in the same pass: `docker-compose.yml` mounts `./app`, `./policies`, and `./config` as live volumes but deliberately does not mount `./tests` — so `tests/` inside a running container is a static `COPY` from image build time, and a host-side edit to a test file needs an image rebuild (`docker compose up -d --build`), not just a file save, before it's visible in the container. This is correct scoping (tests aren't meant to hot-reload against a running server), but worth knowing so a "the container didn't pick up my fix" moment doesn't get misdiagnosed as a Docker bug. Fixed: the test now computes its root via `Path(__file__).resolve().parents[2]` — structural (this file is always `tests/unit/<name>.py`, two directories under the project root) rather than name-based, so it's correct on any checkout path and inside any container regardless of what the root directory is called. | Local host: 145/145 passed before the fix (bug invisible there). Isolated cold-clone container, before the fix: `NotADirectoryError: [Errno 20] Not a directory: '/code/tests/unit/test_policy_engine.py/backend'`. After the fix + image rebuild, same isolated container: 145/145 passed. Isolated stack torn down clean afterward (`docker compose down -v`); original stack confirmed untouched throughout (540 invoices intact, `/health` OK). | **Post-D9, pre-submission** |
| **F12** | **Found during a live rehearsal of the judge demo — actually clicking through the dashboard the way a presenter would, not by reading the CSS.** Two bugs in the same pass. First: `.queue`/`.detail` used `max-height: calc(100vh - 56px)` with independent internal scroll, an assumption that only held while `.layout` was the first thing rendered under the header. Adding the Portfolio ROI card (§1.1a) above `.layout` broke it — the panes' internal scroll position and the page's own scroll position fought each other, producing a visible overlap while scrolling that would have looked broken on camera. Second: the counterfactual card's right-hand column clipped text mid-word ("held for huma[n] approval") — a classic flexbox bug, flex children default to `min-width: auto` (content-sized), so long text overflowed the column instead of wrapping. Fixed: `body` is now a flex column with `.layout` set to `flex: 1 1 auto; min-height: 0`, so the panes size against whatever space genuinely remains instead of a stale viewport-height assumption; `.cf-col` got `min-width: 0` and `.cf-action`/`.cf-reason` got `overflow-wrap: break-word`. | Confirmed via computed layout (`getBoundingClientRect`, `getComputedStyle`) and the accessibility tree, not screenshots alone — the browser pane's own screenshot capture was unreliable mid-session, so verification leaned on DOM/CSS introspection instead of trusting a possibly-stale pixel capture. 150/150 tests still pass (no decision logic touched). | **Pre-recording rehearsal** |
| **F13** | **Reported directly by the user clicking "Execute recommended action" and seeing nothing: "no email sent, no call or nothing, it is just simply UI changes."** Two compounding bugs. First, and more fundamental: `execute_tool()` for every action except the two real Razorpay calls (`send_upi_payment_link`, `resend_payment_link`) returned a bare `{"recorded": true}` or `{"sent": true, "channel": "console"}` — genuinely no visible content for a viewer to evaluate, honest about not sending anything for real but unconvincing on a demo screen. Second, and the actual root cause of "it's just a UI change": even where content *was* about to be shown, the dashboard's execute handler called `selectInvoice(currentInvoiceId)` immediately after rendering the result, and `renderDetail()` rebuilds the whole `#detail` pane from scratch — including a fresh, empty `#act-result` div — so any result was wiped before a viewer could see it, within a single JS tick. The strikethrough on the ranked-actions row was the only thing that ever had time to render. Fixed: `app/tools/templates.py` renders real subject/body content (a genuine drafted email/call note, explicitly labeled "not sent — no provider connected") for every message-shaped action; the dashboard now persists the last act-result HTML keyed to the invoice (`lastActResultHtml`/`lastActResultInvoiceId`) and `renderDetail()` restores it into the fresh `#act-result` div instead of leaving it empty; a real Razorpay `short_url` is now rendered as a clickable link. A related copy bug caught in the same pass: the "no provider connected" message read `${r.channel \|\| "no"} provider connected`, which always substituted the real channel name and so read backwards ("email provider connected") except in the one case where channel was empty — fixed to always say "no". | Executed `resend_payment_link` on a fresh invoice: real Razorpay link `https://rzp.io/rzp/qfWSwa6` rendered as a clickable link and survived the automatic re-evaluate refresh (confirmed via the accessibility tree, not just an instant-after screenshot). Executed `offer_payment_plan` on another: full drafted email content rendered and persisted, and the audit timeline's narrated line read "Drafted (not sent): ..." correctly. 158/158 tests pass (150 + 8 new for `app/tools/templates.py` and the updated registry tests). | **Pre-recording, user-reported** |
| **F14** | **Reported directly by the user immediately after F13 was fixed: "how can a invoice doesn't have the vendor or customer details, that is bullshit right."** Correct call. `Customer.name` and `Customer.email` were real, generated fields sitting in the DB the whole time, but `execute_tool()` never received them — `render_message()` produced a drafted email with no "To:" and no greeting at all, addressed to nobody. `_Decision` (the shared diagnose/rank/govern result used by both `/evaluate` and `/act`) already fetched the `Customer` row for policy context but never exposed it to its caller. Fixed: `_Decision` now carries `customer`; `act_on_invoice()` passes `customer.name`/`customer.email` through to `execute_tool()` and `render_message()`; templates now render a real "Hi {name}," greeting and the response carries `to`/`to_name` for the dashboard to display as a real "To:" line — and a genuinely missing customer record renders as an honest "no email on file for this customer" in red, not a silently blank line. | Executed `offer_payment_plan` live on INV-1043: rendered "To: Douglas Inc \<osbornejeffery@holmes.com\>" and "Hi Douglas Inc," in the actual dashboard `#act-result` panel, confirmed via `document.getElementById('act-result').innerHTML` after the automatic re-evaluate refresh (persisting per the F13 fix). 162/162 tests pass (158 + 4 new). | **Pre-recording, user-reported** |
| **F15** | **Found while proving the webhook loop closes end to end, with real money moving through Razorpay's test mode.** A real invoice accumulated three real audit events — `invoice_ingested`, `action_executed`, `payment_received` (the last one written by the webhook handler in a separate HTTP request from the first two) — and `/invoices/{id}/audit/verify` reported `intact: false`. Root cause: this project's simulated demo clock stamps every event with the identical `created_at` (every event this build has ever produced shows `2026-01-01T09:00:00+00:00`, regardless of when it was actually written), and `AuditEvent.id` is a random UUID with zero correlation to insertion order. `_tip_hash()` (which every new audit write depends on to find "the previous event's hash") and `verify_invoice_chain()` both ordered rows by `ORDER BY created_at DESC/ASC` alone — genuinely ambiguous once 2+ events on one invoice share a timestamp, which is the normal case under this project's frozen clock, not an edge case. Postgres returned `invoice_ingested`'s hash as the "tip" instead of `action_executed`'s, so `payment_received`'s `prev_hash` pointed at the wrong event — a real, silent break in the exact tamper-evidence guarantee this project lists as "not cut under any circumstance." Fixed: added `AuditEvent.seq`, a genuine Postgres `IDENTITY` column — monotonic by construction, independent of both the UUID and the clock — and switched `_tip_hash()`, `verify_invoice_chain()`, and `GET /invoices/{id}/audit` to order by `seq` instead of `created_at`. Required a schema reset (`python -m app.db.reset`, consistent with this project's no-migrations design — plan.md ADR on Alembic) since there's no migration chain to add a column to a live table. | Reproduced deterministically after the fix: executed a real `send_upi_payment_link` on a fresh invoice, then sent a properly HMAC-signed synthetic `payment_link.paid` webhook (signed with the real secret, computed and used entirely inside the container so it never appeared in any tool output) for that invoice's real `plink_...` id. All three events landed with the identical frozen timestamp exactly as before — and this time `/audit/verify` returned `intact: true, events_checked: 3`. 162/162 tests still pass (pure-Python chain logic in `test_audit_chain.py` was already correct and untouched; the bug was entirely in how rows were fetched before reaching it). | **Pre-recording, user-initiated real payment test** |

### 1.1a Three presentation-layer additions, post-D9, pre-submission

None of these change any decision logic — they surface data the system
already computed, for a judge watching a 5-minute video rather than reading
API responses. Built and verified live against the running stack (150/150
tests, up from 145, after adding `tests/unit/test_baseline_counterfactual.py`).

- **Counterfactual side-by-side** (`app/domain/baseline.py`,
  `build_explanation()`'s new `counterfactual` field). Every invoice's
  evaluate response now states what a naive, diagnosis-blind fixed cadence
  would do to it right now, next to what this system actually decided —
  making "the policy overrides the naive choice" visible on one invoice
  instead of asserted in aggregate metrics. `app/evaluation/simulate.py`'s
  baseline arm now imports its cadence from this same module, so the live
  counterfactual and the three-arm measurement can never silently define
  "baseline" two different ways. Verified live on INV-1017
  (`channel_failure`, 3 days overdue): fixed cadence says `send_reminder`;
  this system says `send_upi_payment_link`, because a payment link was
  already sent and never opened — reminders don't fix a channel problem.
- **Portfolio ROI card** (`/evaluation/summary`'s new fields,
  dashboard's "Portfolio ROI" card). One arithmetic chain, not a chart:
  incremental recovery vs. holdout, minus the real cost of every action
  taken to get it, equals net incremental recovery. Verified live at
  seed=42/size=300: ₹5,68,84,482 − ₹1,58,442 = ₹5,67,26,040, matching the
  card's displayed subtraction exactly — checked so a judge doing the
  mental math on screen doesn't catch an inconsistency.
- **Narrated audit trail** (`narrate_audit_event()` in `app/audit/explain.py`,
  a new `narrative` field on every `/invoices/{id}/audit` row). The same
  hash-chained events, rendered as plain-English lines instead of raw JSON.
  Honestly thin today — only `invoice_ingested` and `action_executed`/
  `action_failed` are ever written, since `/evaluate` is deliberately
  side-effect-free (documented in its own docstring) and the webhook
  receiver doesn't yet link back to an invoice's audit trail. Worth
  stating if asked rather than letting the UI imply a richer trail than
  what's actually recorded.

### 1.2 What the track bar demands that v2 under-weighted

Re-reading the published track brief and the buildathon's stated evaluation
focus changed three priorities:

- **"handle at least one system failure gracefully" is an explicit criterion**,
  and v2 had no story for it beyond a cold-start fallback nobody would see.
  → §6.8 adds a **chaos switch** that kills the LLM and the Razorpay client
  mid-demo and shows the loop continuing on rules and templates. Two hours of
  work against a directly stated criterion.
- **"if your project touches agents, RAG, or LLM orchestration, that should be
  the part of the demo you spend the most time on."** v2 buried reply
  intelligence at M6 of 9. → It gets a real-accuracy spot-check on Day 2
  (before the full build, not after it), a full day of its own on Day 6
  protected by the cut ladder, and 90 seconds of a 5-minute video instead of
  30.
- **"AI Judgment — whether AI tools were applied appropriately instead of
  forcing unnecessary tech stacks."** This actively rewards restraint. → The
  README's "deliberately not used" section is now a scored asset, and it grew
  one entry (see §1.3).

### 1.3 What got cut, and the reasoning

Each of these is a decision you must be ready to defend on camera. The
reasoning is the deliverable, not just the cut.

| Cut | Replaced by | Why this is defensible, not lazy |
|---|---|---|
| **The trained model** (logistic + isotonic calibration, reliability diagram) | `prior_v1` — a hand-set, published prior table over (diagnosis, action) | This is the strongest cut in the list. We *publish* the decision environment (§6.2) to defeat circular evaluation. A logistic regression trained on samples from a published environment is estimating numbers we already printed in the repo — it adds a day of work and zero information. Say this out loud: *"we didn't train a model because in a declared environment a trained model is a lossy copy of the declaration. We'd rather spend that honesty budget on the holdout arm."* The `Predictor` protocol stays, so a real model drops in behind it unchanged. |
| **Alembic migrations** | `Base.metadata.create_all()` on startup + `make reset` | The demo seeds from scratch on every run. There is no production data and no forward history, so a migration chain is ceremony that also churns daily as the schema moves. Fixes F1 in 20 minutes instead of half a day. Note it in the README as a deliberate, reversible choice. |
| **APScheduler background tick** | The tick is a plain function; `POST /simulate/advance` calls it | Removes a whole class of concurrency bugs and makes every run byte-reproducible, which is the thing the evaluation actually depends on. The tick is a pure function of (clock, DB state) — wiring it to a 30-second timer is four lines we would add for production and zero lines the demo needs. |
| ~~Three extra risk sources~~ **Revised after review: built one stub, not zero.** | `app/sources/base.py` (`RiskSource` Protocol), `app/sources/receivables.py` (real, DB-backed — verified live against the docker Postgres, 5 repeated ticks, 540 invoices, identical set every time, zero duplication), and `app/sources/checkout_abandonment.py` (a genuine ~30-line stub over a *different domain object* — an order, not an invoice) | The track brief explicitly spans "payment failures and checkout abandonment to overdue receivables" — shipping zero evidence the architecture generalizes beyond invoices was a real, fair thing to be pushed on, and cheap to close. One stub (not three) proves the seam without the cost of building adapters nobody demos: `RiskEvent` uses `reference_id`, not `invoice_id`, precisely so a checkout — which has no due date, no dispute flag, no payment history — satisfies the identical `RiskSource` Protocol as a receivable. `subscription_dunning` and `payment_failure` remain named-but-unbuilt in the architecture doc, same reasoning as before. |
| **React + Vite + Tailwind + shadcn + Recharts** | One server-rendered Jinja page, vanilla JS, hand-written inline SVG chart | A solo builder debugging a Tailwind config on day 7 is the classic way to lose a submission. Server-rendered means: no node, no build step, no second process, no CORS, one URL for the judge. The design direction (§6.10) is unchanged — it will look the same. |
| `POST /policy/simulate` | — | Lovely feature; nobody scores it if the loop doesn't run. |
| LLM message generation | Jinja templates | The LLM's place is *reading* replies (genuinely unstructured), not *writing* reminders (a solved template problem). This cut is itself an "AI Judgment" data point — put it in the README. |
| QR codes, `schedule_call`, per-instalment payment-plan links | Payment plan is an internal record; one link type only | Surface area, not substance. |

**Not cut, under any circumstance:** the holdout arm, the audit hash chain,
HMAC webhook verification, the honesty contract, the chaos demo. Those five map
directly onto the published bar.

---

## 2. The claim

Everything below exists to make exactly one sentence true and falsifiable:

> **Given a declared decision environment, this agent recovers *X*% more of a
> receivables portfolio than a fixed-cadence dunning ladder and *Y*% more than
> a no-contact holdout — with a 95% confidence interval, under three
> environments including one where its own beliefs are deliberately wrong —
> while every action it takes is policy-gated, contact-capped, and recorded in
> a tamper-evident ledger.**

Note what is *not* claimed: that this recovers X% more real merchant cash. That
claim would require real merchants. Volunteering the difference is worth more
than hoping nobody asks — see §5.

---

## 3. Architecture

Unchanged from v2. This is the spine of the pitch and does not move.

```text
  RISK SOURCE ──▶ 1. OBSERVE     normalise → RiskEvent
                  2. DIAGNOSE    deterministic cascade R01–R06
                  3. PREDICT     p(recover | action)  ← prior_v1
                  4. RANK        risk-adjusted expected value + ladder
                  5. GOVERN      ◀── FINAL AUTHORITY — policy YAML
                                     allow / gate / block / substitute
                  6. EXECUTE     typed tools, idempotency-keyed,
                                 Razorpay test mode
                  7. LISTEN      webhooks + inbound replies → LLM extraction
                  8. VERIFY      outcome vs holdout; audit close-out
                        │
              retry ▸ escalate ▸ stop ──▶ back to 2
```

**The core invariant — slide 2 of the pitch:**

```text
The model produces a RANKING.
The policy engine produces a DECISION.
The tool registry produces an EFFECT.

A model can never produce a decision.
A decision can never produce an uncontracted effect.
Every effect is idempotent, and every transition is logged.
```

Every arrow writes an audit event. There are no unlogged transitions.

### 3.1 Mapping to the published bar

Build nothing that does not land in this table. Show all four on one screen.

| The bar says | We ship | Where |
|---|---|---|
| "measured money recovered across a batch" | Three-arm experiment, incremental ₹ vs no-contact holdout, bootstrap 95% CI, across 3 environments | §6.7 |
| "compliant escalation" | Escalation ladder with cooldowns; P06 financial-authority gate; approval queue | §6.4, §6.5 |
| "stopping rules" | P02 hard suppression, P03 rolling contact cap, P05 open-promise suppression, P09 daily action budget, chronic → stop | §6.5 |
| "an audit trail" | Per-invoice SHA-256 hash chain + `GET /invoices/{id}/audit/verify` + live tamper demo | §6.6 |
| *(stated eval focus)* "handle one system failure gracefully" | Chaos switch: LLM down + Razorpay down → loop degrades to rules + templates, keeps running, stamps `degraded` | §6.8 |
| *(stated eval focus)* "AI applied appropriately, not forced" | LLM on exactly one path (reading replies); README's "deliberately not used" list | §6.8, §8 |

---

## 4. Domain model

### 4.1 Tables

Unchanged from v2 except: no `predictions` table (priors are deterministic —
recompute rather than store), and `actions.days_to_cash` added for F3.

```sql
-- Portfolio (BUILT)
customers          (id, name, email, industry, segment, relationship_tier,
                    timezone, suppressed, created_at)
customer_history   (customer_id PK, prior_invoice_count, prior_late_rate,
                    prior_broken_promises, avg_days_to_pay,
                    contact_count_30d, last_contacted_at)
invoices           (id, batch_id, customer_id, invoice_number, amount_paise BIGINT,
                    issued_at, due_date, status, dispute_flag,
                    payment_link_sent, payment_link_opened,
                    razorpay_invoice_id, razorpay_payment_link_id, created_at)
batches            (id, seed, size, created_at, notes)
arm_assignments    (invoice_id PK, arm, assigned_at, assignment_hash)   -- BUILT
promises_to_pay    (id, invoice_id, promised_date, promised_amount_paise,
                    source, state, created_at)                          -- BUILT
reply_fixtures     (id, invoice_id, intent_label, text, created_at)     -- BUILT
audit_events       (id, invoice_id, kind, actor, payload JSONB, policy_version,
                    idempotency_key UNIQUE, prev_hash, hash, created_at) -- BUILT

-- Pipeline (D3–D4)
risk_events        (id, source, invoice_id, detected_at,
                    amount_at_risk_paise, payload JSONB)
diagnoses          (id, risk_event_id, code, confidence, rule_id, explanation,
                    signals JSONB, produced_by, created_at)
decisions          (id, risk_event_id, ranked JSONB, chosen_action_key,
                    expected_value_paise, policy_version, policy_result,
                    policy_reasons JSONB, requires_approval,
                    degraded BOOLEAN, created_at)
actions            (id, decision_id, invoice_id, action_key,
                    idempotency_key UNIQUE, state, tool_name,
                    request JSONB, response JSONB, cost_paise,
                    scheduled_for, executed_at, days_to_cash)
scheduled_actions  (id, invoice_id, fire_at, kind, payload JSONB, state)
outcomes           (id, action_id, invoice_id, kind,
                    amount_recovered_paise, observed_at, source)

-- Listening (D6)
inbound_messages   (id, invoice_id, channel, raw_text_redacted, received_at,
                    extraction JSONB, llm_model, llm_cost_micros)
llm_cache          (key PK, response JSONB, model, created_at, hits)
```

### 4.2 Conventions — enforced by CI grep

- **All money is `BIGINT` paise.** No floats in the money path, ever. Format to
  ₹ only at the API boundary.
- **All timestamps `TIMESTAMPTZ` UTC.** Business hours use `Asia/Kolkata`.
- **`datetime.now()` in `app/domain/**` is a CI failure.** Now always comes
  from `clock.now()`. Already enforced by `tests/unit/test_no_wall_clock.py`.
- **`app/domain/` is pure.** No I/O, no network, no clock construction. This is
  what makes the property tests possible.

---

## 5. Honesty contract

Goes in the README **and** on a slide. Volunteering this converts the single
most dangerous question into a credibility signal.

| Component | Status in demo |
|---|---|
| Portfolio, customer history, inbound replies | **Synthetic** — seeded generator, DGP published in `docs/generative_model.md` |
| Diagnosis, ranking, policy, audit, measurement | **Real code** — deterministic and reproducible |
| Reply understanding | **Real LLM calls** — Gemini (free tier), schema-constrained, PII-redacted before every call |
| Razorpay payment links | **Real API calls**, test mode |
| Webhook receipt + HMAC verification | **Real** |
| Whether a customer pays | **Simulated** by a declared environment (§6.2) |
| Recovery probabilities | **Hand-set priors, published** — not a trained model. See §1.3. |
| Reported ₹ recovered | **Simulated cash, real decisions** — never described as merchant cash |

> Every simulated figure in the dashboard renders with a `SIM` chip. The word
> "recovered" never appears without it in demo mode.

---

## 6. Layer specifications

Layers marked **BUILT** exist and pass tests. Layers marked **FIX** exist but
have a defect from §1.1. Layers marked **NEW** do not exist yet.

### 6.1 — Data foundation · **BUILT + FIX (F4, F5)**

The correlated generator, reply corpus, promise generation and declared DGP all
exist and are good. Three edits.

**Edit 1 — fix composition (F4). The fix is in the rules, not the generator.**

The obvious move — lowering the generator's `Poisson(0.3 + 4.5·late_rate)` —
was tested and **does not work**: `cash_flow_risk` only falls 56.8% → 59.3%,
and the correlation gate breaks (0.548 → 0.339, below the 0.4 threshold). The
generator is fine. Leave it alone.

The real mechanism, measured at n=6,000:

```text
P(broken_promises >= 1) = 72.7%   ← R03 fires on this, so R03 claims 74.4%
P(broken_promises >= 2) = 42.9%
P(link sent, never opened, contacts >= 2) = 9.3%   ← R04's natural pool
   ...of which R03 claims first: 74%              ← leaving R04 with 1.4%
```

Two changes, both defensible on business grounds rather than as tuning hacks:

1. **`broken_promises >= 1` is too loose for R03.** One broken promise is noise;
   two is a pattern. Raise the threshold to `>= 2`.
2. **R04 `channel_failure` moves above R03.** If a payment link was sent and
   never opened across repeated contacts, you cannot conclude *anything* about
   ability or willingness to pay from someone who demonstrably never saw the
   invoice. Diagnosing "cash-flow risk" for that customer is simply wrong. This
   ordering change makes the cascade more correct, not just better-balanced.

Full corrected cascade in §6.3. Two supporting generator edits:

- Scale `_DISPUTE_BASE` by **0.55** and drop the high-value dispute bump from
  `+0.05` to `+0.02` — the current base rates give 7.2% disputed against a real
  B2B rate of 2–5%.
- **Pre-generated replies are *unread* at generation time.** The 19.7% disputed
  figure came from treating the seeded reply corpus as already-extracted, so
  `has_open_dispute_reply` fired at generation. It must be `False` until the
  M6 extraction layer actually reads the reply — which is both the correct
  model of the world and the thing that makes the D6 demo land ("watch the
  dispute flag appear *after* the agent reads the message").

**Measured result** of the corrected config, stable across 5 seeds at n=3,000:

| Diagnosis | Measured | Accept band |
|---|---:|---:|
| `cash_flow_risk` | 33.4% | 28–38% |
| `standard_overdue` | 23.8% | 19–28% |
| `process_delay` | 20.1% | 16–24% |
| `chronic_non_payment` | 10.8% | 7–14% |
| `channel_failure` | 7.7% | 5–11% |
| `disputed` | 4.0% | 2–6% |

Every diagnosis is now demoable and measurable. `channel_failure` matters
disproportionately — it is the only diagnosis whose correct response is
*mechanical* (switch rail) rather than *persuasive* (firmer email). At 1.4% you
cannot find one on camera; at 7.7% a 500-invoice batch has ~40 of them.

**Edit 2 — anchor the clock (F5).**

```python
ANCHOR = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)

def generate_portfolio(size: int, seed: int, now: datetime | None = None):
    now = now if now is not None else ANCHOR   # NOT datetime.now()
```

Seed alone now determines output. `POST /batches` passes `clock.now()`
explicitly only when the caller asks for a live-dated portfolio.

**Edit 3 — curated demo batch.** A fixed seed producing ~40 invoices with a
guaranteed instance of each of the six diagnoses, one high-value
approval-gated invoice, one `stop_contact` reply and one dispute reply.
Labelled `demo_curated` in the README. The 500-invoice random batch is what
gets measured; this one is what gets filmed.

**Done when**

- `generate_portfolio(50, 42)` twice → identical fingerprint.
- Diagnosis mix within the accept bands above, at n≥3,000, on ≥3 seeds.
- `corr(late_rate, broken_promises) > 0.4` still holds. *(Currently 0.548, and
  the generator is deliberately unchanged, so this stays passing — that is
  precisely why the F4 fix lives in the rules and not in the DGP.)*
- `P(dispute | healthcare) > P(dispute | saas)`.
- Curated batch contains ≥1 of each diagnosis code.

> **Two v2 gates were wrong and are hereby replaced.** v2 §6.1 required "every
> invoice has ≥1 reply candidate" — but 30.0% of invoices are generated with
> zero replies, which is *correct*, because most overdue invoices get no reply.
> v2 also said seven reply classes; the implementation ships eight (it added
> `acknowledgement`). The implementation is better than both gates.

---

### 6.2 — Declared decision environment · **BUILT (F2, F3 fixed and verified)**

The three environments (`E_train`, `E_shift`, `E_adversarial`) exist, are
documented, and are the single best thing in the repo. Both fixes below are
built, tested, and empirically verified against a real generated portfolio —
not just designed.

**F2 — self-cure.** Originally planned as decomposing every cell of
`_BASE_RECOVERY_PROB` into "self-cure plus lift" (36 cells, retuned by
hand). Built instead as an **independent estimate**, deliberately not
derived from the action table by subtraction — retuning 36 cells added
mechanical risk this build's compressed schedule had no room for, for no
gain in what the holdout arm actually needs: a plausible, non-zero,
sensibly-varying no-action baseline, not a mathematically exact
decomposition. `p_self_cure()` declines with `days_overdue`, falls with a
worse `prior_late_payment_rate`, and varies by segment (bigger, more
process-driven accounts self-cure *less* — release is slower and less
discretionary, not less likely).

```python
def p_self_cure(facts: InvoiceFacts, segment: str, env: EnvironmentSpec) -> float:
    base = env.self_cure_base.get(segment, 0.15)
    decay = math.exp(-facts.days_overdue / env.self_cure_halflife_days)
    reliability = 1.0 - 0.6 * facts.prior_late_payment_rate
    return float(np.clip(base * decay * reliability, 0.01, 0.60))

# self_cure_base = {smb: 0.30, mid_market: 0.23, enterprise: 0.15}
# self_cure_halflife_days = 32.0
```

**Verified, not assumed:** mean self-cure across a 3,000-invoice portfolio
(seed 42) is **11.3%**, inside the declared 8–25% plausible band, and stable
within 0.2pp across three independent seeds and all three environments. As
a sanity property (not a hard guarantee — the code comment says so
explicitly), self-cure sits below the best available action's probability
for 97.8% of a sampled portfolio.

**F3 — the time axis.** `sample_outcome` no longer returns a bare `bool`.
Every recovery samples *when*, via `Outcome(recovered, days_to_cash)`,
`days_to_cash` sampled `Gamma(shape=2, scale=mean/2)` per action, clipped
to `[1, 180]` days, `None` when not recovered. A parallel
`sample_no_action_outcome()` gives the holdout arm its own outcome path —
self-cure only, no `ActionKey` involved — reusing `offer_payment_plan`'s
delay shape (the slowest real action) for its own timing rather than
inventing a second, unjustified distribution.

| Action | mean days to cash |
|---|---:|
| `send_upi_payment_link` | 2 |
| `resend_payment_link` | 3 |
| `send_reminder` | 5 |
| `schedule_call` | 8 |
| `escalate_to_am` | 12 |
| `offer_payment_plan` | 60 |

Full formulas and the verification numbers are published in
`docs/environment.md`, kept in sync with the code as a matter of practice,
not left to drift.

**Oracle hygiene — preserved, and already enforced.** The model sees invoice
features + diagnosis code + candidate action, and nothing else.
`app/domain/features.py` makes this structural rather than aspirational: the
`to_feature_vector()` signature physically cannot accept an environment
parameter, and `ALLOWED_FEATURE_KEYS` is asserted equal to the model's field
set. Keep the test.

**Done when**

- `docs/environment.md` republished with the self-cure curve and the delay
  distribution.
- Holdout arm returns a **plausible non-zero** recovery rate in all three
  environments (sanity band: 8–25%).
- Action ordering within each diagnosis is unchanged from the current table.
- One command regenerates every dataset byte-identically.
- Feature-allowlist test passes.

---

### 6.3 — Diagnosis · **BUILT + FIX (F4, F5)**

The cascade machinery is correct — ordered, mutually exclusive, first match
wins, one code per input. The *thresholds and ordering* need the F4 correction.

**Corrected cascade.** Changes from the current implementation in **bold**.

| Order | Code | Condition | Conf |
|---|---|---|---:|
| R01 | `disputed` | `dispute_flag` OR an inbound reply **extracted at runtime** as `dispute` | 1.00 |
| R02 | `chronic_non_payment` | **`days_overdue > 35`** AND `prior_broken_promises >= 2` | 0.90 |
| **R03** | **`channel_failure`** | **(moved up)** payment link sent AND never opened AND `contact_count_30d >= 2` | 0.70 |
| **R04** | **`cash_flow_risk`** | **(moved down)** `prior_late_rate >= 0.4` OR **`prior_broken_promises >= 2`** | 0.75 |
| R05 | `process_delay` | **`days_overdue <= 21`** AND **`prior_late_rate < 0.3`** AND **`prior_broken_promises <= 1`** | 0.65 |
| R06 | `standard_overdue` | fallback | 0.40 |

The ordering is a deliberate business call and each step is defensible:

- **Disputed dominates everything.** A disputed invoice must never enter dunning
  regardless of how bad the payment history looks.
- **Chronic outranks channel and cash-flow** because it changes the *action
  set* — from "help them pay" to "escalate or write off" — not just the wording.
  The `> 35` day threshold (down from 60) reflects that two broken promises plus
  five weeks overdue is already chronic behaviour; waiting to day 61 to say so
  costs a month of pointless reminders.
- **Channel failure outranks cash-flow** (the F4 fix). You learn nothing about a
  customer's finances from someone who never opened the invoice.
- **Cash-flow requires two broken promises or a genuinely high late rate.** One
  broken promise is noise.
- **Process delay tolerates one historical slip.** The old `bp == 0 AND
  late < 0.2 AND days <= 14` was so narrow that a reliable customer with a
  single old slip fell through to `standard_overdue`, which carries no useful
  action signal.

**Test-expectation bug (F5).** `tests/unit/test_diagnosis.py` case 7 passes
`prior_late_payment_rate=0.39` and expects `process_delay`; the old R05 required
`< 0.2`, so `standard_overdue` was correct and the code returned it. Under the
new R05 (`< 0.3`) this case is `standard_overdue` too. Either way: **fix the
expectation, not the cascade.**

**Done when**

- Table-driven test: one fixture per boundary condition on every threshold above.
- Property test: every input produces exactly one code (already passing — keep).
- A disputed + chronic + high-late-rate invoice returns `disputed`.
- A link-never-opened invoice with a bad payment history returns
  `channel_failure`, not `cash_flow_risk` (this is the F4 regression test).
- Mix within the accept bands in §6.1 at n≥3,000, on at least 3 seeds.

---

### 6.4 — Ranking: risk-adjusted EV + escalation ladder · **NEW (D3)**

`EV = p × amount` is wrong four ways: it ignores that a payment plan does not
collect in full today, prices an email and a human escalation identically at
₹0, never penalises the eleventh contact, and — because it is a myopic argmax —
re-picks the same top action every tick forever.

**Contract**

```python
def expected_value_paise(
    p: float,                   # P(recover | action) from prior_v1
    collectible_paise: int,     # what this action can actually collect
    days_to_cash: float,        # belief, from config/actions.yaml
    action_cost_paise: int,
    fatigue_penalty: float,     # 0..1, from contact density
    annual_discount_rate: float = 0.12,
) -> int:
    tvm = 1.0 / (1.0 + annual_discount_rate) ** (days_to_cash / 365.0)
    return int(p * collectible_paise * tvm * (1.0 - fatigue_penalty)
               - action_cost_paise)
```

**`config/actions.yaml`**

| Action | collectible | days_to_cash | cost | cooldown |
|---|---|---:|---:|---:|
| `send_reminder` | full | 5 | ₹2 | 5d |
| `resend_payment_link` | full | 3 | ₹2 | 4d |
| `send_upi_payment_link` | full | 2 | ₹2 | 4d |
| `offer_payment_plan` | full × (1 − concession) | 60 | ₹5 | 14d |
| `escalate_to_am` | full | 12 | ₹1,200 | 21d |

Two consequences fall straight out of the formula, and **both are worth
narrating on camera because they are counter-intuitive but obviously right**:

- **Escalation is correctly expensive.** At ₹1,200 of human time it can never
  win on a ₹15,000 invoice — which is exactly the rule an experienced AR team
  applies by instinct and that fixed-cadence software ignores entirely.
- **Payment plans stop being over-picked.** Discounting 60 days plus the
  concession haircut prices a plan honestly against a link resend.

**Fatigue penalty**

```python
fatigue_penalty = min(0.6, 0.15 * contact_count_30d)
```

Caps at 0.6 so fatigue suppresses but never zeroes an action — the hard stop is
policy's job, not the scorer's. Keeping soft economics and hard constraints in
separate layers is what keeps the system explainable.

**The escalation ladder** — the sequential correction:

```yaml
ladder: [send_reminder, resend_payment_link, send_upi_payment_link,
         offer_payment_plan, escalate_to_am]
rules:
  - an action may not repeat within its cooldown_days
  - the agent may not move more than one rung per cycle
  - the agent may not move down the ladder
  - max 2 executions of the same action per invoice, ever
```

This is a deliberate engineering choice over the theoretically correct answer
(a contextual bandit or finite-horizon MDP). The ladder captures most of the
sequential value, is explainable to a finance team, and is auditable. **Say the
trade-off out loud** — naming the sophisticated alternative and justifying the
simpler pick reads as judgement; silence reads as ignorance. This is ADR-001.

**Excluded from ranking:** `request_human_approval`, `stop`, `route_to_dispute`
are policy *outcomes*, not revenue tactics, and must never compete on EV.

**`prior_v1`** (`app/ml/priors.py`) — the deterministic stand-in for a trained
model. A published table over (diagnosis, action), stamped
`model_version="prior_v1"` on every decision. Derived from the *ranking* of the
environment table, deliberately **not** its exact values: priors that exactly
equal the environment would be an oracle. Perturb each cell by a fixed,
documented ±15% and note in the README that the agent is working from
approximate beliefs, not ground truth. That gap is what makes the E_shift and
E_adversarial results meaningful.

**Done when**

- Unit test per formula term in isolation.
- `escalate_to_am` never wins on an invoice below ₹50,000.
- No action repeats inside its cooldown across a 90-day simulated run.
- Ladder monotonicity property test (hypothesis).
- `prior_v1` is not equal to the environment table (asserted).

---

### 6.5 — Policy engine · **NEW (D3) — this is the product**

Policy is the differentiator, so it lives in a versioned, human-readable file
that can be shown on screen, diffed, and explained — not in Python.

**Contract**

```python
class PolicyResult(BaseModel):
    outcome: Literal["allow", "require_approval", "block", "substitute"]
    substituted_action: ActionKey | None
    reasons: list[PolicyReason]     # rule_id, rule_text, matched_facts
    policy_version: str
```

**`policies/default.yaml`** — version `1.3.0`

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
    reason: "Outside 09:00-19:00 IST business hours."

  - id: P05_open_promise
    when: "invoice.has_open_promise and clock.today <= promise.promised_date"
    then: block
    reason: "Customer has an open promise-to-pay; suppress until due."

  - id: P06_high_value_approval
    when: "invoice.amount_paise > 50000000"          # Rs 5,00,000
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

  - id: P10_low_confidence_llm
    when: "diagnosis.produced_by == 'llm_fallback' and diagnosis.confidence < 0.7"
    then: require_approval
    reason: "Low-confidence LLM diagnosis requires human confirmation."
```

**Rules**

- **Evaluate all rules; collect all matches. Never short-circuit.** "Blocked
  for three reasons" is a far better audit record than "blocked".
- Severity ordering on conflict:
  `block > substitute > require_approval > allow`.
- Conditions are evaluated by **`simpleeval` over a whitelisted fact namespace
  with no builtins** — never `eval()`. Never execute arbitrary strings from a
  config file, even your own. CI greps for `eval(`/`exec(`.
- `policy_version` is stamped on every `decisions` row. Changing policy does not
  rewrite history.

**P03, P05 and P09 are the literal implementation of "stopping rules" and
"bounded"** in the track brief. P09 in particular is a hard ceiling on how much
the agent can do before a human looks at it — give it a visible dial on the
dashboard and point at it in the video.

**Done when**

- Every rule has a passing positive **and** negative test.
- Conflict test: dispute + high-value + cap reached → `block`, exactly 3 reasons.
- `grep -rE "\beval\(|\bexec\(" app/` returns nothing (CI).
- A `stop_contact` reply produces permanent suppression that survives a restart.

---

### 6.6 — Audit ledger and explanation · **BUILT + EXTEND (D4)**

The hash chain, `verify_chain`, and `GET /invoices/{id}/audit/verify` all exist
and work. Extend the event vocabulary to cover the full loop:

`risk_detected`, `diagnosis_produced`, `actions_ranked`, `policy_evaluated`,
`approval_requested`, `approval_granted`, `approval_denied`, `action_scheduled`,
`action_executed`, `action_failed`, `webhook_received`, `reply_received`,
`reply_extracted`, `promise_created`, `promise_resolved`, `outcome_observed`,
`escalated`, `stopped`, `degraded_mode_entered`.

**The explanation object** — every decision must render as one paragraph a
finance person reads without training:

```json
{
  "invoice": "INV-2291", "amount": "₹2,50,000", "days_overdue": 45,
  "diagnosis": {
    "code": "cash_flow_risk",
    "because": ["late payment rate 0.48 (threshold 0.40)",
                "1 broken promise (below the chronic threshold of 2)"],
    "rule": "R04.cash_flow_risk"
  },
  "considered": [
    {"action": "offer_payment_plan",  "p": 0.42, "ev": "₹94,300",   "rank": 1},
    {"action": "resend_payment_link", "p": 0.38, "ev": "₹91,200",   "rank": 2},
    {"action": "escalate_to_am",      "p": 0.51, "ev": "₹1,26,300", "rank": 0,
     "note": "highest EV but gated"}
  ],
  "policy": {
    "outcome": "require_approval", "version": "1.3.0",
    "because": ["P06: amount over review threshold for payment plans"]
  },
  "final": "Awaiting human approval — requested 2026-09-02T14:02:11Z",
  "chain_verified": true
}
```

**The highest-EV action is shown even when policy took it away.** Showing the
option that was removed is far more persuasive than showing only what was
allowed — it makes governance *visible*, which is precisely what the bar's
"compliant escalation" is asking to see.

**Done when**

- Chain verification passes over a 500-invoice batch.
- Mutating one payload row makes `/verify` return `intact: false`.
- Every decision renders an explanation object.

---

### 6.7 — Measurement · **NEW (D5) — the headline number**

**Three arms**, assigned deterministically by
`sha256(invoice_id + salt) % 100` — never RNG, so arms are reproducible and
immune to the accusation that they were re-rolled until the numbers looked
good. Already implemented and measured at 68.9 / 20.3 / 10.8.

| Arm | Share | Behaviour |
|---|---:|---|
| `agent` | 70% | Full loop |
| `baseline` | 20% | Fixed cadence: D+1 reminder, D+7 reminder, D+15 link, D+30 escalate |
| `holdout` | 10% | **No contact at all** — measures natural self-cure |

```text
incremental_recovery     = (rate_agent − rate_holdout) × portfolio_value
uplift_vs_baseline       = rate_agent − rate_baseline
```

**Report with error bars.** Across the ten evaluation seeds: mean ± 95% CI by
bootstrap, 1,000 resamples. A number without a CI is an anecdote.

**Also report — this is the part most submissions omit, and it is cheap:**

- **Cost of recovery** — `total_action_cost / incremental_recovered`. An agent
  that recovers 3% more by escalating everything to humans is not a good agent.
- **Contacts per recovery** — the customer-experience cost.
- **Suppression precision** — of the invoices where the agent stopped, how many
  were genuinely unrecoverable? Knowing when to stop is a first-class result,
  and it is the direct evidence for "stopping rules".
- **Uplift under `E_shift` and `E_adversarial`** — the robustness curve. Most
  submissions show one number on one environment. A degradation curve across
  three is what wins a track judged on rigour.

`reports/evaluation.md` is regenerated by `make evaluate` and **committed**, so
a judge reads the numbers without running anything.

**Done when**

- `make evaluate` regenerates the full report from seeds.
- Arm assignment stable across re-runs (hash test).
- Every reported metric carries a CI.
- Holdout rate is non-zero and plausible (this is the F2 fix paying off).

---

### 6.8 — Reply intelligence + graceful degradation · **NEW (D6)**

This is the layer that turns a scoring engine into an agent, and per the
buildathon's stated evaluation focus it is **the part of the demo to spend the
most time on**.

**Why an LLM here and nowhere near the money.** Free-text B2B replies are
genuinely unstructured — regex on "we will pay" fails on *"cheque is being
couriered Tuesday"*, *"released in the next payment run"*, *"post GST
correction"*. But the LLM's output is **evidence, not a decision**: it produces
structured facts that feed the deterministic layers, which retain authority.

**Contract**

```python
from pydantic import BaseModel
from datetime import date
from typing import Literal

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
    evidence_quote: str                  # verbatim span, <=200 chars
```

**Implementation** — Google GenAI Python SDK (`google-genai`, the current GA
library — not the older, now-superseded `google-generativeai`), schema-
enforced structured output via the Interactions API:

```python
from google import genai

client = genai.Client()          # reads GEMINI_API_KEY from the environment

interaction = client.interactions.create(
    model=EXTRACTION_MODEL,                 # confirmed free-tier model — see below
    system_instruction=EXTRACTION_SYSTEM_PROMPT,
    input=redacted_text,
    response_format={
        "type": "text",
        "mime_type": "application/json",
        "schema": ReplyExtraction.model_json_schema(),
    },
)
extraction = ReplyExtraction.model_validate_json(interaction.output_text)
```

`model_validate_json()` validates the response against the Pydantic schema —
no free-text JSON parsing anywhere. (An async client variant exists in the
same SDK; confirm its exact namespace against the docs when this is actually
built on D6, rather than assuming it mirrors the sync call.)

**Model routing, and why the exact model string isn't pinned here.** Google's
free tier is genuinely free (no card, not a trial that can lapse — see §1.3's
switch note), but which specific model is free-tier-eligible shifts with
Google's release cadence faster than this document can track — the model
lineup itself moved twice between when this project's cost research started
and when this section was last verified. **On D2, before writing anything
else, open [aistudio.google.com/rate-limit](https://aistudio.google.com/rate-limit)
against the real account and confirm two things in writing:** which model is
the free, cheap default (`EXTRACTION_MODEL` above), and whether a second,
more capable free-tier model exists to escalate to below `confidence < 0.6`
— if only one free model exists, the escalation tier is dropped and every
call uses the one model; that's a minor, honestly-narrated simplification,
not a broken design.

> **Cost: $0**, not "well under $1" — this is the actual point of the switch.
> Free-tier requests are genuinely free, not discounted; the only real
> constraint is the rate limit (requests per minute / per day), not a dollar
> figure. Log request counts per batch anyway and put the real number in the
> README — showing you tracked it, even at zero cost, is still the cost-
> discipline signal the buildathon rewards. Gemini's caching feature isn't
> used here: it targets prompts in the tens of thousands of tokens, and this
> system prompt is a few hundred — resending it plainly is simpler and, on
> the free tier, free either way.

**Rules**

- **PII redaction before the call.** Emails, phones, GSTIN, bank digits, and
  names replaced with typed placeholders; restored only for display. Covered by
  unit tests. This matters more than usual on a free API tier — Google's terms
  for the free tier permit using submitted content to improve their products
  (not true on a paid tier), so redacting before the call is what makes it
  fine to send this data there at all, not an optional hardening step. Say
  this in the honesty contract (§5): the data is synthetic anyway, but the
  redaction discipline is real and would hold on real customer text too.
- **`evidence_quote` must be a verbatim substring of the input**, verified
  programmatically, not trusted. If it is not a substring, the extraction is
  rejected. A cheap, hard anti-hallucination guarantee — narrate this.
- `confidence < 0.6` → human queue, do not act.
- `intent == "dispute"` → set `dispute_flag`, which forces R01 and halts dunning
  on the next tick. **A disputing customer stops receiving automated contact
  within one cycle.** This is the clearest demonstration of "bounded" in the
  whole build.
- `intent == "stop_contact"` → permanent suppression, policy-enforced (P02).
- `intent == "promise_to_pay"` → create the promise, schedule a check for
  `promised_date + 1`, **suppress all outreach until then** (P05). Nothing
  destroys a receivables relationship faster than chasing a customer who has
  already committed to a date.

**Graceful degradation — the chaos switch.** The buildathon states that
submissions must handle at least one system failure gracefully. Make it a
deliberate, demoable feature rather than a hope:

```text
POST /demo/chaos?llm=down&razorpay=down
```

With the switch on:

- Every LLM call raises. The extraction layer catches, falls back to a
  keyword-based classifier with `confidence = 0.5`, which lands under the 0.6
  threshold and therefore routes to the **human queue** rather than acting.
  The loop keeps running. Diagnosis falls back to rules-only.
- Every Razorpay call raises. The tool layer catches, transitions the action to
  `failed`, schedules a retry with backoff, and — because the idempotency key
  already exists — the retry cannot double-send when the API recovers.
- Every decision taken in this state is stamped `degraded=true`, a
  `degraded_mode_entered` audit event is written, and the dashboard shows a
  visible **DEGRADED** banner.

**Nothing crashes, nothing double-sends, no money moves without a human.** That
is a 30-second segment of the video and a direct hit on a published criterion.

**Done when**

- 60 labelled fixtures: intent accuracy ≥0.85, date exact-match ≥0.80.
  **Verified live against `gemini-3.5-flash-lite`, 31 Aug 2026: 64 fixtures,
  90.6% intent accuracy, 100% date exact-match, 0 PII leaks, 0 rejected
  extractions.** First run scored 81.2%/0% — the date failures turned out
  to be a fixture bug (dates given as "15 Sep" with no year; the model
  correctly extracted day/month but had no way to infer 2026 without
  context), and "unrelated" was 0/8 from an underspecified category
  boundary against "acknowledgement". Both fixed (today's date now passed
  into the prompt; category definitions tightened), not worked around.
- Every accepted extraction's `evidence_quote` verifies as a substring.
- Redaction test: no raw email / phone / GSTIN in any outbound payload.
- Dispute reply halts dunning within one tick.
- **Chaos test:** with both services down, a 30-day run completes, produces zero
  executed external actions, zero exceptions, and ≥1 `degraded_mode_entered`
  audit event.

---

### 6.9 — Execution · **NEW (D4) — spike on D2**

Split deliberately into two phases, not one. The spike de-risks the external
dependency; the full build happens right after it, in the same day as the
state machine it extends, rather than three days later as a separately
scheduled concern.

**Narrow registry** — five tools, not nine.

| Tool | Surface | Real in demo |
|---|---|---|
| `send_reminder` | Jinja template → console sink | Console |
| `resend_payment_link` | `payment_links.create` | **Yes, test mode** |
| `send_upi_payment_link` | `payment_links.create` (UPI) | **Yes, test mode** |
| `escalate_to_am` / `route_to_dispute` / `request_human_approval` / `stop` | Internal records + queue | Yes |
| `offer_payment_plan` | Internal record, whitelisted plans only | Yes |

Tool names deliberately mirror the [official Razorpay MCP server](https://github.com/razorpay/razorpay-mcp-server)
(`create_payment_link`, `fetch_payment`, …) so the agent can be pointed at the
real MCP server with a config flag instead of a rewrite — and so it reads as
fluency with Razorpay's own agent tooling on an agentic track.

**Idempotency**

```python
idempotency_key = sha256(f"{invoice_id}:{action_key}:{attempt_no}:{policy_version}")
```

`UNIQUE` constraint on the column. On collision, return the stored `ToolResult`
— never re-execute. `policy_version` is in the key so a deliberate
post-policy-change retry is a *different* action, not a silently swallowed
duplicate.

**State machine** — illegal transitions raise; test every edge.

```text
pending ─▶ approved ─▶ executing ─▶ executed ─▶ (outcome)
   │           │            │
   └▶ cancelled             └▶ failed ─▶ retry w/ backoff, max 3
```

**Webhook security — non-negotiable**

- Verify `X-Razorpay-Signature` = `HMAC_SHA256(body, webhook_secret)` using
  `hmac.compare_digest`. Reject unverified with 400 **before parsing JSON**.
- Store `event.id`; drop duplicates (Razorpay retries).
- Respond 200 fast.

Handled events: `payment_link.paid`, `payment.captured`, `payment.failed`.

> **The spike (Day 2, first hour): account, keys, one payment link, one
> verified webhook.** This is the only hard external dependency in the whole
> build, account activation isn't instant, and discovering a credentials
> problem on Day 4 costs a full day instead of an hour. Test-mode signup
> needs no KYC and no registered business — an individual account activates
> immediately. Webhooks need a publicly reachable URL: `cloudflared tunnel
> --url http://localhost:8010` (or ngrok), registered in the test dashboard's
> webhook settings, pointed at `/webhooks/razorpay`. Prove the whole round
> trip once — create a link via `curl`, pay it in the test dashboard, watch
> the webhook arrive — and stop there. The typed tool registry, idempotency
> keys, and state machine below are Day 4's work, built against a pattern
> you've already watched succeed once, not one you're discovering live.

**Done when**

- Same idempotency key twice → one API call, identical stored result.
- Tampered body → 400, nothing written.
- Same `event.id` twice → one outcome row.
- **A real test-mode payment link created, paid in the Razorpay dashboard, and
  the webhook closing the loop end-to-end — screen-recorded the day it works.**
  This is the money shot of the pitch video; do not rely on it live.

---

### 6.10 — Dashboard · **NEW (D7)**

One server-rendered page: **Recovery Command Center**. Optimise for the
five-minute video — a judge should understand the system from one screen.

```text
┌────────────────────────────────────────────────────────────────────┐
│ Revenue at Risk ₹1.84 Cr    │ Incremental Recovered ₹22.4 L  [SIM] │
│ Portfolio 500 invoices      │ vs holdout +8.2pp (CI 6.1-10.3)      │
│ Actions today 43/120 ▓▓▓░░  │ Cost of recovery ₹1.02 per ₹100      │
├──────────────────┬─────────────────────────────────────────────────┤
│ QUEUE            │ DECISION DETAIL                                 │
│ ● Approvals (4)  │ INV-2291 · Acme Mfg · ₹2,50,000 · 45d overdue   │
│ ● Disputes (2)   │ ┌─────────────────────────────────────────────┐ │
│ ● Promises (11)  │ │ DIAGNOSIS cash_flow_risk        conf 0.75   │ │
│ ● Suppressed (7) │ │ late rate 0.48 · 1 broken promise · R04      │ │
│                  │ ├─────────────────────────────────────────────┤ │
│ FILTERS          │ │ RANKED ACTIONS                               │ │
│ [diagnosis ▾]    │ │ 1 payment_plan   0.42 → ₹94,300             │ │
│ [arm ▾]          │ │ 2 resend_link    0.38 → ₹91,200             │ │
│                  │ │ ⊘ escalate_am    0.51 → ₹1,26,300   GATED   │ │
│                  │ ├─────────────────────────────────────────────┤ │
│                  │ │ POLICY v1.3.0   REQUIRE_APPROVAL             │ │
│                  │ │ P06 amount over ₹5,00,000 threshold          │ │
│                  │ │       [ Approve ]   [ Deny ]                 │ │
│                  │ ├─────────────────────────────────────────────┤ │
│                  │ │ AUDIT TIMELINE       🔒 chain verified       │ │
│                  │ │ ●─●─●─●─● 5 events                           │ │
│                  │ └─────────────────────────────────────────────┘ │
├──────────────────┴─────────────────────────────────────────────────┤
│ [⏩ Advance 7 days]  [Recovery curve: agent / baseline / holdout]   │
└────────────────────────────────────────────────────────────────────┘
```

**Four things that must be on screen** — they map 1:1 onto the published bar:

1. The **gated** action shown struck through beside the chosen one → *compliant escalation*
2. The **action budget meter** → *stopping rules / bounded*
3. The **three-arm recovery curve** → *measured money recovered across a batch*
4. The **chain-verified audit timeline** → *audit trail*

Plus the **DEGRADED** banner when the chaos switch is on.

`Advance 7 days` is the hero control: curves move, promises resolve, approvals
appear. This is what makes a 45-day recovery journey fit in a 5-minute video.

**Build:** one Jinja template served by FastAPI, vanilla `fetch()` for the
advance button, hand-written inline SVG for the curve. No node, no build step,
no second process.

**Aesthetic:** dark slate base; emerald for money-in; amber for risk; red
reserved exclusively for blocked/disputed. Tabular numerals for all currency.
No gradients, no glass, no emoji. It should look like a finance tool, not a
startup landing page.

**Done when** — all four items visible without scrolling; advance visibly moves
the curves; approve/deny writes an audit event and unblocks the action.

---

## 7. API surface

```text
GET  /health
POST /batches?size=&seed=                 generate + persist portfolio
GET  /invoices?batch_id=
GET  /invoices/{id}
GET  /invoices/{id}/diagnosis
GET  /invoices/{id}/audit
GET  /invoices/{id}/audit/verify          hash-chain integrity
GET  /batches/{id}/summary

POST /invoices/{id}/evaluate              diagnose + rank + policy, no execution
POST /invoices/{id}/act                   execute the policy-approved action
GET  /invoices/{id}/explanation           §6.6 explanation object

GET  /approvals                           pending queue
POST /approvals/{id}/approve
POST /approvals/{id}/deny

POST /invoices/{id}/replies               ingest text → extract → facts
GET  /policy                              active YAML + version

POST /simulate/advance?days=              advance clock, run ticks, return diff
POST /simulate/run-batch?batch_id=&env=   full run under E_train|E_shift|E_adversarial
POST /demo/chaos?llm=&razorpay=           graceful-degradation switch

GET  /evaluation/{batch_id}               arms, uplift, CIs, cost-of-recovery
GET  /evaluation/{batch_id}/curve         recovery curve by arm over time

POST /webhooks/razorpay                   HMAC-verified, deduped
GET  /                                    the dashboard
```

---

## 8. Stack

| Concern | Choice | Rationale |
|---|---|---|
| Language | Python 3.12 | Existing stack |
| API | FastAPI + Pydantic v2 | Async, typed, free OpenAPI docs |
| ORM | SQLAlchemy 2.0 async | Typed `Mapped[]` |
| Schema | `Base.metadata.create_all()` | §1.3 — no migrations; demo seeds from scratch |
| DB | Postgres 16 (docker compose) | JSONB, real concurrency; already configured |
| Scheduling | Plain tick function, driven by `/simulate/advance` | §1.3 — reproducible, no concurrency bugs |
| Prediction | `prior_v1` published table | §1.3 — a trained model on a declared env is a lossy copy |
| LLM | `google-genai` SDK, `interactions.create()` + Pydantic `model_json_schema()` | Schema-enforced structured output; free tier, no card (§9 switch note) |
| Models | Whichever Gemini model shows free-tier-eligible in AI Studio at signup — confirmed D2, not pinned in this document | Google's free-tier model lineup moves faster than this plan can track; verify live, don't assume a name from here is still current |
| Payments | `razorpay` Python SDK, test mode | Real API calls; names mirror Razorpay MCP |
| Rule eval | `simpleeval` | Safe restricted evaluation — never `eval()` |
| Testing | pytest + pytest-asyncio + hypothesis | Property tests on ladder and policy |
| Frontend | Jinja + vanilla JS + inline SVG | §1.3 — one process, one URL, no build step |
| Container | docker compose (db + api) | One command for a judge |

**Deliberately not used** — this belongs in the README verbatim, because the
buildathon explicitly scores whether AI and infrastructure were applied
appropriately rather than forced:

- **Celery / Redis / RabbitMQ** — a Postgres table and an explicit tick is
  sufficient, cheaper to run, and trivially debuggable. A broker here would be
  resume-driven architecture.
- **Vector DB / RAG** — there is no corpus to retrieve over. Adding one would be
  decoration.
- **LangChain / agent frameworks** — the control flow is an 8-step state machine
  the code should state plainly. A framework would obscure the auditability that
  is this project's main claim.
- **Deep learning, and in fact any trained model** — see §1.3.
- **An LLM anywhere on the money path** — it reads replies; it never chooses an
  action, sets a probability, authors financial terms, or computes a number that
  reaches the dashboard. Every one of those has a deterministic owner.

---

## 9. The six remaining days

**D1 is done** (Fri 28 Aug — see §1.1 for F1–F7, all fixed and verified live
against a running stack, not just in tests). Six calendar days remain for six
milestones — the count matches exactly because two things moved: the
Razorpay execution build merged into D4 (next to the state machine it
extends), and dashboard + ship merged into D7 (documentation is written
incrementally through the week, not saved for the end — see the note after
the table).

**Hand over the Razorpay test keys at the start of Day 2** — not before
(D1 never touched execution) and not later (the spike is the first hour of
D2, and everything on D4 depends on having proven it once already). You
don't need to paste the actual key values into chat: create the test-mode
account, generate the key pair, and paste them directly into
`backend/.env` yourself (the variable names already match `.env.example` —
`RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`). Every
line of Razorpay code reads from `get_settings().razorpay_key_id` etc., so
the integration is written once against the env var, never against a
literal key — just say the word once `.env` is populated and we run the
spike together.

| Day | Date | Milestone | Gate — do not proceed until this passes |
|---|---|---|---|
| **D2** | Sat 29 Aug | **De-risk + Environment v2.** *First hour:* Razorpay test-mode signup (no KYC needed for test mode), one `curl` payment link, one `cloudflared` tunnel, one verified webhook round-trip — stop there, the full build is D4. *Then:* Gemini API signup at [aistudio.google.com](https://aistudio.google.com) (free, no card), confirm the current free-tier model at [aistudio.google.com/rate-limit](https://aistudio.google.com/rate-limit), write 10 real reply fixtures by hand and run them through it via `client.interactions.create()` to get a real intent-accuracy number before committing to it as D6's primary path. *Then:* the environment fix — self-cure hazard, actions as lift over self-cure (F2); `Outcome(recovered, days_to_cash)` (F3); republish `docs/environment.md`; `prior_v1` table; regenerate all datasets. | Webhook round-trip recorded once. Free-tier model confirmed and written down. Spot-check accuracy known and written down (even if it's bad news). Holdout recovers a plausible non-zero rate (8–25%) under all three environments. Datasets regenerate byte-identically. |
| **D3** | Sun 30 Aug | **Ranking + policy** — EV formula, ladder, cooldowns, `config/actions.yaml`; `policies/default.yaml` through the simpleeval sandbox; all-reasons collection and severity ordering. | Every rule has ± tests. Conflict test → `block` with 3 reasons. `escalate_to_am` never wins under ₹50k. No `eval(` in CI grep. |
| **D4** | Mon 31 Aug | **The loop + full execution.** 8-step cycle, `scheduled_actions`, tick function, action state machine, idempotency, full audit vocabulary, `POST /simulate/advance` — **plus** the typed tool registry, real Razorpay payment-link/UPI calls, and the HMAC-verified webhook receiver, built against the pattern proven on D2. Internal tools (escalate/dispute/approval/stop) and external tools (Razorpay) are the same state machine; building them on the same day is the point. | 90-day simulated run: no duplicate actions, no orphaned events, promises resolve both ways, chain intact. Same idempotency key twice → one API call. Tampered webhook body → 400. **A real test-mode payment link created, paid, and closed by webhook — screen-recorded today**, not left for later. |
| **D5** | Tue 1 Sep | **Measurement** — three arms end to end, fixed-cadence baseline, bootstrap CIs, `reports/evaluation.md` across three environments, cost-of-recovery, contacts-per-recovery, suppression precision. | **A real incremental-uplift number with a 95% CI against a non-zero holdout.** This is the most important gate remaining. If it isn't real by tonight, stop and go to §10 — every day after this assumes the number exists. |
| **D6** | Wed 2 Sep | **Reply intelligence + chaos** — redaction, the full `client.interactions.create()` pipeline (already proven on D2's spot-check, so this is wiring, not discovery), quote verification, confidence routing (D2's confirmed free-tier model default, a second free-tier model as escalation below 0.6 confidence if one exists), dispute → suppression, promise → schedule, request-count meter (cost is $0 on the free tier — see §6.8); the chaos switch and degraded mode. | 60 fixtures ≥0.85 intent accuracy (or the honest number from D2's spot-check, documented either way). Redaction test passes. Dispute halts dunning in one tick. Chaos test: 30-day run, both services down, zero exceptions, zero external actions. |
| **D7** | Thu 3 Sep | **Dashboard + ship.** Command Center on one screen — gated action, budget meter, three-arm curve, audit timeline, advance control, DEGRADED banner. Then: `docs/architecture.md`, README (honesty contract + measured LLM spend + "deliberately not used"), ADR-001/002/003, 5-minute video, cold-clone verification. **Submit.** | All four bar items visible without scrolling. Advance moves the curves. Cold clone on a second machine → `docker compose up` → working demo. Video under 5:00. Repo public. |

**Which vendor, and why it changed the night before D2.** This project ran on
`claude-haiku-4-5` / `claude-opus-5` through v4 of this plan. The Anthropic
Console free trial credit did not materialize after signup and 24 hours of
waiting (see ADR-004) — rather than lose D2 morning to account
troubleshooting or spend real money on a solo, no-slack build, the LLM seat
moved to **Google's Gemini API**, which is free on an ongoing basis (no
card, no trial that can lapse) rather than a one-time credit. The
architecture is unchanged: still exactly one LLM seat, still reply
extraction only, still evidence-not-decisions. Only the vendor and the two
lines of SDK code differ.

| Use | Model | Why |
|---|---|---|
| Reply extraction, the ~90% typical case | Whichever model AI Studio shows as free-tier default (confirmed D2) | A structured 8-way intent classification with a fixed Pydantic schema (§6.8) doesn't need a frontier model, and the free tier's rate limit — not a dollar cost — is the only real constraint |
| Reply extraction, `confidence < 0.6` | A second, more capable free-tier model, **if one exists** at signup | The harder ~10% — ambiguous phrasing, mixed intents. If AI Studio shows only one free model, this tier is dropped and every call uses the same model — a minor, honestly-narrated simplification |
| Everywhere else in the system | **No LLM** | Diagnosis, ranking, policy, and measurement are deterministic Python by design (§1.3) — there is no third model to pick, that absence is the point |

**D2's spot-check uses the confirmed free-tier model directly** against the
10 hand-written fixtures — same model, same schema, same
`client.interactions.create()` call D6 will make at volume. If the spot-
check accuracy is bad, the fix is a prompt change or a fallback-first
design, decided with 5 days of runway left — not discovered on D6 with one
day left.

**Documentation is written the day its decision is made, not saved for D7.**
Each ADR (§12) is one paragraph — write it the day you make that call: ADR-001
when the ladder is built (D3), ADR-002 when `prior_v1` replaces a trained
model (D2, since it's already decided — just write it down), ADR-003 when
the stack section (§8) is finalized (D4, once execution is real). By D7 the
only writing left is `docs/architecture.md` and the honesty-contract section
of the README, both of which are largely already drafted in this document
(§2, §5) and need transcription, not composition.

**From here on, the cut ladder (§10) is the default operating mode, not an
emergency fallback.** Solo, at this pace, there is no slack day to absorb a
slipped gate — the moment a day's gate doesn't pass by that day's end, cut
per §10 immediately rather than planning to catch up tomorrow, because
tomorrow already has its own full day of work.

---

## 10. The cut ladder

Cut **before** you run out of time, not after. Each row names the trigger.

| If you are behind at the end of… | Cut this |
|---|---|
| **D2** | `E_shift` and `E_adversarial` *reporting* — keep the code (it already exists), report `E_train` only, and add the other two back on D7 if the report regenerates cleanly. If the LLM spot-check accuracy is bad, do not try to fix the prompt today — note the real number and move on; D6 decides what to do with it. |
| **D3** | `P04` quiet hours and `P07` concession whitelist. Keep P01, P02, P03, P05, P06, P08, P09 — those are the ones that map to the bar. |
| **D4** | First cut retry-with-backoff on failed actions (fail, log, move on). If still behind, cut `send_upi_payment_link` and ship only `resend_payment_link` as the one real Razorpay tool — one working payment-link path beats two half-working ones. **Do not cut the webhook loop itself or its recording** — it's the money shot of the video and there's no later day to recover it. |
| **D5** | Dashboard degrades to three static tables plus one SVG curve. No filters, no queue panel, no approve/deny buttons — approve via `curl` on camera instead. |
| **D6** | Live reply-paste box. Run extraction offline over the pre-generated corpus and show stored results. **Do not cut the extraction itself** — it is the most-scored part of the demo. |
| **D7** | Two of the three ADRs (keep ADR-002, the trained-model decision — it's the one a judge actually probes). Dashboard styling polish. **Do not cut the video's length or the cold-clone verification** — an unverified "works on my machine" submission is worse than a smaller one that's proven to run. |

**Never cut:** the holdout arm, the audit hash chain, HMAC verification, the
chaos demo, the honesty contract. Those five are the published bar.

---

## 11. Video beat sheet — 5:00

Reweighted from v2: the LLM/agent segment doubles, because the buildathon
states that if a project touches agents or LLM orchestration, that should be
where the demo spends most of its time.

| Time | Beat | On screen |
|---|---|---|
| 0:00–0:25 | **The problem.** Fixed dunning ladders send the same four emails to a reliable ₹40k SaaS account and a thrice-defaulted ₹8L manufacturer. | Baseline cadence diagram |
| 0:25–0:50 | **The invariant.** "Model ranks. Policy decides. Tools execute. Everything is logged." | Architecture slide |
| 0:50–1:45 | **One invoice, end to end.** ₹2.5L, 45 days. Diagnosis with evidence → ranked actions → *escalation is highest-EV and policy gates it* → approval queue. | Command Center detail pane |
| 1:45–3:00 | **The agent listens.** ← *the longest beat, deliberately.* Paste "we dispute this, wrong GST" → redaction → schema-constrained extraction → verbatim quote verified → dispute flag → dunning halts within one cycle. Then a promise-to-pay: outreach suppressed until the promised date. | Reply panel + audit timeline + extraction JSON |
| 3:00–3:25 | **Real execution.** UPI payment link created in Razorpay test mode → paid → HMAC-verified webhook → outcome closes the loop. | Split screen: app + Razorpay dashboard |
| 3:25–3:55 | **It survives failure.** Flip the chaos switch. LLM down, Razorpay down. Loop keeps running, degrades to rules and templates, routes to the human queue, sends nothing, double-sends nothing. | DEGRADED banner + audit trail |
| 3:55–4:35 | **The measurement.** Advance 30 days. Three-arm curve separates. Incremental uplift vs a *no-contact holdout*, with a CI. Cost of recovery. Budget meter. Tamper a row → `intact: false`. | Recovery curve + scoreboard + live verify |
| 4:35–5:00 | **The honest close.** "Decisions are real, cash is simulated under a published environment. We didn't train a model — in a declared environment a trained model is a lossy copy of the declaration, and we'd rather you could check our arithmetic. Here is uplift under three environments, including one where our own beliefs are deliberately wrong: the policy layer contains the damage." | Robustness table |

The last 25 seconds is the highest-leverage part of the video. Most submissions
end on their best number. Ending on **the limits of your own claim, plus
evidence you stress-tested it** is far more memorable to a technical panel — and
it inoculates you against the exact question they were about to ask.

---

## 12. Architecture decision records

Four, one paragraph each, **written the day the decision is made** (§9) —
not batched at the end. The buildathon states you must be ready to justify
every major decision; these are the four you will be asked about.

- **ADR-001 — Escalation ladder over contextual bandit.** *Write it D3, when
  the ladder is built.* Names the theoretically correct answer, explains why
  explainability and auditability beat optimality on a finance product,
  states what it costs.
- **ADR-002 — Published priors over a trained model.** *Write it D2 — the
  decision is already made, this is transcription, not composition.* The
  circular-evaluation argument from §1.3. This is the one a judge with an ML
  background will probe, and it is a strong answer when stated first.
- **ADR-003 — No broker, no framework, no vector DB.** *Write it D4, once
  execution is real and §8's stack is finalized.* Why a Postgres table and
  an explicit tick beat Celery here; why a state machine you can read beats an
  agent framework when auditability is the product.
- **ADR-004 — Gemini over Claude for the one LLM seat.** *Already decided —
  write it now, the night before D2.* Anthropic's Console free trial credit
  did not appear after signup and 24 hours' wait; on a solo, no-slack build,
  losing D2 morning to account troubleshooting (or spending real money to
  route around it) cost more than switching vendors once, cleanly, before
  any code was written against the first choice. The architecture didn't
  change — one LLM seat, reply extraction only, evidence not decisions
  (§6.8) — only the SDK and the model names did. Worth stating plainly if
  asked: this was a pragmatic constraint, not a technical judgment that
  Gemini is better suited to the task than Claude would have been.

---

## 13. Risks

| Risk | Mitigation |
|---|---|
| **Razorpay credentials/activation delay** | Account + keys + one `curl` link + one verified webhook in the first hour of D2. Highest-variance external dependency in the build, moved as early as it can go now that D1's foundation work is done. |
| **D5 slips and there is no uplift number** | D5 is the hinge gate. If it slips, invoke §10 immediately — do not build D6 on an unmeasured system. |
| **Circular-evaluation challenge** | Pre-empt it: publish the environment, state the narrow claim (§2), ship the robustness curve, and *raise it before the judge does* in the closing beat. |
| **LLM extraction flaky on camera** | Cache all demo replies; `confidence < 0.6` routing to a human is a **feature to narrate**, not a failure to hide. |
| **Gemini's free-tier model or its rate limit changes mid-week** | Confirmed once on D2 (ADR-004), not re-checked daily. If a model used in a screen recording stops being free before submission, the recording still stands as evidence — re-verify against AI Studio only if D7's cold-clone check surfaces an actual failure, not preemptively. |
| **D7 now carries dashboard + all of ship prep in one day** | Server-rendered, no build step (§1.3) — the dashboard itself is small. Docs and ADRs are written incrementally on D2–D4 (§9), so D7 starts with only `docs/architecture.md`, transcription of the README, video, and cold-clone verification — not composition from scratch. |
| **Solo, no slack — one slipped gate has nowhere to land** | The cut ladder (§10) is the default operating mode from D2 onward, not a fallback. Cut the moment a gate misses, same day, not "tomorrow." |
| **Scope creep** | The cut ladder (§10) is pre-decided with triggers. Adding scope to this document is the primary failure mode. |
| **"It's only synthetic data"** | The honesty contract (§5) is on a slide. Volunteering the limitation converts an attack into a credibility signal. |

---

## 14. The pitch, in one paragraph

> Fixed dunning ladders send the same four emails to every overdue invoice.
> This agent diagnoses *why* each invoice is stuck, scores every permitted
> action by time-discounted expected value net of the cost of acting, and then
> submits that recommendation to a deterministic policy engine that has final
> authority — it can block, gate, or substitute the action, and it does.
> Approved actions execute through Razorpay's API under idempotency keys and a
> daily action budget, and every step lands in a hash-chained audit ledger. When
> a customer replies, the agent reads it: a promise-to-pay suppresses outreach
> until the promised date, a dispute halts dunning entirely within one cycle,
> and a request to stop is permanent. When the LLM or the payment API goes down,
> it degrades to rules and templates and keeps running without sending anything
> twice. We measure ourselves against a no-contact holdout, so the number we
> report is *incremental* recovery with a confidence interval — reported under
> three environments, including one where our own beliefs are deliberately
> wrong, to show that the guardrails, not the model, are what make it safe to
> let this thing near money.

---

*v4 — 28 August 2026, evening; amended later the same evening for ADR-004
(LLM vendor: Anthropic → Gemini). Supersedes `plan.v2.superseded.md` (v3 was
edited in place, no snapshot kept). Re-sequenced after Day 1's actual
execution (§1.1, F1–F7) for a solo builder with no slack — architecture
unchanged from v3, only the calendar, the model-routing decisions (§9), and
the LLM vendor were added or moved. Gemini API details (SDK, structured-
output pattern, current model names) verified against ai.google.dev on
28 August 2026 — re-verify at signup if this document is read later, per
§8's note that Google's free-tier lineup moves fast. Track brief and
evaluation criteria sourced from razorpay.com/buildathon.*
