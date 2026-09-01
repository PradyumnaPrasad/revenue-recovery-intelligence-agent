"""Template bank for the synthetic inbound-reply corpus (plan.md §6.1 change
3). ~60 templates x Faker slotting is deliberately "enough, not exhaustive"
— this corpus exists to give the M6 reply-extraction layer something
realistic to be evaluated against, not to be a production dataset.
"""
from __future__ import annotations

PROMISE_TO_PAY = [
    "We'll settle this by {date}, once the current payment run clears.",
    "Payment is scheduled for {date} — cheque is being couriered.",
    "Apologies for the delay, we will pay {amount} by {date}.",
    "Our finance team has approved this; expect payment on {date}.",
    "We can clear it on {date} after the PO reconciliation finishes.",
]

DISPUTE = [
    "We dispute this invoice — the GST number listed is incorrect.",
    "This amount doesn't match what was agreed in the contract, please review.",
    "We never received the goods listed on this invoice.",
    "There's a duplicate charge here, we already paid invoice {other_ref}.",
    "The quantities billed don't match our PO. Please correct and resend.",
]

APPROVAL_BLOCKER = [
    "This is stuck with our finance head for approval, following up internally.",
    "Waiting on PO approval before we can release payment.",
    "Our AP team processes vendor payments only on the last Friday of the month.",
    "Need a fresh invoice copy addressed to accounts payable to route it internally.",
]

DETAILS_INCORRECT = [
    "Can you resend this with our correct billing address?",
    "The invoice number doesn't match our PO reference, please reissue.",
    "Our company name is misspelled on this invoice, need a corrected copy.",
]

REQUESTS_PAYMENT_PLAN = [
    "Can we split this into instalments? Cash flow is tight this quarter.",
    "We'd like to propose a 3-month payment plan for this amount.",
    "Is a part-payment now and the rest next month possible?",
]

STOP_CONTACT = [
    "Please stop emailing multiple people on our side, route everything through me.",
    "We are aware of this invoice, please do not send further reminders this week.",
    "Stop contacting our CFO directly, all correspondence should go through AP.",
]

ACKNOWLEDGEMENT = [
    "Got it, looking into this.",
    "Thanks for the reminder, will check with the team.",
    "Noted, will revert shortly.",
]

UNRELATED = [
    "Out of office until next week, will respond on return.",
    "This mailbox is no longer monitored, please use accounts@ instead.",
    "Thanks!",
]

TEMPLATE_BANK: dict[str, list[str]] = {
    "promise_to_pay": PROMISE_TO_PAY,
    "dispute": DISPUTE,
    "approval_blocker": APPROVAL_BLOCKER,
    "details_incorrect": DETAILS_INCORRECT,
    "requests_payment_plan": REQUESTS_PAYMENT_PLAN,
    "stop_contact": STOP_CONTACT,
    "acknowledgement": ACKNOWLEDGEMENT,
    "unrelated": UNRELATED,
}

# Target label distribution for the corpus (plan.md §6.1 done-when: within
# +/-5pp of target).
TARGET_DISTRIBUTION: dict[str, float] = {
    "promise_to_pay": 0.28,
    "dispute": 0.12,
    "approval_blocker": 0.16,
    "details_incorrect": 0.08,
    "requests_payment_plan": 0.10,
    "stop_contact": 0.04,
    "acknowledgement": 0.14,
    "unrelated": 0.08,
}
