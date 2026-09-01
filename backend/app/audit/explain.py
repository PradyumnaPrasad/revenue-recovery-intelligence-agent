"""The explanation object — plan.md §6.10. Every decision must render as
one paragraph a finance person reads without training. The highest-EV
action is shown even when policy gated it — showing what governance took
away is more persuasive than showing only what it allowed, and it's what
makes "compliant escalation" (the track's own bar) visible on screen
instead of asserted in a README.
"""
from __future__ import annotations

from app.domain.policy.types import PolicyResult
from app.domain.ranking import RankedAction
from app.domain.types import Diagnosis


def format_rupees(amount_paise: int) -> str:
    """Indian digit grouping (lakhs/crores — groups of 2 after the first
    group of 3 from the right), not Python's `:,` which groups by 3
    throughout (Western convention). Found as a real, visible
    inconsistency: the dashboard's queue list used the frontend's
    `toLocaleString("en-IN")` while this function used `:,.0f`, so the
    same invoice showed "Rs 3,62,554" in one place and "Rs 362,554" in
    another on the same screen.
    """
    sign = "-" if amount_paise < 0 else ""
    rupees = str(round(abs(amount_paise) / 100))
    if len(rupees) <= 3:
        grouped = rupees
    else:
        last_three = rupees[-3:]
        remainder = rupees[:-3]
        pairs = []
        while len(remainder) > 2:
            pairs.insert(0, remainder[-2:])
            remainder = remainder[:-2]
        if remainder:
            pairs.insert(0, remainder)
        grouped = ",".join(pairs) + "," + last_three
    return f"{sign}₹{grouped}"


def build_explanation(
    invoice_number: str,
    amount_paise: int,
    days_overdue: int,
    diagnosis: Diagnosis,
    ranked: list[RankedAction],
    policy: PolicyResult,
    model_version: str,
) -> dict:
    considered = [
        {
            "action": r.action.value,
            "p": round(r.p, 3),
            "ev": format_rupees(r.ev_paise) if r.ev_paise >= 0 else f"-{format_rupees(-r.ev_paise)}",
            "ev_paise": r.ev_paise,
            "rank": rank,
            "ladder_eligible": r.ladder_eligible,
            **({"note": "highest EV but gated"} if rank == 0 and not r.ladder_eligible else {}),
        }
        for rank, r in enumerate(ranked)
    ]

    top_eligible = next((r for r in ranked if r.ladder_eligible), None)
    recommended_action = top_eligible.action.value if top_eligible else None

    if policy.outcome == "block":
        final = "Blocked — no automated action taken."
    elif policy.outcome == "require_approval":
        final = f"Awaiting human approval for {recommended_action}."
    elif policy.outcome == "substitute":
        final = f"Substituted to {policy.substituted_action} by policy."
    else:
        final = f"Approved — executing {recommended_action}."

    return {
        "invoice": invoice_number,
        "amount": format_rupees(amount_paise),
        "amount_paise": amount_paise,
        "days_overdue": days_overdue,
        "diagnosis": {
            "code": diagnosis.code.value,
            "confidence": diagnosis.confidence,
            "because": diagnosis.signals,
            "rule": diagnosis.rule_id,
            "explanation": diagnosis.explanation,
        },
        "considered": considered,
        "recommended_action": recommended_action,
        "policy": {
            "outcome": policy.outcome,
            "version": policy.policy_version,
            "substituted_action": policy.substituted_action,
            "because": [f"{r.rule_id}: {r.reason}" for r in policy.reasons],
        },
        "model_version": model_version,
        "final": final,
    }
