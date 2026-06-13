import uuid

from sqlalchemy import Boolean, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin, UUIDMixin


class KnowledgeGraphNode(UUIDMixin, TimestampMixin, Base):
    """One node per semantic entity in the knowledge graph (KG-001)."""

    __tablename__ = "knowledge_graph_nodes"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("semantic_entities.id", ondelete="CASCADE"), nullable=False
    )
    node_label: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(50), nullable=False)
    node_properties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "entity_id", name="uq_kg_node_entity"),
    )


class KnowledgeGraphEdge(UUIDMixin, TimestampMixin, Base):
    """
    Directed edge between KG nodes.
    Direction: child → parent (e.g. Invoice → Customer).
    Explicit FK edges = 1.0, inferred = < 1.0 (KG-002, KG-003).
    """

    __tablename__ = "knowledge_graph_edges"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_graph_nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    to_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_graph_nodes.id", ondelete="CASCADE"), nullable=False
    )
    relation_name: Mapped[str] = mapped_column(String(255), nullable=False)
    edge_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # explicit_fk | inferred_name | ai_inferred | business_logical
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    is_admin_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Confidence < 0.8 requires admin confirmation before use in SQL generation (KG-006)
    join_condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Stored ON condition for SQL join builder (KG-007)

    __table_args__ = (
        UniqueConstraint("tenant_id", "from_node_id", "to_node_id", "relation_name",
                         name="uq_kg_edge_unique"),
    )
