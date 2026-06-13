import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin, UUIDMixin


class Connection(UUIDMixin, TimestampMixin, Base):
    """
    Source database connections per tenant.
    Credentials stored as Vault reference path — never raw values.
    AES-256 encrypted at rest (NFR-SEC02, DC-012).
    """

    __tablename__ = "connections"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    db_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # db_type: hana | mssql

    host: Mapped[str] = mapped_column(String(500), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    database_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Vault reference — never the raw credential
    vault_credential_path: Mapped[str] = mapped_column(String(500), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_tls: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_health_check_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_health_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # last_health_status: ok | error | timeout

    connection_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # extra driver-specific options

    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_connection_tenant_name"),)
