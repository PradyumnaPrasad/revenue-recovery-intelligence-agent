"""Guards F21/F22: a real Gemini call once hung for minutes with no
configured timeout, and because extract_reply() was called synchronously
inside an `async def` FastAPI endpoint (app/api/invoices.py's
receive_reply()), that single stuck call blocked the entire event loop --
every request, including /health, went unresponsive for every user, not
just the one who triggered it. Reproduced live, twice.

Two independent fixes, two guards:
- app/llm/reply_extraction.py's _client() now sets a bounded timeout
- app/api/invoices.py's receive_reply() now runs extract_reply() via
  asyncio.to_thread(), off the event loop

The event-loop half can't be unit-tested without a running server (that's
what was verified live: fired a reply extraction, curl'd /health while it
was in flight, got 200 OK). This test guards the half that can be --
the timeout actually being configured, not silently absent again.
"""
from __future__ import annotations

import inspect

from app.llm import reply_extraction as reply_extraction_module


def test_genai_client_has_a_bounded_timeout_configured():
    source = inspect.getsource(reply_extraction_module._client)
    assert "timeout=" in source
    assert "HttpOptions" in source


def test_receive_reply_runs_extract_reply_off_the_event_loop():
    import app.api.invoices as invoices_module

    source = inspect.getsource(invoices_module.receive_reply)
    assert "asyncio.to_thread" in source
