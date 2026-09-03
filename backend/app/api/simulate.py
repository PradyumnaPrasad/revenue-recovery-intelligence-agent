"""The live orchestrator — plan.md always intended `/simulate/advance`
(see app/deps.py's docstring, app/domain/clock.py's VirtualClock), but it
was never actually wired up as a route. Found and built in response to
direct feedback: "I want an end-to-end agent, not just a human clicking
Execute per invoice." Right now that's exactly what the demo was — a
frozen clock, and every action requiring one person, one invoice, one
click.

This gives the loop an actual autonomous mode: advance the process clock,
then run diagnose -> rank -> govern -> execute across an entire portfolio
in one call, no human touching each invoice. It is NOT new decision
logic — `/simulate/tick` calls the exact same `_decide()` and
`_execute_decision()` functions `/evaluate` and `/act` already use, just
looped across many invoices instead of one. Policy still has the only say
over what executes: `block` and `require_approval` outcomes are counted
here, never auto-executed, exactly as they aren't via a manual `/act`
call — an autonomous agent is not the same thing as an ungoverned one.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.invoices import _decide, _execute_decision
from app.db.models import Invoice
from app.db.session import get_session
from app.deps import get_clock

router = APIRouter(tags=["simulate"])


@router.post("/simulate/advance")
async def advance_clock(days: float = 0, hours: float = 0):
    """Moves the process VirtualClock forward — the thing that was always
    supposed to exist so a demo could compress a multi-day recovery
    journey without waiting on real wall-clock time, per
    app/domain/clock.py's own docstring, but was never actually reachable
    over HTTP until now.
    """
    clock = get_clock()
    if not hasattr(clock, "advance"):
        # RealClock has no advance() by design — a genuine production
        # deployment's clock moves on its own and should never be pushed
        # forward by an API call. Fail loudly, not silently no-op.
        return {"error": "the active clock does not support advance() (RealClock is in use, not VirtualClock)"}
    new_now = clock.advance(days=days, hours=hours)
    return {"now": new_now.isoformat()}


@dataclass
class TickSummary:
    batch_id: str
    now: str
    evaluated: int = 0
    executed: int = 0
    idempotent_replay: int = 0
    blocked: int = 0
    require_approval: int = 0
    already_closed: int = 0
    executed_actions: list = field(default_factory=list)


@router.post("/simulate/tick")
async def tick(batch_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> dict:
    """Runs the full 8-step loop autonomously across every open invoice in
    a batch — this is what makes it an agent that runs, not a form a
    human fills in once per invoice. `require_approval` outcomes are
    tallied but never auto-executed: the whole point of that policy
    outcome is that a human decides, not the tick.
    """
    clock = get_clock()
    now = clock.now()

    stmt = select(Invoice).where(Invoice.batch_id == batch_id)
    invoices = (await session.execute(stmt)).scalars().all()

    summary = TickSummary(batch_id=str(batch_id), now=now.isoformat())
    for invoice in invoices:
        if invoice.status == "paid":
            summary.already_closed += 1
            continue
        summary.evaluated += 1
        decision = await _decide(session, invoice, now)
        result = await _execute_decision(session, invoice, decision, now, clock)

        if result["outcome"] == "blocked":
            summary.blocked += 1
        elif result["outcome"] == "requires_approval":
            summary.require_approval += 1
        elif result["outcome"] == "idempotent_replay":
            summary.idempotent_replay += 1
        elif result["outcome"] == "executed":
            summary.executed += 1
            summary.executed_actions.append(
                {
                    "invoice_id": str(invoice.id),
                    "invoice_number": invoice.invoice_number,
                    "action": result["action"],
                    "state": result["state"],
                }
            )

    return asdict(summary)
