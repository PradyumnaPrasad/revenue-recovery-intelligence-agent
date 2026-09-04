"""Real SMTP sending — built live in response to "make it real." Every
generated customer email is fictitious (fake names at fake domains,
nobody there to receive anything), so every real send is deliberately
redirected to `settings.demo_recipient_email` (the operator's own inbox)
regardless of which customer the message is nominally for. The drafted
subject/body still say who it was "for" — the redirect is disclosed in
the email body itself, not hidden.

Mirrors app/tools/razorpay_client.py's shape on purpose: a plain
`smtplib` call, no SDK, caught exceptions turned into a typed error, no
raising past this module. If SMTP isn't configured (blank credentials),
`is_configured()` says so and callers fall back to drafted-not-sent
instead of crashing — the same graceful-degradation posture the chaos
switch already has for Razorpay and the LLM.
"""
from __future__ import annotations

import smtplib
from email.mime.text import MIMEText

from app.settings import get_settings

_email_down = False


def set_email_down(down: bool) -> None:
    """The email half of the chaos switch, mirroring
    set_razorpay_down()/set_llm_down() — a real chaos demo should be able
    to kill this channel independently too."""
    global _email_down
    _email_down = down


def is_email_down() -> bool:
    return _email_down


def is_configured() -> bool:
    settings = get_settings()
    return bool(settings.smtp_username and settings.smtp_password and settings.demo_recipient_email)


def send_email(subject: str, body: str, nominal_recipient: str | None, nominal_name: str | None) -> dict:
    """Sends a real email via SMTP, redirected to demo_recipient_email.
    Returns {"delivered": True, "to": <actual address>, ...} on success,
    or {"delivered": False, "error": ...} — never raises.
    """
    settings = get_settings()
    if is_email_down():
        return {"delivered": False, "error": "chaos switch: email marked down"}
    if not is_configured():
        return {"delivered": False, "error": "SMTP not configured (SMTP_USERNAME/PASSWORD/DEMO_RECIPIENT_EMAIL blank)"}

    disclosed_body = (
        f"{body}\n\n---\n"
        f"[This demo redirects every drafted message to the operator's own inbox — "
        f"the customer's real address on file was {nominal_recipient or 'none'} "
        f"({nominal_name or 'unknown customer'}), which is a fictitious address generated "
        f"for this demo, not a real recipient.]"
    )
    msg = MIMEText(disclosed_body)
    msg["Subject"] = subject
    msg["From"] = settings.smtp_username
    msg["To"] = settings.demo_recipient_email

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            server.starttls()
            server.login(settings.smtp_username, settings.smtp_password)
            server.sendmail(settings.smtp_username, [settings.demo_recipient_email], msg.as_string())
        return {"delivered": True, "to": settings.demo_recipient_email}
    except smtplib.SMTPException as e:
        return {"delivered": False, "error": f"SMTP error: {e}"}
    except OSError as e:
        return {"delivered": False, "error": f"SMTP connection failed: {e}"}
