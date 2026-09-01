"""Correlated synthetic portfolio generator — plan.md §6.1.

The generative model is DECLARED, not incidental (see docs/generative_model.md
for the exact structural equations this code implements). Determinism is the
whole point: same seed -> byte-identical rows, always, so `/batches` results
are reproducible and the evaluation harness in later milestones can be
trusted.

This module is I/O-light on purpose: `generate_portfolio()` is a pure
function returning plain dataclasses (no ORM, no DB session), so it can be
unit-tested without a database. Persisting the result is a separate step
(`persist_portfolio`) so the pure generation logic stays testable in
milliseconds.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np
from faker import Faker

from app.evaluation.arms import assign_arm
from app.simulation.reply_templates import TEMPLATE_BANK, TARGET_DISTRIBUTION

SEGMENTS = ["smb", "mid_market", "enterprise"]
SEGMENT_WEIGHTS = [0.55, 0.32, 0.13]

INDUSTRIES = ["saas", "manufacturing", "logistics", "healthcare", "retail", "education"]
INDUSTRY_WEIGHTS = [0.22, 0.20, 0.16, 0.14, 0.18, 0.10]

# Beta(a, b) params for prior_late_payment_rate, by segment — enterprise
# customers pay more reliably on average (tighter procurement processes) but
# with a longer tail than SMB.
_LATE_RATE_BETA = {
    "smb": (2.0, 4.0),
    "mid_market": (1.6, 5.0),
    "enterprise": (1.2, 7.0),
}

# LogNormal(mu, sigma) for invoice amount in paise, by segment.
_AMOUNT_LOGNORMAL = {
    "smb": (10.9, 0.55),          # median ~ Rs 54k
    "mid_market": (12.4, 0.65),   # median ~ Rs 2.4L
    "enterprise": (14.2, 0.75),   # median ~ Rs 14.8L
}

# Base dispute probability by industry; healthcare and manufacturing dispute
# more often (billing-code / PO-mismatch friction) than saas/retail. Scaled
# by _DISPUTE_SCALE below (plan.md F4): the unscaled rates gave a measured
# 7.2% disputed against a real B2B rate of 2-5%.
_DISPUTE_BASE = {
    "saas": 0.04,
    "manufacturing": 0.10,
    "logistics": 0.07,
    "healthcare": 0.12,
    "retail": 0.05,
    "education": 0.06,
}
_DISPUTE_SCALE = 0.55

_HIGH_VALUE_PAISE = 500_000 * 100  # Rs 5,00,000

# Fixed reference instant for portfolio generation (plan.md §6.1, F5 fix).
# Seed alone must determine every field, including due_date/issued_at — a
# wall-clock default silently broke that guarantee (same seed twice, called a
# few seconds apart, produced different timestamps even though
# portfolio_fingerprint() matched, because the fingerprint deliberately
# excludes timestamps). Callers that want a live-dated portfolio pass
# `now=clock.now()` explicitly.
ANCHOR = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)

# Gamma(shape, scale) baseline for days_overdue, modulated by late_rate.
_DAYS_OVERDUE_SHAPE_BASE = 1.6
_DAYS_OVERDUE_SCALE_BASE = {"smb": 10.0, "mid_market": 14.0, "enterprise": 18.0}


@dataclass
class GeneratedCustomer:
    id: uuid.UUID
    name: str
    email: str
    industry: str
    segment: str
    relationship_tier: str
    timezone: str
    prior_invoice_count: int
    prior_late_rate: float
    prior_broken_promises: int
    avg_days_to_pay: float
    contact_count_30d: int


@dataclass
class GeneratedPromise:
    id: uuid.UUID
    invoice_id: uuid.UUID
    promised_date: datetime
    promised_amount_paise: int
    kept: bool


@dataclass
class GeneratedReply:
    id: uuid.UUID
    invoice_id: uuid.UUID
    intent_label: str
    text: str


@dataclass
class GeneratedInvoice:
    id: uuid.UUID
    customer: GeneratedCustomer
    invoice_number: str
    amount_paise: int
    issued_at: datetime
    due_date: datetime
    days_overdue: int
    dispute_flag: bool
    payment_link_sent: bool
    payment_link_opened: bool
    arm: str
    assignment_hash: str
    promises: list[GeneratedPromise] = field(default_factory=list)
    replies: list[GeneratedReply] = field(default_factory=list)


@dataclass
class GeneratedPortfolio:
    batch_id: uuid.UUID
    seed: int
    size: int
    generated_at: datetime
    invoices: list[GeneratedInvoice]


def _clip(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return np.clip(x, lo, hi)


def generate_portfolio(size: int, seed: int, now: datetime | None = None) -> GeneratedPortfolio:
    rng = np.random.default_rng(seed)
    fake = Faker()
    Faker.seed(seed)
    now = now if now is not None else ANCHOR

    batch_id = uuid.uuid5(uuid.NAMESPACE_URL, f"rria-batch-{seed}-{size}")

    segments = rng.choice(SEGMENTS, size=size, p=SEGMENT_WEIGHTS)
    industries = rng.choice(INDUSTRIES, size=size, p=INDUSTRY_WEIGHTS)

    invoices: list[GeneratedInvoice] = []

    for i in range(size):
        segment = str(segments[i])
        industry = str(industries[i])

        a, b = _LATE_RATE_BETA[segment]
        late_rate = float(_clip(rng.beta(a, b, size=1), 0.0, 0.95)[0])

        broken_promises = int(rng.poisson(lam=max(0.05, 0.3 + 4.5 * late_rate)))
        broken_promises = min(broken_promises, 8)

        # F8 fix: _AMOUNT_LOGNORMAL's (mu, sigma) were tuned so the raw draw
        # represents RUPEES (exp(10.9)~54,176 documented as "median ~Rs 54k"
        # above) — the missing *100 meant every invoice amount was stored
        # ~100x too small. This was silent and structural: no invoice in a
        # 500-batch ever exceeded ~Rs 1L, meaning P06's Rs 5,00,000
        # approval-gate could never fire and every "revenue at risk" figure
        # was off by two orders of magnitude. Caught by noticing a live
        # /evaluate response's amounts looked too small, then confirming
        # the segment medians against the documented DGP, not by code
        # review alone.
        mu, sigma = _AMOUNT_LOGNORMAL[segment]
        amount_rupees = rng.lognormal(mu, sigma, size=1)
        amount_paise = int(_clip(amount_rupees * 100, 5_000_00, 5_000_000_00)[0])

        dispute_p = _DISPUTE_BASE[industry] * _DISPUTE_SCALE + (
            0.02 if amount_paise > _HIGH_VALUE_PAISE else 0.0
        )
        dispute_flag = bool(rng.random() < dispute_p)

        shape = _DAYS_OVERDUE_SHAPE_BASE + 2.0 * late_rate
        scale = _DAYS_OVERDUE_SCALE_BASE[segment]
        days_overdue = int(_clip(rng.gamma(shape, scale, size=1), 1, 180)[0])

        prior_invoice_count = int(_clip(rng.poisson(lam=8 + 6 * (segment != "smb")), 0, 60))
        avg_days_to_pay = float(max(0.0, 10 + 25 * late_rate + rng.normal(0, 5)))
        contact_count_30d = int(min(4, rng.poisson(lam=0.6 + 1.5 * late_rate)))

        # IDs are derived deterministically from (seed, index), NOT uuid4().
        # This matters: assign_arm() hashes the invoice_id to pick agent /
        # baseline / holdout, so a random UUID here would make arm
        # assignment (and therefore the whole portfolio fingerprint)
        # non-reproducible across two runs of the same seed — silently
        # breaking the exact guarantee this generator exists to provide.
        customer_id = uuid.uuid5(uuid.NAMESPACE_URL, f"rria-customer-{seed}-{i}")
        invoice_id = uuid.uuid5(uuid.NAMESPACE_URL, f"rria-invoice-{seed}-{i}")

        customer = GeneratedCustomer(
            id=customer_id,
            name=fake.company(),
            email=fake.company_email(),
            industry=industry,
            segment=segment,
            relationship_tier="strategic" if segment == "enterprise" and rng.random() < 0.3 else "standard",
            timezone="Asia/Kolkata",
            prior_invoice_count=prior_invoice_count,
            prior_late_rate=round(late_rate, 4),
            prior_broken_promises=broken_promises,
            avg_days_to_pay=round(avg_days_to_pay, 1),
            contact_count_30d=contact_count_30d,
        )

        due_date = now - timedelta(days=days_overdue)
        issued_at = due_date - timedelta(days=30)

        payment_link_sent = bool(rng.random() < 0.6)
        payment_link_opened = bool(payment_link_sent and rng.random() < (0.55 - 0.3 * late_rate))

        arm, ahash = assign_arm(str(invoice_id))

        invoice = GeneratedInvoice(
            id=invoice_id,
            customer=customer,
            invoice_number=f"INV-{1000 + i}",
            amount_paise=amount_paise,
            issued_at=issued_at,
            due_date=due_date,
            days_overdue=days_overdue,
            dispute_flag=dispute_flag,
            payment_link_sent=payment_link_sent,
            payment_link_opened=payment_link_opened,
            arm=arm.value,
            assignment_hash=ahash,
        )

        # Promise-to-pay: probability of having made one rises with late_rate;
        # kept-probability falls with broken_promises history (both kept=True
        # and kept=False examples are generated deliberately — plan.md §6.1).
        if rng.random() < min(0.5, 0.15 + 0.5 * late_rate):
            promised_date = now + timedelta(days=int(rng.integers(2, 21)))
            kept_p = max(0.1, 0.75 - 0.12 * broken_promises)
            kept = bool(rng.random() < kept_p)
            invoice.promises.append(
                GeneratedPromise(
                    id=uuid.uuid5(uuid.NAMESPACE_URL, f"rria-promise-{seed}-{i}"),
                    invoice_id=invoice_id,
                    promised_date=promised_date,
                    promised_amount_paise=amount_paise,
                    kept=kept,
                )
            )

        # Reply corpus: 0-3 replies per invoice, sampled straight from the
        # declared target distribution (plan.md F4: a dispute_flag-based x4
        # reweighting used to sit here, which is what pushed the measured
        # disputed share to 19.7% against a real B2B rate of 2-5%). Replies
        # are generated but deliberately UNREAD at this stage — diagnosis
        # never looks at reply content directly; only the M6 extraction
        # layer reading a reply can set has_open_dispute_reply, which is why
        # generate_labeled_dataset() must not derive it from this corpus
        # (see app/simulation/training_data.py).
        n_replies = int(rng.choice([0, 1, 1, 2, 3], p=[0.30, 0.35, 0.15, 0.13, 0.07]))
        labels = list(TARGET_DISTRIBUTION.keys())
        weights = np.array(list(TARGET_DISTRIBUTION.values()), dtype=float)
        weights = weights / weights.sum()
        for _ in range(n_replies):
            label = str(rng.choice(labels, p=weights))
            template = str(rng.choice(TEMPLATE_BANK[label]))
            text = template.format(
                date=(now + timedelta(days=int(rng.integers(2, 21)))).strftime("%d %b"),
                amount=f"Rs {amount_paise // 100:,}",
                other_ref=f"INV-{rng.integers(1000, 1999)}",
            )
            invoice.replies.append(
                GeneratedReply(
                    id=uuid.uuid5(uuid.NAMESPACE_URL, f"rria-reply-{seed}-{i}-{len(invoice.replies)}"),
                    invoice_id=invoice_id,
                    intent_label=label,
                    text=text,
                )
            )

        invoices.append(invoice)

    return GeneratedPortfolio(batch_id=batch_id, seed=seed, size=size, generated_at=now, invoices=invoices)


def portfolio_fingerprint(portfolio: GeneratedPortfolio) -> str:
    """Stable hash of the generated content (not the random UUIDs) — used by
    the reproducibility test to assert two runs with the same seed produce
    byte-identical *business* data.
    """
    import hashlib
    import json

    rows = []
    for inv in sorted(portfolio.invoices, key=lambda x: x.invoice_number):
        rows.append(
            {
                "invoice_number": inv.invoice_number,
                "amount_paise": inv.amount_paise,
                "days_overdue": inv.days_overdue,
                "dispute_flag": inv.dispute_flag,
                "segment": inv.customer.segment,
                "industry": inv.customer.industry,
                "late_rate": inv.customer.prior_late_rate,
                "broken_promises": inv.customer.prior_broken_promises,
                "arm": inv.arm,
            }
        )
    return hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()
