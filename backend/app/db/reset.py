"""Drop and recreate every table — the deliberate replacement for a
migration chain (plan.md §1.3 / F1). The demo always seeds from scratch, so
there is no forward history to migrate; `create_all()` on startup handles
the normal case, and this script is for when the schema itself changed
underneath existing data.

Run via `make reset`.
"""
from __future__ import annotations

import asyncio

from app.db.models import Base
from app.db.session import engine


async def reset() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("Schema dropped and recreated.")


if __name__ == "__main__":
    asyncio.run(reset())
