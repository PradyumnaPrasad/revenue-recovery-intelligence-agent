"""Deterministic arm assignment — plan.md §4.3.

Arm is derived from sha256(invoice_id + experiment_salt) % 100, NOT random.
This is deliberate: it makes assignment reproducible (same invoice always
lands in the same arm across re-runs) and immune to the accusation that
arms were re-rolled until the holdout/agent split looked favourable.
"""
from __future__ import annotations

import hashlib

from app.domain.types import Arm

EXPERIMENT_SALT = "rria-v1"

# 70% agent / 20% baseline / 10% holdout
_AGENT_CUTOFF = 70
_BASELINE_CUTOFF = 90  # 70..89 -> baseline, 90..99 -> holdout


def assignment_hash(invoice_id: str) -> str:
    return hashlib.sha256(f"{invoice_id}{EXPERIMENT_SALT}".encode()).hexdigest()


def assign_arm(invoice_id: str) -> tuple[Arm, str]:
    h = assignment_hash(invoice_id)
    bucket = int(h[:8], 16) % 100
    if bucket < _AGENT_CUTOFF:
        arm = Arm.agent
    elif bucket < _BASELINE_CUTOFF:
        arm = Arm.baseline
    else:
        arm = Arm.holdout
    return arm, h
