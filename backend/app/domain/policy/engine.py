"""Policy engine — plan.md §6.5. Policy has FINAL authority: a model can
rank actions, but only this module decides whether one actually executes.

Every rule is evaluated, every match is collected — never short-circuit on
the first hit. "Blocked for three reasons" is a far better audit record
than "blocked", and it's what makes the explanation object (§6.10) show
the full picture instead of one arbitrary cause.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from app.domain.policy.evaluator import evaluate_condition
from app.domain.policy.types import (
    _SEVERITY,
    ActionContext,
    PolicyContext,
    PolicyReason,
    PolicyResult,
)
from app.domain.types import ActionKey

DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[3] / "policies" / "default.yaml"


@dataclass(frozen=True)
class PolicyRule:
    id: str
    when: str
    then: str  # PolicyOutcome
    reason: str
    with_action: str | None = None  # ActionKey value OR a policy-outcome
    # terminal (route_to_dispute, request_human_approval, stop) — see
    # app/domain/policy/types.py's SubstitutionTarget docstring


@dataclass(frozen=True)
class LoadedPolicy:
    version: str
    rules: list[PolicyRule]


def load_policy(path: Path = DEFAULT_POLICY_PATH) -> LoadedPolicy:
    raw = yaml.safe_load(path.read_text())
    rules = [
        PolicyRule(
            id=r["id"],
            when=r["when"],
            then=r["then"],
            reason=r["reason"],
            with_action=r.get("with"),
        )
        for r in raw["rules"]
    ]
    return LoadedPolicy(version=raw["version"], rules=rules)


def evaluate(policy: LoadedPolicy, context: PolicyContext, action: ActionKey) -> PolicyResult:
    names = {
        "diagnosis": context.diagnosis,
        "customer": context.customer,
        "invoice": context.invoice,
        "batch": context.batch,
        "action": ActionContext(key=action.value),
    }

    matches: list[PolicyReason] = []
    for rule in policy.rules:
        if evaluate_condition(rule.when, names):
            matches.append(
                PolicyReason(
                    rule_id=rule.id,
                    rule_text=rule.when,
                    outcome=rule.then,  # type: ignore[arg-type]
                    reason=rule.reason,
                    substituted_action=rule.with_action,
                )
            )

    if not matches:
        return PolicyResult(
            outcome="allow", substituted_action=None, reasons=[], policy_version=policy.version
        )

    winner = max(matches, key=lambda m: _SEVERITY[m.outcome])
    substituted = winner.substituted_action if winner.outcome == "substitute" else None

    return PolicyResult(
        outcome=winner.outcome,
        substituted_action=substituted,
        reasons=matches,
        policy_version=policy.version,
    )
