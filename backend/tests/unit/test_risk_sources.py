"""plan.md §6.0 'Done when': a second source registers with zero pipeline
edits. ReceivablesSource needs a live Postgres session (JSONB/enum
columns don't run against sqlite) — verified live against the docker
stack instead, same pattern this project already uses for every other
DB-touching check (see plan.md's F1/F6/F7/F9/F10 verification notes).
CheckoutAbandonmentSource needs no DB at all, so it's tested here directly.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.domain.types import RiskEvent
from app.sources.base import RiskSource
from app.sources.checkout_abandonment import CheckoutAbandonmentSource
from app.sources.receivables import ReceivablesSource
from app.sources.registry import RISK_SOURCES


def test_registry_has_both_sources_under_distinct_keys():
    assert set(RISK_SOURCES.keys()) == {"receivables", "checkout_abandonment"}
    assert RISK_SOURCES["receivables"].key == "receivables"
    assert RISK_SOURCES["checkout_abandonment"].key == "checkout_abandonment"


def test_both_sources_satisfy_the_same_protocol_shape():
    """Structural check, not isinstance — RiskSource is a Protocol. Every
    registered source must expose the same `key` attribute and `detect`
    coroutine method, regardless of how different their underlying domain
    object is (an invoice vs. an order).
    """
    for source in RISK_SOURCES.values():
        assert isinstance(source.key, str) and source.key
        assert asyncio.iscoroutinefunction(source.detect)


def test_checkout_abandonment_stub_needs_no_database():
    source = CheckoutAbandonmentSource()
    events = asyncio.run(source.detect(session=None, now=datetime.now(timezone.utc)))
    assert len(events) == 2
    for e in events:
        assert isinstance(e, RiskEvent)
        assert e.source == "checkout_abandonment"
        assert e.amount_at_risk_paise > 0
        assert e.reference_id.startswith("order_")


def test_checkout_abandonment_is_deterministic_across_calls():
    """The same 'no double-emit across ticks' property receivables gets
    from querying live DB state — the stub gets it from returning a fixed
    declared list every time, which is the honest, stated version of the
    same guarantee for a source with no real backing table yet.
    """
    source = CheckoutAbandonmentSource()
    now = datetime.now(timezone.utc)
    first = asyncio.run(source.detect(session=None, now=now))
    second = asyncio.run(source.detect(session=None, now=now))
    assert [e.reference_id for e in first] == [e.reference_id for e in second]


def test_receivables_source_is_importable_and_matches_protocol_shape():
    """The live DB-backed behaviour (one event per overdue invoice, no
    duplicates across repeated ticks) is verified against the real docker
    Postgres instance — this test only confirms the class is wired
    correctly without needing a live session.
    """
    source = ReceivablesSource()
    assert source.key == "receivables"
    assert asyncio.iscoroutinefunction(source.detect)
