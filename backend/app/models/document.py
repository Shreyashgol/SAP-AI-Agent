import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import VECTOR_TYPE, TimestampMixin, UUIDMixin


class Document(UUIDMixin, TimestampMixin, Base):
    """Uploaded document for RAG pipeline (DI-001)."""

    __tablename__ = "documents"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    # pdf | docx | xlsx | txt
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)

    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # pending | processing | ready | error

    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    document_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    access_roles: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Role IDs that can access this document (DI-009)
    linked_entity_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # entity_ids for document-to-data linking (DI-007)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class DocumentChunk(UUIDMixin, TimestampMixin, Base):
    """One chunk of a document after recursive splitting (DI-002)."""

    __tablename__ = "document_chunks"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Soft-delete on re-upload — old chunks deactivated atomically (DI-010)


class DocumentEmbedding(UUIDMixin, TimestampMixin, Base):
    """Claude embedding for a document chunk (DI-003)."""

    __tablename__ = "document_embeddings"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    # Real pgvector vector(1024) — see app.models.base.VECTOR_TYPE
    embedding: Mapped[list[float]] = mapped_column(VECTOR_TYPE, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
