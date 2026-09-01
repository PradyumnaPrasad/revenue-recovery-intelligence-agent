"""Bootstrap confidence intervals and the headline metrics — plan.md §6.11.
A number without a CI is an anecdote, not a measurement.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.evaluation.simulate import InvoiceOutcome


def bootstrap_mean_ci(
    values: list[float], n_resamples: int = 1000, ci: float = 0.95, seed: int = 42
) -> tuple[float, float, float]:
    """Returns (mean, lower, upper) via a straightforward percentile
    bootstrap. Deterministic given `seed` — re-running the report produces
    the same interval, not a new random one each time.
    """
    arr = np.array(values, dtype=float)
    if len(arr) == 0:
        return (0.0, 0.0, 0.0)
    rng = np.random.default_rng(seed)
    n = len(arr)
    resample_means = np.array(
        [rng.choice(arr, size=n, replace=True).mean() for _ in range(n_resamples)]
    )
    lower_pct = (1 - ci) / 2 * 100
    upper_pct = (1 + ci) / 2 * 100
    return (
        float(arr.mean()),
        float(np.percentile(resample_means, lower_pct)),
        float(np.percentile(resample_means, upper_pct)),
    )


@dataclass
class ArmMetrics:
    arm: str
    n: int
    recovery_rate: float
    recovery_rate_ci: tuple[float, float]
    portfolio_value_paise: int
    recovered_paise: int
    total_action_cost_paise: int
    contacts_per_recovery: float


def arm_metrics(outcomes: list[InvoiceOutcome], arm: str) -> ArmMetrics:
    subset = [o for o in outcomes if o.arm == arm]
    n = len(subset)
    recovered_flags = [1.0 if o.recovered else 0.0 for o in subset]
    mean, lo, hi = bootstrap_mean_ci(recovered_flags)
    total_recovered_paise = sum(o.recovered_paise for o in subset)
    total_value_paise = sum(o.amount_paise for o in subset)
    total_cost_paise = sum(o.action_cost_paise for o in subset)
    n_recovered = sum(1 for o in subset if o.recovered)
    n_contacted = sum(1 for o in subset if o.action_taken is not None)
    contacts_per_recovery = (n_contacted / n_recovered) if n_recovered else float("nan")

    return ArmMetrics(
        arm=arm,
        n=n,
        recovery_rate=mean,
        recovery_rate_ci=(lo, hi),
        portfolio_value_paise=total_value_paise,
        recovered_paise=total_recovered_paise,
        total_action_cost_paise=total_cost_paise,
        contacts_per_recovery=contacts_per_recovery,
    )


@dataclass
class HeadlineMetrics:
    agent: ArmMetrics
    baseline: ArmMetrics
    holdout: ArmMetrics
    incremental_recovery_paise: int
    incremental_recovery_rate: float
    incremental_recovery_rate_ci: tuple[float, float]
    uplift_vs_baseline: float
    cost_of_recovery_paise_per_100: float
    suppression_precision: float


def compute_headline(outcomes: list[InvoiceOutcome]) -> HeadlineMetrics:
    agent = arm_metrics(outcomes, "agent")
    baseline = arm_metrics(outcomes, "baseline")
    holdout = arm_metrics(outcomes, "holdout")

    # Incremental recovery: (agent rate - holdout rate) x portfolio value —
    # the headline number, plan.md §6.11. Bootstrapped as the DIFFERENCE of
    # two independent resampled means, not the difference of two point
    # estimates, so the CI reflects uncertainty in both arms.
    agent_flags = [1.0 if o.recovered else 0.0 for o in outcomes if o.arm == "agent"]
    holdout_flags = [1.0 if o.recovered else 0.0 for o in outcomes if o.arm == "holdout"]
    rng = np.random.default_rng(43)
    diffs = []
    for _ in range(1000):
        a = rng.choice(agent_flags, size=len(agent_flags), replace=True).mean() if agent_flags else 0.0
        h = rng.choice(holdout_flags, size=len(holdout_flags), replace=True).mean() if holdout_flags else 0.0
        diffs.append(a - h)
    diffs = np.array(diffs)
    incremental_rate = agent.recovery_rate - holdout.recovery_rate
    incremental_ci = (float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5)))

    # Full portfolio value used for the headline Rs figure (not just the
    # agent-arm's own value) — this is "what would incremental recovery be
    # worth if applied across the whole book," the framing plan.md uses.
    full_portfolio_value = agent.portfolio_value_paise + baseline.portfolio_value_paise + holdout.portfolio_value_paise
    incremental_recovery_paise = int(incremental_rate * full_portfolio_value)

    uplift_vs_baseline = agent.recovery_rate - baseline.recovery_rate

    cost_of_recovery = (
        (agent.total_action_cost_paise / incremental_recovery_paise) * 100
        if incremental_recovery_paise > 0
        else float("inf")
    )

    # Suppression precision — best-effort, documented approximation (no
    # ground-truth "genuinely unrecoverable" label exists): of agent
    # invoices where no automated action was taken (blocked or routed to
    # dispute), the fraction that also did NOT self-cure. A high value
    # means suppression mostly targeted invoices that truly needed no
    # automated contact, not ones that would have paid anyway.
    suppressed = [o for o in outcomes if o.arm == "agent" and o.action_taken is None]
    if suppressed:
        suppression_precision = sum(1 for o in suppressed if not o.recovered) / len(suppressed)
    else:
        suppression_precision = float("nan")

    return HeadlineMetrics(
        agent=agent,
        baseline=baseline,
        holdout=holdout,
        incremental_recovery_paise=incremental_recovery_paise,
        incremental_recovery_rate=incremental_rate,
        incremental_recovery_rate_ci=incremental_ci,
        uplift_vs_baseline=uplift_vs_baseline,
        cost_of_recovery_paise_per_100=cost_of_recovery,
        suppression_precision=suppression_precision,
    )
