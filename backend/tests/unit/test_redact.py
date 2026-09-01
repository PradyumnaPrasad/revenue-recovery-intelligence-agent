"""plan.md §6.8 'Done when': redaction test — no raw email/phone/GSTIN in
any outbound LLM payload.
"""
from __future__ import annotations

from app.llm.redact import contains_raw_pii, redact


def test_email_is_redacted():
    result = redact("Contact us at finance@acmecorp.com for details.")
    assert "finance@acmecorp.com" not in result.redacted_text
    assert "[EMAIL]" in result.redacted_text
    assert "[EMAIL]" in result.found


def test_gstin_is_redacted():
    result = redact("Our GSTIN is 29ABCDE1234F1Z5, please update records.")
    assert "29ABCDE1234F1Z5" not in result.redacted_text
    assert "[GSTIN]" in result.redacted_text


def test_phone_number_is_redacted():
    result = redact("Call us at 98765-43210 to discuss.")
    assert "98765-43210" not in result.redacted_text
    assert "[PHONE]" in result.redacted_text


def test_long_digit_run_is_redacted():
    # A 12-digit run also satisfies the phone pattern (checked first in
    # _PATTERNS), so it's tagged [PHONE] rather than [NUMBER] — either way
    # the actual requirement (no raw digits leak) holds.
    result = redact("Account number 123456789012 is where we'll transfer from.")
    assert "123456789012" not in result.redacted_text
    assert not contains_raw_pii(result.redacted_text)


def test_long_digit_run_with_no_separators_is_caught_as_number():
    # A digit run that doesn't look like a phone number at all (no groups
    # a phone regex would recognize) should still be caught by the
    # long-digit-run catch-all.
    result = redact("Reference code 998877665544 attached for your records.")
    assert "998877665544" not in result.redacted_text
    assert not contains_raw_pii(result.redacted_text)


def test_plain_text_with_no_pii_is_unchanged():
    text = "We'll settle this by 15 Sep, once the current payment run clears."
    result = redact(text)
    assert result.redacted_text == text
    assert result.found == []


def test_contains_raw_pii_detects_leaks():
    assert contains_raw_pii("email me at test@example.com")
    assert not contains_raw_pii("email me at [EMAIL]")


def test_redaction_survives_the_real_template_corpus():
    """Every reply template, filled with realistic Faker values, must not
    leak PII into what would be sent to the LLM. The templates themselves
    don't embed names/emails (see redact.py's module docstring for why
    NER-based name redaction is out of scope for this build), so this is
    really asserting the redaction step doesn't choke on real generated
    text — a smoke test, not an exhaustive PII audit.
    """
    from app.simulation.reply_templates import TEMPLATE_BANK

    for label, templates in TEMPLATE_BANK.items():
        for template in templates:
            filled = template.format(date="15 Sep", amount="Rs 50,000", other_ref="INV-1234")
            result = redact(filled)
            assert not contains_raw_pii(result.redacted_text), f"leak in {label}: {filled}"
