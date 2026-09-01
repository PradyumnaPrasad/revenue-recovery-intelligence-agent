"""Policy contracts — plan.md §6.5.

Context objects are the ONLY namespace a policy rule's `when` string can
see (via app/domain/policy/evaluator.py). Every value here is precomputed
by the caller before evaluation — in particular, InvoiceContext.
promise_still_open is `has_open_promise AND today <= promised_date`,
computed once upstream, so the policy expression itself never touches a
clock, a date comparison, or a possibly-absent promise object. That keeps
the evaluator's job to pure attribute/comparison/boolean logic, nothing
temporal or nullable to get wrong inside a config file.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

PolicyOutcome = Literal["allow", "require_approval", "block", "substitute"]

# A policy `substitute` rule may target either a real revenue ActionKey
# (P08 substitutes to escalate_to_am, itself a candidate for future
# ranking) or one of the three POLICY-OUTCOME terminals that ActionKey
# deliberately excludes (P01 substitutes to route_to_dispute — see
# app/domain/types.py's ActionKey docstring for why those three are kept
# out of the ranked-action enum). Plain str rather than a second enum:
# the ranking layer never receives these values as candidates to score,
# only the orchestrator (not yet built) reads them to decide which queue
# an invoice lands in.
SubstitutionTarget = str

# Severity ordering on conflict (plan.md §6.5) — used to resolve the final
# outcome when multiple rules match with different outcomes.
_SEVERITY: dict[PolicyOutcome, int] = {
    "block": 3,
    "substitute": 2,
    "require_approval": 1,
    "allow": 0,
}


class DiagnosisContext(BaseModel):
    code: str
    confidence: float
    produced_by: str


class CustomerContext(BaseModel):
    suppressed: bool
    contact_count_30d: int


class InvoiceContext(BaseModel):
    amount_paise: int
    has_open_promise: bool
    promise_still_open: bool


class BatchContext(BaseModel):
    actions_today: int
    action_budget: int


class ActionContext(BaseModel):
    key: str


class PolicyContext(BaseModel):
    diagnosis: DiagnosisContext
    customer: CustomerContext
    invoice: InvoiceContext
    batch: BatchContext


class PolicyReason(BaseModel):
    rule_id: str
    rule_text: str
    outcome: PolicyOutcome
    reason: str
    substituted_action: SubstitutionTarget | None = None


class PolicyResult(BaseModel):
    outcome: PolicyOutcome
    substituted_action: SubstitutionTarget | None
    reasons: list[PolicyReason]
    policy_version: str
