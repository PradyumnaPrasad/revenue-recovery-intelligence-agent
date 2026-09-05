from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.invoices import OPEN_STATUS
from app.db.models import Action, ActionState, ArmAssignment, Batch, Invoice
from app.db.session import get_session
from app.deps import get_clock
from app.domain.clock import Clock
from app.settings import get_settings
from app.simulation.generator import generate_portfolio
from app.simulation.persist import persist_portfolio

router = APIRouter(tags=["batches"])


@router.post("/batches")
async def create_batch(
    size: int = 250,
    seed: int = 42,
    live_dated: bool = False,
    session: AsyncSession = Depends(get_session),
    clock: Clock = Depends(get_clock),
):
    # Reproducibility (plan.md F5): passing clock.now() unconditionally here
    # was the actual break — generate_portfolio()'s ANCHOR default only
    # helps callers that don't override it. Seed alone must determine every
    # field, including due_date/issued_at, so `now` is omitted by default
    # and generate_portfolio falls back to its fixed ANCHOR. `live_dated=true`
    # is an explicit opt-in for a portfolio dated off today's wall clock,
    # for anyone who wants "overdue as of right now" rather than "the
    # reproducible reference portfolio".
    now = clock.now() if live_dated else None
    portfolio = generate_portfolio(size=size, seed=seed, now=now)
    batch = await persist_portfolio(session, clock, portfolio)
    return {"batch_id": str(batch.id), "seed": seed, "size": size, "live_dated": live_dated}


@router.get("/batches")
async def list_batches(session: AsyncSession = Depends(get_session)):
    stmt = select(Batch).order_by(Batch.created_at.desc()).limit(20)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {"batch_id": str(r.id), "seed": r.seed, "size": r.size, "created_at": r.created_at.isoformat()}
        for r in rows
    ]


@router.get("/batches/{batch_id}/summary")
async def batch_summary(
    batch_id: uuid.UUID, session: AsyncSession = Depends(get_session), clock: Clock = Depends(get_clock)
):
    total_stmt = select(func.count(Invoice.id), func.coalesce(func.sum(Invoice.amount_paise), 0)).where(
        Invoice.batch_id == batch_id
    )
    total_count, total_amount = (await session.execute(total_stmt)).one()

    # Found live, reported directly: "why the top bar not changing... same
    # amount." Because it wasn't excluding anything -- this summed EVERY
    # invoice regardless of status, so a real payment or a manual resolve
    # (F24) could never move this number. "At risk" now means what it
    # says: only invoices still OPEN_STATUS.
    open_stmt = select(func.count(Invoice.id), func.coalesce(func.sum(Invoice.amount_paise), 0)).where(
        Invoice.batch_id == batch_id, Invoice.status == OPEN_STATUS
    )
    open_count, open_amount = (await session.execute(open_stmt)).one()
    closed_amount = int(total_amount) - int(open_amount)

    dispute_stmt = select(func.count(Invoice.id)).where(
        Invoice.batch_id == batch_id, Invoice.dispute_flag.is_(True)
    )
    dispute_count = (await session.execute(dispute_stmt)).scalar_one()

    arm_stmt = (
        select(ArmAssignment.arm, func.count(ArmAssignment.invoice_id))
        .join(Invoice, Invoice.id == ArmAssignment.invoice_id)
        .where(Invoice.batch_id == batch_id)
        .group_by(ArmAssignment.arm)
    )
    arm_rows = (await session.execute(arm_stmt)).all()

    # Found live, reported directly: "actions today 0/120... what does it
    # mean." It meant nothing -- the dashboard variable behind this was
    # declared and never incremented, a dead stub. This counts real
    # executed Action rows, on the simulated clock's current date, for
    # invoices in this batch -- an actual number, not a permanent zero.
    today = clock.now().date()
    actions_today_stmt = (
        select(func.count(Action.id))
        .join(Invoice, Invoice.id == Action.invoice_id)
        .where(
            Invoice.batch_id == batch_id,
            Action.state == ActionState.executed,
            func.date(Action.executed_at) == today,
        )
    )
    actions_today_count = (await session.execute(actions_today_stmt)).scalar_one()

    return {
        "batch_id": str(batch_id),
        "invoice_count": total_count,
        "open_invoice_count": open_count,
        "closed_invoice_count": total_count - open_count,
        "revenue_at_risk_paise": int(open_amount),
        "revenue_resolved_paise": closed_amount,
        "dispute_count": dispute_count,
        "dispute_rate": round(dispute_count / total_count, 4) if total_count else 0.0,
        "arms": {arm.value if hasattr(arm, "value") else arm: n for arm, n in arm_rows},
        "actions_today": actions_today_count,
        "daily_action_budget": get_settings().daily_action_budget,
    }
