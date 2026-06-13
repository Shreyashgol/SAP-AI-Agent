import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import VECTOR_TYPE, TimestampMixin, UUIDMixin


class Tool(UUIDMixin, TimestampMixin, Base):
    """
    Auto-generated or custom business tool (TG-001, TG-002).
    Each tool is a named, versioned, parameterised SQL capability.
    """

    __tablename__ = "tools"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    # kpi | entity_summary | comparative | drill_down | custom
    domain: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    # active | invalid | deprecated | custom
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # True for SAP B1 Tool Pack (TG-012)
    is_human_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Human-edited tools are never overwritten by pack reapply
    pack_source: Mapped[str] = mapped_column(String(50), default="ai_generated", nullable=False)
    # sap_b1 | ai_generated | human_custom

    sql_template: Mapped[str] = mapped_column(Text, nullable=False)
    input_schema: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # [{ name, type, required, default }]
    output_schema: Mapped[dict] = mapped_column(JSONB, nullable=False)
    permissions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # { required_roles: [], required_domains: [] }

    last_validated_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", "version", name="uq_tool_tenant_name_version"),
    )


class ToolEmbedding(UUIDMixin, TimestampMixin, Base):
    """
    Local bge-large embeddings (1024 dim) for tool retrieval.
    HNSW index created via migration (TG-003).
    """

    __tablename__ = "tool_embeddings"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tools.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    # Stored as text JSON until pgvector extension confirmed; real deployments use vector type
    embedding: Mapped[list[float]] = mapped_column(VECTOR_TYPE, nullable=False)
    # Real pgvector vector(1024) — see app.models.base.VECTOR_TYPE


class ToolTableDependency(UUIDMixin, TimestampMixin, Base):
    """Tracks which DB tables a tool depends on for deprecation detection (TG-011)."""

    __tablename__ = "tool_table_dependencies"

    tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tools.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metadata_table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metadata_tables.id", ondelete="CASCADE"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tool_id", "metadata_table_id", name="uq_tool_table_dep"),
    )


class ToolRankingWeight(UUIDMixin, TimestampMixin, Base):
    """Per-tool ranking weights updated nightly from feedback (TR-004, FL-005)."""

    __tablename__ = "tool_ranking_weights"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tools.id", ondelete="CASCADE"), nullable=False
    )
    success_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    feedback_weight: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    execution_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_recalculated_at: Mapped[str | None] = mapped_column(String(50), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "tool_id", name="uq_tool_ranking_weight"),
    )
