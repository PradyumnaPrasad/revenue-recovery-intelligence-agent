"""CLI entrypoint for `make seed` — generates and persists the standard
measurement batch (size=500, seed=42).

generate_portfolio() itself stays a pure function with no DB/CLI concerns by
design (see its module docstring); this script is the thin persistence
wrapper, same pattern as app/simulation/demo_batch.py for the curated batch.
"""
from __future__ import annotations

import argparse
import asyncio

from app.db.session import SessionLocal
from app.deps import get_clock
from app.simulation.generator import generate_portfolio
from app.simulation.persist import persist_portfolio


async def _main(size: int, seed: int) -> None:
    clock = get_clock()
    portfolio = generate_portfolio(size=size, seed=seed)
    async with SessionLocal() as session:
        batch = await persist_portfolio(session, clock, portfolio)
    print(f"Seeded batch: batch_id={batch.id} seed={seed} size={size}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    asyncio.run(_main(args.size, args.seed))
