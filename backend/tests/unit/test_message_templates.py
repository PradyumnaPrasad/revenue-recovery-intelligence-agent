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


def test_no_template_for_a_non_message_action_raises():
    # route_to_dispute is a policy-outcome terminal, never a real ActionKey
    # member, so it can't reach this function via app.tools.registry at
    # all -- but if it ever did, silently returning something generic
    # would be worse than a loud failure.
    with pytest.raises(KeyError):
        render_message(ActionKey.send_upi_payment_link, "INV-2000", 123_456_00)
