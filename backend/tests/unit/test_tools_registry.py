"""plan.md §6.9 'Done when' (the parts testable without live network):
internal-record tools always succeed and record correctly, and the
razorpay chaos switch degrades gracefully instead of raising.
"""
from __future__ import annotations

from unittest.mock import patch

from app.tools.registry import execute_tool, is_razorpay_down, set_razorpay_down


def teardown_function():
    set_razorpay_down(False)


def test_send_reminder_drafts_a_real_message():
    # Found live during a demo rehearsal: before render_message() existed,
    # every non-Razorpay action returned a bare {"recorded": True} with no
    # visible content, so clicking "execute" on the dashboard produced
    # nothing a viewer could actually see.
    result = execute_tool("send_reminder", "inv-1", "INV-1000", 500_000_00)
    assert result.success is True
    assert result.tool_name == "template.send_reminder"
    assert result.response["delivered"] is False
    assert result.response["channel"] == "email"
    assert "INV-1000" in result.response["subject"]
    assert "₹5,00,000" in result.response["body"]


def test_message_actions_draft_real_content_not_a_bare_flag():
    for action in ("schedule_call", "offer_payment_plan", "escalate_to_am"):
        result = execute_tool(action, "inv-1", "INV-1000", 500_000_00)
        assert result.success is True
        assert result.tool_name == f"template.{action}"
        assert result.response["delivered"] is False
        assert "INV-1000" in result.response["subject"]
        assert result.response["body"]  # non-empty real content, not a stub


def test_customer_name_and_email_reach_the_drafted_message():
    # Found live: execute_tool never received customer_name/customer_email
    # at all, so every drafted message had no recipient -- an
    # invoice-recovery email addressed to nobody isn't credible proof of
    # anything on a demo screen.
    result = execute_tool(
        "send_reminder", "inv-1", "INV-1000", 500_000_00,
        customer_name="Acme Textiles Pvt Ltd", customer_email="ap@acmetextiles.example",
    )
    assert result.response["to"] == "ap@acmetextiles.example"
    assert result.response["to_name"] == "Acme Textiles Pvt Ltd"
    assert "Acme Textiles Pvt Ltd" in result.response["body"]


def test_missing_customer_is_shown_honestly_not_silently():
    result = execute_tool("send_reminder", "inv-1", "INV-1000", 500_000_00)
    assert result.response["to"] is None
    assert result.response["to_name"] is None


def test_policy_outcome_terminals_are_recorded_not_drafted():
    # route_to_dispute etc. are internal queue entries, not customer-facing
    # messages — nothing to draft, unlike the actions above.
    result = execute_tool("route_to_dispute", "inv-1", "INV-1000", 500_000_00)
    assert result.success is True
    assert result.tool_name == "internal.route_to_dispute"
    assert result.response == {"recorded": True}


def test_razorpay_chaos_switch_degrades_gracefully():
    set_razorpay_down(True)
    assert is_razorpay_down() is True
    result = execute_tool("resend_payment_link", "inv-1", "INV-1000", 500_000_00)
    assert result.success is False
    assert result.tool_name == "razorpay.create_payment_link"
    assert "error" in result.response


def test_razorpay_success_path_with_mocked_client():
    """Live network calls belong outside the fast test suite — already
    proven separately (a real test-mode payment link was created live,
    plink_TWR8Y8WeMFwpxV, before any of this wrapper code existed). This
    test proves the wrapper's own plumbing: request shape in, response
    shape out.
    """
    fake_response = {
        "id": "plink_fake123",
        "short_url": "https://rzp.io/i/fake",
        "amount": 500_000_00,
        "status": "created",
    }
    with patch("app.tools.registry.create_payment_link", return_value=fake_response) as mock_create:
        result = execute_tool("send_upi_payment_link", "inv-1", "INV-1000", 500_000_00)
    mock_create.assert_called_once()
    assert result.success is True
    assert result.response == fake_response


def test_razorpay_api_error_is_caught_not_raised():
    from app.tools.razorpay_client import RazorpayError

    with patch("app.tools.registry.create_payment_link", side_effect=RazorpayError("boom")):
        result = execute_tool("resend_payment_link", "inv-1", "INV-1000", 500_000_00)
    assert result.success is False
    assert "boom" in result.response["error"]
