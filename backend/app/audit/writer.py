"""Persists ChainableEvents as AuditEvent rows, looking up each invoice's
current chain tip so the hash chain is continuous per invoice.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.chain import GENESIS_HASH, next_event
from app.db.models import AuditEvent
from app.domain.clock import Clock


async def _tip_hash(session: AsyncSession, invoice_id: uuid.UUID | None) -> str:
    if invoice_id is None:
        return GENESIS_HASH
    # Ordered by `seq`, not `created_at` — found live (see AuditEvent.seq's
    # docstring): under this project's frozen demo clock, multiple events
    # on the same invoice can share an identical created_at, making
    # "the most recent event" genuinely ambiguous to Postgres. `seq` is a
    # real monotonic identity column, so the tip is always unambiguous.
    stmt = (
        select(AuditEvent.hash)
        .where(AuditEvent.invoice_id == invoice_id)
        .order_by(AuditEvent.seq.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    return row or GENESIS_HASH


async def write_audit_event(
    session: AsyncSession,
    clock: Clock,
    invoice_id: uuid.UUID | None,
    kind: str,
    payload: dict[str, Any],
    actor: str = "system",
    policy_version: str | None = None,
    idempotency_key: str | None = None,
) -> AuditEvent:
    prev_hash = await _tip_hash(session, invoice_id)
    now = clock.now()
    event = next_event(
        prev_hash=prev_hash,
        kind=kind,
        payload=payload,
        created_at=now,
        actor=actor,
        policy_version=policy_version,
        idempotency_key=idempotency_key,
    )
    row = AuditEvent(
        invoice_id=invoice_id,
        kind=event.kind,
        actor=event.actor,
        payload=event.payload,
        policy_version=event.policy_version,
        idempotency_key=event.idempotency_key,
        prev_hash=event.prev_hash,
        hash=event.hash,
        created_at=event.created_at,
    )
    session.add(row)
    await session.flush()
    return row


async def verify_invoice_chain(session: AsyncSession, invoice_id: uuid.UUID) -> tuple[bool, int]:
    from app.audit.chain import verify_chain

    # seq, not created_at, for the same reason as _tip_hash above — the
    # chain was actually built in seq order, so verification must walk it
    # in that same order, not one that ties can scramble.
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.invoice_id == invoice_id)
        .order_by(AuditEvent.seq.asc())
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()
    events = [
        {"prev_hash": r.prev_hash, "hash": r.hash, "payload": r.payload} for r in rows
    ]
    return verify_chain(events)
