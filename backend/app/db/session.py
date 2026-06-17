import json
import math
import uuid
from collections.abc import AsyncGenerator
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.settings import get_settings

settings = get_settings()


def _json_sanitize(obj: object) -> object:
    """Recursively coerce DB-source values to Postgres-JSON-safe types before they
    land in JSONB columns (e.g. conversation_turns.answer_data/lineage built from
    MSSQL/HANA query results). Handles Decimal, datetime/date, UUID, and — crucially —
    NaN/Infinity floats, which Python's json.dumps emits but Postgres JSON rejects."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, Decimal):
        f = float(obj)
        return f if math.isfinite(f) else None
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): _json_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_json_sanitize(v) for v in obj]
    return obj


def _json_serializer(obj: object) -> str:
    return json.dumps(_json_sanitize(obj))


engine = create_async_engine(
    settings.database_url,
    echo=settings.sql_echo,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    json_serializer=_json_serializer,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
