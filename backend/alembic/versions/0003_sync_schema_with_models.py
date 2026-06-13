"""Sync schema with models — drift found during testing.

- semantic_entity_embeddings table was defined in the ORM but never migrated
- audit_log.extra_metadata column missing
- tools.is_human_override column missing

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "semantic_entity_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("semantic_entities.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        # JSON-serialised float list; switched to pgvector Vector once ANN lands
        sa.Column("embedding", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_semantic_entity_embeddings_tenant_id",
                    "semantic_entity_embeddings", ["tenant_id"])

    op.add_column("audit_log", sa.Column("extra_metadata", postgresql.JSONB(), nullable=True))

    op.add_column(
        "tools",
        sa.Column("is_human_override", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("tools", "is_human_override")
    op.drop_column("audit_log", "extra_metadata")
    op.drop_index("ix_semantic_entity_embeddings_tenant_id",
                  table_name="semantic_entity_embeddings")
    op.drop_table("semantic_entity_embeddings")
