"""Persists a GeneratedPortfolio (pure dataclasses) into Postgres, and emits
one `invoice_ingested` audit event per invoice — the first link in each
invoice's hash chain.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.writer import write_audit_event
from app.db.models import (
    ArmAssignment,
    Batch,
    Customer,
    CustomerHistory,
    Invoice,
    PromiseToPay,
    ReplyFixture,
)
from app.domain.clock import Clock
from app.simulation.generator import GeneratedPortfolio


async def persist_portfolio(
    session: AsyncSession, clock: Clock, portfolio: GeneratedPortfolio
) -> Batch:
    batch = Batch(
        id=portfolio.batch_id,
        seed=portfolio.seed,
        size=portfolio.size,
        created_at=clock.now(),
    )
    session.add(batch)

    for inv in portfolio.invoices:
        c = inv.customer
        customer_row = Customer(
            id=c.id,
            name=c.name,
            email=c.email,
            industry=c.industry,
            segment=c.segment,
            relationship_tier=c.relationship_tier,
            timezone=c.timezone,
            suppressed=False,
            created_at=clock.now(),
        )
        session.add(customer_row)
        session.add(
            CustomerHistory(
                customer_id=c.id,
                prior_invoice_count=c.prior_invoice_count,
                prior_late_rate=c.prior_late_rate,
                prior_broken_promises=c.prior_broken_promises,
                avg_days_to_pay=c.avg_days_to_pay,
                contact_count_30d=c.contact_count_30d,
                last_contacted_at=None,
            )
        )

        invoice_row = Invoice(
            id=inv.id,
            batch_id=batch.id,
            customer_id=c.id,
            invoice_number=inv.invoice_number,
            amount_paise=inv.amount_paise,
            issued_at=inv.issued_at,
            due_date=inv.due_date,
            status="overdue",
            dispute_flag=inv.dispute_flag,
            payment_link_sent=inv.payment_link_sent,
            payment_link_opened=inv.payment_link_opened,
            created_at=clock.now(),
        )
        session.add(invoice_row)

        # Explicit flush before any FK-dependent row. ArmAssignment,
        # PromiseToPay, ReplyFixture and AuditEvent all reference
        # invoices.id by a raw ForeignKey column with no ORM relationship()
        # linking the classes — so SQLAlchemy's unit-of-work has no edge to
        # infer that Invoice must be inserted first, and batches per-table
        # inserts in an order that can (and did, at 500 rows) violate the
        # FK constraint. Flushing here makes the ordering explicit rather
        # than relying on unit-of-work's dependency inference.
        await session.flush()

        session.add(
            ArmAssignment(
                invoice_id=inv.id,
                arm=inv.arm,
                assigned_at=clock.now(),
                assignment_hash=inv.assignment_hash,
            )
        )

        for p in inv.promises:
            session.add(
                PromiseToPay(
                    id=p.id,
                    invoice_id=inv.id,
                    promised_date=p.promised_date,
                    promised_amount_paise=p.promised_amount_paise,
                    source="simulator",
                    state="kept" if p.kept else "open",
                    created_at=clock.now(),
                )
            )

        for r in inv.replies:
            session.add(
                ReplyFixture(
                    id=r.id,
                    invoice_id=inv.id,
                    intent_label=r.intent_label,
                    text=r.text,
                    created_at=clock.now(),
                )
            )

        await write_audit_event(
            session=session,
            clock=clock,
            invoice_id=inv.id,
            kind="invoice_ingested",
            payload={
                "invoice_number": inv.invoice_number,
                "amount_paise": inv.amount_paise,
                "days_overdue": inv.days_overdue,
                "arm": inv.arm,
                "batch_id": str(batch.id),
            },
            idempotency_key=f"{inv.id}:invoice_ingested",
        )

    await session.commit()
    return batch
