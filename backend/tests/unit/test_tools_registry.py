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


def test_message_action_artifacts_flow_through_execute_tool():
    # Found live, called out directly: "if we click for
    # offer_payment_plan, there is no plan, just an email drafted."
    # execute_tool's response is what the API and the dashboard actually
    # see -- the artifact must survive the trip from render_message()
    # through here, not just exist inside templates.py's own tests.
    plan_result = execute_tool("offer_payment_plan", "inv-1", "INV-1000", 500_000_00)
    assert "plan" in plan_result.response
    assert len(plan_result.response["plan"]) == 3

    call_result = execute_tool("schedule_call", "inv-1", "INV-1000", 500_000_00)
    assert "scheduled_for" in call_result.response

    escalate_result = execute_tool("escalate_to_am", "inv-1", "INV-1000", 500_000_00)
    assert "assigned_to" in escalate_result.response
    assert "respond_by" in escalate_result.response


def test_deliver_false_never_attempts_a_real_send_even_if_configured():
    # The safety guard behind real SMTP: /simulate/tick calls execute_tool
    # with deliver defaulting to False specifically so an autonomous batch
    # run across hundreds of invoices can never flood a real inbox.
    with patch("app.tools.registry.email_is_configured", return_value=True), \
         patch("app.tools.registry.send_email") as mock_send:
        result = execute_tool("send_reminder", "inv-1", "INV-1000", 500_000_00, deliver=False)
    mock_send.assert_not_called()
    assert result.response["delivered"] is False


def test_deliver_true_sends_for_real_when_configured():
    # /act passes deliver=True -- a human explicitly asked for this one
    # action, right now.
    with patch("app.tools.registry.email_is_configured", return_value=True), \
         patch("app.tools.registry.send_email", return_value={"delivered": True, "to": "me@example.com"}) as mock_send:
        result = execute_tool("send_reminder", "inv-1", "INV-1000", 500_000_00, deliver=True)
    mock_send.assert_called_once()
    assert result.response["delivered"] is True
    assert result.response["actually_sent_to"] == "me@example.com"


def test_deliver_true_but_unconfigured_stays_a_draft():
    with patch("app.tools.registry.email_is_configured", return_value=False), \
         patch("app.tools.registry.send_email") as mock_send:
        result = execute_tool("send_reminder", "inv-1", "INV-1000", 500_000_00, deliver=True)
    mock_send.assert_not_called()
    assert result.response["delivered"] is False


def test_deliver_true_but_send_failure_stays_honestly_undelivered():
    with patch("app.tools.registry.email_is_configured", return_value=True), \
         patch("app.tools.registry.send_email", return_value={"delivered": False, "error": "SMTP error: boom"}):
        result = execute_tool("send_reminder", "inv-1", "INV-1000", 500_000_00, deliver=True)
    assert result.response["delivered"] is False
    assert "boom" in result.response["note"]


def test_deliver_true_only_applies_to_email_channel_actions():
    # schedule_call's channel is "call" and escalate_to_am's is "internal"
    # -- there's no telephony integration to gate, so deliver=True must
    # not attempt to email either of them.
    with patch("app.tools.registry.email_is_configured", return_value=True), \
         patch("app.tools.registry.send_email") as mock_send:
        execute_tool("schedule_call", "inv-1", "INV-1000", 500_000_00, deliver=True)
        execute_tool("escalate_to_am", "inv-1", "INV-1000", 500_000_00, deliver=True)
    mock_send.assert_not_called()


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
