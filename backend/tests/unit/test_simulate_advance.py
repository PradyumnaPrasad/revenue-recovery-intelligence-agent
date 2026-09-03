"""app/api/simulate.py's advance_clock() -- the parts testable without a
live DB (see backend/README.md: DB-touching flows in this project are
verified live against the running Postgres container, not through
pytest, the same precedent as app/sources/receivables.py). tick() itself
is verified live in plan.md's F19 entry.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import patch

from app.api.simulate import advance_clock
from app.domain.clock import RealClock, VirtualClock


def test_advance_moves_a_virtual_clock_forward():
    vc = VirtualClock(start=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc))
    with patch("app.api.simulate.get_clock", return_value=vc):
        result = asyncio.run(advance_clock(days=7))
    assert result["now"] == "2026-01-08T09:00:00+00:00"
    assert vc.now() == datetime(2026, 1, 8, 9, 0, tzinfo=timezone.utc)


def test_advance_supports_fractional_hours_too():
    vc = VirtualClock(start=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc))
    with patch("app.api.simulate.get_clock", return_value=vc):
        asyncio.run(advance_clock(days=1, hours=6))
    assert vc.now() == datetime(2026, 1, 2, 15, 0, tzinfo=timezone.utc)


def test_advance_refuses_a_real_clock_instead_of_silently_doing_nothing():
    # A production deployment's clock moves on its own; an API forcing it
    # forward would be a genuine bug, not a feature -- this must fail
    # loudly, not silently no-op and let a caller believe time advanced.
    with patch("app.api.simulate.get_clock", return_value=RealClock()):
        result = asyncio.run(advance_clock(days=1))
    assert "error" in result
