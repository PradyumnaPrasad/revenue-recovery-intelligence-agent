"""Three-arm measurement simulation — plan.md §6.7, the track's literal bar
("measured money recovered across a batch").

A multi-tick simulation, not the full orchestrator/scheduler (that's D4
scope, not yet built under this build's compressed schedule) — but BOTH
the agent and the baseline arm get the SAME four scripted touchpoints
(day 1, 7, 15, 30). This mattered more than it sounds: an earlier version
of this module gave the agent exactly one decision and the baseline four
scripted attempts, and the agent lost badly (30% vs 64% recovery) — not
because the agent's decisions were worse, but because compounding four
independent chances to recover beats one chance almost regardless of
quality. That would have been a real, damaging, and false conclusion to
report. Giving both arms equal opportunity and letting the agent choose
*which* action to take at each of its four touchpoints (informed by
diagnosis and the ladder) instead of a fixed script is the actual
comparison the track's bar asks for.

All three arms share the same ground truth: diagnose() runs for every
invoice regardless of arm, because diagnosis reflects the invoice's real
state, not something only the agent "knows" — the baseline arm's fixed
cadence still succeeds or fails according to the true environment
probability for its diagnosis, it just never uses that diagnosis to choose
an action. Only the agent arm's ACTION CHOICE (at each touchpoint) is
diagnosis- and ladder-informed.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.domain.baseline import BASELINE_CADENCE
from app.domain.diagnosis import diagnose
from app.domain.policy.engine import evaluate as evaluate_policy
from app.domain.policy.engine import load_policy
from app.domain.policy.types import (
    BatchContext,
    CustomerContext,
    DiagnosisContext,
    InvoiceContext,
    PolicyContext,
)
from app.domain.ranking import ActionEconomics, ActionHistoryEntry, load_action_config, rank_actions
from app.domain.types import ActionKey, InvoiceFacts
from app.ml import priors
from app.simulation.environment import (
    EnvironmentSpec,
    sample_no_action_outcome,
    sample_outcome,
)
from app.simulation.generator import GeneratedInvoice, GeneratedPortfolio, generate_portfolio

HORIZON_DAYS = 90

_POLICY = load_policy()
_ACTION_CONFIG = load_action_config()

# Fixed-cadence baseline — plan.md §6.11, now shared with the live
# counterfactual display (app/domain/baseline.py) so the dashboard's "what
# would the naive cadence do" and this measurement's baseline arm can never
# silently drift apart into two different definitions of "baseline."
_BASELINE_CADENCE = BASELINE_CADENCE

# The agent gets the SAME four touchpoints — see this module's docstring
# for why equal opportunity between arms is not optional.
_AGENT_TOUCHPOINT_DAYS: list[int] = [1, 7, 15, 30]


@dataclass
class InvoiceOutcome:
    invoice_id: str
    arm: str
    amount_paise: int
    recovered: bool
    recovered_paise: int
    days_to_cash: int | None
    action_taken: str | None
    action_cost_paise: int
    diagnosis_code: str


def _facts_from_generated(inv: GeneratedInvoice) -> InvoiceFacts:
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


def _econ(action: ActionKey) -> ActionEconomics:
    return _ACTION_CONFIG.actions[action]


def _simulate_holdout(
    rng: np.random.Generator, inv: GeneratedInvoice, env: EnvironmentSpec
) -> InvoiceOutcome:
    facts = _facts_from_generated(inv)
    diagnosis = diagnose(facts)
    outcome = sample_no_action_outcome(rng, facts, inv.customer.segment, env)
    recovered = outcome.recovered and outcome.days_to_cash is not None and outcome.days_to_cash <= HORIZON_DAYS
    return InvoiceOutcome(
        invoice_id=str(inv.id),
        arm="holdout",
        amount_paise=inv.amount_paise,
        recovered=recovered,
        recovered_paise=inv.amount_paise if recovered else 0,
        days_to_cash=outcome.days_to_cash if recovered else None,
        action_taken=None,
        action_cost_paise=0,
        diagnosis_code=diagnosis.code.value,
    )


def _simulate_baseline(
    rng: np.random.Generator, inv: GeneratedInvoice, env: EnvironmentSpec
) -> InvoiceOutcome:
    facts = _facts_from_generated(inv)
    diagnosis = diagnose(facts)  # ground truth; the baseline never looks at this
    total_cost = 0
    for scripted_day, action in _BASELINE_CADENCE:
        total_cost += _econ(action).cost_paise
        outcome = sample_outcome(rng, facts, diagnosis.code, action, inv.customer.segment, env)
        if outcome.recovered and outcome.days_to_cash is not None:
            actual_day = scripted_day + outcome.days_to_cash
            if actual_day <= HORIZON_DAYS:
                return InvoiceOutcome(
                    invoice_id=str(inv.id),
                    arm="baseline",
                    amount_paise=inv.amount_paise,
                    recovered=True,
                    recovered_paise=inv.amount_paise,
                    days_to_cash=actual_day,
                    action_taken=action.value,
                    action_cost_paise=total_cost,
                    diagnosis_code=diagnosis.code.value,
                )
    return InvoiceOutcome(
        invoice_id=str(inv.id),
        arm="baseline",
        amount_paise=inv.amount_paise,
        recovered=False,
        recovered_paise=0,
        days_to_cash=None,
        action_taken=None,
        action_cost_paise=total_cost,
        diagnosis_code=diagnosis.code.value,
    )


def _simulate_agent(
    rng: np.random.Generator, inv: GeneratedInvoice, env: EnvironmentSpec
) -> InvoiceOutcome:
    facts = _facts_from_generated(inv)
    diagnosis = diagnose(facts)
    predictions = priors.predict(diagnosis.code)

    # (action, day_it_was_executed) pairs — a plain ActionHistoryEntry's
    # days_ago is only valid at the instant it's created, and the same
    # history must be reinterpreted relative to whichever tick is
    # currently being evaluated, so the executed day is what's stored.
    executed: list[tuple[ActionKey, int]] = []
    total_cost = 0
    last_action_label: str | None = None

    for tick_day in _AGENT_TOUCHPOINT_DAYS:
        history_at_tick = [
            ActionHistoryEntry(action=action, days_ago=tick_day - executed_day)
            for action, executed_day in executed
        ]

        ranked = rank_actions(facts, predictions, _ACTION_CONFIG, history=history_at_tick)
        top = next((r for r in ranked if r.ladder_eligible), None)
        if top is None:
            continue  # ladder exhausted (max executions on every rung) — skip this touchpoint

        # contact_count_30d grows with the agent's own contacts in the
        # trailing 30 days, same fatigue signal a real deployment would see.
        recent_contacts = sum(1 for h in history_at_tick if h.days_ago <= 30)
        policy_context = PolicyContext(
            diagnosis=DiagnosisContext(
                code=diagnosis.code.value, confidence=diagnosis.confidence, produced_by=diagnosis.produced_by
            ),
            customer=CustomerContext(
                suppressed=False, contact_count_30d=facts.contact_count_30d + recent_contacts
            ),
            invoice=InvoiceContext(
                amount_paise=facts.amount_paise, has_open_promise=False, promise_still_open=False
            ),
            batch=BatchContext(actions_today=0, action_budget=10_000),  # budget not exercised here
        )
        policy_result = evaluate_policy(_POLICY, policy_context, top.action)

        action_to_execute: ActionKey | None
        if policy_result.outcome == "block":
            action_to_execute = None
        elif policy_result.outcome == "substitute":
            sub = policy_result.substituted_action
            action_to_execute = ActionKey(sub) if sub in {a.value for a in ActionKey} else None
        else:  # allow or require_approval — simulation assumes approval is granted
            action_to_execute = top.action

        if action_to_execute is None:
            last_action_label = policy_result.substituted_action  # e.g. "route_to_dispute", or None
            continue  # blocked/routed-away this touchpoint — no outcome sample, try again next tick

        total_cost += _econ(action_to_execute).cost_paise
        last_action_label = action_to_execute.value
        executed.append((action_to_execute, tick_day))

        outcome = sample_outcome(rng, facts, diagnosis.code, action_to_execute, inv.customer.segment, env)
        if outcome.recovered and outcome.days_to_cash is not None:
            actual_day = tick_day + outcome.days_to_cash
            if actual_day <= HORIZON_DAYS:
                return InvoiceOutcome(
                    invoice_id=str(inv.id),
                    arm="agent",
                    amount_paise=inv.amount_paise,
                    recovered=True,
                    recovered_paise=inv.amount_paise,
                    days_to_cash=actual_day,
                    action_taken=action_to_execute.value,
                    action_cost_paise=total_cost,
                    diagnosis_code=diagnosis.code.value,
                )

    # Never recovered via any executed action across all touchpoints —
    # whatever's left is self-cure, exactly like the holdout arm's ground
    # truth (a policy-blocked/never-contacted invoice's only path to
    # recovery is the same one a holdout invoice has).
    self_cure_outcome = sample_no_action_outcome(rng, facts, inv.customer.segment, env)
    recovered = (
        self_cure_outcome.recovered
        and self_cure_outcome.days_to_cash is not None
        and self_cure_outcome.days_to_cash <= HORIZON_DAYS
    )
    return InvoiceOutcome(
        invoice_id=str(inv.id),
        arm="agent",
        amount_paise=inv.amount_paise,
        recovered=recovered,
        recovered_paise=inv.amount_paise if recovered else 0,
        days_to_cash=self_cure_outcome.days_to_cash if recovered else None,
        action_taken=last_action_label,
        action_cost_paise=total_cost,
        diagnosis_code=diagnosis.code.value,
    )


def simulate_invoice(
    rng: np.random.Generator, inv: GeneratedInvoice, env: EnvironmentSpec
) -> InvoiceOutcome:
    arm = inv.arm
    if arm == "holdout":
        return _simulate_holdout(rng, inv, env)
    if arm == "baseline":
        return _simulate_baseline(rng, inv, env)
    return _simulate_agent(rng, inv, env)


def simulate_portfolio(
    portfolio: GeneratedPortfolio, env: EnvironmentSpec, rng_seed_offset: int = 104_729
) -> list[InvoiceOutcome]:
    """rng_seed_offset is multiplied against the portfolio's own seed so
    outcome sampling is a distinct, reproducible random stream from
    portfolio generation itself — same pattern as
    app/simulation/training_data.py's rng derivation.
    """
    rng = np.random.default_rng(portfolio.seed * 7919 + rng_seed_offset)
    return [simulate_invoice(rng, inv, env) for inv in portfolio.invoices]
