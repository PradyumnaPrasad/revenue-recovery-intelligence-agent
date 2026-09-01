"""Deterministic diagnosis cascade — plan.md §6.3 (fixes C9: the original
design had overlapping, non-exclusive rules; a disputed+chronic invoice
could get two labels, which breaks the "deterministic and explainable"
claim). Rules are evaluated IN ORDER; the first match wins and short-
circuits the rest, so every InvoiceFacts maps to exactly one Diagnosis.

Ordering is a deliberate business call, not alphabetical, and it changed
from the original design (plan.md F4):
  R01 disputed            — dominates everything; a disputed invoice must
                             never enter dunning no matter how bad the
                             payment history looks.
  R02 chronic_non_payment — outranks channel/cash-flow because it changes
                             the action set (escalate/write-off vs "help
                             them pay"), not just the wording. Threshold
                             lowered from 60 to 35 days: two broken promises
                             plus five weeks overdue is already chronic
                             behaviour, and waiting until day 61 to say so
                             costs a month of pointless reminders.
  R03 channel_failure     — MOVED ABOVE cash_flow_risk. If a payment link
                             was sent and never opened across repeated
                             contacts, you learn nothing about the
                             customer's finances from someone who never saw
                             the invoice — labelling that cash-flow risk is
                             simply wrong, not just imbalanced. Before this
                             reorder, cash_flow_risk's broken_promises>=1
                             threshold claimed 74% of channel_failure's
                             natural population before it was ever
                             evaluated, driving channel_failure down to an
                             undemoable 1.4% of the portfolio.
  R04 cash_flow_risk      — broken_promises threshold raised from 1 to 2:
                             one broken promise is noise; two is a pattern.
  R05 process_delay       — days_overdue window widened 14->21, late_rate
                             ceiling widened 0.2->0.3, and broken_promises
                             changed from ==0 to <=1: the original window
                             was so narrow that a reliable customer with a
                             single old slip fell through to
                             standard_overdue, which carries no useful
                             action signal.
  R06 standard_overdue    — fallback; never fails to match.

See plan.md §6.1 for the measured diagnosis-mix effect of this change.
"""
from __future__ import annotations

from app.domain.types import Diagnosis, DiagnosisCode, InvoiceFacts

_CHRONIC_DAYS_OVERDUE = 35
_CHRONIC_BROKEN_PROMISES = 2
_CHANNEL_FAILURE_CONTACTS = 2
_CASH_FLOW_LATE_RATE = 0.4
_CASH_FLOW_BROKEN_PROMISES = 2
_PROCESS_DELAY_MAX_DAYS = 21
_PROCESS_DELAY_LATE_RATE = 0.3
_PROCESS_DELAY_MAX_BROKEN_PROMISES = 1


def diagnose(facts: InvoiceFacts) -> Diagnosis:
    if facts.dispute_flag or facts.has_open_dispute_reply:
        signals = []
        if facts.dispute_flag:
            signals.append("dispute_flag=true")
        if facts.has_open_dispute_reply:
            signals.append("inbound reply classified as dispute")
        return Diagnosis(
            code=DiagnosisCode.disputed,
            confidence=1.00,
            rule_id="R01.disputed",
            explanation="Invoice is disputed and must route to human dispute "
            "resolution instead of automated dunning.",
            signals=signals,
        )

    if (
        facts.days_overdue > _CHRONIC_DAYS_OVERDUE
        and facts.prior_broken_promises >= _CHRONIC_BROKEN_PROMISES
    ):
        return Diagnosis(
            code=DiagnosisCode.chronic_non_payment,
            confidence=0.90,
            rule_id="R02.chronic_non_payment",
            explanation="Long-overdue invoice with repeated broken promises; "
            "further reminders are unlikely to change behaviour.",
            signals=[
                f"days_overdue={facts.days_overdue} (>{_CHRONIC_DAYS_OVERDUE})",
                f"prior_broken_promises={facts.prior_broken_promises} "
                f"(>={_CHRONIC_BROKEN_PROMISES})",
            ],
        )

    if (
        facts.payment_link_sent
        and not facts.payment_link_opened
        and facts.contact_count_30d >= _CHANNEL_FAILURE_CONTACTS
    ):
        return Diagnosis(
            code=DiagnosisCode.channel_failure,
            confidence=0.70,
            rule_id="R03.channel_failure",
            explanation="Payment link was sent but never opened across "
            "repeated contacts; the outreach channel itself is likely the "
            "problem, not persuasion or ability to pay.",
            signals=[
                "payment_link_sent=true",
                "payment_link_opened=false",
                f"contact_count_30d={facts.contact_count_30d}",
            ],
        )

    if (
        facts.prior_late_payment_rate >= _CASH_FLOW_LATE_RATE
        or facts.prior_broken_promises >= _CASH_FLOW_BROKEN_PROMISES
    ):
        signals = [f"prior_late_payment_rate={facts.prior_late_payment_rate:.2f}"]
        if facts.prior_broken_promises >= _CASH_FLOW_BROKEN_PROMISES:
            signals.append(f"prior_broken_promises={facts.prior_broken_promises}")
        return Diagnosis(
            code=DiagnosisCode.cash_flow_risk,
            confidence=0.75,
            rule_id="R04.cash_flow_risk",
            explanation="Payment history indicates elevated cash-flow or "
            "payment-reliability risk.",
            signals=signals,
        )

    if (
        facts.days_overdue <= _PROCESS_DELAY_MAX_DAYS
        and facts.prior_late_payment_rate < _PROCESS_DELAY_LATE_RATE
        and facts.prior_broken_promises <= _PROCESS_DELAY_MAX_BROKEN_PROMISES
    ):
        return Diagnosis(
            code=DiagnosisCode.process_delay,
            confidence=0.65,
            rule_id="R05.process_delay",
            explanation="Historically reliable customer, only recently "
            "overdue; likely internal approval or invoicing friction rather "
            "than unwillingness to pay.",
            signals=[
                f"days_overdue={facts.days_overdue} (<={_PROCESS_DELAY_MAX_DAYS})",
                f"prior_late_payment_rate={facts.prior_late_payment_rate:.2f} "
                f"(<{_PROCESS_DELAY_LATE_RATE})",
                f"prior_broken_promises={facts.prior_broken_promises} "
                f"(<={_PROCESS_DELAY_MAX_BROKEN_PROMISES})",
            ],
        )

    return Diagnosis(
        code=DiagnosisCode.standard_overdue,
        confidence=0.40,
        rule_id="R06.standard_overdue",
        explanation="Overdue, but no stronger diagnosis signal is present.",
        signals=[f"days_overdue={facts.days_overdue}"],
    )
