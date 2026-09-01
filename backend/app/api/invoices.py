from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.explain import build_explanation, narrate_audit_event
from app.audit.writer import verify_invoice_chain, write_audit_event
from app.db.models import (
    Action,
    ActionState,
    AuditEvent,
    Customer,
    CustomerHistory,
    Invoice,
    PromiseState,
    PromiseToPay,
)
from app.db.session import get_session
from app.domain.diagnosis import diagnose
from app.domain.policy.engine import evaluate as evaluate_policy
from app.domain.policy.engine import load_policy
from app.domain.policy.types import BatchContext, CustomerContext, DiagnosisContext, InvoiceContext, PolicyContext
from app.domain.ranking import ActionHistoryEntry, load_action_config, rank_actions
from app.domain.types import ActionKey, InvoiceFacts
from app.ml import priors
from app.settings import get_settings
from app.tools.registry import execute_tool

router = APIRouter(tags=["invoices"])

_POLICY = load_policy()
_ACTION_CONFIG = load_action_config()


async def _load_invoice(session: AsyncSession, invoice_id: uuid.UUID) -> Invoice:
    invoice = await session.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="invoice not found")
    return invoice


def _days_overdue(invoice: Invoice, now) -> int:
    delta = now - invoice.due_date
    return max(0, delta.days)


async def _facts_for(session: AsyncSession, invoice: Invoice, now) -> InvoiceFacts:
    history = await session.get(CustomerHistory, invoice.customer_id)
    return InvoiceFacts(
        invoice_id=str(invoice.id),
        amount_paise=invoice.amount_paise,
        days_overdue=_days_overdue(invoice, now),
        dispute_flag=invoice.dispute_flag,
        prior_late_payment_rate=history.prior_late_rate if history else 0.0,
        prior_broken_promises=history.prior_broken_promises if history else 0,
        prior_invoice_count=history.prior_invoice_count if history else 0,
        contact_count_30d=history.contact_count_30d if history else 0,
        payment_link_sent=invoice.payment_link_sent,
        payment_link_opened=invoice.payment_link_opened,
        has_open_dispute_reply=False,
    )


@router.get("/invoices")
async def list_invoices(batch_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    stmt = select(Invoice).where(Invoice.batch_id == batch_id)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(r.id),
            "invoice_number": r.invoice_number,
            "amount_paise": r.amount_paise,
            "due_date": r.due_date.isoformat(),
            "dispute_flag": r.dispute_flag,
            "status": r.status,
        }
        for r in rows
    ]


@router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    invoice = await _load_invoice(session, invoice_id)
    return {
        "id": str(invoice.id),
        "invoice_number": invoice.invoice_number,
        "amount_paise": invoice.amount_paise,
        "due_date": invoice.due_date.isoformat(),
        "issued_at": invoice.issued_at.isoformat(),
        "dispute_flag": invoice.dispute_flag,
        "status": invoice.status,
        "payment_link_sent": invoice.payment_link_sent,
        "payment_link_opened": invoice.payment_link_opened,
    }


@router.get("/invoices/{invoice_id}/diagnosis")
async def get_diagnosis(invoice_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    from app.deps import get_clock

    invoice = await _load_invoice(session, invoice_id)
    clock = get_clock()
    facts = await _facts_for(session, invoice, clock.now())
    diagnosis = diagnose(facts)
    return diagnosis.model_dump()


@dataclass
class _Decision:
    facts: InvoiceFacts
    diagnosis: object
    ranked: list
    top: object
    policy_result: object


async def _decide(session: AsyncSession, invoice: Invoice, now) -> _Decision:
    """Diagnose -> predict -> rank -> govern — the shared core of both
    /evaluate (read-only) and /act (executes). One code path computes the
    decision; only /act's caller decides whether to act on it, so
    evaluating and acting can never silently share a side effect.
    """
    facts = await _facts_for(session, invoice, now)
    diagnosis = diagnose(facts)

    # Real action history, not history=[] — a gap found live: an earlier
    # version hardcoded an empty history on every call, so the escalation
    # ladder's cooldown/rung constraints could never actually apply even
    # after a real action had been executed on this invoice moments
    # earlier. days_ago is computed from each action's real executed_at,
    # not assumed.
    executed_stmt = select(Action).where(
        Action.invoice_id == invoice.id, Action.state == ActionState.executed
    )
    executed_rows = (await session.execute(executed_stmt)).scalars().all()
    history = [
        ActionHistoryEntry(
            action=ActionKey(row.action_key),
            days_ago=(now - row.executed_at).days,
        )
        for row in executed_rows
        if row.action_key in {a.value for a in ActionKey}  # skip policy-outcome terminals
    ]

    predictions = priors.predict(diagnosis.code)
    ranked = rank_actions(facts, predictions, _ACTION_CONFIG, history=history)
    top = next((r for r in ranked if r.ladder_eligible), ranked[0])

    customer = await session.get(Customer, invoice.customer_id)
    open_promise_stmt = select(PromiseToPay).where(
        PromiseToPay.invoice_id == invoice.id, PromiseToPay.state == PromiseState.open
    )
    open_promise = (await session.execute(open_promise_stmt)).scalars().first()
    promise_still_open = bool(open_promise and open_promise.promised_date >= now.date())

    settings = get_settings()
    policy_context = PolicyContext(
        diagnosis=DiagnosisContext(
            code=diagnosis.code.value, confidence=diagnosis.confidence, produced_by=diagnosis.produced_by
        ),
        customer=CustomerContext(
            suppressed=customer.suppressed if customer else False,
            contact_count_30d=facts.contact_count_30d,
        ),
        invoice=InvoiceContext(
            amount_paise=facts.amount_paise,
            has_open_promise=open_promise is not None,
            promise_still_open=promise_still_open,
        ),
        # actions_today is a known simplification: live daily-action tracking
        # is D4/orchestrator scope (scheduled_actions + the tick), not yet
        # built. Defaulting to 0 means P09 never fires from this endpoint
        # today — stated here rather than silently wrong.
        batch=BatchContext(actions_today=0, action_budget=settings.daily_action_budget),
    )
    policy_result = evaluate_policy(_POLICY, policy_context, top.action)
    return _Decision(facts=facts, diagnosis=diagnosis, ranked=ranked, top=top, policy_result=policy_result)


@router.post("/invoices/{invoice_id}/evaluate")
async def evaluate_invoice(invoice_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    """Diagnose + rank + govern, no execution — plan.md §7. This is the
    core decision loop (steps 2-5 of the eight-step cycle) with nothing
    that touches money: safe to call as often as you like, on any invoice,
    at any time. Execution (step 6) is a separate, explicit endpoint on
    purpose — evaluating and acting are two different levels of
    consequence and must never share a code path.
    """
    from app.deps import get_clock

    invoice = await _load_invoice(session, invoice_id)
    clock = get_clock()
    now = clock.now()
    decision = await _decide(session, invoice, now)
    facts, diagnosis, ranked, top, policy_result = (
        decision.facts, decision.diagnosis, decision.ranked, decision.top, decision.policy_result
    )

    explanation = build_explanation(
        invoice_number=invoice.invoice_number,
        amount_paise=invoice.amount_paise,
        days_overdue=facts.days_overdue,
        diagnosis=diagnosis,
        ranked=ranked,
        policy=policy_result,
        model_version=priors.MODEL_VERSION,
    )
    return explanation


@router.post("/invoices/{invoice_id}/act")
async def act_on_invoice(invoice_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    """Execute the policy-approved action — plan.md §7/§6.9. Re-runs the
    same decision as /evaluate (never trusts a client-supplied action —
    the server decides what "the recommended action" is, every time), then
    executes it exactly once per idempotency key. Idempotent by
    construction: a UNIQUE constraint on Action.idempotency_key means a
    replayed call with the same key returns the ORIGINAL stored result
    instead of a second real Razorpay call or a second internal record.
    """
    from app.deps import get_clock

    invoice = await _load_invoice(session, invoice_id)
    clock = get_clock()
    now = clock.now()
    decision = await _decide(session, invoice, now)
    top, policy_result = decision.top, decision.policy_result

    if policy_result.outcome == "block":
        raise HTTPException(
            status_code=409, detail={"blocked": True, "reasons": [r.reason for r in policy_result.reasons]}
        )
    if policy_result.outcome == "require_approval":
        raise HTTPException(
            status_code=403,
            detail={
                "requires_approval": True,
                "action": top.action.value,
                "reasons": [r.reason for r in policy_result.reasons],
            },
        )

    if policy_result.outcome == "substitute":
        sub = policy_result.substituted_action
        action_to_execute = sub if sub is not None else top.action.value
    else:  # allow
        action_to_execute = top.action.value

    # A successfully EXECUTED action for this (invoice, action_key) is
    # final — return it unconditionally on any later call, never
    # re-execute. Bug found live, not by review: an earlier version
    # computed attempt_no as "count of all existing rows," which
    # increments on every call including successful ones, so every repeat
    # call produced a NEW idempotency key and genuinely re-executed —
    # exactly the double-send this mechanism exists to prevent. Two
    # payment links were created for one /act call before this was caught.
    # attempt_no now counts only FAILED prior attempts, so a retry only
    # produces a new key when the previous one actually failed (matching
    # the state machine: failed -> retry, executed -> terminal).
    already_executed_stmt = select(Action).where(
        Action.invoice_id == invoice_id,
        Action.action_key == action_to_execute,
        Action.state == ActionState.executed,
    )
    already_executed = (await session.execute(already_executed_stmt)).scalars().first()
    if already_executed is not None:
        return {
            "idempotent_replay": True,
            "action": already_executed.action_key,
            "state": already_executed.state.value,
            "response": already_executed.response,
        }

    attempt_stmt = select(func.count(Action.id)).where(
        Action.invoice_id == invoice_id,
        Action.action_key == action_to_execute,
        Action.state == ActionState.failed,
    )
    attempt_no = (await session.execute(attempt_stmt)).scalar_one()
    idempotency_key = hashlib.sha256(
        f"{invoice_id}:{action_to_execute}:{attempt_no}:{policy_result.policy_version}".encode()
    ).hexdigest()

    existing_stmt = select(Action).where(Action.idempotency_key == idempotency_key)
    existing = (await session.execute(existing_stmt)).scalars().first()
    if existing is not None:
        return {
            "idempotent_replay": True,
            "action": existing.action_key,
            "state": existing.state.value,
            "response": existing.response,
        }

    tool_result = execute_tool(action_to_execute, str(invoice_id), invoice.invoice_number, invoice.amount_paise)
    cost_paise = 0
    if action_to_execute in {a.value for a in ActionKey}:
        cost_paise = _ACTION_CONFIG.actions[ActionKey(action_to_execute)].cost_paise

    action_row = Action(
        invoice_id=invoice_id,
        action_key=action_to_execute,
        idempotency_key=idempotency_key,
        state=ActionState.executed if tool_result.success else ActionState.failed,
        tool_name=tool_result.tool_name,
        request=tool_result.request,
        response=tool_result.response,
        cost_paise=cost_paise,
        created_at=now,
        executed_at=now,
    )
    session.add(action_row)
    await write_audit_event(
        session=session,
        clock=clock,
        invoice_id=invoice_id,
        kind="action_executed" if tool_result.success else "action_failed",
        payload={
            "action": action_to_execute,
            "tool_name": tool_result.tool_name,
            "success": tool_result.success,
            "response": tool_result.response,
        },
        policy_version=policy_result.policy_version,
        idempotency_key=idempotency_key,
    )
    await session.commit()

    return {
        "idempotent_replay": False,
        "action": action_to_execute,
        "state": action_row.state.value,
        "tool_name": tool_result.tool_name,
        "response": tool_result.response,
    }


@router.get("/invoices/{invoice_id}/audit")
async def get_audit(invoice_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.invoice_id == invoice_id)
        .order_by(AuditEvent.created_at.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(r.id),
            "kind": r.kind,
            "actor": r.actor,
            "payload": r.payload,
            "prev_hash": r.prev_hash,
            "hash": r.hash,
            "created_at": r.created_at.isoformat(),
            "narrative": narrate_audit_event(r.kind, r.payload or {}),
        }
        for r in rows
    ]


@router.get("/invoices/{invoice_id}/audit/verify")
async def verify_audit(invoice_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    intact, checked = await verify_invoice_chain(session, invoice_id)
    return {"invoice_id": str(invoice_id), "intact": intact, "events_checked": checked}
