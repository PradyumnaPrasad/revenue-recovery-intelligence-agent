import numpy as np
import pytest

from app.domain.diagnosis import diagnose
from app.domain.types import ActionKey, DiagnosisCode, InvoiceFacts
from app.simulation.environment import (
    ENVIRONMENTS,
    Outcome,
    effective_probability,
    env_adversarial,
    env_shift,
    env_train,
    p_self_cure,
    sample_no_action_outcome,
    sample_outcome,
)


def _facts(**overrides) -> InvoiceFacts:
    base = dict(
        invoice_id="inv-1",
        amount_paise=100_000_00,
        days_overdue=20,
        dispute_flag=False,
        prior_late_payment_rate=0.2,
        prior_broken_promises=0,
        prior_invoice_count=8,
        contact_count_30d=0,
    )
    base.update(overrides)
    return InvoiceFacts(**base)


def test_all_probabilities_are_valid():
    for env in ENVIRONMENTS.values():
        for code in DiagnosisCode:
            for action in ActionKey:
                p = effective_probability(_facts(), code, action, "mid_market", env)
                assert 0.0 <= p <= 1.0


def test_higher_contact_count_reduces_probability_under_train():
    env = env_train()
    low = effective_probability(_facts(contact_count_30d=0), DiagnosisCode.cash_flow_risk, ActionKey.offer_payment_plan, "smb", env)
    high = effective_probability(_facts(contact_count_30d=4), DiagnosisCode.cash_flow_risk, ActionKey.offer_payment_plan, "smb", env)
    assert high < low


def test_adversarial_fatigue_hurts_more_than_train():
    train_env = env_train()
    adv_env = env_adversarial()
    p_train = effective_probability(_facts(contact_count_30d=3), DiagnosisCode.process_delay, ActionKey.send_reminder, "mid_market", train_env)
    p_adv = effective_probability(_facts(contact_count_30d=3), DiagnosisCode.process_delay, ActionKey.send_reminder, "mid_market", adv_env)
    assert p_adv < p_train


def test_adversarial_escalation_penalty_hurts_smb_only():
    env = env_adversarial()
    smb = effective_probability(_facts(), DiagnosisCode.chronic_non_payment, ActionKey.escalate_to_am, "smb", env)
    enterprise = effective_probability(_facts(), DiagnosisCode.chronic_non_payment, ActionKey.escalate_to_am, "enterprise", env)
    train_env = env_train()
    smb_train = effective_probability(_facts(), DiagnosisCode.chronic_non_payment, ActionKey.escalate_to_am, "smb", train_env)
    assert smb < smb_train  # penalty applied
    assert enterprise > smb  # penalty is smb-specific


def test_shift_inverts_escalation_for_chronic():
    train_env = env_train()
    shift_env = env_shift()
    p_train = effective_probability(_facts(), DiagnosisCode.chronic_non_payment, ActionKey.escalate_to_am, "mid_market", train_env)
    p_shift = effective_probability(_facts(), DiagnosisCode.chronic_non_payment, ActionKey.escalate_to_am, "mid_market", shift_env)
    assert p_shift < p_train  # the 0.65 multiplier makes escalation weaker in E_shift


def test_sample_outcome_is_deterministic_given_rng_state():
    env = env_train()
    facts = _facts()
    r1 = np.random.default_rng(123)
    r2 = np.random.default_rng(123)
    out1 = [sample_outcome(r1, facts, DiagnosisCode.standard_overdue, ActionKey.send_reminder, "smb", env) for _ in range(20)]
    out2 = [sample_outcome(r2, facts, DiagnosisCode.standard_overdue, ActionKey.send_reminder, "smb", env) for _ in range(20)]
    assert out1 == out2


# --- plan.md F2: self-cure (the holdout arm's ground truth) ---------------


def test_self_cure_is_a_valid_probability():
    env = env_train()
    for segment in ("smb", "mid_market", "enterprise"):
        for days in (1, 10, 30, 60, 120, 180):
            p = p_self_cure(_facts(days_overdue=days), segment, env)
            assert 0.0 <= p <= 1.0


def test_self_cure_decays_with_days_overdue():
    env = env_train()
    early = p_self_cure(_facts(days_overdue=5), "mid_market", env)
    late = p_self_cure(_facts(days_overdue=90), "mid_market", env)
    assert late < early


def test_self_cure_falls_with_worse_payment_history():
    env = env_train()
    reliable = p_self_cure(_facts(prior_late_payment_rate=0.05), "smb", env)
    unreliable = p_self_cure(_facts(prior_late_payment_rate=0.6), "smb", env)
    assert unreliable < reliable


def test_self_cure_is_usually_below_the_best_available_action():
    """Sanity property, not a hard guarantee (plan.md §6.2): an invoice's
    self-cure rate should typically be lower than what its best available
    action would achieve — otherwise the environment is telling the agent
    that acting is pointless. Checked as a majority property across a real
    portfolio, not a per-cell mathematical proof.
    """
    from app.simulation.generator import generate_portfolio

    env = env_train()
    portfolio = generate_portfolio(size=1000, seed=42)
    below = 0
    for inv in portfolio.invoices:
        c = inv.customer
        facts = InvoiceFacts(
            invoice_id=str(inv.id), amount_paise=inv.amount_paise, days_overdue=inv.days_overdue,
            dispute_flag=inv.dispute_flag, prior_late_payment_rate=c.prior_late_rate,
            prior_broken_promises=c.prior_broken_promises, prior_invoice_count=c.prior_invoice_count,
            contact_count_30d=c.contact_count_30d, payment_link_sent=inv.payment_link_sent,
            payment_link_opened=inv.payment_link_opened, has_open_dispute_reply=False,
        )
        diagnosis = diagnose(facts)
        best = max(
            effective_probability(facts, diagnosis.code, a, c.segment, env) for a in ActionKey
        )
        if p_self_cure(facts, c.segment, env) < best:
            below += 1
    assert below / len(portfolio.invoices) > 0.95


def test_self_cure_lands_in_the_declared_plausible_band():
    """plan.md §6.2 'Done when': the holdout arm must recover a plausible
    non-zero rate (sanity band 8-25%) under all three environments — this
    is the actual fix for F2 (previously the holdout recovered 0% by
    construction, since no self-cure path existed at all).
    """
    from app.simulation.generator import generate_portfolio

    portfolio = generate_portfolio(size=3000, seed=42)
    for env in ENVIRONMENTS.values():
        vals = [
            p_self_cure(
                InvoiceFacts(
                    invoice_id=str(inv.id), amount_paise=inv.amount_paise,
                    days_overdue=inv.days_overdue, dispute_flag=inv.dispute_flag,
                    prior_late_payment_rate=inv.customer.prior_late_rate,
                    prior_broken_promises=inv.customer.prior_broken_promises,
                    prior_invoice_count=inv.customer.prior_invoice_count,
                    contact_count_30d=inv.customer.contact_count_30d,
                    payment_link_sent=inv.payment_link_sent,
                    payment_link_opened=inv.payment_link_opened,
                    has_open_dispute_reply=False,
                ),
                inv.customer.segment,
                env,
            )
            for inv in portfolio.invoices
        ]
        avg = sum(vals) / len(vals)
        assert 0.08 <= avg <= 0.25, f"{env.name}: mean self-cure {avg:.3f} outside [0.08, 0.25]"


# --- plan.md F3: the time axis --------------------------------------------


def test_outcome_has_no_days_to_cash_when_not_recovered():
    env = env_train()
    facts = _facts(prior_late_payment_rate=0.95, contact_count_30d=4)  # low-probability case
    rng = np.random.default_rng(7)
    outcome = sample_outcome(rng, facts, DiagnosisCode.chronic_non_payment, ActionKey.send_reminder, "smb", env)
    if not outcome.recovered:
        assert outcome.days_to_cash is None


def test_outcome_has_positive_days_to_cash_when_recovered():
    env = env_train()
    facts = _facts(days_overdue=5, prior_late_payment_rate=0.05)  # high-probability case
    rng = np.random.default_rng(11)
    outcomes = [
        sample_outcome(rng, facts, DiagnosisCode.process_delay, ActionKey.send_upi_payment_link, "enterprise", env)
        for _ in range(50)
    ]
    recovered = [o for o in outcomes if o.recovered]
    assert len(recovered) > 0
    assert all(o.days_to_cash is not None and o.days_to_cash > 0 for o in recovered)


def test_no_action_outcome_never_exceeds_action_recovery_delay_bounds():
    env = env_train()
    facts = _facts(days_overdue=10, prior_late_payment_rate=0.1)
    rng = np.random.default_rng(3)
    outcomes = [sample_no_action_outcome(rng, facts, "smb", env) for _ in range(200)]
    for o in outcomes:
        assert isinstance(o, Outcome)
        if o.recovered:
            assert 1 <= o.days_to_cash <= 180
        else:
            assert o.days_to_cash is None
