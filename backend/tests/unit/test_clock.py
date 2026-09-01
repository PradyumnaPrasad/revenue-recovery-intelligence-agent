from datetime import datetime, timezone

from app.domain.clock import RealClock, VirtualClock


def test_virtual_clock_only_moves_on_advance():
    c = VirtualClock(start=datetime(2026, 1, 1, tzinfo=timezone.utc))
    t0 = c.now()
    t1 = c.now()
    assert t0 == t1

    c.advance(days=45)
    t2 = c.now()
    assert (t2 - t0).days == 45


def test_two_virtual_clocks_are_independent():
    a = VirtualClock(start=datetime(2026, 1, 1, tzinfo=timezone.utc))
    b = VirtualClock(start=datetime(2026, 1, 1, tzinfo=timezone.utc))
    a.advance(days=10)
    assert a.now() != b.now()


def test_real_clock_is_close_to_wall_time():
    import time

    c = RealClock()
    before = time.time()
    now = c.now().timestamp()
    after = time.time()
    assert before - 1 <= now <= after + 1
