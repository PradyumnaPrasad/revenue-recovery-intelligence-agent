"""The restricted rule evaluator — plan.md §6.5.

Never eval()/exec() on a config-file string, even our own. simpleeval's
EvalWithCompoundTypes gives attribute access (diagnosis.code) and `in` on
list literals (action.key in [...]) while refusing dunder attributes,
imports, and arbitrary function calls — verified directly (not assumed):
`__import__(...)` raises FunctionNotDefined, and the classic
`().__class__.__bases__[0].__subclasses__()` sandbox-escape raises
FeatureNotAvailable. CI greps for eval(/exec( across app/ as a second line
of defence (plan.md's "Done when" for this layer).
"""
from __future__ import annotations

from typing import Any

from simpleeval import EvalWithCompoundTypes


def evaluate_condition(expression: str, names: dict[str, Any]) -> bool:
    evaluator = EvalWithCompoundTypes(names=names)
    result = evaluator.eval(expression)
    return bool(result)
