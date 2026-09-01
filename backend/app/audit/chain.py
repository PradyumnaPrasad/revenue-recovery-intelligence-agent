"""Hash-chained audit ledger — plan.md §6.10 / §4.3.

Each event's hash = sha256(prev_hash + canonical_json(payload)). Per-invoice
chain (chain scope is `invoice_id`, genesis events use a fixed root). This
turns "we log everything" into "we can prove the log wasn't edited after
the fact" — `verify_chain` recomputes every hash and will catch a single
mutated payload anywhere in the chain.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

GENESIS_HASH = "0" * 64


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def compute_hash(prev_hash: str, payload: dict[str, Any]) -> str:
    body = f"{prev_hash}{canonical_json(payload)}".encode("utf-8")
    return hashlib.sha256(body).hexdigest()


@dataclass
class ChainableEvent:
    kind: str
    payload: dict[str, Any]
    created_at: datetime
    actor: str = "system"
    policy_version: str | None = None
    idempotency_key: str | None = None
    prev_hash: str = GENESIS_HASH
    hash: str = ""

    def sealed(self) -> "ChainableEvent":
        self.hash = compute_hash(self.prev_hash, self.payload)
        return self


def next_event(
    prev_hash: str,
    kind: str,
    payload: dict[str, Any],
    created_at: datetime,
    actor: str = "system",
    policy_version: str | None = None,
    idempotency_key: str | None = None,
) -> ChainableEvent:
    event = ChainableEvent(
        kind=kind,
        payload=payload,
        created_at=created_at,
        actor=actor,
        policy_version=policy_version,
        idempotency_key=idempotency_key,
        prev_hash=prev_hash,
    )
    return event.sealed()


def verify_chain(events: list[dict[str, Any]]) -> tuple[bool, int]:
    """events: ordered list of dicts with keys prev_hash, hash, payload.
    Returns (intact, events_checked). Stops at the first break.
    """
    expected_prev = GENESIS_HASH
    checked = 0
    for event in events:
        if event["prev_hash"] != expected_prev:
            return False, checked
        recomputed = compute_hash(event["prev_hash"], event["payload"])
        if recomputed != event["hash"]:
            return False, checked
        expected_prev = event["hash"]
        checked += 1
    return True, checked
