from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.api import batches, demo, evaluation, invoices, webhooks
from app.db.models import Base
from app.db.session import engine

_DASHBOARD_PATH = Path(__file__).resolve().parent / "templates" / "dashboard.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # No migration chain (plan.md §1.3 / §8): the demo seeds from scratch on
    # every run, so create_all() is sufficient and Alembic would be pure
    # ceremony. `make reset` drops and recreates for a clean seed.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="Revenue Recovery Intelligence Agent", version="0.1.0", lifespan=lifespan
)

app.include_router(batches.router)
app.include_router(invoices.router)
app.include_router(webhooks.router)
app.include_router(evaluation.router)
app.include_router(demo.router)


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}


@app.get("/", tags=["meta"], response_class=HTMLResponse)
async def dashboard():
    # Server-rendered, no build step (plan.md §1.3) — one static HTML file
    # with vanilla JS that fetches everything client-side. Re-read from
    # disk on every request (not cached at import time) so --reload
    # picks up template edits the same way it does Python changes.
    return _DASHBOARD_PATH.read_text()
