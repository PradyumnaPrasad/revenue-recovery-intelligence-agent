"""plan.md §6.9 'Done when' (the parts testable without live network):
internal-record tools always succeed and record correctly, and the
razorpay chaos switch degrades gracefully instead of raising.
"""
from __future__ import annotations

from unittest.mock import patch

from app.tools.registry import execute_tool, is_razorpay_down, set_razorpay_down


def teardown_function():
    set_razorpay_down(False)


def test_send_reminder_uses_console_sink():
    result = execute_tool("send_reminder", "inv-1", "INV-1000", 500_000_00)
    assert result.success is True
    assert result.tool_name == "console.send_reminder"


def test_internal_actions_are_recorded_not_called_externally():
    for action in ("schedule_call", "offer_payment_plan", "escalate_to_am", "route_to_dispute"):
        result = execute_tool(action, "inv-1", "INV-1000", 500_000_00)
        assert result.success is True
        assert result.tool_name == f"internal.{action}"
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
