"""The declared decision environment — plan.md §6.4 (the fix for C1,
circular evaluation).

WHY THIS FILE EXISTS AND WHY IT'S WRITTEN THIS WAY:

The original design had a hidden simulator define P(recover | action), a
model trained on samples from it, and then the resulting policy evaluated
against that SAME simulator. That proves the pipeline has no bugs; it
proves nothing about whether the agent recovers money. The fix is not to
hide the simulator better — it's the opposite: publish every number in
this file (mirrored in docs/environment.md), and test the decision layer
against THREE versions of it, including one where our own beliefs are
deliberately wrong. What we can honestly claim afterward is: "given this
declared environment, the decision layer captures Y% of the available
uplift over a fixed-cadence baseline, and degrades gracefully when the
environment is mis-specified" — not "this recovers X% more in the real
world." That's a smaller, true, defensible claim instead of a bigger, false
one.

Nothing in here is ever exposed to the model. `sample_outcome()` returns
only a boolean. The probability that produced it is never returned,
logged into a feature row, or passed downstream — see app/domain/features.py
for the enforced allowlist that makes this structural, not just a promise.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from app.domain.types import ActionKey, DiagnosisCode, InvoiceFacts

# ---------------------------------------------------------------------------
# E_train: the base environment. Every cell is a considered guess at how
# each action performs for each diagnosis, informed by the story each
# diagnosis tells (plan.md §6.2) — e.g. escalate_to_am is the best action
# for chronic_non_payment (a human relationship matters when reminders have
# stopped working), and offer_payment_plan is the best for cash_flow_risk
# (the customer's problem is liquidity, not willingness).
# ---------------------------------------------------------------------------

_BASE_RECOVERY_PROB: dict[DiagnosisCode, dict[ActionKey, float]] = {
    DiagnosisCode.process_delay: {
        ActionKey.send_reminder: 0.45,
        ActionKey.resend_payment_link: 0.50,
        ActionKey.send_upi_payment_link: 0.52,
        ActionKey.offer_payment_plan: 0.30,
        ActionKey.escalate_to_am: 0.55,
        ActionKey.schedule_call: 0.48,
    },
    DiagnosisCode.cash_flow_risk: {
        ActionKey.send_reminder: 0.18,
        ActionKey.resend_payment_link: 0.22,
        ActionKey.send_upi_payment_link: 0.24,
        ActionKey.offer_payment_plan: 0.40,
        ActionKey.escalate_to_am: 0.35,
        ActionKey.schedule_call: 0.30,
    },
    DiagnosisCode.chronic_non_payment: {
        ActionKey.send_reminder: 0.05,
        ActionKey.resend_payment_link: 0.06,
        ActionKey.send_upi_payment_link: 0.07,
        ActionKey.offer_payment_plan: 0.15,
        ActionKey.escalate_to_am: 0.28,
        ActionKey.schedule_call: 0.20,
    },
    DiagnosisCode.channel_failure: {
        ActionKey.send_reminder: 0.10,
        ActionKey.resend_payment_link: 0.15,
        ActionKey.send_upi_payment_link: 0.38,
        ActionKey.offer_payment_plan: 0.12,
        ActionKey.escalate_to_am: 0.30,
        ActionKey.schedule_call: 0.33,
    },
    DiagnosisCode.standard_overdue: {
        ActionKey.send_reminder: 0.28,
        ActionKey.resend_payment_link: 0.33,
        ActionKey.send_upi_payment_link: 0.35,
        ActionKey.offer_payment_plan: 0.25,
        ActionKey.escalate_to_am: 0.32,
        ActionKey.schedule_call: 0.30,
    },
    # Disputed invoices are routed away from dunning by the policy engine
    # (P01 in plan.md §6.7) before they ever reach the ranking layer. These
    # numbers exist only so the environment is total (defined for every
    # diagnosis/action pair) and tests don't need a special case — they are
    # deliberately low and roughly flat, because none of these actions are
    # the right response to a dispute.
    DiagnosisCode.disputed: {
        ActionKey.send_reminder: 0.05,
        ActionKey.resend_payment_link: 0.05,
        ActionKey.send_upi_payment_link: 0.05,
        ActionKey.offer_payment_plan: 0.05,
        ActionKey.escalate_to_am: 0.10,
        ActionKey.schedule_call: 0.08,
    },
}

_SEGMENT_MULTIPLIER: dict[str, float] = {
    "smb": 0.90,
    "mid_market": 1.00,
    "enterprise": 1.10,
}

# Self-cure — plan.md F2 fix. P(this invoice gets paid with NO intervention
# at all). This is the holdout arm's ground truth: without it, "incremental
# recovery" has nothing to subtract and silently collapses back to raw
# recovery, which is the exact inflated number a holdout exists to prevent.
#
# Declared, not derived from _BASE_RECOVERY_PROB by subtraction (the
# originally-planned "lift over self-cure" decomposition of all 36 cells was
# judged not worth the mechanical risk under this build's compressed
# schedule — see the note on generate_labeled_dataset below). Instead this
# is an independent, standalone estimate of the no-action baseline: larger
# accounts with tighter procurement self-cure less (they need cash-flow help
# less often, but the internal process to release payment is slower and less
# discretionary); it decays with days_overdue (the longer nothing happens,
# the less likely a spontaneous payment); and it falls with a poor payment
# history (late_rate). Every action's recovery probability in
# _BASE_RECOVERY_PROB should exceed this for a realistic invoice — that's a
# property of the two tables being sanely related, not a hard constraint.
_SELF_CURE_BASE: dict[str, float] = {
    "smb": 0.30,
    "mid_market": 0.23,
    "enterprise": 0.15,
}
_SELF_CURE_HALFLIFE_DAYS = 32.0

# Mean days-to-cash per action (plan.md F3 fix) — a declared belief about
# how long each action takes to turn into cash in hand, sampled from a
# Gamma(shape=2, scale=mean/2) so most outcomes land near the mean with a
# realistic right tail (a few invoices pay very late even on a fast rail).
# This is the TRUE, environment-side generative delay — separate from
# whatever the ranking layer (not yet built) BELIEVES about days_to_cash in
# its own EV formula; the two are deliberately different objects.
_DAYS_TO_CASH_MEAN: dict[ActionKey, float] = {
    ActionKey.send_upi_payment_link: 2.0,
    ActionKey.resend_payment_link: 3.0,
    ActionKey.send_reminder: 5.0,
    ActionKey.schedule_call: 8.0,
    ActionKey.escalate_to_am: 12.0,
    ActionKey.offer_payment_plan: 60.0,
}


@dataclass(frozen=True)
class EnvironmentSpec:
    name: str
    base_prob: dict[DiagnosisCode, dict[ActionKey, float]]
    segment_multiplier: dict[str, float]
    fatigue_coefficient: float = 0.08
    escalation_smb_penalty: float = 1.0  # 1.0 = no penalty; <1.0 = adversarial
    amount_decay_coefficient: float = 0.03
    self_cure_base: dict[str, float] = field(default_factory=lambda: dict(_SELF_CURE_BASE))
    self_cure_halflife_days: float = _SELF_CURE_HALFLIFE_DAYS


def _amount_factor(amount_paise: int, coefficient: float) -> float:
    rupees = max(1, amount_paise // 100)
    import math

    excess_orders_of_magnitude = max(0.0, math.log10(rupees) - 4.0)  # above ~Rs 10,000
    return float(np.clip(1.0 - coefficient * excess_orders_of_magnitude, 0.55, 1.0))


def effective_probability(
    facts: InvoiceFacts,
    diagnosis_code: DiagnosisCode,
    action: ActionKey,
    segment: str,
    env: EnvironmentSpec,
) -> float:
    """The hidden ground-truth probability. Called only by sample_outcome()
    and by the evaluation harness (M7) for reporting the DECLARED environment
    parameters — never passed to, or derived by, the prediction model.
    """
    base = env.base_prob[diagnosis_code][action]
    seg_mult = env.segment_multiplier.get(segment, 1.0)
    amount_mult = _amount_factor(facts.amount_paise, env.amount_decay_coefficient)
    fatigue_mult = max(0.35, 1.0 - env.fatigue_coefficient * facts.contact_count_30d)

    p = base * seg_mult * amount_mult * fatigue_mult

    if action == ActionKey.escalate_to_am and segment == "smb":
        p *= env.escalation_smb_penalty

    return float(np.clip(p, 0.02, 0.95))


def p_self_cure(facts: InvoiceFacts, segment: str, env: EnvironmentSpec) -> float:
    """The holdout arm's ground truth (plan.md F2) — P(recovered | no action
    taken at all). Called by the measurement layer's holdout-arm sampling,
    never by anything that produces a model feature: this number is exactly
    as oracle-only as effective_probability(), and app/domain/features.py's
    allowlist keeps it structurally unreachable from FeatureVector the same
    way.
    """
    base = env.self_cure_base.get(segment, 0.15)
    decay = math.exp(-facts.days_overdue / env.self_cure_halflife_days)
    reliability = 1.0 - 0.6 * facts.prior_late_payment_rate
    return float(np.clip(base * decay * reliability, 0.01, 0.60))


@dataclass(frozen=True)
class Outcome:
    """plan.md F3: sample_outcome() used to return a bare bool, which has no
    time axis — but the (not-yet-built) EV formula needs days_to_cash, a
    90-day simulated run needs to know when money actually lands, and the
    dashboard's hero is a recovery *curve* over time. days_to_cash is None
    exactly when recovered is False — there is no cash date for money that
    never arrived.
    """

    recovered: bool
    days_to_cash: int | None


def sample_no_action_outcome(
    rng: np.random.Generator,
    facts: InvoiceFacts,
    segment: str,
    env: EnvironmentSpec,
) -> Outcome:
    """The holdout arm's outcome sampler — self-cure only, no action taken.
    No days-to-cash belief exists for "nothing happened"; when self-cure
    does land, model it as a slow, action-independent event on the same
    Gamma shape as the slowest real action (offer_payment_plan) rather than
    inventing a second delay distribution this build has no data to justify.
    """
    p = p_self_cure(facts, segment, env)
    recovered = bool(rng.random() < p)
    if not recovered:
        return Outcome(False, None)
    mean = _DAYS_TO_CASH_MEAN[ActionKey.offer_payment_plan]
    days = int(np.clip(rng.gamma(shape=2.0, scale=mean / 2.0), 1, 180))
    return Outcome(True, days)


def sample_outcome(
    rng: np.random.Generator,
    facts: InvoiceFacts,
    diagnosis_code: DiagnosisCode,
    action: ActionKey,
    segment: str,
    env: EnvironmentSpec,
) -> Outcome:
    """Samples ONE outcome for an action actually taken. This is the only
    function training-data generation is allowed to call — the probability
    itself is never returned, so it can never leak into a feature row
    (plan.md: "the training model never receives the hidden probability").
    """
    p = effective_probability(facts, diagnosis_code, action, segment, env)
    recovered = bool(rng.random() < p)
    if not recovered:
        return Outcome(False, None)
    mean = _DAYS_TO_CASH_MEAN[action]
    days = int(np.clip(rng.gamma(shape=2.0, scale=mean / 2.0), 1, 180))
    return Outcome(True, days)


# ---------------------------------------------------------------------------
# Three declared environments (plan.md §6.4, Change 3).
# ---------------------------------------------------------------------------


def env_train() -> EnvironmentSpec:
    """The environment the model is trained on. Our best-effort, stated
    belief about how each action performs."""
    return EnvironmentSpec(
        name="E_train",
        base_prob=_BASE_RECOVERY_PROB,
        segment_multiplier=_SEGMENT_MULTIPLIER,
    )


def env_shift() -> EnvironmentSpec:
    """Tests robustness to a mis-specified world: every action's true
    effectiveness is perturbed, and — deliberately — the ranking for
    chronic_non_payment is partially INVERTED (send_reminder becomes
    relatively better, escalate_to_am relatively worse) versus what E_train
    taught the model. This is not random noise; it's an explicit, documented
    alternate belief, chosen so the perturbation is reproducible and
    inspectable rather than a random seed nobody can audit.
    """
    shifted: dict[DiagnosisCode, dict[ActionKey, float]] = {
        code: dict(actions) for code, actions in _BASE_RECOVERY_PROB.items()
    }
    # General perturbation: +/-40% on every cell via a fixed, declared
    # per-action multiplier (not sampled at runtime — the whole point is
    # that E_shift is a FIXED alternate world, checked into the repo).
    multipliers = {
        ActionKey.send_reminder: 1.40,
        ActionKey.resend_payment_link: 0.85,
        ActionKey.send_upi_payment_link: 1.10,
        ActionKey.offer_payment_plan: 0.60,
        ActionKey.escalate_to_am: 0.65,  # inverted: escalation is weaker than E_train believes
        ActionKey.schedule_call: 1.15,
    }
    for code, actions in shifted.items():
        for action, base in actions.items():
            actions[action] = float(np.clip(base * multipliers[action], 0.02, 0.95))

    return EnvironmentSpec(
        name="E_shift",
        base_prob=shifted,
        segment_multiplier={"smb": 1.05, "mid_market": 0.95, "enterprise": 0.90},
        amount_decay_coefficient=0.05,
    )


def env_adversarial() -> EnvironmentSpec:
    """Tests whether the POLICY layer, not the model, is what keeps the
    system safe when the model's beliefs are actively wrong. Two specific,
    documented failure modes:

    1. Contact fatigue is tripled — repeated contact suppresses recovery
       much faster than E_train assumes.
    2. Escalating to an account manager for an SMB customer actively HURTS
       recovery (escalation reads as disproportionate/aggressive for a
       small account) instead of helping — the opposite of what the model
       learned from E_train.

    The expected result, and the point of the whole exercise: the model's
    recommendations get worse under this environment, but the policy
    engine's contact caps (P03) and cooldowns (the ladder, §6.6) limit how
    much damage a confidently-wrong model can do. That is a live
    demonstration that "policy overrides model" is a safety property, not
    a slogan.
    """
    return EnvironmentSpec(
        name="E_adversarial",
        base_prob=_BASE_RECOVERY_PROB,
        segment_multiplier=_SEGMENT_MULTIPLIER,
        fatigue_coefficient=0.24,          # tripled vs E_train's 0.08
        escalation_smb_penalty=0.45,       # escalation actively backfires for smb
    )


ENVIRONMENTS: dict[str, EnvironmentSpec] = {
    "E_train": env_train(),
    "E_shift": env_shift(),
    "E_adversarial": env_adversarial(),
}
