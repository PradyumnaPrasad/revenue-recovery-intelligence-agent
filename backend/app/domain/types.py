"""Shared value types for the pure domain layer. Plain dataclasses/Pydantic
models only — no ORM imports here. This keeps app/domain/ importable and
testable with zero database or network dependency (see plan.md §9).
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Arm(str, Enum):
    agent = "agent"
    baseline = "baseline"
    holdout = "holdout"


class ActionKey(str, Enum):
    """Candidate recovery actions the ranking layer (M3) chooses between.

    Deliberately excludes `request_human_approval`, `stop`, and
    `route_to_dispute` — those are POLICY OUTCOMES, not revenue tactics, and
    must never compete in the same expected-value ranking (plan.md §6.6).
    """

    send_reminder = "send_reminder"
    resend_payment_link = "resend_payment_link"
    send_upi_payment_link = "send_upi_payment_link"
    offer_payment_plan = "offer_payment_plan"
    escalate_to_am = "escalate_to_am"
    schedule_call = "schedule_call"


class DiagnosisCode(str, Enum):
    disputed = "disputed"
    chronic_non_payment = "chronic_non_payment"
    cash_flow_risk = "cash_flow_risk"
    channel_failure = "channel_failure"
    process_delay = "process_delay"
    standard_overdue = "standard_overdue"


class InvoiceFacts(BaseModel):
    """The read-only, observable facts a diagnosis rule is allowed to look
    at. Deliberately narrow: adding a field here is a considered decision,
    not an accident, because every field is something the rules (and later,
    the policy evaluator) can branch on.
    """

    invoice_id: str
    amount_paise: int
    days_overdue: int
    dispute_flag: bool
    prior_late_payment_rate: float = Field(ge=0.0, le=1.0)
    prior_broken_promises: int = Field(ge=0)
    prior_invoice_count: int = Field(ge=0)
    contact_count_30d: int = Field(ge=0)
    payment_link_sent: bool = False
    payment_link_opened: bool = False
    has_open_dispute_reply: bool = False


class Diagnosis(BaseModel):
    code: DiagnosisCode
    confidence: float = Field(ge=0.0, le=1.0)
    rule_id: str
    explanation: str
    signals: list[str]
    produced_by: Literal["rules", "llm_fallback"] = "rules"


class RiskEvent(BaseModel):
    """The one shape every money-at-risk surface normalises into — the
    seam that makes 'one engine, many risk sources' true in code, not just
    in a pitch (plan.md §6.0 / C6). Overdue invoices are the deep, fully
    built surface (app/sources/receivables.py); failed payments,
    subscription dunning, and checkout abandonment are surfaces this same
    RiskEvent shape can carry without a pipeline change — proven, not just
    claimed, by app/sources/checkout_abandonment.py: a genuinely different
    domain (an order, not an invoice) satisfying the exact same contract.
    """

    source: Literal[
        "receivables", "payment_failure", "subscription_dunning", "checkout_abandonment"
    ]
    reference_id: str  # the source's own id for the at-risk thing (invoice id, order id, ...)
    detected_at: datetime
    amount_at_risk_paise: int
    payload: dict
