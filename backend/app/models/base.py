import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

# Shared pgvector column type for all embedding tables (1024-dim bge-large).
# The DB columns are real pgvector `vector(1024)` (migration 0004); the ORM
# must match so values bind/return as vectors, not text.
EMBEDDING_DIM = 1024
try:
    from pgvector.sqlalchemy import Vector

    VECTOR_TYPE = Vector(EMBEDDING_DIM)
except ImportError:  # pragma: no cover - pgvector present in the runtime image
    from sqlalchemy import Text

    VECTOR_TYPE = Text()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
