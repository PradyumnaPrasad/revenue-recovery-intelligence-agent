"""app/tools/email_client.py -- real SMTP sending, built live in response
to "make it real." Every generated customer email is fictitious, so a
real send always redirects to demo_recipient_email -- these tests guard
that redirect happening correctly and every failure mode degrading
honestly instead of crashing.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.settings import Settings
from app.tools.email_client import is_configured, send_email, set_email_down


def teardown_function():
    set_email_down(False)


_CONFIGURED = Settings(
    smtp_host="smtp.gmail.com",
    smtp_port=587,
    smtp_username="operator@example.com",
    smtp_password="an-app-password",
    demo_recipient_email="operator@example.com",
)
# Explicit empty strings, not Settings() with no args -- found live the
# moment real SMTP credentials were added to .env: pydantic-settings
# reads the real environment by default, so a bare Settings() picked up
# the now-real SMTP_USERNAME/PASSWORD/DEMO_RECIPIENT_EMAIL instead of
# being blank, and this "unconfigured" fixture silently stopped being
# unconfigured. Explicit kwargs override the environment, so this stays
# genuinely blank regardless of what's actually configured on the host.
_UNCONFIGURED = Settings(smtp_username="", smtp_password="", demo_recipient_email="")


def test_is_configured_requires_all_three_fields():
    with patch("app.tools.email_client.get_settings", return_value=_UNCONFIGURED):
        assert is_configured() is False
    with patch("app.tools.email_client.get_settings", return_value=_CONFIGURED):
        assert is_configured() is True


def test_missing_config_fails_honestly_not_silently():
    with patch("app.tools.email_client.get_settings", return_value=_UNCONFIGURED):
        result = send_email("subject", "body", "fake@customer.example", "Fake Customer")
    assert result["delivered"] is False
    assert "not configured" in result["error"]


def test_send_redirects_to_demo_recipient_not_the_fake_customer_address():
    # The whole point: every generated customer email is fictitious, so
    # nothing should ever actually be sent there.
    mock_server = MagicMock()
    with patch("app.tools.email_client.get_settings", return_value=_CONFIGURED), \
         patch("smtplib.SMTP") as mock_smtp:
        mock_smtp.return_value.__enter__.return_value = mock_server
        result = send_email("Subject", "Body", "fake@customer.example", "Fake Customer")

    assert result["delivered"] is True
    assert result["to"] == "operator@example.com"
    mock_server.sendmail.assert_called_once()
    sent_to = mock_server.sendmail.call_args[0][1]
    assert sent_to == ["operator@example.com"]
    assert "fake@customer.example" not in sent_to


def test_send_discloses_the_redirect_inside_the_body():
    import email

    mock_server = MagicMock()
    with patch("app.tools.email_client.get_settings", return_value=_CONFIGURED), \
         patch("smtplib.SMTP") as mock_smtp:
        mock_smtp.return_value.__enter__.return_value = mock_server
        send_email("Subject", "Body", "fake@customer.example", "Fake Customer")

    # MIMEText base64-encodes the body, so the raw sendmail() string won't
    # contain it in plain text -- decode the actual MIME message the same
    # way a real mail client would before checking what it says.
    sent_message = mock_server.sendmail.call_args[0][2]
    decoded_body = email.message_from_string(sent_message).get_payload(decode=True).decode()
    assert "fake@customer.example" in decoded_body  # disclosed, not hidden
    assert "fictitious" in decoded_body


def test_chaos_switch_blocks_sending_without_touching_smtp():
    set_email_down(True)
    with patch("app.tools.email_client.get_settings", return_value=_CONFIGURED), \
         patch("smtplib.SMTP") as mock_smtp:
        result = send_email("Subject", "Body", "fake@customer.example", "Fake Customer")
    mock_smtp.assert_not_called()
    assert result["delivered"] is False
    assert "chaos switch" in result["error"]


def test_smtp_exception_is_caught_not_raised():
    import smtplib

    with patch("app.tools.email_client.get_settings", return_value=_CONFIGURED), \
         patch("smtplib.SMTP", side_effect=smtplib.SMTPAuthenticationError(535, b"bad creds")):
        result = send_email("Subject", "Body", "fake@customer.example", "Fake Customer")
    assert result["delivered"] is False
    assert "SMTP error" in result["error"]
