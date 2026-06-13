import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin, UUIDMixin


class ReportSchedule(UUIDMixin, TimestampMixin, Base):
    """NL-defined scheduled report (RD-001, RD-002)."""

    __tablename__ = "report_schedules"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    questions: Mapped[list] = mapped_column(JSONB, nullable=False)
    # List of NL questions — each becomes a report section
    cron_expression: Mapped[str] = mapped_column(String(100), nullable=False)
    delivery_channels: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # { email: [addresses], teams_webhook: url, slack_webhook: url }
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    subscriber_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)


class ReportExecution(UUIDMixin, TimestampMixin, Base):
    """One generated report execution (RD-010)."""

    __tablename__ = "report_executions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_schedules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # pending | running | completed | failed
    storage_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    execution_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
