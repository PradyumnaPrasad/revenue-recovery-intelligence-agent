"""The chaos switch — plan.md §6.8. A deliberate, demoable failure toggle,
not just a hope that failures are handled. `POST /demo/chaos?llm=down`
(wiring pending the dashboard/API layer) calls set_llm_down(True); every
subsequent extract_reply() call degrades to the keyword fallback instead of
calling Gemini at all.
"""
from __future__ import annotations

_llm_down = False


def set_llm_down(down: bool) -> None:
    global _llm_down
    _llm_down = down


def is_llm_down() -> bool:
    return _llm_down
