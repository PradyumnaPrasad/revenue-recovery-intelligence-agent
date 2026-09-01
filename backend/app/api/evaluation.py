"""Live evaluation summary for the dashboard — plan.md §6.10. A fast,
single-seed recompute (not the full 10-seed evaluation report, which is
the authoritative number in reports/evaluation.md) so the dashboard can
render the three-arm comparison without a multi-second wait on every
page load.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.evaluation.metrics import compute_headline
from app.evaluation.simulate import simulate_portfolio
from app.simulation.environment import ENVIRONMENTS
from app.simulation.generator import generate_portfolio

router = APIRouter(tags=["evaluation"])


@router.get("/evaluation/summary")
async def evaluation_summary(seed: int = 42, size: int = 300, env: str = "E_train"):
    portfolio = generate_portfolio(size=size, seed=seed)
    outcomes = simulate_portfolio(portfolio, ENVIRONMENTS[env])
    h = compute_headline(outcomes)
    return {
        "env": env,
        "seed": seed,
        "size": size,
        "arms": {
            "agent": {
                "n": h.agent.n,
                "recovery_rate": h.agent.recovery_rate,
                "ci": h.agent.recovery_rate_ci,
            },
            "baseline": {
                "n": h.baseline.n,
                "recovery_rate": h.baseline.recovery_rate,
                "ci": h.baseline.recovery_rate_ci,
            },
            "holdout": {
                "n": h.holdout.n,
                "recovery_rate": h.holdout.recovery_rate,
                "ci": h.holdout.recovery_rate_ci,
            },
        },
        "incremental_recovery_rate": h.incremental_recovery_rate,
        "incremental_recovery_rate_ci": h.incremental_recovery_rate_ci,
        "incremental_recovery_paise": h.incremental_recovery_paise,
        "uplift_vs_baseline": h.uplift_vs_baseline,
        "suppression_precision": h.suppression_precision,
        # Portfolio ROI — plan.md's "wow factor" pass: judges remember one
        # number, not a chart. net_recovery_paise is the honest bottom
        # line: incremental recovery MINUS what it cost to go get it,
        # because the agent spends more per invoice than doing nothing (it
        # takes real actions with real cost_paise) — the claim is that the
        # incremental recovery still comfortably exceeds that spend, not
        # that the agent is cheaper than silence.
        "portfolio_value_paise": (
            h.agent.portfolio_value_paise + h.baseline.portfolio_value_paise + h.holdout.portfolio_value_paise
        ),
        "agent_recovered_paise": h.agent.recovered_paise,
        "holdout_recovered_paise": h.holdout.recovered_paise,
        "agent_action_cost_paise": h.agent.total_action_cost_paise,
        "net_recovery_paise": h.incremental_recovery_paise - h.agent.total_action_cost_paise,
        "cost_of_recovery_paise_per_100": h.cost_of_recovery_paise_per_100,
    }
