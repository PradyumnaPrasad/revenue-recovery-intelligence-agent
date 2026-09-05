"""app/api/invoices.py's OPEN_STATUS/RESOLUTION_REASONS -- found missing
entirely: there was no way to manually close an invoice out (a bank
transfer, a write-off, a dispute resolved outside this system), so every
invoice stayed "overdue" and ladder-eligible forever unless a real
Razorpay webhook happened to mark it paid. The actual DB-touching
endpoint (POST /invoices/{id}/resolve) is verified live, same precedent
as the other DB-dependent endpoints in this build; these guard the pure
constants the live behavior depends on.
"""
from __future__ import annotations

from app.api.invoices import OPEN_STATUS, RESOLUTION_REASONS


def test_paid_is_not_a_valid_manual_resolution_reason():
    # "paid" stays reserved for a real, webhook-verified payment (F15) --
    # resolving as paid_offline deliberately does NOT claim the same
    # thing "paid" claims, since it's asserted by a human, not verified
    # by Razorpay.
    assert "paid" not in RESOLUTION_REASONS


def test_open_status_is_not_itself_a_resolution_reason():
    assert OPEN_STATUS not in RESOLUTION_REASONS


def test_every_resolution_reason_is_distinct_from_the_open_status():
    for reason in RESOLUTION_REASONS:
        assert reason != OPEN_STATUS
