"""plan.md §6.11 'Done when': make evaluate regenerates from seeds, arm
assignment is stable, every metric carries a CI. These tests exercise the
simulation and metrics modules directly (report.py's file-writing is
covered by actually running it — see reports/evaluation.md).
"""
from __future__ import annotations

import numpy as np

from app.domain.types import ActionKey
from app.evaluation.metrics import bootstrap_mean_ci, compute_headline
from app.evaluation.simulate import simulate_invoice, simulate_portfolio
from app.simulation.environment import env_train
from app.simulation.generator import generate_portfolio


def test_bootstrap_ci_brackets_the_mean():
    values = [1.0] * 60 + [0.0] * 40  # true mean 0.6
    mean, lo, hi = bootstrap_mean_ci(values, n_resamples=500, seed=1)
    assert abs(mean - 0.6) < 1e-9
    assert lo <= mean <= hi


def test_bootstrap_ci_widens_with_fewer_samples():
    rng = np.random.default_rng(0)
    big = list(rng.random(2000) < 0.4)
    small = big[:30]
    _, lo_big, hi_big = bootstrap_mean_ci([float(v) for v in big], seed=1)
    _, lo_small, hi_small = bootstrap_mean_ci([float(v) for v in small], seed=1)
    assert (hi_small - lo_small) > (hi_big - lo_big)


def test_bootstrap_ci_empty_input_does_not_crash():
    mean, lo, hi = bootstrap_mean_ci([])
    assert (mean, lo, hi) == (0.0, 0.0, 0.0)


def test_holdout_outcome_takes_no_action():
    env = env_train()
    portfolio = generate_portfolio(size=200, seed=42)
    rng = np.random.default_rng(1)
    holdout_invoices = [inv for inv in portfolio.invoices if inv.arm == "holdout"]
    assert holdout_invoices, "fixture assumption: seed 42 produces at least one holdout invoice"
    for inv in holdout_invoices[:20]:
        outcome = simulate_invoice(rng, inv, env)
        assert outcome.arm == "holdout"
        assert outcome.action_taken is None
        assert outcome.action_cost_paise == 0


def test_agent_and_baseline_take_at_least_one_action_on_most_invoices():
    """Sanity, not a hard guarantee: policy can legitimately block every
    touchpoint (e.g. an already-suppressed or capped customer), but that
    should be rare across a real portfolio, not the norm.
    """
    env = env_train()
    portfolio = generate_portfolio(size=300, seed=42)
    rng = np.random.default_rng(2)
    contacted = 0
    total = 0
    for inv in portfolio.invoices:
        if inv.arm not in ("agent", "baseline"):
            continue
        outcome = simulate_invoice(rng, inv, env)
        total += 1
        if outcome.action_taken is not None or outcome.recovered:
            contacted += 1
    assert contacted / total > 0.7


def test_chronic_invoices_get_escalated_by_the_agent():
    """Regression test for the specific policy behaviour (P08) the
    evaluation report's cost narrative depends on being true.
    """
    from app.domain.diagnosis import diagnose
    from app.evaluation.simulate import _facts_from_generated

    env = env_train()
    portfolio = generate_portfolio(size=2000, seed=42)
    rng = np.random.default_rng(3)
    chronic_invoices = [
        inv for inv in portfolio.invoices
        if inv.arm == "agent" and diagnose(_facts_from_generated(inv)).code.value == "chronic_non_payment"
    ]
    assert len(chronic_invoices) > 5
    escalated_or_called = 0
    for inv in chronic_invoices:
        outcome = simulate_invoice(rng, inv, env)
        if outcome.action_taken in (ActionKey.escalate_to_am.value, "schedule_call"):
            escalated_or_called += 1
    assert escalated_or_called / len(chronic_invoices) > 0.5


def test_simulation_is_reproducible_given_same_seed():
    env = env_train()
    p1 = generate_portfolio(size=200, seed=42)
    p2 = generate_portfolio(size=200, seed=42)
    out1 = simulate_portfolio(p1, env)
    out2 = simulate_portfolio(p2, env)
    recovered1 = [o.recovered for o in out1]
    recovered2 = [o.recovered for o in out2]
    assert recovered1 == recovered2


def test_compute_headline_produces_a_ci_on_every_arm_and_the_incremental_number():
    env = env_train()
    portfolio = generate_portfolio(size=500, seed=42)
    outcomes = simulate_portfolio(portfolio, env)
    headline = compute_headline(outcomes)

    for arm_metrics in (headline.agent, headline.baseline, headline.holdout):
        lo, hi = arm_metrics.recovery_rate_ci
        assert lo <= arm_metrics.recovery_rate <= hi

    lo, hi = headline.incremental_recovery_rate_ci
    assert lo <= hi
    # Holdout should recover meaningfully less than a contacted arm — this
    # is the whole reason the holdout exists (plan.md F2).
    assert headline.holdout.recovery_rate < headline.agent.recovery_rate
    assert headline.holdout.recovery_rate < headline.baseline.recovery_rate


def test_incremental_recovery_paise_is_positive_and_plausible():
    env = env_train()
    portfolio = generate_portfolio(size=500, seed=42)
    outcomes = simulate_portfolio(portfolio, env)
    headline = compute_headline(outcomes)
    total_value = sum(o.amount_paise for o in outcomes)
    assert 0 < headline.incremental_recovery_paise < total_value
