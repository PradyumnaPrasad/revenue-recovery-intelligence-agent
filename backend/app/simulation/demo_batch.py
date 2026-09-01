"""The curated demo batch — plan.md §6.1, Edit 3.

The 500-invoice random batch (seed=42, size=500) is what gets *measured*.
This smaller batch is what gets *filmed*: a fixed seed and size chosen so
every one of the six diagnosis codes appears at least once, so the video can
show a real example of each without hunting through a large batch or
cherry-picking by hand.

Run via `make seed-demo`. Persisted with the same /batches machinery, just a
distinct (seed, size) pair — `demo_curated` in the batch's `notes` field is
what marks it as the filming batch rather than the measurement batch.
"""
from __future__ import annotations

import asyncio

from app.domain.diagnosis import diagnose
from app.domain.types import DiagnosisCode, InvoiceFacts
from app.simulation.generator import generate_portfolio

# Deliberately NOT 42 — that's the standard measurement batch's seed
# (app/simulation/seed.py), and customer/invoice IDs are deterministic from
# (seed, index) alone, independent of `size`. Reusing 42 here would collide
# on the first 40 rows the moment both batches exist in the same database,
# since size doesn't factor into ID derivation.
DEMO_SEED = 7
DEMO_SIZE = 40


def _facts(inv) -> InvoiceFacts:
    c = inv.customer
    return InvoiceFacts(
        invoice_id=str(inv.id),
        amount_paise=inv.amount_paise,
        days_overdue=inv.days_overdue,
        dispute_flag=inv.dispute_flag,
        prior_late_payment_rate=c.prior_late_rate,
        prior_broken_promises=c.prior_broken_promises,
        prior_invoice_count=c.prior_invoice_count,
        contact_count_30d=c.contact_count_30d,
        payment_link_sent=inv.payment_link_sent,
        payment_link_opened=inv.payment_link_opened,
        has_open_dispute_reply=False,
    )


def assert_covers_all_diagnoses(seed: int = DEMO_SEED, size: int = DEMO_SIZE) -> None:
    """Fails loudly if a future generator or diagnosis change breaks the one
    invariant this batch exists to guarantee. Called by both the persist
    script below and tests/unit/test_demo_batch.py.
    """
    portfolio = generate_portfolio(size=size, seed=seed)
    seen = {diagnose(_facts(inv)).code for inv in portfolio.invoices}
    missing = set(DiagnosisCode) - seen
    if missing:
        raise AssertionError(
            f"Curated demo batch (seed={seed}, size={size}) is missing "
            f"diagnoses: {sorted(m.value for m in missing)}. Pick a "
            f"different DEMO_SEED — see the sweep in plan.md §6.1."
        )


async def _main() -> None:
    # Imported lazily so `assert_covers_all_diagnoses()` — and the test that
    # calls it — never needs a database or even sqlalchemy installed; it's
    # pure generator + pure diagnosis, same as the rest of app/simulation's
    # testable-in-milliseconds design.
    from app.db.session import SessionLocal
    from app.deps import get_clock
    from app.simulation.persist import persist_portfolio

    assert_covers_all_diagnoses()
    clock = get_clock()
    portfolio = generate_portfolio(size=DEMO_SIZE, seed=DEMO_SEED)
    async with SessionLocal() as session:
        batch = await persist_portfolio(session, clock, portfolio)
    print(
        f"Curated demo batch: batch_id={batch.id} seed={DEMO_SEED} "
        f"size={DEMO_SIZE} — all six diagnoses present."
    )


if __name__ == "__main__":
    asyncio.run(_main())
