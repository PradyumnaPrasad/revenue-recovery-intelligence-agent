"""Stub adapter — plan.md §3.3, "proves extensibility, not demoed live."

Deliberately shallow: no `abandoned_checkouts` table exists (building one
would be real, out-of-scope work for a stub whose only job is to prove the
seam). What this DOES prove is real: a checkout is not an invoice — it has
no due date, no dispute flag, no customer payment history — and yet it
satisfies the exact same RiskSource Protocol as ReceivablesSource with a
fraction of the code, because RiskEvent was designed generic from the
start (reference_id, not invoice_id) rather than retrofitted.

A real implementation would query orders created more than N minutes ago
with no successful payment attempt; this stub returns a small, fixed,
declared list so the interface can be exercised and tested without a new
domain model.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.types import RiskEvent

_DECLARED_ABANDONED_CHECKOUTS = [
    {"order_id": "order_demo_001", "amount_paise": 4_999_00, "minutes_since_created": 45},
    {"order_id": "order_demo_002", "amount_paise": 12_499_00, "minutes_since_created": 90},
]


class CheckoutAbandonmentSource:
    key = "checkout_abandonment"

    async def detect(self, session: AsyncSession, now: datetime) -> list[RiskEvent]:
        return [
            RiskEvent(
                source=self.key,
                reference_id=c["order_id"],
                detected_at=now,
                amount_at_risk_paise=c["amount_paise"],
                payload={"minutes_since_created": c["minutes_since_created"]},
            )
            for c in _DECLARED_ABANDONED_CHECKOUTS
        ]
