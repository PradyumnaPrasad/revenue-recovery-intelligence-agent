"""plan.md §6.4 'Done when': unit test per formula term, escalate_to_am
never wins below Rs 50k, no action repeats inside its cooldown, ladder
monotonicity property test, prior_v1 != environment table.
"""
from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from app.domain.ranking import (
    ActionHistoryEntry,
    allowed_actions,
    expected_value_paise,
    fatigue_penalty,
    load_action_config,
    rank_actions,
)
from app.domain.types import ActionKey, DiagnosisCode, InvoiceFacts
from app.ml import priors
from app.simulation.environment import env_train

CONFIG = load_action_config()


def facts(**overrides) -> InvoiceFacts:
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


# --- formula terms, in isolation ---


def test_fatigue_penalty_scales_linearly_below_cap():
    assert fatigue_penalty(0) == 0.0
    assert fatigue_penalty(2) == 0.30


def test_fatigue_penalty_caps_at_point_six():
    assert fatigue_penalty(10) == 0.6
    assert fatigue_penalty(100) == 0.6


def test_higher_probability_increases_ev():
    low = expected_value_paise(0.1, 100_000_00, 5, 2, 0.0)
    high = expected_value_paise(0.5, 100_000_00, 5, 2, 0.0)
    assert high > low


def test_longer_days_to_cash_decreases_ev():
    fast = expected_value_paise(0.4, 100_000_00, 2, 2, 0.0)
    slow = expected_value_paise(0.4, 100_000_00, 60, 2, 0.0)
    assert slow < fast


def test_higher_cost_decreases_ev():
    cheap = expected_value_paise(0.4, 100_000_00, 5, 2, 0.0)
    expensive = expected_value_paise(0.4, 100_000_00, 5, 120_000, 0.0)
    assert expensive < cheap


def test_higher_fatigue_decreases_ev():
    fresh = expected_value_paise(0.4, 100_000_00, 5, 2, 0.0)
    fatigued = expected_value_paise(0.4, 100_000_00, 5, 2, 0.5)
    assert fatigued < fresh


# --- the ladder ---


def test_no_history_has_no_rung_restriction():
    allowed = allowed_actions([], CONFIG)
    assert allowed == set(ActionKey)


def test_cooldown_blocks_recent_repeat():
    history = [ActionHistoryEntry(action=ActionKey.send_reminder, days_ago=2)]
    allowed = allowed_actions(history, CONFIG)
    assert ActionKey.send_reminder not in allowed  # cooldown is 5 days


def test_cooldown_expires():
    history = [ActionHistoryEntry(action=ActionKey.send_reminder, days_ago=10)]
    allowed = allowed_actions(history, CONFIG)
    # 10 days > 5-day cooldown, and this is the current (only) rung, so a
    # same-rung repeat is allowed
    assert ActionKey.send_reminder in allowed


def test_max_executions_blocks_even_after_cooldown():
    history = [
        ActionHistoryEntry(action=ActionKey.send_reminder, days_ago=100),
        ActionHistoryEntry(action=ActionKey.send_reminder, days_ago=50),
    ]
    allowed = allowed_actions(history, CONFIG)
    assert ActionKey.send_reminder not in allowed  # max_executions_per_action = 2


def test_ladder_never_moves_down():
    # most recent action is resend_payment_link (ladder index 1)
    history = [ActionHistoryEntry(action=ActionKey.resend_payment_link, days_ago=10)]
    allowed = allowed_actions(history, CONFIG)
    assert ActionKey.send_reminder not in allowed  # index 0, below current rung 1


def test_ladder_never_skips_more_than_one_rung():
    history = [ActionHistoryEntry(action=ActionKey.resend_payment_link, days_ago=10)]
    allowed = allowed_actions(history, CONFIG)
    assert ActionKey.escalate_to_am not in allowed  # far above current+1
    assert ActionKey.offer_payment_plan not in allowed


def test_ladder_allows_current_and_next_rung():
    history = [ActionHistoryEntry(action=ActionKey.resend_payment_link, days_ago=10)]
    allowed = allowed_actions(history, CONFIG)
    assert ActionKey.resend_payment_link in allowed  # same rung, cooldown expired
    assert ActionKey.send_upi_payment_link in allowed  # one rung forward


def test_ladder_uses_the_furthest_rung_when_two_actions_share_a_timestamp():
    # Found live: under this project's frozen demo clock, two genuinely
    # different real actions executed in the same tick (a manual /act
    # immediately followed by another) get the IDENTICAL days_ago -- an
    # unresolvable tie for "most recent". The old implementation
    # (min(history, key=days_ago)) silently picked whichever entry
    # happened to come first in the list, which could be the EARLIER
    # rung, incorrectly narrowing the "advance one rung" window and
    # blocking a rung that should have been legitimately reachable.
    # send_upi_payment_link (rung 2) and schedule_call (rung 3) both at
    # days_ago=0, in an order that would previously have picked rung 2 as
    # "current" -- offer_payment_plan (rung 4) must still be reachable,
    # since the ladder's real position is rung 3, not rung 2.
    history = [
        ActionHistoryEntry(action=ActionKey.send_upi_payment_link, days_ago=0),
        ActionHistoryEntry(action=ActionKey.schedule_call, days_ago=0),
    ]
    allowed = allowed_actions(history, CONFIG)
    assert ActionKey.offer_payment_plan in allowed
    assert ActionKey.send_reminder not in allowed  # still never moves down


@given(
    days_ago=st.integers(min_value=0, max_value=200),
    rung_index=st.integers(min_value=0, max_value=5),
)
def test_ladder_monotonicity_property(days_ago, rung_index):
    """No matter the history, allowed_actions() never permits a rung below
    the current one, and never more than one rung above it."""
    current_action = CONFIG.ladder[rung_index]
    history = [ActionHistoryEntry(action=current_action, days_ago=days_ago)]
    allowed = allowed_actions(history, CONFIG)
    for i, action in enumerate(CONFIG.ladder):
        if action in allowed:
            assert i >= rung_index
            assert i <= rung_index + 1


# --- prior_v1 ---


def test_prior_v1_is_not_equal_to_environment_table():
    env_table = env_train().base_prob
    assert priors.PRIOR_V1 != env_table


def test_prior_v1_covers_every_diagnosis_and_action():
    for code in DiagnosisCode:
        preds = priors.predict(code)
        assert set(preds.keys()) == set(ActionKey)
        for p in preds.values():
            assert 0.0 <= p <= 1.0


def test_prior_v1_predict_returns_a_copy_not_a_reference():
    preds = priors.predict(DiagnosisCode.cash_flow_risk)
    preds[ActionKey.send_reminder] = -999.0
    assert priors.PRIOR_V1[DiagnosisCode.cash_flow_risk][ActionKey.send_reminder] != -999.0


# --- escalate_to_am never wins below Rs 50,000 (empirical, on real priors) ---


def test_escalate_to_am_never_wins_below_50k():
    """Using prior_v1's actual predicted probabilities (not arbitrary p
    combinations — see plan.md's own framing of this gate as a realistic
    property, not a universal one over any possible p).
    """
    for code in DiagnosisCode:
        preds = priors.predict(code)
        small_invoice = facts(amount_paise=15_000_00, contact_count_30d=0)  # Rs 15,000
        ranked = rank_actions(small_invoice, preds, CONFIG, history=[])
        top = ranked[0]
        assert top.action != ActionKey.escalate_to_am, (
            f"{code}: escalate_to_am won on a Rs 15,000 invoice (ev={top.ev_paise})"
        )


def test_rank_actions_orders_by_ev_descending():
    preds = priors.predict(DiagnosisCode.cash_flow_risk)
    ranked = rank_actions(facts(), preds, CONFIG, history=[])
    ev_values = [r.ev_paise for r in ranked]
    assert ev_values == sorted(ev_values, reverse=True)
    assert len(ranked) == len(ActionKey)
