"""app/tools/templates.py -- the concrete content behind every
non-Razorpay action, so a demo viewer sees a real drafted message instead
of a bare {"recorded": true}.
"""
from __future__ import annotations

import pytest

from app.domain.types import ActionKey
from app.tools.templates import render_message


@pytest.mark.parametrize(
    "action,expected_channel",
    [
        (ActionKey.send_reminder, "email"),
        (ActionKey.offer_payment_plan, "email"),
        (ActionKey.schedule_call, "call"),
        (ActionKey.escalate_to_am, "internal"),
    ],
)
def test_every_message_action_has_a_channel(action, expected_channel):
    msg = render_message(action, "INV-2000", 123_456_00)
    assert msg["channel"] == expected_channel


def test_invoice_number_appears_in_both_subject_and_body():
    msg = render_message(ActionKey.send_reminder, "INV-2000", 123_456_00)
    assert "INV-2000" in msg["subject"]
    assert "INV-2000" in msg["body"]


def test_amount_is_rendered_with_indian_grouping_in_body():
    msg = render_message(ActionKey.offer_payment_plan, "INV-2000", 123_456_00)
    assert "₹1,23,456" in msg["body"]


def test_real_customer_name_and_email_appear_in_the_message():
    # Found live: every drafted message had NO recipient at all, even
    # though Customer.name/.email are real generated fields already
    # sitting in the DB -- an invoice-recovery email addressed to nobody
    # is not credible proof of anything on a demo screen.
    msg = render_message(
        ActionKey.send_reminder, "INV-2000", 123_456_00,
        customer_name="Acme Textiles Pvt Ltd", customer_email="ap@acmetextiles.example",
    )
    assert msg["to"] == "ap@acmetextiles.example"
    assert msg["to_name"] == "Acme Textiles Pvt Ltd"
    assert "Acme Textiles Pvt Ltd" in msg["body"]


def test_missing_customer_falls_back_honestly_not_silently():
    msg = render_message(ActionKey.send_reminder, "INV-2000", 123_456_00)
    assert msg["to"] is None
    assert msg["to_name"] is None
    # Still a coherent, readable message -- a missing customer record
    # shouldn't produce a broken "Hi None," greeting.
    assert "None" not in msg["body"]


def test_offer_payment_plan_includes_a_real_installment_schedule():
    # Found live, called out directly: "if we click for
    # offer_payment_plan, there is no plan, just an email drafted."
    msg = render_message(ActionKey.offer_payment_plan, "INV-2000", 1_000_000)
    assert "plan" in msg
    assert len(msg["plan"]) == 3
    assert "Installment 1" in msg["body"]
    assert str(msg["plan"][0]["due_date"]) in msg["body"]


def test_schedule_call_includes_a_real_slot():
    msg = render_message(ActionKey.schedule_call, "INV-2000", 1_000_000)
    assert "scheduled_for" in msg
    assert "on " in msg["body"]  # "...regarding invoice INV-2000 (...) on <slot>."


def test_escalate_to_am_includes_a_real_assignment_and_sla():
    msg = render_message(ActionKey.escalate_to_am, "INV-2000", 1_000_000)
    assert "assigned_to" in msg
    assert "respond_by" in msg
    assert msg["assigned_to"]["name"] in msg["body"]
    assert msg["assigned_to"]["email"] in msg["body"]


def test_send_reminder_has_no_extra_artifact():
    # Only the three actions above have a computed artifact -- a plain
    # reminder genuinely is just a reminder, and shouldn't fabricate one.
    msg = render_message(ActionKey.send_reminder, "INV-2000", 1_000_000)
    assert "plan" not in msg
    assert "scheduled_for" not in msg
    assert "assigned_to" not in msg


def test_no_template_for_a_non_message_action_raises():
    # route_to_dispute is a policy-outcome terminal, never a real ActionKey
    # member, so it can't reach this function via app.tools.registry at
    # all -- but if it ever did, silently returning something generic
    # would be worse than a loud failure.
    with pytest.raises(KeyError):
        render_message(ActionKey.send_upi_payment_link, "INV-2000", 123_456_00)
