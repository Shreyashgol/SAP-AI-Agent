import uuid

from sqlalchemy import Boolean, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin, UUIDMixin


class AlertRule(UUIDMixin, TimestampMixin, Base):
    """Threshold and anomaly alert rules (PI-002, PI-004)."""

    __tablename__ = "alert_rules"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kpi_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # threshold | anomaly | business_event

    operator: Mapped[str | None] = mapped_column(String(5), nullable=True)
    # > | < | = | >= | <=
    threshold_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[str] = mapped_column(String(20), default="warning", nullable=False)
    # critical | warning | info

    assigned_role_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    report_template_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Anomaly-triggered reports (RD-008)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    monitoring_schedule: Mapped[str] = mapped_column(String(20), default="hourly", nullable=False)
    # hourly | 4hourly | daily


class Alert(UUIDMixin, TimestampMixin, Base):
    """Triggered alert instance — immutable append-only log (PI-010)."""

    __tablename__ = "alerts"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alert_rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    triggered_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_range: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    # active | acknowledged | snoozed | escalated
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    snoozed_until: Mapped[str | None] = mapped_column(String(50), nullable=True)
    suggested_questions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    rca_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
