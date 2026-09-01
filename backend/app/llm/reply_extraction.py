"""Reply extraction — plan.md §6.8. Turns a free-text customer reply into a
structured ReplyExtraction via Gemini's schema-constrained output. This is
the one LLM seat in the whole system (§1.3) — reading replies, never
choosing an action, never setting a probability, never authoring terms.

Model routing: `settings.llm_model_small` handles the typical case;
`settings.llm_model_large` is reserved for future confidence-based
escalation (not yet wired into a caller — see the module docstring in
plan.md §9's model-routing table for why the exact tier split is decided
live against AI Studio, not hardcoded here).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date as date_type

from google import genai
from pydantic import ValidationError

from app.llm.chaos import is_llm_down
from app.llm.fallback import fallback_classify
from app.llm.redact import redact
from app.llm.types import ReplyExtraction
from app.settings import get_settings

FALLBACK_MODEL_LABEL = "fallback_keyword_classifier"

CONFIDENCE_THRESHOLD = 0.6

EXTRACTION_SYSTEM_PROMPT_TEMPLATE = """You are extracting structured facts from a business reply about an overdue invoice. Today's date is {today}. Output ONLY the fields in the schema. You must never invent a fact that is not stated or clearly implied by the text.

Rules:
- intent: pick exactly one of the eight categories.
  - "promise_to_pay": a stated or clearly implied commitment to pay, with or without a date.
  - "dispute": the customer contests the validity, amount, or details of the charge.
  - "approval_blocker": payment is stuck in the customer's OWN internal process (finance sign-off, PO approval, a scheduled payment run) — the customer intends to pay but names an internal obstacle or process, not a firm date.
  - "details_incorrect": the customer is asking for a corrected/reissued invoice (wrong address, wrong reference, misspelled name), not disputing the charge itself.
  - "requests_payment_plan": the customer explicitly asks to split or delay payment into instalments.
  - "stop_contact": an EXPLICIT request to stop, reduce, or redirect contact (e.g. "stop emailing X", "route through me instead", "don't send further reminders"). A message merely announcing an inactive mailbox is NOT this category — see "unrelated" below.
  - "acknowledgement": the sender confirms they have seen THIS invoice/reminder and will look into it or revert, WITHOUT committing to a date, amount, or naming a blocker. Must reference the invoice/payment situation, even briefly.
  - "unrelated": the message does not meaningfully engage with the invoice or payment status at all — an out-of-office autoresponder, a notice that a mailbox is unmonitored/inactive, or a bare closing remark ("Thanks!") with no other content. If the message could just as easily have been sent in response to any email regardless of its subject, it is "unrelated", not "acknowledgement".
- evidence_quote: copy a verbatim, contiguous span (<=200 characters) directly from the input text that best supports your intent classification. Do not paraphrase or summarize it — it must be an exact substring of the input.
- confidence: your genuine confidence in the intent classification, from 0.0 to 1.0. Use confidence below 0.6 whenever the text is ambiguous, sarcastic, or could plausibly fit two categories.
- promised_date: if the text gives a date without a year (e.g. "15 Sep"), infer the year using today's date above — if that day/month has already passed this year, assume next year, otherwise this year. Leave null if no date is stated.
- Leave promised_amount_paise, dispute_reason, and blocker_owner as null unless the text actually states them.
- sentiment reflects the tone of the message itself, not whether it's good news for the recipient.
"""


def _system_prompt(today: date_type) -> str:
    return EXTRACTION_SYSTEM_PROMPT_TEMPLATE.format(today=today.isoformat())


@dataclass
class ExtractionResult:
    extraction: ReplyExtraction | None
    redacted_text: str
    rejected_reason: str | None  # None if accepted
    model_used: str


def _client() -> genai.Client:
    # genai.Client() reads GEMINI_API_KEY from the environment on its own —
    # never passed as a Settings field, so no code path can accidentally
    # log or serialize it.
    return genai.Client()


def _normalize_model_name(model: str) -> str:
    """Defensive normalization: AI Studio's UI shows a display name
    ("Gemini 3.5 Flash Lite") that isn't the API model ID
    ("gemini-3.5-flash-lite") — an easy .env config mistake. Lowercasing
    and replacing spaces with hyphens recovers the correct ID either way,
    so a display-name value in settings doesn't hard-fail at call time.
    """
    return model.strip().lower().replace(" ", "-")


def extract_reply(
    text: str, model: str | None = None, today: date_type | None = None
) -> ExtractionResult:
    settings = get_settings()
    model = _normalize_model_name(model or settings.llm_model_small)
    redaction = redact(text)
    today = today or date_type.today()

    # Chaos switch — deliberate (is_llm_down()) or a real, unexpected
    # failure (network, rate limit, auth, malformed response) both degrade
    # to the same keyword fallback rather than propagating. The loop keeps
    # running; the fallback's fixed 0.5 confidence means nothing it
    # produces is ever acted on automatically (should_act_automatically()
    # below) — every fallback classification routes to a human.
    if is_llm_down():
        return ExtractionResult(
            extraction=fallback_classify(redaction.redacted_text),
            redacted_text=redaction.redacted_text,
            rejected_reason=None,
            model_used=FALLBACK_MODEL_LABEL,
        )

    try:
        client = _client()
        interaction = client.interactions.create(
            model=model,
            system_instruction=_system_prompt(today),
            input=redaction.redacted_text,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": ReplyExtraction.model_json_schema(),
            },
        )
        raw_output = interaction.output_text
    except Exception:
        return ExtractionResult(
            extraction=fallback_classify(redaction.redacted_text),
            redacted_text=redaction.redacted_text,
            rejected_reason=None,
            model_used=FALLBACK_MODEL_LABEL,
        )
    try:
        extraction = ReplyExtraction.model_validate_json(raw_output)
    except (ValidationError, json.JSONDecodeError) as e:
        return ExtractionResult(
            extraction=None,
            redacted_text=redaction.redacted_text,
            rejected_reason=f"schema_validation_failed: {e}",
            model_used=model,
        )

    # Anti-hallucination guarantee — verified programmatically, not
    # trusted: the evidence quote must be a real, exact substring of the
    # (redacted) input the model actually saw.
    if extraction.evidence_quote not in redaction.redacted_text:
        return ExtractionResult(
            extraction=None,
            redacted_text=redaction.redacted_text,
            rejected_reason="evidence_quote_not_a_substring",
            model_used=model,
        )

    return ExtractionResult(
        extraction=extraction,
        redacted_text=redaction.redacted_text,
        rejected_reason=None,
        model_used=model,
    )


def should_act_automatically(extraction: ReplyExtraction) -> bool:
    """confidence < 0.6 -> human queue, do not act (plan.md §6.8)."""
    return extraction.confidence >= CONFIDENCE_THRESHOLD
