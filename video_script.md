# Pitch video script — 5:00 — Revenue Recovery Intelligence Agent

Razorpay AI Buildathon 2026, Track 03. Read this out loud once before recording —
it's timed to speak, not to read silently. Where a line is long, that's the
beat where you're clicking, not talking; let the screen do the work.

Everything you say a number in this script, it's a real number from the live
system (checked against plan.md's defect log and the last verified test run).
Don't round up. If you re-run something before recording and a number moves,
update the script, not the other way around.

---

## 0:00–0:25 — The problem (25s)

**[On screen: a simple diagram — one dunning ladder, two very different
customers hitting it]**

> "Every accounts-receivable system on the market has the same blind spot.
> A ₹40,000 SaaS invoice from a customer who's always paid on time, and an
> ₹8 lakh invoice from a customer who's defaulted three times before —
> today, both of them get the exact same four emails, on the exact same
> schedule. The system doesn't know the difference. We built one that
> does."

---

## 0:25–0:50 — The invariant (25s)

**[On screen: architecture slide — the eight-step loop, or just three boxes:
Model → Policy → Tools]**

> "Our whole system comes down to one sentence: the model ranks, the policy
> decides, the tools execute — and everything is logged. The model never
> touches money. It scores options. A separate, auditable policy engine
> decides what's actually allowed to happen. Only then do real tools —
> Razorpay, in our case — get called."

---

## 0:50–1:45 — One invoice, end to end (55s)

**[On screen: Command Center dashboard, live. Click INV-1012 — ₹6,22,858,
29 days overdue, batch `fc1fa32f-7dd5-53fd-b02a-3b3c8493599b`. Scroll to
show both the "Baseline vs. this system" card and the ranked-actions
table.]**

> "Here's one real invoice from our seeded portfolio. ₹6.2 lakh, 29 days
> overdue. The system diagnoses it first — not a black box, an evidence
> trail: this customer has a 16% prior late-payment rate and three broken
> promises before — cash-flow risk, not just 'overdue.'
>
> Then it ranks every available action by risk-adjusted expected value, and
> the top choice is escalating straight to an account manager. Now watch
> this card — [point at the 'Baseline vs. this system' card, which reads
> DIVERGES] — a fixed, diagnosis-blind cadence would just resend the
> payment link at 29 days, the same thing it does for every invoice. Our
> system wants to escalate instead. But before that happens — [point at the
> policy card] — the policy engine steps in: this invoice is over our
> ₹5 lakh threshold, so escalation doesn't fire automatically. It goes to a
> human for approval first. That's two layers doing their job in one
> screen: the ranking model disagreeing with a naive script, and governance
> disagreeing with the ranking model."

**[Backup invoice if you want a second, sharper contrast:
INV-1001 — ₹1,22,223, 37 days overdue — where a fixed cadence would
escalate to an account manager, but this system BLOCKS entirely because
the customer already has an open promise-to-pay. That's an even cleaner
"the naive system would annoy someone who already said yes" story if you
have time for two invoices instead of one.]**

---

## 1:45–3:00 — The agent listens (75s — the longest beat, deliberately)

**[On screen: reply panel / extraction flow. This is where you spend the
most time, per the track brief's own guidance on LLM-orchestration demos.]**

> "The hardest part of collections isn't sending messages — it's reading
> replies. Customers don't reply in structured data, they reply in whatever
> they feel like typing. Watch what happens when I paste in a real,
> messy customer reply: [type/paste] 'we're not paying this, the GST
> number on the invoice is wrong, dispute this.'
>
> First it's redacted for PII before it ever leaves our system — emails,
> phone numbers, GST numbers get masked before anything goes to the model.
> Then Gemini extracts structured intent under a locked schema — [show the
> JSON: intent: dispute, confidence, evidence quote]. We don't trust this
> blindly: the model has to return a verbatim quote from the actual reply
> as evidence, and we verify that quote is genuinely present in the
> original text before we act on it — that's how we catch hallucination
> before it becomes a wrong decision. This one lands as a dispute with high
> confidence, so dunning halts immediately, and it's routed to the dispute
> queue instead.
>
> And on a full accuracy pass against realistic fixtures, this
> classification pipeline holds 90.6% intent accuracy and a perfect
> date-extraction match rate — with zero PII leaks. When confidence drops
> below 0.6, we don't guess — it goes to a human review queue instead."

---

## 3:00–3:25 — Real execution (25s)

**[On screen: split — your app on one side, actual Razorpay test-mode
dashboard on the other.]**

> "This isn't a mockup. When the system decides to send a payment link, it
> calls the real Razorpay API in test mode — [show the plink_... ID] — and
> when that invoice gets paid, a real HMAC-verified webhook closes the
> loop back in our system automatically. And every action is idempotent —
> call the same action twice by accident, you get the same result once,
> not a duplicate charge link."

---

## 3:25–3:55 — It survives failure (30s)

**[On screen: flip the chaos switch live — /demo/chaos toggle — show the
DEGRADED banner appear on the dashboard within a few seconds.]**

> "Real systems fail. So we built a chaos switch — watch. I'm killing the
> LLM and the Razorpay connection live, right now. [flip switch] The
> dashboard flags it immediately — DEGRADED — and the loop doesn't stop.
> It falls back to keyword-based classification and template messages
> instead of the LLM, queues anything it can't safely resolve for a human,
> and never double-sends or silently drops an action while it's down."

---

## 3:55–4:35 — The measurement (40s)

**[On screen: three-arm bar chart, then scroll to the "Portfolio ROI" card
just below it. Then click into the audit chain and tamper a row live to
show the hash break.]**

> "Here's the number that actually matters: we don't just measure recovery
> rate, because that number is meaningless on its own — some invoices
> would've paid themselves with zero contact. So we run three arms:
> our agent, a fixed baseline cadence, and a true no-contact holdout.
> [point at bars] This gap, right here, is the actual incremental
> recovery our agent adds — with a bootstrap confidence interval, not a
> single lucky run.
>
> But recovering more doesn't mean much if it costs more than it recovers
> — so here's the one number we'd want you to remember. [point at the ROI
> card] Incremental recovery over the holdout, minus the actual cost of
> every action we took to get it, still nets out to real money — not just
> 'we recover more,' but 'we recover more than it costs us to try.'
>
> And every decision behind these numbers is hash-chained — watch what
> happens if I tamper with one row after the fact. [tamper it]
> Verification immediately flags it: not intact. You can't quietly edit
> the record of what the agent did."

---

## 4:35–5:00 — The honest close (25s)

**[On screen: the robustness table — three environments, uplift under
each.]**

> "Two things we want to say plainly, because we'd rather you hear them
> from us. The decisions in this system are real. The customer cash flow
> underneath them is simulated, against a fully published environment —
> we tell you exactly how it works, on purpose, so our own numbers can be
> checked, not just trusted.
>
> And we didn't train a machine learning model here. In a declared
> environment, a trained model is just a lossy copy of the declaration we
> already published — so instead we spent that effort proving something
> more useful: this uplift number holds not just in the environment we
> designed for, but even in a second world where our own beliefs are
> deliberately wrong. That's the actual claim: not that the model is
> smart, but that the policy layer contains the damage when it isn't."

**[Hard cut to black or end card. Don't linger.]**

---

## Recording notes

- **Total: 5:00 flat.** Buildathon judges skim; going over costs you more
  than any beat is worth. Time yourself against this script once before
  the real take — cut words, not beats, if you're over.
- **Do the chaos-switch and tamper-the-row moments live, not as a slide.**
  Live and slightly risky reads as real; a screenshot of a green checkmark
  reads as staged. You've verified both work — trust the live system.
- **Numbers to have pulled up and re-verified same-day before recording:**
  90.6% intent accuracy, 150/150 tests, INV-1012's diagnosis/policy/ROI
  numbers (₹6,22,858, cash_flow_risk, requires approval over ₹5L), the
  bootstrap CI on the recovery curve, and the Portfolio ROI card's three
  numbers (they must literally subtract correctly on screen — verify with
  `curl "localhost:8000/evaluation/summary?seed=42&size=300"` right before
  recording). If any of these drifted since the last full run, re-run
  `app.evaluation.report` and the spot-check before you hit record — don't
  recite a stale number.
- **INV-1012's batch is the standard seed-42/size-500 batch** (batch_id
  `fc1fa32f-7dd5-53fd-b02a-3b3c8493599b` on this build — re-confirm via
  `GET /batches` same-day, since a fresh `docker compose up` reseeds a new
  batch_id even with the same seed/size). If INV-1012 isn't at the queue
  position you expect, use `POST /invoices/{id}/evaluate` to find it by
  invoice_number, or fall back to INV-1001 (the promise-to-pay block case).
- **The last 25 seconds is the highest-leverage part of the video.** Most
  submissions end on their best number; ending on the limits of your own
  claim plus evidence you stress-tested it is what a technical panel
  remembers, and it pre-empts the question they were about to ask you.
- **If something breaks mid-recording:** that's fine, it's an artifact of
  a live demo — but in *your* video, don't leave it in. Cut and re-take
  that beat rather than narrating around a bug, unless it's the chaos beat
  where a "failure" is literally the point.
