from datetime import datetime, timezone

from app.audit.chain import GENESIS_HASH, next_event, verify_chain


def _events(n: int):
    events = []
    prev = GENESIS_HASH
    for i in range(n):
        e = next_event(
            prev_hash=prev,
            kind="test_event",
            payload={"i": i, "note": "hello"},
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        events.append(e)
        prev = e.hash
    return events


def test_chain_verifies_intact():
    events = _events(5)
    rows = [{"prev_hash": e.prev_hash, "hash": e.hash, "payload": e.payload} for e in events]
    intact, checked = verify_chain(rows)
    assert intact is True
    assert checked == 5


def test_chain_detects_tampered_payload():
    events = _events(5)
    rows = [{"prev_hash": e.prev_hash, "hash": e.hash, "payload": dict(e.payload)} for e in events]
    rows[2]["payload"]["i"] = 999  # tamper with one payload, downstream hashes now mismatch
    intact, checked = verify_chain(rows)
    assert intact is False
    assert checked == 2  # first two events still verify before the break


def test_chain_detects_reordering():
    events = _events(3)
    rows = [{"prev_hash": e.prev_hash, "hash": e.hash, "payload": e.payload} for e in events]
    rows[0], rows[1] = rows[1], rows[0]
    intact, _ = verify_chain(rows)
    assert intact is False


def test_empty_chain_is_intact():
    intact, checked = verify_chain([])
    assert intact is True
    assert checked == 0
