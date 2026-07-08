import asyncio
import sys
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings

if sys.platform == "win32":
    # psycopg cannot run in async mode under Windows' default
    # ProactorEventLoop; dev/test only, prod runs on Fly's Linux images.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
    # Neon is a serverless/pooled Postgres already (and pgbouncer-fronted in
    # production) -- keep the app-side pool minimal and let Neon's own
    # pooler do the work.
    poolclass=NullPool,
)

AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
