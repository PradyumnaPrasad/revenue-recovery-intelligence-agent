"""Regression test for a real, visible bug: format_rupees() used Python's
`:,` (Western, groups of 3) while the dashboard's frontend used
toLocaleString("en-IN") (Indian, groups of 2 after the first 3) — the same
invoice amount rendered as "Rs 362,554" in one place and "Rs 3,62,554" in
another on the same screen.
"""
from __future__ import annotations

from app.audit.explain import format_rupees


def test_small_amount_no_grouping_needed():
    assert format_rupees(50_000) == "₹500"


def test_thousands_group():
    assert format_rupees(99_999_00) == "₹99,999"


def test_lakh_uses_indian_grouping_not_western():
    # Rs 3,62,554 (Indian) not Rs 362,554 (Western) — this is the exact bug.
    assert format_rupees(362_554_00) == "₹3,62,554"


def test_crore_uses_indian_grouping():
    # 17,417,007,154 paise = Rs 174,170,072 (rounded) = 17 crore 41 lakh 70
    # thousand 72 rupees -> "17,41,70,072" in Indian grouping.
    assert format_rupees(17_417_007_154) == "₹17,41,70,072"


def test_negative_amount():
    assert format_rupees(-500_000) == "-₹5,000"


def test_zero():
    assert format_rupees(0) == "₹0"
