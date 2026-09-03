"""app/tools/plan_builder.py -- the real computed artifacts behind
offer_payment_plan, schedule_call, and escalate_to_am. Found live, called
out directly by a user clicking through the demo: "if we click for
offer_payment_plan, there is no plan, just an email drafted." These tests
guard the actual numbers, not just that a function returns something.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.domain.ranking import load_action_config
from app.domain.types import ActionKey
from app.tools.plan_builder import (
    assign_account_manager,
    build_installment_plan,
    escalation_sla,
    next_business_slot,
)

NOW = datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc)  # a Monday


def test_installments_sum_exactly_to_the_collectible_amount():
    # Not approximately -- exactly. A payment plan that doesn't sum to
    # what it claims to collect isn't a real plan.
    econ = load_action_config().actions[ActionKey.offer_payment_plan]
    amount_paise = 7_327_249
    plan = build_installment_plan(amount_paise, NOW)
    assert sum(i["amount_paise"] for i in plan) == round(amount_paise * econ.collectible_fraction)


def test_installment_count_defaults_to_three():
    plan = build_installment_plan(1_000_000, NOW)
    assert len(plan) == 3
    assert [i["installment_no"] for i in plan] == [1, 2, 3]


def test_installment_due_dates_are_spread_across_configured_days_to_cash():
    plan = build_installment_plan(1_000_000, NOW)
    due_dates = [i["due_date"] for i in plan]
    assert due_dates == sorted(due_dates)  # strictly increasing
    assert len(set(due_dates)) == len(due_dates)  # no two installments on the same day


def test_next_business_slot_skips_the_weekend():
    friday = datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc)  # a Friday
    slot = datetime.fromisoformat(next_business_slot(friday))
    assert slot.weekday() == 0  # Monday, not Saturday
    assert slot.hour == 11


def test_next_business_slot_is_always_eleven_am():
    for day_offset in range(7):
        from datetime import timedelta
        d = NOW + timedelta(days=day_offset)
        slot = datetime.fromisoformat(next_business_slot(d))
        assert slot.hour == 11
        assert slot.weekday() < 5


def test_account_manager_assignment_is_deterministic():
    first = assign_account_manager("INV-1015")
    second = assign_account_manager("INV-1015")
    assert first == second


def test_different_invoices_can_get_different_account_managers():
    from app.tools.plan_builder import _ACCOUNT_MANAGERS

    assignments = {assign_account_manager(f"INV-{i}")["name"] for i in range(1000, 1050)}
    # Not asserting a specific distribution, just that the roster is
    # actually exercised, not silently collapsing to one person for
    # every invoice.
    assert len(assignments) > 1
    assert assignments.issubset({am["name"] for am in _ACCOUNT_MANAGERS})


def test_escalation_sla_is_hours_after_now():
    sla = datetime.fromisoformat(escalation_sla(NOW))
    assert sla > NOW
    assert (sla - NOW).total_seconds() / 3600 == 4
