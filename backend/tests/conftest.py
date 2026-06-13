"""
Root pytest configuration and shared fixtures.
All fixtures follow factory-boy pattern for consistent test data creation.
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator

import fakeredis.aioredis as fakeredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.redis import get_redis
from app.core.settings import get_settings
from app.db.session import Base, get_db
from app.main import app

settings = get_settings()

# ── Test database ─────────────────────────────────────────────────────────────
TEST_DB_URL = settings.database_url.replace(
    f"/{settings.postgres_db}", "/sap_ai_platform_test"
)

# NullPool: each test runs in its own event loop, so pooled connections must not
# be reused across loops ("attached to a different loop" / "operation in progress").
test_engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def setup_test_db():
    """Create all tables in test DB once per session."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session(setup_test_db) -> AsyncGenerator[AsyncSession, None]:
    """Provide a transaction-scoped DB session that rolls back after each test."""
    async with test_engine.begin() as conn:
        async with TestSessionLocal(bind=conn) as session:
            yield session
            await session.rollback()


@pytest_asyncio.fixture
async def fake_redis():
    """In-memory Redis for unit/integration tests."""
    r = fakeredis.FakeRedis(decode_responses=True)
    yield r
    await r.flushall()
    await r.aclose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, fake_redis) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP test client with DB + Redis overridden to test doubles."""
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_redis] = lambda: fake_redis
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
    app.dependency_overrides.clear()


# ── Test data factories ───────────────────────────────────────────────────────
@pytest.fixture
def test_tenant_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def test_user_id() -> uuid.UUID:
    return uuid.uuid4()
