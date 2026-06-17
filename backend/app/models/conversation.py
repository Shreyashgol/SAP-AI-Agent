import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import VECTOR_TYPE, TimestampMixin, UUIDMixin


class Conversation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Auto-generated from first question
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    turn_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    redis_session_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Redis key for 24h session context (Agent 3)


class ConversationTurn(UUIDMixin, TimestampMixin, Base):
    """
    One user question + one platform answer pair.
    Partitioned by created_at month for performance.
    """

    __tablename__ = "conversation_turns"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)

    question: Mapped[str] = mapped_column(Text, nullable=False)
    enriched_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Context-resolved question from Conversation Context Agent

    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Structured result: { rows, columns, chart_hint, kpi_values }

    intent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Lookup | Aggregation | Trend | Comparative | RCA | Document | Hybrid

    tool_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    sql_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_sql_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    lineage: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # { source_db, tables_used, tool_id, documents_cited, agents_invoked }

    follow_up_questions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    chart_hint: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # bar | line | area | donut | waterfall | kpi_card | table

    execution_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agents_invoked: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    error_log: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class ConversationTurnEmbedding(UUIDMixin, TimestampMixin, Base):
    """
    Local bge-large embedding (1024 dim) of a conversation turn, enabling
    cross-conversation semantic recall (long-term memory). One row per turn,
    scoped to tenant + user so recall never crosses tenant/user boundaries.
    HNSW cosine index created via migration 0005.
    """

    __tablename__ = "conversation_turn_embeddings"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # No FK: conversation_turns has a composite PK (id, created_at) for
    # partitioning, so a single-column FK isn't allowed. Cleanup is handled by
    # the conversation_id CASCADE below.
    turn_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True
    )
    # The text that was embedded ("Q: ...\nA: ..."), kept for recall display.
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(VECTOR_TYPE, nullable=False)
