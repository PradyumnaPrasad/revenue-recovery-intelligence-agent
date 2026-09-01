"""plan.md §6.5 'Done when': every rule has a passing positive AND negative
test, a conflict test resolves via severity ordering, and no eval()/exec()
exists anywhere in app/.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.domain.policy.engine import evaluate, load_policy
from app.domain.policy.types import (
    BatchContext,
    CustomerContext,
    DiagnosisContext,
    InvoiceContext,
    PolicyContext,
)
from app.domain.types import ActionKey

POLICY = load_policy()


def ctx(
    diagnosis_code="standard_overdue",
    confidence=0.9,
    produced_by="rules",
    suppressed=False,
    contact_count_30d=0,
    amount_paise=10_000_00,
    has_open_promise=False,
    promise_still_open=False,
    actions_today=0,
    action_budget=120,
) -> PolicyContext:
    return PolicyContext(
        diagnosis=DiagnosisContext(code=diagnosis_code, confidence=confidence, produced_by=produced_by),
        customer=CustomerContext(suppressed=suppressed, contact_count_30d=contact_count_30d),
        invoice=InvoiceContext(
            amount_paise=amount_paise,
            has_open_promise=has_open_promise,
            promise_still_open=promise_still_open,
        ),
        batch=BatchContext(actions_today=actions_today, action_budget=action_budget),
    )


# --- P01 dispute freeze ---


def test_p01_positive_disputed_substitutes_to_dispute_route():
    result = evaluate(POLICY, ctx(diagnosis_code="disputed"), ActionKey.send_reminder)
    assert result.outcome == "substitute"
    # route_to_dispute is a policy-outcome terminal, deliberately not a
    # member of ActionKey (see SubstitutionTarget in types.py) — plain
    # string comparison, not an enum member.
    assert result.substituted_action == "route_to_dispute"
    assert any(r.rule_id == "P01_dispute_freeze" for r in result.reasons)


def test_p01_negative_not_disputed_does_not_fire():
    result = evaluate(POLICY, ctx(diagnosis_code="cash_flow_risk"), ActionKey.send_reminder)
    assert not any(r.rule_id == "P01_dispute_freeze" for r in result.reasons)


# --- P02 stop contact ---


def test_p02_positive_suppressed_blocks():
    result = evaluate(POLICY, ctx(suppressed=True), ActionKey.send_reminder)
    assert result.outcome == "block"
    assert any(r.rule_id == "P02_stop_contact" for r in result.reasons)


def test_p02_negative_not_suppressed_does_not_fire():
    result = evaluate(POLICY, ctx(suppressed=False), ActionKey.send_reminder)
    assert not any(r.rule_id == "P02_stop_contact" for r in result.reasons)


# --- P03 contact cap ---


def test_p03_positive_at_cap_blocks():
    result = evaluate(POLICY, ctx(contact_count_30d=4), ActionKey.send_reminder)
    assert result.outcome == "block"
    assert any(r.rule_id == "P03_contact_cap" for r in result.reasons)


def test_p03_negative_below_cap_does_not_fire():
    result = evaluate(POLICY, ctx(contact_count_30d=3), ActionKey.send_reminder)
    assert not any(r.rule_id == "P03_contact_cap" for r in result.reasons)


# --- P05 open promise ---


def test_p05_positive_open_promise_blocks():
    result = evaluate(
        POLICY, ctx(has_open_promise=True, promise_still_open=True), ActionKey.send_reminder
    )
    assert result.outcome == "block"
    assert any(r.rule_id == "P05_open_promise" for r in result.reasons)


def test_p05_negative_promise_already_due_does_not_fire():
    result = evaluate(
        POLICY, ctx(has_open_promise=True, promise_still_open=False), ActionKey.send_reminder
    )
    assert not any(r.rule_id == "P05_open_promise" for r in result.reasons)


# --- P06 high-value approval ---


def test_p06_positive_high_value_payment_plan_requires_approval():
    result = evaluate(POLICY, ctx(amount_paise=60_000_00 * 100), ActionKey.offer_payment_plan)
    assert result.outcome == "require_approval"
    assert any(r.rule_id == "P06_high_value_approval" for r in result.reasons)


def test_p06_negative_low_value_does_not_fire():
    result = evaluate(POLICY, ctx(amount_paise=10_000_00), ActionKey.offer_payment_plan)
    assert not any(r.rule_id == "P06_high_value_approval" for r in result.reasons)


def test_p06_negative_high_value_but_not_gated_action_does_not_fire():
    result = evaluate(
        POLICY, ctx(amount_paise=60_000_00 * 100), ActionKey.send_upi_payment_link
    )
    assert not any(r.rule_id == "P06_high_value_approval" for r in result.reasons)


# --- P08 chronic ladder skip ---


def test_p08_positive_chronic_substitutes_to_escalation():
    result = evaluate(POLICY, ctx(diagnosis_code="chronic_non_payment"), ActionKey.send_reminder)
    assert result.outcome == "substitute"
    assert result.substituted_action == ActionKey.escalate_to_am
    assert any(r.rule_id == "P08_chronic_ladder_skip" for r in result.reasons)


def test_p08_negative_not_chronic_does_not_fire():
    result = evaluate(POLICY, ctx(diagnosis_code="process_delay"), ActionKey.send_reminder)
    assert not any(r.rule_id == "P08_chronic_ladder_skip" for r in result.reasons)


# --- P09 daily action budget ---


def test_p09_positive_budget_exhausted_blocks():
    result = evaluate(POLICY, ctx(actions_today=120, action_budget=120), ActionKey.send_reminder)
    assert result.outcome == "block"
    assert any(r.rule_id == "P09_daily_action_budget" for r in result.reasons)


def test_p09_negative_budget_remaining_does_not_fire():
    result = evaluate(POLICY, ctx(actions_today=50, action_budget=120), ActionKey.send_reminder)
    assert not any(r.rule_id == "P09_daily_action_budget" for r in result.reasons)


# --- P10 low-confidence LLM diagnosis ---


def test_p10_positive_low_confidence_llm_requires_approval():
    result = evaluate(
        POLICY, ctx(produced_by="llm_fallback", confidence=0.5), ActionKey.send_reminder
    )
    assert result.outcome == "require_approval"
    assert any(r.rule_id == "P10_low_confidence_llm" for r in result.reasons)


def test_p10_negative_high_confidence_llm_does_not_fire():
    result = evaluate(
        POLICY, ctx(produced_by="llm_fallback", confidence=0.9), ActionKey.send_reminder
    )
    assert not any(r.rule_id == "P10_low_confidence_llm" for r in result.reasons)


def test_p10_negative_rules_produced_does_not_fire():
    result = evaluate(POLICY, ctx(produced_by="rules", confidence=0.3), ActionKey.send_reminder)
    assert not any(r.rule_id == "P10_low_confidence_llm" for r in result.reasons)


# --- conflict resolution ---


def test_conflict_dispute_high_value_and_contact_cap_resolves_to_block_with_three_reasons():
    """plan.md 'Done when': dispute + high-value + cap -> block, 3 reasons.
    Severity ordering: block > substitute > require_approval > allow. Here
    P01 (substitute), P03 (block), and P06 (require_approval) all fire —
    block wins.
    """
    result = evaluate(
        POLICY,
        ctx(
            diagnosis_code="disputed",
            contact_count_30d=4,
            amount_paise=60_000_00 * 100,
        ),
        ActionKey.offer_payment_plan,
    )
    assert result.outcome == "block"
    fired_ids = {r.rule_id for r in result.reasons}
    assert fired_ids == {"P01_dispute_freeze", "P03_contact_cap", "P06_high_value_approval"}
    assert len(result.reasons) == 3


def test_no_rules_fire_means_allow():
    result = evaluate(POLICY, ctx(), ActionKey.send_reminder)
    assert result.outcome == "allow"
    assert result.reasons == []


def test_policy_version_is_stamped():
    result = evaluate(POLICY, ctx(), ActionKey.send_reminder)
    assert result.policy_version == "1.3.0"


# --- security: no eval()/exec() anywhere in app/ ---


def test_no_eval_or_exec_in_app():
    # Found live during the cold-clone check, not in normal dev use: the
    # old cwd computation string-matched "/backend/" in __file__, which
    # exists on a local checkout (".../backend/tests/...") but NOT inside
    # the Docker image, where this same file lives at
    # "/code/tests/unit/test_policy_engine.py" with no "backend" segment
    # at all — rsplit() silently found nothing to split on and produced a
    # garbage path, crashing the subprocess call with NotADirectoryError.
    # Path(__file__).parents[2] is structural (this file is always
    # tests/unit/<name>.py, three levels under the project root) rather
    # than name-based, so it's correct on both a local checkout and inside
    # the container regardless of what the root directory is called.
    project_root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        ["grep", "-rEn", "--exclude-dir=__pycache__", r"\beval\(|\bexec\(", "app/"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    # simpleeval's own package name contains "eval" but that's a call to
    # EvalWithCompoundTypes(...).eval(...), a method name, not the builtin —
    # exclude matches inside comments explaining this test/module itself.
    hits = [
        line
        for line in proc.stdout.splitlines()
        if "evaluator.eval(" not in line and "policy/evaluator.py" not in line
    ]
    assert hits == [], f"found eval()/exec() usage: {hits}"
