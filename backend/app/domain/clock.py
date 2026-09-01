"""Clock abstraction. Domain code must NEVER call datetime.now()/utcnow()
directly — grep-tested in CI (see tests/unit/test_no_wall_clock.py). All
"now" comes from an injected Clock so a demo can compress a 45-day recovery
journey into `/simulate/advance?days=45` and tests are deterministic.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

_BUSINESS_START_HOUR = 9
_BUSINESS_END_HOUR = 19


class Clock(Protocol):
    def now(self) -> datetime: ...

    def is_business_hours(self, tz: str = "Asia/Kolkata") -> bool:
        ...


def _is_business_hours(instant: datetime, tz: str) -> bool:
    local = instant.astimezone(ZoneInfo(tz)) if ZoneInfo else instant
    if local.weekday() >= 5:  # Sat/Sun
        return False
    return _BUSINESS_START_HOUR <= local.hour < _BUSINESS_END_HOUR


class RealClock:
    """Production clock — wall time, UTC."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def is_business_hours(self, tz: str = "Asia/Kolkata") -> bool:
        return _is_business_hours(self.now(), tz)


class VirtualClock:
    """Demo/test clock. Starts at a fixed instant and only moves when
    `advance()` is called — never on its own. This is what makes a 90-day
    simulated workflow run deterministically in a unit test.
    """

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._now

    def advance(self, days: float = 0, hours: float = 0) -> datetime:
        self._now = self._now + timedelta(days=days, hours=hours)
        return self._now

    def set(self, instant: datetime) -> None:
        self._now = instant

    def is_business_hours(self, tz: str = "Asia/Kolkata") -> bool:
        return _is_business_hours(self._now, tz)
