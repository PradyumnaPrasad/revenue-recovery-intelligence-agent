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

from app.db.models import WebhookEvent
from app.db.session import get_session
from app.settings import get_settings

router = APIRouter(tags=["webhooks"])

HANDLED_EVENTS = {"payment_link.paid", "payment.captured", "payment.failed"}


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
    row = WebhookEvent(
        event_id=event_id, event_type=event_type, payload=payload, received_at=clock.now()
    )
    session.add(row)
    await session.commit()

    return {"status": "received", "event_id": event_id, "handled": event_type in HANDLED_EVENTS}
