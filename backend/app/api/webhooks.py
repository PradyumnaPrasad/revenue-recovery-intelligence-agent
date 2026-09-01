"""Razorpay webhook receiver — plan.md §6.9. Non-negotiable order: verify
the HMAC signature BEFORE parsing JSON at all, reject with 400 on
mismatch, and never trust anything in the body until the signature has
been checked using a constant-time comparison.

Verified against Razorpay's own docs (razorpay.com/docs/webhooks/validate-
test/), not assumed: the signature header is `X-Razorpay-Signature`,
computed as HMAC-SHA256 over the raw request body using the webhook secret
as key; the deduplication key for retried deliveries is the
`x-razorpay-event-id` HTTP header — NOT a field inside the JSON body, which
an earlier draft of this file assumed incorrectly before checking.
"""
from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.writer import write_audit_event
from app.db.models import Invoice, WebhookEvent
from app.db.session import get_session
from app.settings import get_settings

router = APIRouter(tags=["webhooks"])

HANDLED_EVENTS = {"payment_link.paid", "payment.captured", "payment.failed"}

# Events that actually update an invoice, not just get stored. Found live
# during a real end-to-end test (a genuine payment link, paid, webhook
# delivered through a cloudflared tunnel): HANDLED_EVENTS was returned in
# the response as "handled": true, but nothing downstream ever happened --
# Invoice.status never changed, no audit event was written. "Handled" was
# a lie. payment_link.paid is the one event that reliably carries the
# payment_link id needed to correlate back to an invoice at all
# (payment.captured alone does not, without also tracking order_id).
_INVOICE_CLOSING_EVENTS = {"payment_link.paid"}


def _verify_signature(body: bytes, signature: str, secret: str) -> bool:
    if not signature or not secret:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request, session: AsyncSession = Depends(get_session)):
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    event_id = request.headers.get("x-razorpay-event-id", "")
    settings = get_settings()

    # Verify BEFORE parsing JSON — an unverified body is never trusted
    # enough to even deserialize, let alone act on.
    if not _verify_signature(body, signature, settings.razorpay_webhook_secret):
        raise HTTPException(status_code=400, detail="invalid webhook signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="malformed JSON body")

    event_type = payload.get("event", "unknown")

    if not event_id:
        # Razorpay always sends this header on real deliveries; a request
        # with a valid signature but no event id is unusual enough to
        # reject rather than silently dedup on an empty key.
        raise HTTPException(status_code=400, detail="missing x-razorpay-event-id header")

    existing_stmt = select(WebhookEvent).where(WebhookEvent.event_id == event_id)
    existing = (await session.execute(existing_stmt)).scalars().first()
    if existing is not None:
        return {"status": "duplicate", "event_id": event_id}

    from app.deps import get_clock

    clock = get_clock()
    now = clock.now()
    row = WebhookEvent(event_id=event_id, event_type=event_type, payload=payload, received_at=now)
    session.add(row)

    invoice_updated = False
    invoice_id: str | None = None
    if event_type in _INVOICE_CLOSING_EVENTS:
        plink_id = (
            payload.get("payload", {})
            .get("payment_link", {})
            .get("entity", {})
            .get("id")
        )
        if plink_id:
            invoice_stmt = select(Invoice).where(Invoice.razorpay_payment_link_id == plink_id)
            invoice = (await session.execute(invoice_stmt)).scalars().first()
            if invoice is not None:
                invoice.status = "paid"
                invoice_updated = True
                invoice_id = str(invoice.id)
                amount_paid = (
                    payload.get("payload", {})
                    .get("payment_link", {})
                    .get("entity", {})
                    .get("amount_paid")
                )
                await write_audit_event(
                    session=session,
                    clock=clock,
                    invoice_id=invoice.id,
                    kind="payment_received",
                    payload={
                        "event": event_type,
                        "payment_link_id": plink_id,
                        "amount_paid_paise": amount_paid,
                        "razorpay_event_id": event_id,
                    },
                    actor="razorpay_webhook",
                    idempotency_key=event_id,
                )
        # A closing event with no matching invoice (unknown plink_id, or
        # one this system never issued) is stored honestly as unmatched,
        # not silently dropped and not falsely reported as handled.

    await session.commit()

    return {
        "status": "received",
        "event_id": event_id,
        "handled": event_type in HANDLED_EVENTS,
        "invoice_updated": invoice_updated,
        "invoice_id": invoice_id,
    }
