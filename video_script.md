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

**[On screen: Command Center dashboard, live. Click an invoice — pick a
real ₹2.5L / ~45-days-overdue one from the queue.]**

> "Here's one real invoice from our seeded portfolio. ₹2.5 lakh, 45 days
> overdue. The system diagnoses it first — not a black box, an evidence
> trail: broken promises, contact history, payment channel status — and
> lands on a specific diagnosis, not just 'overdue.'
>
> Then it ranks every available action by risk-adjusted expected value —
> cost of the action, probability it recovers the money, how long that
> takes, discounted for time. Watch this one: the highest expected-value
> action here is actually a hard escalation to an account manager. But our
> policy engine gates it — [click to show the gate/reason] — because this
> customer already has an open promise-to-pay that hasn't come due yet.
> Contacting them again right now would just be noise. That's the policy
> layer doing its job: overriding the 'optimal' answer because it knows
> something the ranking model doesn't."

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

**[On screen: recovery curve chart, three arms. Then click into the audit
chain and tamper a row live to show the hash break.]**

> "Here's the number that actually matters: we don't just measure recovery
> rate, because that number is meaningless on its own — some invoices
> would've paid themselves with zero contact. So we run three arms:
> our agent, a fixed baseline cadence, and a true no-contact holdout.
> [point at curve] This gap, right here, is the actual incremental
> recovery our agent adds — with a bootstrap confidence interval, not a
> single lucky run. And every decision behind that curve is hash-chained —
> watch what happens if I tamper with one row after the fact. [tamper it]
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
  90.6% intent accuracy, 145/145 tests, the specific invoice ID and amounts
  you'll click through, the bootstrap CI on the recovery curve. If any of
  these drifted since the last full run, re-run `app.evaluation.report`
  and the spot-check before you hit record — don't recite a stale number.
- **The last 25 seconds is the highest-leverage part of the video.** Most
  submissions end on their best number; ending on the limits of your own
  claim plus evidence you stress-tested it is what a technical panel
  remembers, and it pre-empts the question they were about to ask you.
- **If something breaks mid-recording:** that's fine, it's an artifact of
  a live demo — but in *your* video, don't leave it in. Cut and re-take
  that beat rather than narrating around a bug, unless it's the chaos beat
  where a "failure" is literally the point.
