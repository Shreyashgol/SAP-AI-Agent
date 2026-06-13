"""
Audit log service — append-only writes (GS-005, NFR-SEC10).
DB trigger blocks UPDATE/DELETE on the audit_log table.
Never logs raw query results (NFR-SEC11).
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


class AuditService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def log(
        self,
        *,
        event_type: str,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        question: str | None = None,
        tool_id: uuid.UUID | None = None,
        sql_query: str | None = None,
        confidence_score: float | None = None,
        execution_time_ms: int | None = None,
        result_row_count: int | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        entry = AuditLog(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            question=question,
            tool_id=tool_id,
            sql_query=sql_query,
            confidence_score=confidence_score,
            execution_time_ms=execution_time_ms,
            result_row_count=result_row_count,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            metadata=metadata,
            created_at=datetime.now(UTC).isoformat(),
        )
        self.db.add(entry)
        await self.db.flush()
        # Note: caller must commit — keeps audit in same transaction as the operation


# ── Well-known event type constants ───────────────────────────────────────────
class AuditEvent:
    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    AUTH_LOCKOUT = "auth.lockout"
    AUTH_REFRESH = "auth.refresh"

    QUERY_EXECUTED = "query.executed"
    TOOL_EXECUTED = "tool.executed"
    SQL_GENERATED = "sql.generated"
    DML_BLOCKED = "sql.dml_blocked"

    CONNECTION_CREATED = "connection.created"
    CONNECTION_TESTED = "connection.tested"
    CONNECTION_DELETED = "connection.deleted"

    DISCOVERY_STARTED = "discovery.started"
    DISCOVERY_COMPLETED = "discovery.completed"

    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_DELETED = "document.deleted"

    USER_CREATED = "user.created"
    ROLE_ASSIGNED = "role.assigned"

    EXPORT_PDF = "export.pdf"
    EXPORT_EXCEL = "export.excel"
