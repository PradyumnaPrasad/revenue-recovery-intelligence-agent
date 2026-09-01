"""The fixed, diagnosis-blind dunning cadence every real system already
runs today — plan.md §6.11. This is deliberately the *only* thing this
project compares itself against besides a no-contact holdout: the same
four scripted touchpoints regardless of what's actually wrong with the
invoice.

Lives in `app/domain/` rather than `app/evaluation/` on purpose. It started
life as a private constant inside the three-arm measurement simulation
(`app/evaluation/simulate.py`), but the live dashboard also needs "what
would the naive cadence do to *this* invoice, right now" for the
counterfactual side-by-side shown on the invoice detail pane — that's a
concept about how collections has always worked, not a detail of how this
project measures itself, so it belongs at the domain layer and the
evaluation module imports it, not the other way around.
"""
from __future__ import annotations

from app.domain.types import ActionKey

# D+1 reminder, D+7 reminder, D+15 payment-link resend, D+30 escalate.
# Applied identically regardless of diagnosis — that sameness is precisely
# what this project is measured against.
BASELINE_CADENCE: list[tuple[int, ActionKey]] = [
    (1, ActionKey.send_reminder),
    (7, ActionKey.send_reminder),
    (15, ActionKey.resend_payment_link),
    (30, ActionKey.escalate_to_am),
]


def baseline_next_action(days_overdue: int) -> ActionKey:
    """Which rung of the fixed cadence a naive system would be on right
    now, given only days_overdue — no diagnosis, no history, no policy.

    This is a display-only snapshot for the counterfactual UI, not a
    re-implementation of the three-arm measurement: the measurement
    (`app/evaluation/simulate.py::_simulate_baseline`) walks the full
    scripted sequence touchpoint by touchpoint and tracks whether each one
    actually recovered the invoice. This function only answers "which rung
    would we be on today," for showing next to what the agent actually
    decided.
    """
    current = BASELINE_CADENCE[0][1]
    for scripted_day, action in BASELINE_CADENCE:
        if days_overdue >= scripted_day:
            current = action
        else:
            break
    return current
