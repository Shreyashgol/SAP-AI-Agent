import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin, UUIDMixin


class UserFeedback(UUIDMixin, TimestampMixin, Base):
    """Per-response thumbs up/down (FL-001)."""

    __tablename__ = "user_feedback"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    conversation_turn_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversation_turns.id", ondelete="CASCADE"), nullable=False
    )
    tool_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    # 1 = thumbs up, -1 = thumbs down


class FeedbackCorrection(UUIDMixin, TimestampMixin, Base):
    """User-submitted answer corrections (FL-002)."""

    __tablename__ = "feedback_corrections"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    conversation_turn_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversation_turns.id", ondelete="CASCADE"), nullable=False
    )
    correction_text: Mapped[str] = mapped_column(Text, nullable=False)
    admin_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # pending | approved | rejected
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
