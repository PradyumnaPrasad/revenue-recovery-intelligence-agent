"""app/db/session.py's engine configuration -- guards against F20
regressing silently. Found live: `make reset` (this project's documented,
no-migrations way to pick up a schema change) crashed an already-running
API server with `asyncpg.exceptions.InternalServerError: cache lookup
failed for type <oid>`, because asyncpg's prepared-statement cache holds
type OIDs from before the reset. statement_cache_size=0 is what fixes it;
this test makes sure nobody removes that argument without noticing why
it's there.
"""
from __future__ import annotations

from app.db.session import engine


def test_asyncpg_statement_cache_is_disabled():
    # Found live, reproduced cleanly (F20): without this, a schema reset
    # against a live server crashes the next query on any already-open
    # connection with "cache lookup failed for type <oid>" -- exactly the
    # sequence backend/README.md's own Quick Start documents (reset,
    # reseed) without mentioning a required restart in between.
    connect_args = engine.dialect.dbapi and getattr(engine.pool, "_creator", None)
    # The engine's connect_args aren't directly introspectable via a public
    # SQLAlchemy API across versions, so assert on what we control instead:
    # the URL/engine was built through create_async_engine with this kwarg
    # in app/db/session.py -- read the source to confirm the guard is
    # still there, since that's the actual contract this test protects.
    import inspect

    import app.db.session as session_module

    source = inspect.getsource(session_module)
    assert "statement_cache_size" in source
    assert "0" in source.split("statement_cache_size")[1][:10]
