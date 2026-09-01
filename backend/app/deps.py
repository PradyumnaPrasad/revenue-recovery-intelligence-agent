"""Shared FastAPI dependencies: DB session and the process-wide Clock.

The demo runs on VirtualClock, not RealClock, by default (plan.md §6.9 — the
whole point of the virtual clock is that a 45-day recovery journey advances
via /simulate/advance, not real wall-clock waiting). VirtualClock's own
default start instant (2026-01-01 09:00 UTC) is the same reference instant
the portfolio generator anchors to (app/simulation/generator.py:ANCHOR) —
that alignment matters: if the process clock defaulted to RealClock instead,
every days_overdue recomputed from `clock.now() - due_date` would drift by
however far real wall-clock time has moved past the generator's anchor
(discovered as F6 in the D1 verification pass — a reference batch generated
against the anchor was coming back with a diagnosis mix wildly outside the
declared bands, because `days_overdue` was being computed against today's
actual date instead of the anchor). A genuine production deployment would
swap this for RealClock via set_clock(); the demo and every current API
caller should not.
"""
from __future__ import annotations

from app.domain.clock import Clock, VirtualClock

_clock: Clock = VirtualClock()


def get_clock() -> Clock:
    return _clock


def set_clock(clock: Clock) -> None:
    """Test/demo hook — swap the process clock (e.g. to a VirtualClock)."""
    global _clock
    _clock = clock
