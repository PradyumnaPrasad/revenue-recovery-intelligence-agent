from app.simulation.generator import generate_portfolio, portfolio_fingerprint
from app.simulation.reply_templates import TARGET_DISTRIBUTION


def test_same_seed_is_byte_identical():
    p1 = generate_portfolio(size=200, seed=42)
    p2 = generate_portfolio(size=200, seed=42)
    assert portfolio_fingerprint(p1) == portfolio_fingerprint(p2)


def test_different_seed_differs():
    p1 = generate_portfolio(size=200, seed=42)
    p2 = generate_portfolio(size=200, seed=43)
    assert portfolio_fingerprint(p1) != portfolio_fingerprint(p2)


def test_late_rate_correlates_with_broken_promises():
    p = generate_portfolio(size=2000, seed=7)
    late_rates = [inv.customer.prior_late_rate for inv in p.invoices]
    broken = [inv.customer.prior_broken_promises for inv in p.invoices]
    import numpy as np

    corr = float(np.corrcoef(late_rates, broken)[0, 1])
    assert corr > 0.4, f"expected corr>0.4, got {corr}"


def test_healthcare_disputes_more_than_saas():
    p = generate_portfolio(size=3000, seed=11)
    by_industry: dict[str, list[bool]] = {}
    for inv in p.invoices:
        by_industry.setdefault(inv.customer.industry, []).append(inv.dispute_flag)
    healthcare_rate = sum(by_industry["healthcare"]) / len(by_industry["healthcare"])
    saas_rate = sum(by_industry["saas"]) / len(by_industry["saas"])
    assert healthcare_rate > saas_rate


def test_every_invoice_has_at_least_one_reply_or_generator_allows_zero():
    # Not every invoice needs a reply, but across a large batch every intent
    # class in the target distribution should appear.
    p = generate_portfolio(size=1500, seed=99)
    seen_labels = {r.intent_label for inv in p.invoices for r in inv.replies}
    assert seen_labels == set(TARGET_DISTRIBUTION.keys())


def test_arm_assignment_roughly_matches_target_split():
    p = generate_portfolio(size=3000, seed=5)
    arms = [inv.arm for inv in p.invoices]
    agent_share = arms.count("agent") / len(arms)
    holdout_share = arms.count("holdout") / len(arms)
    assert 0.65 <= agent_share <= 0.75
    assert 0.07 <= holdout_share <= 0.13


def test_amount_medians_match_the_declared_dgp():
    """Regression test for a real bug (found live, not by code review): the
    LogNormal (mu, sigma) parameters were tuned assuming the raw draw
    represents RUPEES (docs/generative_model.md documents smb's median as
    "~Rs 54k"), but the code stored that raw number directly as PAISE with
    no x100 conversion — every invoice amount was ~100x too small. No
    invoice in a 500-batch ever exceeded ~Rs 1L, so P06's Rs 5,00,000
    approval gate could never fire, and every 'revenue at risk' figure in
    the demo would have been off by two orders of magnitude.
    """
    p = generate_portfolio(size=2000, seed=42)
    by_segment: dict[str, list[int]] = {}
    for inv in p.invoices:
        by_segment.setdefault(inv.customer.segment, []).append(inv.amount_paise)

    import statistics

    # Declared medians (docs/generative_model.md): smb ~Rs 54k, mid_market
    # ~Rs 2.4L, enterprise ~Rs 14.8L. Checked within a wide band (lognormal
    # medians drift with sample composition) — the point of this test is
    # to catch a 100x-class error, not to pin the exact figure.
    expectations = {
        "smb": (30_000_00, 100_000_00),
        "mid_market": (120_000_00, 450_000_00),
        "enterprise": (700_000_00, 2_500_000_00),
    }
    for segment, (lo, hi) in expectations.items():
        median = statistics.median(by_segment[segment])
        assert lo <= median <= hi, (
            f"{segment}: median amount_paise={median} outside [{lo}, {hi}] "
            f"(Rs {median/100:,.0f}) — check for a units/scale regression"
        )

    # At least some invoices should exceed the Rs 5,00,000 policy threshold
    # (P06) — with the bug, this was always zero.
    over_5l = sum(1 for inv in p.invoices if inv.amount_paise > 50_000_000)
    assert over_5l > 0, "no invoice exceeds Rs 5,00,000 — P06 could never fire"
