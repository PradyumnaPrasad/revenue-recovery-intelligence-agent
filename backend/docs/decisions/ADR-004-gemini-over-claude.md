# ADR-004: Gemini over Claude for the one LLM seat

## Status
Accepted. Worth stating plainly if asked: this was a pragmatic constraint,
not a technical judgment that one model is better suited to reply
extraction than the other.

## Context
The system's one LLM role (reply extraction, `app/llm/`) was originally
built against Anthropic's Claude API. The Anthropic Console's free trial
credit did not appear after signup and roughly 24 hours of waiting. On a
solo, no-slack build with a fixed deadline, two options existed: keep
troubleshooting an account issue outside this project's control, or spend
real money to route around it, or switch providers to one with a
genuinely free (not trial-credit-based) tier.

## Decision
Switch the one LLM seat to Google's Gemini API (`google-genai` SDK,
`client.interactions.create()` with schema-constrained
`response_format`). Confirmed live against a real account (not assumed):
`gemini-3.5-flash-lite` and `gemini-3.5-flash` both return HTTP 200 with
no billing error, while `gemini-2.5-flash(-lite)` are already deprecated
for new users as of the switch date.

## Why
Gemini's free tier is free on an ongoing basis — no card, no trial credit
that can fail to materialize or expire. Given the account-level blocker
was outside this project's control and the deadline was fixed, switching
once, cleanly, before more code was written against the first choice cost
less than continuing to wait on it.

## Consequences
The architecture didn't change: one LLM seat, reply extraction only,
schema-constrained output, evidence-not-decisions. Only the SDK calls and
model names differ from what an earlier version of this plan specified.
The system prompt now includes the current date explicitly, after an
earlier accuracy run showed the model correctly extracting a reply's
day and month but defaulting to the wrong year when no year was stated in
the text — not a model failure, a missing-context bug in how the fixtures
were built, fixed by giving the model the context a production system
would already have (its own clock).
