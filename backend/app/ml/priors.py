"""prior_v1 — the deterministic stand-in for a trained model (ADR-002,
plan.md §6.4).

Why no trained model at all: this project publishes its decision
environment (app/simulation/environment.py, docs/environment.md) to defeat
circular evaluation. A logistic regression trained on samples from that
published environment would just be re-estimating numbers already printed
in this repo — real engineering effort for zero information gain. Instead:
a published, versioned prior table, stamped on every decision, that a real
model could later replace behind the same `predict()` signature with zero
changes to any caller.

Deliberately NOT equal to the environment's true table — that would make
this an oracle. Every cell is perturbed by a fixed, documented +/-15% (seed
below, so the perturbation is itself reproducible and auditable, not a
fresh random draw on every import). The agent works from this approximate
belief; the gap between this table and the true environment is exactly
what makes the E_shift and E_adversarial robustness results mean anything.
"""
from __future__ import annotations

import numpy as np

from app.domain.types import ActionKey, DiagnosisCode
from app.simulation.environment import env_train

MODEL_VERSION = "prior_v1"
_PERTURBATION_SEED = 20260831
_PERTURBATION_MAGNITUDE = 0.15


def _build_prior_table() -> dict[DiagnosisCode, dict[ActionKey, float]]:
    base = env_train().base_prob
    rng = np.random.default_rng(_PERTURBATION_SEED)
    table: dict[DiagnosisCode, dict[ActionKey, float]] = {}
    for code, actions in base.items():
        table[code] = {}
        for action, p in actions.items():
            factor = 1.0 + rng.uniform(-_PERTURBATION_MAGNITUDE, _PERTURBATION_MAGNITUDE)
            table[code][action] = float(np.clip(p * factor, 0.02, 0.95))
    return table


PRIOR_V1: dict[DiagnosisCode, dict[ActionKey, float]] = _build_prior_table()


def predict(diagnosis_code: DiagnosisCode) -> dict[ActionKey, float]:
    """The only sanctioned way to get a recovery-probability prediction.
    Returns a fresh dict copy per call so callers can't mutate the module-
    level table.
    """
    return dict(PRIOR_V1[diagnosis_code])
