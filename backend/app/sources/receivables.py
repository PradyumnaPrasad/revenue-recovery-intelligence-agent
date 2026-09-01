"""The deep-built risk source — plan.md §3.3. Overdue B2B invoices are
this project's full-depth vertical: every layer (diagnosis, ranking,
policy, execution, measurement) exists for this surface. Other sources
(payment_failure, subscription_dunning, checkout_abandonment) plug into
the same RiskEvent shape without touching any of that.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Invoice
from app.domain.types import RiskEvent


class ReceivablesSource:
    key = "receivables"

    async def detect(self, session: AsyncSession, now: datetime) -> list[RiskEvent]:
        stmt = select(Invoice).where(Invoice.due_date < now, Invoice.status == "overdue")
        rows = (await session.execute(stmt)).scalars().all()
        return [
            RiskEvent(
                source=self.key,
                reference_id=str(inv.id),
                detected_at=now,
                amount_at_risk_paise=inv.amount_paise,
                payload={"invoice_number": inv.invoice_number, "batch_id": str(inv.batch_id)},
            )
            for inv in rows
        ]
