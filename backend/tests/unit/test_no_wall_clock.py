"""CI guard for plan.md §6.9: `datetime.now()` / `datetime.utcnow()` must
never appear in app/domain/ — all "now" comes from an injected Clock so
domain logic stays deterministic and testable.
"""
import re
from pathlib import Path

DOMAIN_DIR = Path(__file__).resolve().parents[2] / "app" / "domain"
FORBIDDEN = re.compile(r"datetime\.(now|utcnow)\(")


def test_no_wall_clock_calls_in_domain():
    offenders = []
    for path in DOMAIN_DIR.rglob("*.py"):
        if path.name == "clock.py":
            continue  # the clock module itself is allowed to call wall time
        text = path.read_text()
        if FORBIDDEN.search(text):
            offenders.append(str(path))
    assert not offenders, f"datetime.now()/utcnow() found outside clock.py: {offenders}"
