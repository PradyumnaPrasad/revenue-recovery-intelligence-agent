"""The reply-extraction contract — plan.md §6.8. The LLM's output is
EVIDENCE, not a decision: a structured fact fed to the deterministic
layers, which retain all authority over what happens next.
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

ReplyIntent = Literal[
    "promise_to_pay",
    "dispute",
    "approval_blocker",
    "details_incorrect",
    "requests_payment_plan",
    "stop_contact",
    "acknowledgement",
    "unrelated",
]


class ReplyExtraction(BaseModel):
    intent: ReplyIntent
    promised_date: date | None = None
    promised_amount_paise: int | None = None
    dispute_reason: str | None = None
    blocker_owner: str | None = None  # "PO approval", "finance head", ...
    sentiment: Literal["cooperative", "neutral", "hostile"]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_quote: str = Field(max_length=200)  # verbatim span, verified as a substring
