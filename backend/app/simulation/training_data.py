"""Historical action-outcome dataset generation — plan.md §6.4 / M1.

Produces rows of the shape (invoice features, diagnosis, action_taken) ->
recovered, which is exactly what a supervised classifier needs and nothing
more (plan.md, original design's leakage-avoidance principle, preserved).

Design note on "action_taken": for each invoice we sample ONE action from a
declared historical policy (not all six actions), because that's what a
real logged dataset looks like — you only ever observe the outcome of the
action that was actually taken. Sampling all six actions per invoice would
be easier but would (a) not resemble real logged data and (b) hand the
model an unrealistically easy problem, since near-identical invoices would
appear six times with only the action differing. The historical policy
below is intentionally noisy (has real "exploration") so every action gets
enough examples across every diagnosis to be learnable — a purely
diagnosis-appropriate policy would starve the model of examples of *bad*
action choices, which it also needs to see in order to rank correctly.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.domain.diagnosis import diagnose
from app.domain.features import ALLOWED_FEATURE_KEYS, to_feature_vector
from app.domain.types import ActionKey, DiagnosisCode, InvoiceFacts
from app.simulation.environment import EnvironmentSpec, sample_outcome
from app.simulation.generator import GeneratedInvoice, generate_portfolio

# Declared historical policy: a soft preference for the "sensible" action per
# diagnosis, blended with uniform exploration so every action is observed
# under every diagnosis. This mirrors how a real AR team's inconsistent,
# person-dependent past behaviour would actually look in logged data.
_POLICY_PREFERENCE: dict[DiagnosisCode, dict[ActionKey, float]] = {
    DiagnosisCode.process_delay: {
        ActionKey.send_reminder: 0.40,
        ActionKey.resend_payment_link: 0.25,
        ActionKey.send_upi_payment_link: 0.10,
        ActionKey.offer_payment_plan: 0.05,
        ActionKey.escalate_to_am: 0.05,
        ActionKey.schedule_call: 0.15,
    },
    DiagnosisCode.cash_flow_risk: {
        ActionKey.send_reminder: 0.15,
        ActionKey.resend_payment_link: 0.15,
        ActionKey.send_upi_payment_link: 0.10,
        ActionKey.offer_payment_plan: 0.35,
        ActionKey.escalate_to_am: 0.10,
        ActionKey.schedule_call: 0.15,
    },
    DiagnosisCode.chronic_non_payment: {
        ActionKey.send_reminder: 0.10,
        ActionKey.resend_payment_link: 0.10,
        ActionKey.send_upi_payment_link: 0.05,
        ActionKey.offer_payment_plan: 0.15,
        ActionKey.escalate_to_am: 0.40,
        ActionKey.schedule_call: 0.20,
    },
    DiagnosisCode.channel_failure: {
        ActionKey.send_reminder: 0.10,
        ActionKey.resend_payment_link: 0.20,
        ActionKey.send_upi_payment_link: 0.35,
        ActionKey.offer_payment_plan: 0.05,
        ActionKey.escalate_to_am: 0.10,
        ActionKey.schedule_call: 0.20,
    },
    DiagnosisCode.standard_overdue: {
        ActionKey.send_reminder: 0.25,
        ActionKey.resend_payment_link: 0.25,
        ActionKey.send_upi_payment_link: 0.15,
        ActionKey.offer_payment_plan: 0.10,
        ActionKey.escalate_to_am: 0.10,
        ActionKey.schedule_call: 0.15,
    },
    DiagnosisCode.disputed: {a: 1.0 / len(ActionKey) for a in ActionKey},
}

_EPSILON_EXPLORATION = 0.20


def _blended_policy(code: DiagnosisCode) -> tuple[list[ActionKey], list[float]]:
    actions = list(ActionKey)
    pref = _POLICY_PREFERENCE[code]
    n = len(actions)
    weights = [
        (1 - _EPSILON_EXPLORATION) * pref[a] + _EPSILON_EXPLORATION * (1.0 / n) for a in actions
    ]
    total = sum(weights)
    return actions, [w / total for w in weights]


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
        # Replies are pre-generated fixtures, not yet READ (plan.md F4 / §6.1
        # Edit 1). has_open_dispute_reply may only become true once the M6
        # extraction layer actually processes a reply — deriving it here
        # from inv.replies directly treats unread text as already-extracted
        # evidence, which is both wrong and what inflated disputed to 19.7%.
        has_open_dispute_reply=False,
    )


@dataclass
class DatasetRow:
    features: dict
    recovered: bool
    days_to_cash: int | None
    seed: int
    fold: str
    environment: str


def generate_labeled_dataset(
    seeds: list[int], size_per_seed: int, env: EnvironmentSpec, fold: str
) -> list[DatasetRow]:
    rows: list[DatasetRow] = []
    for seed in seeds:
        portfolio = generate_portfolio(size=size_per_seed, seed=seed)
        # A separate RNG stream for policy/outcome sampling, seeded off the
        # portfolio seed but distinct from the generator's own RNG, so
        # changing outcome sampling logic never perturbs portfolio content
        # (and vice versa) — the two are independent random processes.
        rng = np.random.default_rng(seed * 7919 + 17)

        for inv in portfolio.invoices:
            facts = _facts_from_generated(inv)
            diagnosis = diagnose(facts)

            actions, weights = _blended_policy(diagnosis.code)
            action = actions[rng.choice(len(actions), p=weights)]

            outcome = sample_outcome(
                rng=rng,
                facts=facts,
                diagnosis_code=diagnosis.code,
                action=action,
                segment=inv.customer.segment,
                env=env,
            )

            fv = to_feature_vector(
                facts=facts,
                diagnosis_code=diagnosis.code,
                action=action,
                segment=inv.customer.segment,
                industry=inv.customer.industry,
            )
            rows.append(
                DatasetRow(
                    features=fv.model_dump(),
                    recovered=outcome.recovered,
                    days_to_cash=outcome.days_to_cash,
                    seed=seed,
                    fold=fold,
                    environment=env.name,
                )
            )
    return rows


def assert_no_leakage(rows: list[DatasetRow]) -> None:
    """Property check: every row's feature keys are exactly the allowlist —
    nothing environment-internal ever made it into a row (plan.md §6.4,
    Change 4). Raises on the first violation.
    """
    for row in rows:
        keys = set(row.features.keys())
        if keys != ALLOWED_FEATURE_KEYS:
            raise AssertionError(
                f"feature leakage detected: {keys.symmetric_difference(ALLOWED_FEATURE_KEYS)}"
            )


# Fold seeds — plan.md §6.1, Change 4: three disjoint seed ranges so the
# final evaluation batch is never touched during training or calibration.
TRAIN_SEEDS = list(range(101, 111))     # 101..110
CALIBRATION_SEEDS = list(range(201, 206))  # 201..205
EVALUATION_SEEDS = list(range(301, 311))   # 301..310
