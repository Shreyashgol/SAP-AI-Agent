"""
Worker-side database session factory.

Celery tasks run each invocation in a fresh event loop (asyncio.run), so they
must not share the API's pooled async engine — pooled asyncpg connections are
bound to the loop they were created on and fail with "attached to a different
loop" / "event loop is closed" on the next task. NullPool opens and closes a
connection per use, which is loop-safe.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.settings import get_settings

settings = get_settings()

worker_engine = create_async_engine(
    settings.database_url,
    echo=False,
    poolclass=NullPool,
)

AsyncSessionLocal = async_sessionmaker(
    bind=worker_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)
