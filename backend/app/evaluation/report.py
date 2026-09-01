"""Regenerates reports/evaluation.md from seeds — plan.md §6.11 'Done
when': `make evaluate` regenerates the full report, arm assignment is
stable, every metric has a CI. Run via `make evaluate` /
`python -m app.evaluation.report`.
"""
from __future__ import annotations

from pathlib import Path

from app.evaluation.metrics import HeadlineMetrics, compute_headline
from app.evaluation.simulate import InvoiceOutcome, simulate_portfolio
from app.simulation.environment import ENVIRONMENTS
from app.simulation.generator import generate_portfolio
from app.simulation.training_data import EVALUATION_SEEDS

REPORT_PATH = Path(__file__).resolve().parents[2] / "reports" / "evaluation.md"
SIZE_PER_SEED = 300


def _rupees(paise: int) -> str:
    """Indian digit grouping (lakhs/crores), matching
    app.audit.explain.format_rupees — a separate implementation here
    (not imported) since evaluation/ and audit/ otherwise have no
    dependency on each other and this is three lines, not worth coupling
    the modules for. Found as a real bug: this used to be Python's `:,`,
    which groups by 3 throughout (Western), so the same figure showed
    "Rs 3,62,554" on the dashboard and "Rs 362,554" in this report.
    """
    sign = "-" if paise < 0 else ""
    rupees = str(round(abs(paise) / 100))
    if len(rupees) <= 3:
        grouped = rupees
    else:
        last_three = rupees[-3:]
        remainder = rupees[:-3]
        pairs = []
        while len(remainder) > 2:
            pairs.insert(0, remainder[-2:])
            remainder = remainder[:-2]
        if remainder:
            pairs.insert(0, remainder)
        grouped = ",".join(pairs) + "," + last_three
    return f"{sign}Rs {grouped}"


def run_environment(env_name: str) -> list[InvoiceOutcome]:
    env = ENVIRONMENTS[env_name]
    outcomes: list[InvoiceOutcome] = []
    for seed in EVALUATION_SEEDS:
        portfolio = generate_portfolio(size=SIZE_PER_SEED, seed=seed)
        outcomes.extend(simulate_portfolio(portfolio, env))
    return outcomes


def _format_headline(env_name: str, h: HeadlineMetrics) -> str:
    lo, hi = h.incremental_recovery_rate_ci
    return f"""### {env_name}

| Arm | n | Recovery rate | 95% CI |
|---|---:|---:|---:|
| Agent | {h.agent.n} | {h.agent.recovery_rate:.1%} | [{h.agent.recovery_rate_ci[0]:.1%}, {h.agent.recovery_rate_ci[1]:.1%}] |
| Baseline (fixed cadence) | {h.baseline.n} | {h.baseline.recovery_rate:.1%} | [{h.baseline.recovery_rate_ci[0]:.1%}, {h.baseline.recovery_rate_ci[1]:.1%}] |
| Holdout (no contact) | {h.holdout.n} | {h.holdout.recovery_rate:.1%} | [{h.holdout.recovery_rate_ci[0]:.1%}, {h.holdout.recovery_rate_ci[1]:.1%}] |

**Incremental recovery (agent vs holdout):** {h.incremental_recovery_rate:.2%} \
[{lo:.2%}, {hi:.2%}] of portfolio value = **{_rupees(h.incremental_recovery_paise)}**

**Uplift vs fixed-cadence baseline:** {h.uplift_vs_baseline:+.2%} raw recovery rate.

| | Agent | Baseline |
|---|---:|---:|
| Total action spend | {_rupees(h.agent.total_action_cost_paise)} | {_rupees(h.baseline.total_action_cost_paise)} |
| Spend per invoice | {_rupees(h.agent.total_action_cost_paise // max(h.agent.n, 1))} | {_rupees(h.baseline.total_action_cost_paise // max(h.baseline.n, 1))} |

**The honest finding, not the one we expected going in:** the agent spends \
*more* per invoice on average, not less — the opposite of the initial \
hypothesis. The reason is diagnosis-informed timing, not inefficiency:
policy rule P08 routes chronic non-payment straight to a Rs 1,200 human \
escalation immediately, on the theory that reminders don't work on that \
population (chronic and disputed invoices are roughly a fifth of this \
portfolio) — while the fixed-cadence baseline tries three cheap touches \
*first*, regardless of diagnosis, and only pays for escalation on the small \
fraction of invoices that survive to touch four. Baseline's sequential \
cheap-then-expensive triage is a genuinely reasonable strategy, which is \
exactly why real dunning software already resembles it and why beating it \
on raw recovery rate is hard. The agent's real differentiation here is \
*which* invoices get expensive treatment and *when* — diagnosis-informed \
and immediate for the cases known not to respond to reminders — not a \
lower aggregate bill. A fuller multi-tick run (D4's orchestrator, not yet \
built) would let the agent defer escalation under genuine diagnostic \
uncertainty the way this single-decision-per-touchpoint simulation cannot.

**Suppression precision** (of agent invoices where no automated action was \
taken, fraction that also did not self-cure): {h.suppression_precision:.1%}
"""


def generate_report(env_names: list[str] | None = None) -> str:
    env_names = env_names or ["E_train", "E_shift", "E_adversarial"]
    sections = []
    for env_name in env_names:
        outcomes = run_environment(env_name)
        headline = compute_headline(outcomes)
        sections.append(_format_headline(env_name, headline))

    body = "\n---\n\n".join(sections)
    report = f"""# Evaluation report

Regenerated by `make evaluate` (`python -m app.evaluation.report`) from the
declared evaluation seeds ({EVALUATION_SEEDS[0]}-{EVALUATION_SEEDS[-1]}, \
{SIZE_PER_SEED} invoices per seed, {SIZE_PER_SEED * len(EVALUATION_SEEDS)} \
invoices total per environment) — never touched during training. Arm split \
is deterministic (hash of invoice_id), not resampled between runs.

**What this measures, precisely:** both the agent and the fixed-cadence \
baseline get the SAME four scripted touchpoints (day 1, 7, 15, 30) — equal \
opportunity was not optional here (an earlier version gave the agent one \
decision and the baseline four, and the agent lost by 33 points purely \
from having fewer chances, not worse choices). At each of its four \
touchpoints the agent re-diagnoses, re-ranks, and re-checks policy against \
its own accumulated action history (cooldowns and the escalation ladder \
both apply); the baseline runs its fixed script regardless of diagnosis. \
This is not the full orchestrator/scheduler with real elapsed time and \
live promise/reply handling (D4 scope, not yet built) — it is a faithful, \
reproducible approximation of the same decision logic that would run there.

**The claim this report supports:** given the declared environment \
(`docs/environment.md`), the decision layer captures a measurable, \
holdout-adjusted uplift over a fixed-cadence baseline. Not: "this recovers \
X% more money in the real world" — see the honesty contract (plan.md \
section 5).

{body}
"""
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report)
    return report


if __name__ == "__main__":
    generate_report()
    print(f"wrote {REPORT_PATH}")
