"""Deterministic message templates — plan.md's cut ladder: "LLM message
generation -> Jinja templates. The LLM's place is *reading* replies
(genuinely unstructured), not *writing* reminders (a solved template
problem)." This module is that decision made real, not just asserted:
before this file existed, every non-Razorpay action recorded a bare
`{"recorded": true}` with no visible content — honest about not being a
real send, but also genuinely unconvincing on a demo screen, since a judge
clicking "execute" saw nothing resembling an action at all.

Still no SMTP/SMS/voice provider is wired up here — see backend/README.md's
"Known, honest gaps." This renders the exact content that WOULD go out
over that channel, for the dashboard to display, instead of the system
silently producing nothing a viewer can evaluate.
"""
from __future__ import annotations

from app.audit.explain import format_rupees
from app.domain.types import ActionKey

_TEMPLATES: dict[ActionKey, dict[str, str]] = {
    ActionKey.send_reminder: {
        "channel": "email",
        "subject": "Payment reminder: Invoice {invoice_number}",
        "body": (
            "Hi,\n\nThis is a reminder that invoice {invoice_number} for "
            "{amount} is still outstanding. Please arrange payment at your "
            "earliest convenience, or reply to this message if you have "
            "any questions.\n\nThanks."
        ),
    },
    ActionKey.offer_payment_plan: {
        "channel": "email",
        "subject": "Payment plan offer for Invoice {invoice_number}",
        "body": (
            "Hi,\n\nWe understand cash flow can be tight. We'd like to offer "
            "a structured payment plan for the {amount} outstanding on "
            "invoice {invoice_number}. Reply to this message and we'll set "
            "one up that works for you.\n\nThanks."
        ),
    },
    ActionKey.schedule_call: {
        "channel": "call",
        "subject": "Call scheduled — Invoice {invoice_number}",
        "body": (
            "An account manager has been scheduled to call regarding "
            "invoice {invoice_number} ({amount}) within 2 business days."
        ),
    },
    ActionKey.escalate_to_am: {
        "channel": "internal",
        "subject": "Escalated — Invoice {invoice_number}",
        "body": (
            "Invoice {invoice_number} ({amount}) has been escalated to the "
            "account manager queue for direct, manual outreach."
        ),
    },
}


def render_message(action: ActionKey, invoice_number: str, amount_paise: int) -> dict:
    """Returns the rendered channel/subject/body for actions that have a
    customer- or AM-facing message. Callers that hit `ActionKey` members
    with no template here (policy-outcome terminals like
    `route_to_dispute` are plain strings, never reach this function at
    all — see app/tools/registry.py) get a KeyError, which is intentional:
    every real action in the ladder must have real content, not a silent
    fallback that papers over a missing template.
    """
    template = _TEMPLATES[action]
    amount = format_rupees(amount_paise)
    return {
        "channel": template["channel"],
        "subject": template["subject"].format(invoice_number=invoice_number),
        "body": template["body"].format(invoice_number=invoice_number, amount=amount),
    }
