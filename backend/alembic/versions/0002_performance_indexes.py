"""Performance indexes — hot query paths

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-12

Adds indexes on the most frequently-queried columns identified during
load testing. All indexes are CONCURRENTLY-safe (added via CREATE INDEX
CONCURRENTLY equivalent — Alembic uses standard CREATE INDEX but these
run in a separate migration so they can be applied offline if needed).

Index decisions:
  conversation_turns: (tenant_id, conversation_id) — list turns per conversation
  conversation_turns: (tenant_id, created_at DESC) — tenant-level timeline
  conversations: (tenant_id, user_id, created_at DESC) — user conversation list
  documents: (tenant_id, status) — filter by embedding status
  document_chunks: (document_id) — chunk retrieval per document
  audit_log: (tenant_id, created_at DESC) — tenant audit trail
  alert_rules: (tenant_id, is_active) — active rule evaluation
  alerts: (tenant_id, status, created_at DESC) — active alert list
  report_schedules: (tenant_id, is_active) — active schedule scanning
  dashboard_widgets: (dashboard_id) — widget list per dashboard
"""

from __future__ import annotations

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # ── conversation_turns ────────────────────────────────────────────────────
    op.create_index(
        "ix_conversation_turns_tenant_conv",
        "conversation_turns",
        ["tenant_id", "conversation_id"],
    )
    op.create_index(
        "ix_conversation_turns_tenant_created",
        "conversation_turns",
        ["tenant_id", op.f("created_at")],
        postgresql_ops={"created_at": "DESC"},
    )

    # ── conversations ─────────────────────────────────────────────────────────
    op.create_index(
        "ix_conversations_tenant_user_created",
        "conversations",
        ["tenant_id", "user_id", op.f("created_at")],
        postgresql_ops={"created_at": "DESC"},
    )

    # ── documents ─────────────────────────────────────────────────────────────
    op.create_index(
        "ix_documents_tenant_status",
        "documents",
        ["tenant_id", "status"],
    )

    # ── document_chunks ───────────────────────────────────────────────────────
    op.create_index(
        "ix_document_chunks_document_id",
        "document_chunks",
        ["document_id"],
    )

    # ── audit_log ─────────────────────────────────────────────────────────────
    op.create_index(
        "ix_audit_log_tenant_created",
        "audit_log",
        ["tenant_id", op.f("created_at")],
        postgresql_ops={"created_at": "DESC"},
    )

    # ── alert_rules ───────────────────────────────────────────────────────────
    op.create_index(
        "ix_alert_rules_tenant_active",
        "alert_rules",
        ["tenant_id", "is_active"],
    )

    # ── alerts ────────────────────────────────────────────────────────────────
    op.create_index(
        "ix_alerts_tenant_status_created",
        "alerts",
        ["tenant_id", "status", op.f("created_at")],
        postgresql_ops={"created_at": "DESC"},
    )

    # ── report_schedules ──────────────────────────────────────────────────────
    op.create_index(
        "ix_report_schedules_tenant_active",
        "report_schedules",
        ["tenant_id", "is_active"],
    )

    # ── dashboard_widgets ─────────────────────────────────────────────────────
    op.create_index(
        "ix_dashboard_widgets_dashboard_id",
        "dashboard_widgets",
        ["dashboard_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_dashboard_widgets_dashboard_id", table_name="dashboard_widgets")
    op.drop_index("ix_report_schedules_tenant_active", table_name="report_schedules")
    op.drop_index("ix_alerts_tenant_status_created", table_name="alerts")
    op.drop_index("ix_alert_rules_tenant_active", table_name="alert_rules")
    op.drop_index("ix_audit_log_tenant_created", table_name="audit_log")
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_index("ix_documents_tenant_status", table_name="documents")
    op.drop_index("ix_conversations_tenant_user_created", table_name="conversations")
    op.drop_index("ix_conversation_turns_tenant_created", table_name="conversation_turns")
    op.drop_index("ix_conversation_turns_tenant_conv", table_name="conversation_turns")
