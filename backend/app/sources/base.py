"""The RiskSource contract — plan.md §6.0. Adding a new surface (a failed
payment, a halted subscription, an abandoned checkout) is one adapter
class satisfying this Protocol, with zero changes to diagnosis, ranking,
policy, or audit. That claim is proven, not just stated, by two adapters
existing side by side: app/sources/receivables.py (real, DB-backed, the
deep-built surface) and app/sources/checkout_abandonment.py (a stub over
a genuinely different domain object — an order, not an invoice — that
satisfies the identical interface in under 30 lines).
"""
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.types import RiskEvent


class RiskSource(Protocol):
    key: str

    async def detect(self, session: AsyncSession, now: datetime) -> list[RiskEvent]:
        """Returns the currently at-risk items for this surface. Pure with
        respect to *emission*: calling this repeatedly with unchanged
        underlying data returns the same set every time — it reflects
        current state rather than accumulating a persisted event log, so
        no source can double-emit across repeated ticks by construction.
        """
        ...
