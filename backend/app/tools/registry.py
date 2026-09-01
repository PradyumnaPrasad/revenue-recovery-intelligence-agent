"""The typed tool registry — plan.md §6.9. Every action either makes a
real Razorpay call or writes an internal record; nothing in between, and
nothing that silently does both. Tool names deliberately mirror the
official Razorpay MCP server's naming (create_payment_link, ...) — plan.md
§6.9's stated reason: this agent could point at the real MCP server behind
this same interface with a config flag, not a rewrite.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.domain.types import ActionKey
from app.tools.razorpay_client import RazorpayError, create_payment_link

_razorpay_down = False


def set_razorpay_down(down: bool) -> None:
    """The Razorpay half of the chaos switch (plan.md §6.8) — separate
    flag from the LLM's, since a real chaos demo turns off each
    independently.
    """
    global _razorpay_down
    _razorpay_down = down


def is_razorpay_down() -> bool:
    return _razorpay_down


_REAL_RAZORPAY_ACTIONS = {ActionKey.resend_payment_link, ActionKey.send_upi_payment_link}


@dataclass
class ToolResult:
    tool_name: str
    request: dict
    response: dict
    success: bool


def execute_tool(action: str, invoice_id: str, invoice_number: str, amount_paise: int) -> ToolResult:
    """`action` is a plain string, not ActionKey, because a policy
    substitution can target a policy-outcome terminal (route_to_dispute,
    request_human_approval, stop) that ActionKey deliberately excludes —
    see app/domain/policy/types.py's SubstitutionTarget.
    """
    if action in {a.value for a in _REAL_RAZORPAY_ACTIONS}:
        request = {"amount_paise": amount_paise, "description": f"Payment for {invoice_number}"}
        if is_razorpay_down():
            return ToolResult(
                tool_name="razorpay.create_payment_link",
                request=request,
                response={"error": "chaos switch: razorpay marked down"},
                success=False,
            )
        try:
            response = create_payment_link(amount_paise, f"Payment for {invoice_number}")
            return ToolResult(
                tool_name="razorpay.create_payment_link", request=request, response=response, success=True
            )
        except RazorpayError as e:
            return ToolResult(
                tool_name="razorpay.create_payment_link",
                request=request,
                response={"error": str(e)},
                success=False,
            )

    if action == ActionKey.send_reminder.value:
        return ToolResult(
            tool_name="console.send_reminder",
            request={"invoice_number": invoice_number},
            response={"sent": True, "channel": "console"},
            success=True,
        )

    # Everything else (schedule_call, offer_payment_plan, escalate_to_am,
    # route_to_dispute, request_human_approval, stop) is an internal record
    # — a queue entry, not an external call. One handler covers all of
    # them because the "tool" is genuinely the same shape: write a fact,
    # no external side effect.
    return ToolResult(
        tool_name=f"internal.{action}",
        request={"invoice_number": invoice_number, "amount_paise": amount_paise},
        response={"recorded": True},
        success=True,
    )
