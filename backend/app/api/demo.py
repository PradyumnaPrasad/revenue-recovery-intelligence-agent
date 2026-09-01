"""The chaos switch's API surface — plan.md §6.8. Toggles the same
process-wide flags extract_reply() and execute_tool() already check on
every call; nothing here is a separate code path from the real one.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.llm.chaos import is_llm_down, set_llm_down
from app.tools.registry import is_razorpay_down, set_razorpay_down

router = APIRouter(tags=["demo"])


def _status() -> dict:
    return {"llm_down": is_llm_down(), "razorpay_down": is_razorpay_down()}


@router.get("/demo/chaos")
async def get_chaos():
    return _status()


@router.post("/demo/chaos")
async def set_chaos(llm: bool | None = None, razorpay: bool | None = None):
    if llm is not None:
        set_llm_down(llm)
    if razorpay is not None:
        set_razorpay_down(razorpay)
    return _status()
