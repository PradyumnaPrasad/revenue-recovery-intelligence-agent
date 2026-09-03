"""Real, computed artifacts behind offer_payment_plan, schedule_call, and
escalate_to_am — not just drafted prose.

Found live, called out directly: "if we click for offer_payment_plan,
there is no plan, just a email drafted." Correct. The email body used to
say "we'll set one up that works for you" with no actual numbers behind
it — nothing you could call a plan. This module produces the real
artifact each action name promises:

- offer_payment_plan -> an actual installment schedule (N payments,
  real amounts, real due dates)
- schedule_call -> an actual proposed call slot (a real date/time, not
  "within 2 business days")
- escalate_to_am -> an actual assignment (a real account manager, a
  real response SLA)

The installment schedule is built from config/actions.yaml's
offer_payment_plan economics (collectible_fraction, days_to_cash) — the
SAME numbers the ranking model's expected-value calculation already used
to rank this action in the first place. That's deliberate: the plan a
customer would see is not invented separately from the number the model
was scored against: they're the same number, read twice.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from app.domain.ranking import load_action_config
from app.domain.types import ActionKey

_ACTION_CONFIG = load_action_config()

# A small fixed roster, not a real HR system — but a real, deterministic
# assignment (same invoice always lands on the same AM) rather than a
# generic "the team" with nobody actually on the hook.
_ACCOUNT_MANAGERS = [
    {"name": "Ritika Shah", "email": "ritika.shah@ops.revenuerecoveryagent.internal"},
    {"name": "Arjun Mehta", "email": "arjun.mehta@ops.revenuerecoveryagent.internal"},
    {"name": "Priya Nair", "email": "priya.nair@ops.revenuerecoveryagent.internal"},
]

_ESCALATION_SLA_HOURS = 4


def build_installment_plan(amount_paise: int, now: datetime, n: int = 3) -> list[dict]:
    """N installments summing exactly to the invoice's collectible amount
    (config's collectible_fraction, applied once here — not re-derived or
    re-guessed), spaced evenly across the configured days_to_cash. Any
    rounding remainder lands on the final installment so the schedule
    always sums exactly to the collectible total, never a paise short.
    """
    econ = _ACTION_CONFIG.actions[ActionKey.offer_payment_plan]
    collectible = round(amount_paise * econ.collectible_fraction)
    per_installment = collectible // n
    remainder = collectible - per_installment * n
    step_days = econ.days_to_cash / n

    installments = []
    for i in range(1, n + 1):
        amount = per_installment + (remainder if i == n else 0)
        due = now + timedelta(days=round(step_days * i))
        installments.append(
            {"installment_no": i, "amount_paise": amount, "due_date": due.date().isoformat()}
        )
    return installments


def next_business_slot(now: datetime) -> str:
    """The next weekday at 11:00, on the frozen demo clock's own
    timezone — a real, specific slot, not a vague "within N business
    days." Per-customer timezone lookup is out of scope for this build;
    stated here rather than silently assumed.
    """
    candidate = now + timedelta(days=1)
    while candidate.weekday() >= 5:  # Saturday=5, Sunday=6
        candidate += timedelta(days=1)
    slot = candidate.replace(hour=11, minute=0, second=0, microsecond=0)
    return slot.isoformat()


def assign_account_manager(invoice_number: str) -> dict:
    """Deterministic, not random — the same invoice always lands on the
    same account manager across repeated calls, so the audit trail tells
    one consistent story instead of reassigning on every re-evaluation.
    """
    idx = int(hashlib.sha256(invoice_number.encode()).hexdigest(), 16) % len(_ACCOUNT_MANAGERS)
    return _ACCOUNT_MANAGERS[idx]


def escalation_sla(now: datetime) -> str:
    return (now + timedelta(hours=_ESCALATION_SLA_HOURS)).isoformat()
