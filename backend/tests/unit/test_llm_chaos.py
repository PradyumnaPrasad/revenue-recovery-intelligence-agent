"""plan.md §6.8 graceful degradation — the chaos switch. No network calls
here: everything either goes through the deliberate chaos flag or through
fallback_classify() directly.
"""
from __future__ import annotations

from app.llm.chaos import is_llm_down, set_llm_down
from app.llm.fallback import FALLBACK_CONFIDENCE, fallback_classify
from app.llm.reply_extraction import (
    FALLBACK_MODEL_LABEL,
    CONFIDENCE_THRESHOLD,
    extract_reply,
    should_act_automatically,
)


def teardown_function():
    # Never let one test's chaos state leak into the next.
    set_llm_down(False)


def test_chaos_switch_toggles():
    assert is_llm_down() is False
    set_llm_down(True)
    assert is_llm_down() is True
    set_llm_down(False)
    assert is_llm_down() is False


def test_extract_reply_uses_fallback_when_llm_is_down():
    set_llm_down(True)
    result = extract_reply("Please stop emailing our CFO directly.")
    assert result.model_used == FALLBACK_MODEL_LABEL
    assert result.extraction is not None
    assert result.extraction.confidence == FALLBACK_CONFIDENCE


def test_fallback_confidence_is_always_below_the_action_threshold():
    """This is THE safety property: no fallback classification should ever
    be acted on automatically, regardless of what it says.
    """
    assert FALLBACK_CONFIDENCE < CONFIDENCE_THRESHOLD
    for text in [
        "Please stop emailing our CFO directly.",
        "We dispute this invoice, the amount is wrong.",
        "We will pay by next Friday.",
        "Thanks!",
    ]:
        extraction = fallback_classify(text)
        assert should_act_automatically(extraction) is False


def test_fallback_classify_recognizes_stop_contact():
    extraction = fallback_classify("Please stop contacting our finance team about this.")
    assert extraction.intent == "stop_contact"


def test_fallback_classify_recognizes_dispute():
    extraction = fallback_classify("We dispute this charge, the amount doesn't match our PO.")
    assert extraction.intent == "dispute"


def test_fallback_classify_recognizes_promise_to_pay():
    extraction = fallback_classify("We will pay this by the end of the month.")
    assert extraction.intent == "promise_to_pay"


def test_fallback_classify_defaults_to_unrelated():
    extraction = fallback_classify("Happy Diwali to your whole team!")
    assert extraction.intent == "unrelated"


def test_fallback_classify_evidence_quote_is_always_a_real_substring():
    text = "We will pay this invoice by next Friday once the PO clears."
    extraction = fallback_classify(text)
    assert extraction.evidence_quote in text
