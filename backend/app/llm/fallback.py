"""The chaos-switch fallback — plan.md §6.8 graceful degradation. When
Gemini is unreachable, extraction falls back to keyword matching at a
FIXED confidence of 0.5 — deliberately below CONFIDENCE_THRESHOLD (0.6),
so every fallback classification routes to the human queue rather than
acting automatically. The loop keeps running; nothing gets auto-approved
on a guess.
"""
from __future__ import annotations

from app.llm.types import ReplyExtraction

FALLBACK_CONFIDENCE = 0.5

# Order matters — first match wins, same discipline as the diagnosis
# cascade. stop_contact and dispute are checked first because acting on a
# false negative there is the most costly mistake.
_KEYWORD_RULES: list[tuple[str, list[str]]] = [
    ("stop_contact", ["stop contacting", "stop emailing", "do not contact", "unsubscribe", "stop sending"]),
    ("dispute", ["dispute", "incorrect", "doesn't match", "duplicate charge", "never received", "wrong"]),
    ("requests_payment_plan", ["instalment", "installment", "payment plan", "split this", "part-payment"]),
    ("promise_to_pay", ["will pay", "will settle", "payment is scheduled", "will clear", "expect payment"]),
    ("approval_blocker", ["approval", "finance team", "po approval", "accounts payable", "payment run"]),
    ("details_incorrect", ["resend", "reissue", "correct address", "misspelled", "correct copy"]),
    ("acknowledgement", ["noted", "looking into", "will revert", "got it", "will check"]),
]


def fallback_classify(text: str) -> ReplyExtraction:
    lowered = text.lower()
    quote = text[:200]
    for intent, keywords in _KEYWORD_RULES:
        if any(kw in lowered for kw in keywords):
            return ReplyExtraction(
                intent=intent,  # type: ignore[arg-type]
                sentiment="neutral",
                confidence=FALLBACK_CONFIDENCE,
                evidence_quote=quote,
            )
    return ReplyExtraction(
        intent="unrelated", sentiment="neutral", confidence=FALLBACK_CONFIDENCE, evidence_quote=quote
    )
