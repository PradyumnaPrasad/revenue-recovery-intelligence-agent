"""SQLAlchemy models — Milestone 0 subset.

Only tables needed for: portfolio generation, ordered diagnosis, arm
assignment, promise-to-pay, and the hash-chained audit ledger. Later
milestones (risk_events, predictions, decisions, actions, outcomes,
inbound_messages, llm_cache) are added in M1-M6 without touching these.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Arm is defined once, in the pure domain layer (app/domain/types.py), and
# imported here rather than redefined — app/evaluation/arms.py (deterministic
# hash-based assignment) needs it too and must not import SQLAlchemy to get
# it. Keeping ORM code as the *consumer* of domain types, never the other
# way round, is what lets app/domain/ stay testable with zero DB dependency.
from app.domain.types import Arm  # noqa: F401  (re-exported for callers of this module)


class Base(DeclarativeBase):
    pass


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Segment(str, enum.Enum):
    smb = "smb"
    mid_market = "mid_market"
    enterprise = "enterprise"


class PromiseState(str, enum.Enum):
    open = "open"
    kept = "kept"
    broken = "broken"


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[uuid.UUID] = uuid_pk()
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(200), nullable=False)
    industry: Mapped[str] = mapped_column(String(50), nullable=False)
    segment: Mapped[Segment] = mapped_column(Enum(Segment), nullable=False)
    relationship_tier: Mapped[str] = mapped_column(String(20), nullable=False, default="standard")
    timezone: Mapped[str] = mapped_column(String(40), nullable=False, default="Asia/Kolkata")
    suppressed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    history: Mapped["CustomerHistory"] = relationship(back_populates="customer", uselist=False)


class CustomerHistory(Base):
    __tablename__ = "customer_history"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), primary_key=True
    )
    prior_invoice_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prior_late_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    prior_broken_promises: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_days_to_pay: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    contact_count_30d: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer: Mapped["Customer"] = relationship(back_populates="history")


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = uuid_pk()
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("batches.id"), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="overdue")
    dispute_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    payment_link_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    payment_link_opened: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    razorpay_invoice_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    razorpay_payment_link_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    customer: Mapped["Customer"] = relationship()


class ArmAssignment(Base):
    __tablename__ = "arm_assignments"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), primary_key=True
    )
    arm: Mapped[Arm] = mapped_column(Enum(Arm), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    assignment_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class PromiseToPay(Base):
    __tablename__ = "promises_to_pay"

    id: Mapped[uuid.UUID] = uuid_pk()
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False)
    promised_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    promised_amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="simulator")
    state: Mapped[PromiseState] = mapped_column(Enum(PromiseState), nullable=False, default=PromiseState.open)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReplyFixture(Base):
    """Pre-generated inbound reply text attached to an invoice at generation time.

    Not the live inbound-message pipeline (that's M6's `inbound_messages`) —
    this is the synthetic corpus Layer 1 produces so M6 has fuel to extract from.
    """

    __tablename__ = "reply_fixtures"

    id: Mapped[uuid.UUID] = uuid_pk()
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False)
    intent_label: Mapped[str] = mapped_column(String(30), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditEvent(Base):
    """Hash-chained audit ledger. One chain per invoice (prev_hash links to the
    invoice's previous event, not globally) — see app/audit/chain.py.
    """

    __tablename__ = "audit_events"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_audit_idempotency_key"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    # Found live during a real end-to-end webhook test: this project's
    # simulated/demo clock stamps every event with the SAME created_at
    # (e.g. every audit row shows "2026-01-01 09:00:00+00" regardless of
    # when it was actually written), and `id` is a random UUID with zero
    # correlation to insertion order. _tip_hash() and verify_chain()
    # relied on `ORDER BY created_at DESC` alone with no tiebreaker, which
    # is genuinely ambiguous once an invoice has 2+ prior events under a
    # frozen clock — Postgres can return either row for a tie. A real
    # payment webhook wrote a `payment_received` event whose prev_hash
    # ended up pointing at `invoice_ingested`'s hash instead of
    # `action_executed`'s, and /audit/verify correctly caught it:
    # `intact: false`. `seq` is a genuine, monotonically increasing
    # identity column — independent of both the UUID and the clock — so
    # chain order is never ambiguous again, regardless of how many events
    # share a timestamp.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), unique=True, nullable=False)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    actor: Mapped[str] = mapped_column(String(50), nullable=False, default="system")
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    policy_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ActionState(str, enum.Enum):
    pending = "pending"
    executed = "executed"
    failed = "failed"
    cancelled = "cancelled"


class Action(Base):
    """One row per executed (or attempted) action — plan.md §6.9. The
    UNIQUE constraint on idempotency_key IS the idempotency guarantee: a
    second insert with the same key fails at the database level, and the
    API layer catches that and returns the original stored result instead
    of re-executing (see app/tools/registry.py). policy_version is baked
    into the key generation upstream, not stored redundantly here.
    """

    __tablename__ = "actions"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_action_idempotency_key"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False)
    action_key: Mapped[str] = mapped_column(String(40), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[ActionState] = mapped_column(Enum(ActionState), nullable=False, default=ActionState.pending)
    tool_name: Mapped[str] = mapped_column(String(40), nullable=False)
    request: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    response: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    cost_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WebhookEvent(Base):
    """Dedup ledger for inbound Razorpay webhooks — plan.md §6.9. Razorpay
    retries webhook delivery; storing event_id with a UNIQUE constraint is
    what makes 'same event.id twice -> one outcome row' true at the
    database level, not just by convention in application code.
    """

    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("event_id", name="uq_webhook_event_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    event_id: Mapped[str] = mapped_column(String(80), nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
