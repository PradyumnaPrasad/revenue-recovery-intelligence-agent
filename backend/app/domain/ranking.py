"""Risk-adjusted expected value + escalation ladder — plan.md §6.4.

`EV = p x amount` is wrong four ways: it ignores that a payment plan does
not collect in full today, prices an email and a human escalation
identically at Rs 0, never penalises the eleventh contact this month, and
being a myopic argmax, re-picks the same top action every tick forever.
This module fixes all four: time-discounting, per-action cost, a fatigue
penalty, and a ladder that constrains sequential choice across ticks.

Deliberately a simpler answer than the theoretically correct one (a
contextual bandit or finite-horizon MDP) — see ADR-001. The ladder captures
most of the sequential value, is explainable to a finance team, and is
auditable, which matter more on this track than optimality.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.domain.types import ActionKey, InvoiceFacts

DEFAULT_ACTIONS_PATH = Path(__file__).resolve().parents[2] / "config" / "actions.yaml"


def fatigue_penalty(contact_count_30d: int) -> float:
    """Caps at 0.6 so fatigue suppresses but never fully zeroes an action —
    the hard stop is policy's job (P03), not the scorer's. Keeping soft
    economics and hard constraints in separate layers is what keeps the
    system explainable.
    """
    return min(0.6, 0.15 * contact_count_30d)


def expected_value_paise(
    p: float,
    collectible_paise: int,
    days_to_cash: float,
    action_cost_paise: int,
    fatigue_penalty: float,
    annual_discount_rate: float = 0.12,
) -> int:
    tvm = 1.0 / (1.0 + annual_discount_rate) ** (days_to_cash / 365.0)
    return int(p * collectible_paise * tvm * (1.0 - fatigue_penalty) - action_cost_paise)


@dataclass(frozen=True)
class ActionEconomics:
    collectible_fraction: float
    days_to_cash: float
    cost_paise: int
    cooldown_days: int


@dataclass(frozen=True)
class ActionConfig:
    actions: dict[ActionKey, ActionEconomics]
    ladder: list[ActionKey]
    annual_discount_rate: float
    max_executions_per_action: int


def load_action_config(path: Path = DEFAULT_ACTIONS_PATH) -> ActionConfig:
    raw = yaml.safe_load(path.read_text())
    actions = {
        ActionKey(key): ActionEconomics(
            collectible_fraction=v["collectible_fraction"],
            days_to_cash=v["days_to_cash"],
            cost_paise=v["cost_paise"],
            cooldown_days=v["cooldown_days"],
        )
        for key, v in raw["actions"].items()
    }
    ladder = [ActionKey(a) for a in raw["ladder"]]
    return ActionConfig(
        actions=actions,
        ladder=ladder,
        annual_discount_rate=raw["annual_discount_rate"],
        max_executions_per_action=raw["max_executions_per_action"],
    )


@dataclass(frozen=True)
class ActionHistoryEntry:
    action: ActionKey
    days_ago: int  # how many days before "now" this action was executed


def _current_rung_index(history: list[ActionHistoryEntry], ladder: list[ActionKey]) -> int | None:
    """The furthest point reached on the ladder, or None if this invoice
    has never had an action taken — a brand-new invoice is not forced to
    start at rung 0; the ladder only constrains movement *after* the
    first action, which is why current_rung_index=None skips the
    rung-movement checks entirely in allowed_actions().

    Found live: this used to pick "the most recently executed action" via
    `min(history, key=lambda h: h.days_ago)` — but under this project's
    frozen demo clock, two genuinely different real actions executed in
    the same tick (e.g. a manual /act immediately followed by
    /simulate/tick, or two actions in one autonomous batch run) get the
    identical days_ago, an unresolvable tie for "most recent". min() then
    silently picked whichever entry happened to come first in the list --
    not necessarily the one further along the ladder -- which could
    misidentify the current rung and incorrectly narrow the "advance one
    rung" window, blocking a rung that should have been legitimately
    reachable. Since the ladder only ever moves forward or repeats (never
    backward), the FURTHEST rung any executed action has reached is an
    unambiguous, timestamp-independent definition of "current position" --
    and it's identical to the old chronological definition whenever
    days_ago values are actually distinct, so this only changes behavior
    in the exact tied case that was already broken.
    """
    if not history:
        return None
    return max(ladder.index(h.action) for h in history)


def allowed_actions(
    history: list[ActionHistoryEntry], config: ActionConfig
) -> set[ActionKey]:
    """The ladder-eligible subset of actions right now — cooldowns, max
    executions, and (once at least one action has been taken) the
    never-move-down / at-most-one-rung-forward constraints, all applied.
    """
    current_rung = _current_rung_index(history, config.ladder)
    counts = Counter(h.action for h in history)
    allowed: set[ActionKey] = set()

    for i, action in enumerate(config.ladder):
        if counts[action] >= config.max_executions_per_action:
            continue
        recent_days = [h.days_ago for h in history if h.action == action]
        if recent_days and min(recent_days) < config.actions[action].cooldown_days:
            continue
        if current_rung is not None:
            if i < current_rung:
                continue  # never move down the ladder
            if i > current_rung + 1:
                continue  # never skip more than one rung per cycle
        allowed.add(action)

    return allowed


@dataclass(frozen=True)
class RankedAction:
    action: ActionKey
    p: float
    ev_paise: int
    ladder_eligible: bool


def rank_actions(
    facts: InvoiceFacts,
    predictions: dict[ActionKey, float],
    config: ActionConfig,
    history: list[ActionHistoryEntry],
) -> list[RankedAction]:
    """Every candidate action, ranked by expected value, highest first —
    including ladder-ineligible ones (marked, not dropped). Showing the
    highest-EV action even when it's gated is deliberate (plan.md §6.10):
    it makes the governance layer visible instead of invisible. The caller
    (policy + orchestrator, not yet built) picks the top ladder_eligible
    entry as the actual recommendation.
    """
    fatigue = fatigue_penalty(facts.contact_count_30d)
    eligible = allowed_actions(history, config)

    ranked = []
    for action in ActionKey:
        econ = config.actions[action]
        p = predictions[action]
        ev = expected_value_paise(
            p=p,
            collectible_paise=int(facts.amount_paise * econ.collectible_fraction),
            days_to_cash=econ.days_to_cash,
            action_cost_paise=econ.cost_paise,
            fatigue_penalty=fatigue,
            annual_discount_rate=config.annual_discount_rate,
        )
        ranked.append(
            RankedAction(action=action, p=p, ev_paise=ev, ladder_eligible=action in eligible)
        )

    ranked.sort(key=lambda r: r.ev_paise, reverse=True)
    return ranked
