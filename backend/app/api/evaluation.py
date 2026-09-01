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
    }
