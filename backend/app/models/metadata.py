import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin, UUIDMixin


class MetadataTable(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "metadata_tables"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    schema_name: Mapped[str] = mapped_column(String(255), nullable=False)
    table_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    object_type: Mapped[str] = mapped_column(String(20), default="table", nullable=False)
    # object_type: table | view

    ai_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_count_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_pii_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_system_table: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metadata_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # SHA-256 hash for incremental discovery change detection (DC-010)

    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)
    # Populated by trigger for full-text search (MC-003)

    discovery_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "connection_id", "schema_name", "table_name",
            name="uq_metadata_table_unique"
        ),
    )


class MetadataColumn(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "metadata_columns"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metadata_tables.id", ondelete="CASCADE"), nullable=False, index=True
    )
    column_name: Mapped[str] = mapped_column(String(255), nullable=False)
    data_type: Mapped[str] = mapped_column(String(100), nullable=False)
    is_nullable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_primary_key: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_foreign_key: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_pii_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_masked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # column-level masking (GS-004)

    ai_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sample_values: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # top-10 non-PII values from DC-008
    column_stats: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # { min, max, null_pct, distinct_count } from DC-009

    ordinal_position: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("table_id", "column_name", name="uq_metadata_column_unique"),
    )


class MetadataRelation(UUIDMixin, TimestampMixin, Base):
    """FK and inferred relationships between tables (DC-005)."""

    __tablename__ = "metadata_relations"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metadata_tables.id", ondelete="CASCADE"), nullable=False
    )
    from_column_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metadata_columns.id", ondelete="CASCADE"), nullable=False
    )
    to_table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metadata_tables.id", ondelete="CASCADE"), nullable=False
    )
    to_column_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metadata_columns.id", ondelete="CASCADE"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # relation_type: explicit_fk | inferred_name | ai_inferred
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    is_admin_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Inferred edges with confidence < 0.8 require admin confirmation (KG-003)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Plain-English purpose of the join (e.g. from the ERPRef prior), surfaced to
    # the runtime text-to-SQL prompt so the model picks the right relationship.
