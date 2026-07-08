import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, engine
from app.main import app


def pytest_collection_modifyitems(items):
    # Keep every async test on the same event loop as the session-scoped
    # db/client fixtures below -- avoids DB connections crossing event loop
    # boundaries (a real failure mode on Windows dev machines).
    for item in items:
        if asyncio.iscoroutinefunction(getattr(item, "obj", None)):
            item.add_marker(pytest.mark.asyncio(loop_scope="session"))


TABLES_TO_CLEAR = [
    "bag_photos",
    "booking_qr_tokens",
    "booking_items",
    "refunds",
    "payments",
    "bookings",
    "ticket_messages",
    "tickets",
    "email_log",
    "events",
    "magic_link_tokens",
    "staff_members",
    "location_login_tokens",
    "location_item_types",
    "location_overrides",
    "location_hours",
    "locations",
    "price_list",
    "promo_codes",
    "strikes",
    "settlements",
    "cities",
    "users",
]


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _clean_db():
    yield
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE TABLE {', '.join(TABLES_TO_CLEAR)} CASCADE"))


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    from app.core import rate_limit

    rate_limit._buckets.clear()
    yield


@pytest_asyncio.fixture(loop_scope="session")
async def db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(loop_scope="session")
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
