import uuid

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import UUIDMixin


class AuditLog(UUIDMixin, Base):
    """
    Immutable append-only audit log (GS-005, NFR-SEC10).
    UPDATE and DELETE are blocked by DB trigger.
    Partitioned by created_at month for performance.
    """

    __tablename__ = "audit_log"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # auth.login | auth.logout | auth.lockout | query.executed | tool.executed
    # sql.generated | dml.blocked | connection.tested | discovery.started | etc.

    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    sql_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Raw query never stored if contains PII (NFR-SEC11)

    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    execution_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    extra_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[str] = mapped_column(String(50), nullable=False)
    # Stored as ISO string — no updated_at, this row is immutable
