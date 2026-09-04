from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.settings import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    # Found live: `make reset` (DROP+CREATE all tables/types, this
    # project's documented no-migrations design) leaves an already-running
    # API server's connections holding asyncpg's cached type OIDs from the
    # OLD schema. The next query on any of those connections fails with
    # "cache lookup failed for type <oid>" -- a real crash, reproduced by
    # running the exact reset-then-reseed sequence the README documents,
    # without an API restart in between. asyncpg's prepared-statement
    # cache is what's stale; disabling it (statement_cache_size=0) means
    # every query re-resolves types fresh, so `make reset` actually works
    # against a live server as documented, not just after a restart.
    connect_args={"statement_cache_size": 0},
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
