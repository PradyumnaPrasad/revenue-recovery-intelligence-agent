"""The real accuracy spot-check — plan.md D2/D6. Generates labelled
fixtures from the actual template bank (app/simulation/reply_templates.py),
runs each through the live Gemini extraction call, and reports the honest
number. Makes real network calls — not part of the fast pytest suite.

Run via: python -m app.llm.spot_check
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date, timedelta

from faker import Faker

from app.llm.reply_extraction import extract_reply
from app.llm.redact import contains_raw_pii
from app.simulation.reply_templates import TEMPLATE_BANK

FIXTURES_PER_LABEL = 8  # 8 labels x 8 = ~60 fixtures, matching plan.md's target


@dataclass
class Fixture:
    text: str
    true_label: str
    true_date: date | None


def _fill(template: str, fake: Faker, rng_seed: int) -> tuple[str, date | None]:
    fake.seed_instance(rng_seed)
    promised = fake.date_between(start_date="+2d", end_date="+20d")
    amount = f"Rs {fake.random_int(min=5_000, max=500_000):,}"
    other_ref = f"INV-{fake.random_int(min=1000, max=1999)}"
    text = template.format(date=promised.strftime("%d %b"), amount=amount, other_ref=other_ref)
    has_date = "{date}" in template
    return text, (promised if has_date else None)


def build_fixtures() -> list[Fixture]:
    fake = Faker()
    fixtures = []
    seed = 0
    for label, templates in TEMPLATE_BANK.items():
        for i in range(FIXTURES_PER_LABEL):
            template = templates[i % len(templates)]
            text, true_date = _fill(template, fake, seed)
            fixtures.append(Fixture(text=text, true_label=label, true_date=true_date))
            seed += 1
    return fixtures


def run_spot_check() -> None:
    fixtures = build_fixtures()
    print(f"Running {len(fixtures)} fixtures against the live Gemini API...\n")

    correct_intent = 0
    date_checked = 0
    date_correct = 0
    rejected = 0
    pii_leaks = 0
    low_confidence = 0

    for i, fx in enumerate(fixtures, 1):
        result = extract_reply(fx.text)
        if contains_raw_pii(result.redacted_text):
            pii_leaks += 1

        if result.extraction is None:
            rejected += 1
            print(f"[{i:2d}/{len(fixtures)}] REJECTED ({result.rejected_reason}) — true={fx.true_label}")
            continue

        ex = result.extraction
        intent_ok = ex.intent == fx.true_label
        if intent_ok:
            correct_intent += 1
        if ex.confidence < 0.6:
            low_confidence += 1

        date_note = ""
        if fx.true_date is not None:
            date_checked += 1
            if ex.promised_date == fx.true_date:
                date_correct += 1
                date_note = " date=OK"
            else:
                date_note = f" date=MISMATCH(got {ex.promised_date}, want {fx.true_date})"

        mark = "OK " if intent_ok else "ERR"
        print(
            f"[{i:2d}/{len(fixtures)}] {mark} true={fx.true_label:<20s} got={ex.intent:<20s} "
            f"conf={ex.confidence:.2f}{date_note}"
        )

    n = len(fixtures)
    print("\n" + "=" * 60)
    print(f"Intent accuracy:     {correct_intent}/{n} = {correct_intent/n:.1%}  (target >= 85%)")
    if date_checked:
        print(f"Date exact-match:    {date_correct}/{date_checked} = {date_correct/date_checked:.1%}  (target >= 80%)")
    print(f"Rejected (schema/quote failure): {rejected}/{n}")
    print(f"Low confidence (<0.6):           {low_confidence}/{n}")
    print(f"Raw PII detected in outbound payload: {pii_leaks}/{n}  (target: 0)")
    print("=" * 60)


if __name__ == "__main__":
    run_spot_check()
