"""app/domain/baseline.py — the fixed cadence shown as a counterfactual
next to the agent's actual decision. Same rungs as
app/evaluation/simulate.py's baseline arm; this tests the standalone
lookup used by the live dashboard, not the measurement itself.
"""
from __future__ import annotations

from app.domain.baseline import BASELINE_CADENCE, baseline_next_action
from app.domain.types import ActionKey


def test_before_first_rung_defaults_to_first_action():
    assert baseline_next_action(0) == ActionKey.send_reminder


def test_exactly_on_a_rung_boundary_uses_that_rung():
    assert baseline_next_action(7) == ActionKey.send_reminder
    assert baseline_next_action(15) == ActionKey.resend_payment_link
    assert baseline_next_action(30) == ActionKey.escalate_to_am


def test_between_rungs_uses_the_most_recent_one_passed():
    assert baseline_next_action(10) == ActionKey.send_reminder
    assert baseline_next_action(20) == ActionKey.resend_payment_link


def test_far_past_last_rung_stays_on_last_rung():
    assert baseline_next_action(365) == ActionKey.escalate_to_am


def test_cadence_matches_the_measurement_arm_exactly():
    # app/evaluation/simulate.py imports BASELINE_CADENCE from here — this
    # guards against the two ever silently drifting into two different
    # definitions of "baseline."
    from app.evaluation.simulate import _BASELINE_CADENCE

    assert _BASELINE_CADENCE is BASELINE_CADENCE
