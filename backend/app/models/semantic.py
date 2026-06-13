import uuid

from sqlalchemy import Boolean, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import VECTOR_TYPE, TimestampMixin, UUIDMixin


class SemanticEntity(UUIDMixin, TimestampMixin, Base):
    """Business entity mapped from a metadata table (SL-001)."""

    __tablename__ = "semantic_entities"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metadata_tables.id", ondelete="CASCADE"), nullable=False
    )
    entity_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # e.g. "Customer", "Invoice", "Sales Order"
    domain: Mapped[str] = mapped_column(String(50), nullable=False)
    # finance | sales | purchasing | inventory | operations | hr
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_human_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Human override persists over AI regeneration (SL-009)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    semantic_version: Mapped[int] = mapped_column(default=1, nullable=False)
    # Pack source: sap_b1 | mssql_dynamics | mssql_sage | ai_generated | human
    pack_source: Mapped[str] = mapped_column(String(50), default="ai_generated", nullable=False)


class SemanticAttribute(UUIDMixin, TimestampMixin, Base):
    """Business attribute mapped from a metadata column (SL-002)."""

    __tablename__ = "semantic_attributes"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("semantic_entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    column_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metadata_columns.id", ondelete="CASCADE"), nullable=False
    )
    attribute_name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    semantic_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # currency | date | quantity | code | text | boolean | percentage
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_human_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class KpiDefinition(UUIDMixin, TimestampMixin, Base):
    """KPI catalogue entry (SL-003)."""

    __tablename__ = "kpi_definitions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    formula: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    aggregation_method: Mapped[str] = mapped_column(String(20), default="sum", nullable=False)
    # sum | avg | count | min | max | ratio
    display_format: Mapped[str | None] = mapped_column(String(50), nullable=True)
    domain: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # System KPIs ship with the platform metric library


class BusinessGlossary(UUIDMixin, TimestampMixin, Base):
    """Business glossary definitions (SL-004)."""

    __tablename__ = "business_glossary"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    term: Mapped[str] = mapped_column(String(255), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "term", name="uq_glossary_tenant_term"),
    )


class SynonymMapping(UUIDMixin, TimestampMixin, Base):
    """Many-to-one synonym → canonical metric mapping (SL-006)."""

    __tablename__ = "synonym_mappings"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    synonym: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_term: Mapped[str] = mapped_column(String(255), nullable=False)
    # e.g. "revenue" | "sales" | "turnover" → "Revenue"
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # metric | entity | attribute

    __table_args__ = (
        UniqueConstraint("tenant_id", "synonym", "entity_type", name="uq_synonym_unique"),
    )


class SemanticEntityEmbedding(UUIDMixin, TimestampMixin, Base):
    """
    Voyage-3 embedding for a SemanticEntity (EM-006).
    Used for entity-to-question similarity matching in the Tool Ranker.
    """

    __tablename__ = "semantic_entity_embeddings"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("semantic_entities.id", ondelete="CASCADE"),
        nullable=False, unique=True
    )
    embedding: Mapped[list[float]] = mapped_column(VECTOR_TYPE, nullable=False)
    # Real pgvector vector(1024) — see app.models.base.VECTOR_TYPE


class BusinessRule(UUIDMixin, TimestampMixin, Base):
    """Filter predicates applied to entities at query time (SL-007)."""

    __tablename__ = "business_rules"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("semantic_entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    predicate_sql: Mapped[str] = mapped_column(Text, nullable=False)
    # e.g. "DocStatus = 'O' AND Cancelled = 'N'"
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Default rules applied automatically in tool generation
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pack_source: Mapped[str] = mapped_column(String(50), default="human", nullable=False)
