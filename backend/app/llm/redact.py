"""PII redaction before any LLM call — plan.md §6.8.

Matters more than usual here: Google's free tier permits using submitted
content to improve their products (not true on the paid tier), so
redacting before the call is what makes it acceptable to send this text
there at all, not an optional hardening step.

Regex-based, covering structured PII: emails, phone numbers, GSTIN (Indian
tax ID), and long digit runs that could be bank/card numbers. Deliberately
does NOT attempt person/company-name redaction via NER — the synthetic
reply corpus (app/simulation/reply_templates.py) doesn't embed names inline
(it's generic sentences: "We'll settle this by {date}..."), so this gap
doesn't affect this build's accuracy measurement. A real deployment on
genuine customer text would need a proper NER pass in addition to this.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(?:\+?\d{1,3}[-.\s]?)?(?:\d{3,5}[-.\s]?){2,4}\d{2,4}")
_GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}\b")
# Any run of 9+ consecutive digits that isn't already caught above — a
# conservative catch-all for bank account / card numbers.
_LONG_DIGIT_RUN_RE = re.compile(r"\b\d{9,}\b")

_PATTERNS: list[tuple[re.Pattern, str]] = [
    (_GSTIN_RE, "[GSTIN]"),
    (_EMAIL_RE, "[EMAIL]"),
    (_PHONE_RE, "[PHONE]"),
    (_LONG_DIGIT_RUN_RE, "[NUMBER]"),
]


@dataclass(frozen=True)
class RedactionResult:
    redacted_text: str
    found: list[str]  # which placeholder types were actually used


def redact(text: str) -> RedactionResult:
    redacted = text
    found: list[str] = []
    for pattern, placeholder in _PATTERNS:
        if pattern.search(redacted):
            found.append(placeholder)
            redacted = pattern.sub(placeholder, redacted)
    return RedactionResult(redacted_text=redacted, found=found)


def contains_raw_pii(text: str) -> bool:
    """Used by tests to assert a payload has no leaked PII — checks the
    same patterns redact() uses, so this can never silently drift from
    what's actually redacted.
    """
    return any(pattern.search(text) for pattern, _ in _PATTERNS)
