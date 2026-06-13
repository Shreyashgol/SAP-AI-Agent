"""Initial schema — all 33 tables

Revision ID: 0001
Revises:
Create Date: 2026-06-11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # ── Enable extensions ────────────────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # ── tenants ──────────────────────────────────────────────────────────────
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="UTC"),
        sa.Column("branding", postgresql.JSONB, nullable=True),
        sa.Column("settings", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"])

    # ── roles ────────────────────────────────────────────────────────────────
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name", name="uq_role_tenant_name"),
    )
    op.create_index("ix_roles_tenant_id", "roles", ["tenant_id"])

    # ── role_permissions ─────────────────────────────────────────────────────
    op.create_table(
        "role_permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain", sa.String(50), nullable=False),
        sa.Column("can_read", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("can_export", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("role_id", "domain", name="uq_roleperm_role_domain"),
    )

    # ── users ────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_sso", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("failed_login_attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
    op.create_index("ix_users_email", "users", ["email"])

    # ── user_roles ────────────────────────────────────────────────────────────
    op.create_table(
        "user_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "role_id", name="uq_userrole_user_role"),
    )

    # ── connections ───────────────────────────────────────────────────────────
    op.create_table(
        "connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("db_type", sa.String(20), nullable=False),
        sa.Column("host", sa.String(500), nullable=False),
        sa.Column("port", sa.Integer, nullable=False),
        sa.Column("database_name", sa.String(255), nullable=False),
        sa.Column("vault_credential_path", sa.String(500), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_tls", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_health_check_at", sa.String(50), nullable=True),
        sa.Column("last_health_status", sa.String(20), nullable=True),
        sa.Column("connection_meta", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name", name="uq_connection_tenant_name"),
    )
    op.create_index("ix_connections_tenant_id", "connections", ["tenant_id"])

    # ── metadata_tables ───────────────────────────────────────────────────────
    op.create_table(
        "metadata_tables",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("schema_name", sa.String(255), nullable=False),
        sa.Column("table_name", sa.String(255), nullable=False),
        sa.Column("object_type", sa.String(20), nullable=False, server_default="table"),
        sa.Column("ai_description", sa.Text, nullable=True),
        sa.Column("row_count_estimate", sa.Integer, nullable=True),
        sa.Column("is_pii_flagged", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_system_table", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("metadata_hash", sa.String(64), nullable=True),
        sa.Column("search_vector", postgresql.TSVECTOR, nullable=True),
        sa.Column("discovery_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "connection_id", "schema_name", "table_name",
                            name="uq_metadata_table_unique"),
    )
    op.create_index("ix_metadata_tables_tenant_id", "metadata_tables", ["tenant_id"])
    op.create_index("ix_metadata_tables_table_name", "metadata_tables", ["table_name"])
    op.create_index("ix_metadata_tables_search_vector", "metadata_tables", ["search_vector"],
                    postgresql_using="gin")

    # ── metadata_columns ──────────────────────────────────────────────────────
    op.create_table(
        "metadata_columns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("table_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("metadata_tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("column_name", sa.String(255), nullable=False),
        sa.Column("data_type", sa.String(100), nullable=False),
        sa.Column("is_nullable", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_primary_key", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_foreign_key", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_pii_flagged", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_masked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("ai_description", sa.Text, nullable=True),
        sa.Column("sample_values", postgresql.JSONB, nullable=True),
        sa.Column("column_stats", postgresql.JSONB, nullable=True),
        sa.Column("ordinal_position", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("table_id", "column_name", name="uq_metadata_column_unique"),
    )
    op.create_index("ix_metadata_columns_table_id", "metadata_columns", ["table_id"])

    # ── metadata_relations ────────────────────────────────────────────────────
    op.create_table(
        "metadata_relations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_table_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("metadata_tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_column_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("metadata_columns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_table_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("metadata_tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_column_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("metadata_columns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_type", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("is_admin_confirmed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── semantic_entities ─────────────────────────────────────────────────────
    op.create_table(
        "semantic_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("table_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("metadata_tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_name", sa.String(255), nullable=False),
        sa.Column("domain", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_ai_generated", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_human_override", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("semantic_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("pack_source", sa.String(50), nullable=False, server_default="ai_generated"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_semantic_entities_tenant_id", "semantic_entities", ["tenant_id"])

    # ── semantic_attributes ───────────────────────────────────────────────────
    op.create_table(
        "semantic_attributes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("semantic_entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("column_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("metadata_columns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attribute_name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("semantic_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_human_override", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_ai_generated", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── kpi_definitions ───────────────────────────────────────────────────────
    op.create_table(
        "kpi_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("formula", sa.Text, nullable=True),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("aggregation_method", sa.String(20), nullable=False, server_default="sum"),
        sa.Column("display_format", sa.String(50), nullable=True),
        sa.Column("domain", sa.String(50), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── business_glossary ─────────────────────────────────────────────────────
    op.create_table(
        "business_glossary",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("term", sa.String(255), nullable=False),
        sa.Column("definition", sa.Text, nullable=False),
        sa.Column("domain", sa.String(50), nullable=True),
        sa.Column("is_ai_generated", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "term", name="uq_glossary_tenant_term"),
    )

    # ── synonym_mappings ──────────────────────────────────────────────────────
    op.create_table(
        "synonym_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("synonym", sa.String(255), nullable=False),
        sa.Column("canonical_term", sa.String(255), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "synonym", "entity_type", name="uq_synonym_unique"),
    )

    # ── business_rules ────────────────────────────────────────────────────────
    op.create_table(
        "business_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("semantic_entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_name", sa.String(255), nullable=False),
        sa.Column("predicate_sql", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("pack_source", sa.String(50), nullable=False, server_default="human"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── knowledge_graph_nodes ─────────────────────────────────────────────────
    op.create_table(
        "knowledge_graph_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("semantic_entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_label", sa.String(255), nullable=False),
        sa.Column("domain", sa.String(50), nullable=False),
        sa.Column("node_properties", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "entity_id", name="uq_kg_node_entity"),
    )
    op.create_index("ix_kg_nodes_tenant_id", "knowledge_graph_nodes", ["tenant_id"])

    # ── knowledge_graph_edges ─────────────────────────────────────────────────
    op.create_table(
        "knowledge_graph_edges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("knowledge_graph_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("knowledge_graph_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_name", sa.String(255), nullable=False),
        sa.Column("edge_type", sa.String(20), nullable=False),
        sa.Column("weight", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("is_admin_confirmed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("join_condition", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "from_node_id", "to_node_id", "relation_name",
                            name="uq_kg_edge_unique"),
    )
    op.create_index("ix_kg_edges_from_node", "knowledge_graph_edges", ["from_node_id"])

    # ── tools ─────────────────────────────────────────────────────────────────
    op.create_table(
        "tools",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("domain", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("pack_source", sa.String(50), nullable=False, server_default="ai_generated"),
        sa.Column("sql_template", sa.Text, nullable=False),
        sa.Column("input_schema", postgresql.JSONB, nullable=False),
        sa.Column("output_schema", postgresql.JSONB, nullable=False),
        sa.Column("permissions", postgresql.JSONB, nullable=True),
        sa.Column("last_validated_at", sa.String(50), nullable=True),
        sa.Column("validation_error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name", "version", name="uq_tool_tenant_name_version"),
    )
    op.create_index("ix_tools_tenant_id", "tools", ["tenant_id"])
    op.create_index("ix_tools_name", "tools", ["name"])

    # ── tool_embeddings ───────────────────────────────────────────────────────
    op.create_table(
        "tool_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tool_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tools.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute("ALTER TABLE tool_embeddings ADD COLUMN embedding vector(1536) NOT NULL DEFAULT array_fill(0, ARRAY[1536])::vector")
    op.execute("ALTER TABLE tool_embeddings ALTER COLUMN embedding DROP DEFAULT")
    # HNSW vector index created separately after pgvector confirmed
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_tool_embeddings_hnsw
        ON tool_embeddings USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 128)
    """)

    # ── tool_table_dependencies ───────────────────────────────────────────────
    op.create_table(
        "tool_table_dependencies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tool_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tools.id", ondelete="CASCADE"), nullable=False),
        sa.Column("metadata_table_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("metadata_tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tool_id", "metadata_table_id", name="uq_tool_table_dep"),
    )

    # ── tool_ranking_weights ──────────────────────────────────────────────────
    op.create_table(
        "tool_ranking_weights",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tool_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tools.id", ondelete="CASCADE"), nullable=False),
        sa.Column("success_rate", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("feedback_weight", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("execution_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_recalculated_at", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "tool_id", name="uq_tool_ranking_weight"),
    )

    # ── conversations ─────────────────────────────────────────────────────────
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("turn_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("redis_session_key", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_conversations_tenant_id", "conversations", ["tenant_id"])
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])

    # ── conversation_turns (partitioned by month) ─────────────────────────────
    op.execute("""
        CREATE TABLE conversation_turns (
            id UUID NOT NULL DEFAULT uuid_generate_v4(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            turn_number INTEGER NOT NULL,
            question TEXT NOT NULL,
            enriched_question TEXT,
            answer_text TEXT,
            answer_data JSONB,
            intent VARCHAR(50),
            tool_id UUID,
            sql_query TEXT,
            is_sql_generated BOOLEAN NOT NULL DEFAULT false,
            confidence_score FLOAT,
            lineage JSONB,
            follow_up_questions JSONB,
            chart_hint VARCHAR(50),
            execution_time_ms INTEGER,
            agents_invoked JSONB,
            error_log JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
    """)
    op.execute("""
        CREATE TABLE conversation_turns_default
        PARTITION OF conversation_turns DEFAULT
    """)
    op.create_index("ix_conv_turns_tenant_id", "conversation_turns", ["tenant_id"])
    op.create_index("ix_conv_turns_conversation_id", "conversation_turns", ["conversation_id"])

    # ── documents ─────────────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("file_type", sa.String(10), nullable=False),
        sa.Column("file_size_bytes", sa.Integer, nullable=False),
        sa.Column("storage_path", sa.String(1000), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("page_count", sa.Integer, nullable=True),
        sa.Column("document_type", sa.String(100), nullable=True),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("access_roles", postgresql.JSONB, nullable=True),
        sa.Column("linked_entity_ids", postgresql.JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"])

    # ── document_chunks ───────────────────────────────────────────────────────
    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("page_number", sa.Integer, nullable=True),
        sa.Column("section_title", sa.String(500), nullable=True),
        sa.Column("token_count", sa.Integer, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_doc_chunks_document_id", "document_chunks", ["document_id"])

    # ── document_embeddings ───────────────────────────────────────────────────
    op.create_table(
        "document_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute("ALTER TABLE document_embeddings ADD COLUMN embedding vector(1536) NOT NULL DEFAULT array_fill(0, ARRAY[1536])::vector")
    op.execute("ALTER TABLE document_embeddings ALTER COLUMN embedding DROP DEFAULT")
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_doc_embeddings_hnsw
        ON document_embeddings USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 128)
    """)

    # ── alert_rules ───────────────────────────────────────────────────────────
    op.create_table(
        "alert_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kpi_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("rule_type", sa.String(20), nullable=False),
        sa.Column("operator", sa.String(5), nullable=True),
        sa.Column("threshold_value", sa.Float, nullable=True),
        sa.Column("severity", sa.String(20), nullable=False, server_default="warning"),
        sa.Column("assigned_role_ids", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("report_template_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("monitoring_schedule", sa.String(20), nullable=False, server_default="hourly"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── alerts ────────────────────────────────────────────────────────────────
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alert_rule_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("triggered_value", sa.Float, nullable=True),
        sa.Column("expected_range", postgresql.JSONB, nullable=True),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("acknowledged_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("snoozed_until", sa.String(50), nullable=True),
        sa.Column("suggested_questions", postgresql.JSONB, nullable=True),
        sa.Column("rca_summary", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── user_feedback ─────────────────────────────────────────────────────────
    op.create_table(
        "user_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_turn_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── feedback_corrections ──────────────────────────────────────────────────
    op.create_table(
        "feedback_corrections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_turn_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("correction_text", sa.Text, nullable=False),
        sa.Column("admin_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── audit_log (partitioned by month) ──────────────────────────────────────
    op.execute("""
        CREATE TABLE audit_log (
            id UUID NOT NULL DEFAULT uuid_generate_v4(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
            user_id UUID,
            event_type VARCHAR(100) NOT NULL,
            resource_type VARCHAR(50),
            resource_id VARCHAR(255),
            question TEXT,
            tool_id UUID,
            sql_query TEXT,
            confidence_score FLOAT,
            execution_time_ms INTEGER,
            result_row_count INTEGER,
            ip_address VARCHAR(45),
            user_agent VARCHAR(500),
            request_id VARCHAR(36),
            metadata JSONB,
            created_at VARCHAR(50) NOT NULL
        ) PARTITION BY RANGE (created_at)
    """)
    op.execute("""
        CREATE TABLE audit_log_default
        PARTITION OF audit_log DEFAULT
    """)
    # Immutability trigger — block UPDATE/DELETE
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_audit_log_immutable()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log rows are immutable';
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_audit_log_no_update
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION fn_audit_log_immutable()
    """)
    op.create_index("ix_audit_log_tenant_id", "audit_log", ["tenant_id"])
    op.create_index("ix_audit_log_event_type", "audit_log", ["event_type"])

    # ── dashboards ────────────────────────────────────────────────────────────
    op.create_table(
        "dashboards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_shared", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("share_token", sa.String(100), nullable=True, unique=True),
        sa.Column("layout", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── dashboard_widgets ─────────────────────────────────────────────────────
    op.create_table(
        "dashboard_widgets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("dashboard_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("dashboards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_turn_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("widget_type", sa.String(50), nullable=False),
        sa.Column("position_x", sa.Integer, nullable=False),
        sa.Column("position_y", sa.Integer, nullable=False),
        sa.Column("width", sa.Integer, nullable=False, server_default="4"),
        sa.Column("height", sa.Integer, nullable=False, server_default="3"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── report_schedules ──────────────────────────────────────────────────────
    op.create_table(
        "report_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("questions", postgresql.JSONB, nullable=False),
        sa.Column("cron_expression", sa.String(100), nullable=False),
        sa.Column("delivery_channels", postgresql.JSONB, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("subscriber_ids", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── report_executions ─────────────────────────────────────────────────────
    op.create_table(
        "report_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("schedule_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("report_schedules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("storage_path", sa.String(1000), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("delivered_at", sa.String(50), nullable=True),
        sa.Column("execution_time_ms", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Row-Level Security (RLS) ──────────────────────────────────────────────
    for table in [
        "tenants", "roles", "role_permissions", "users", "user_roles",
        "connections", "metadata_tables", "metadata_columns", "metadata_relations",
        "semantic_entities", "semantic_attributes", "kpi_definitions",
        "business_glossary", "synonym_mappings", "business_rules",
        "knowledge_graph_nodes", "knowledge_graph_edges",
        "tools", "tool_embeddings", "tool_table_dependencies", "tool_ranking_weights",
        "conversations", "documents", "document_chunks", "document_embeddings",
        "alert_rules", "alerts", "user_feedback", "feedback_corrections",
        "dashboards", "report_schedules", "report_executions",
    ]:
        if "tenant_id" in [
            "tenants", "roles", "users", "connections", "metadata_tables",
            "metadata_columns", "metadata_relations", "semantic_entities",
            "semantic_attributes", "kpi_definitions", "business_glossary",
            "synonym_mappings", "business_rules", "knowledge_graph_nodes",
            "knowledge_graph_edges", "tools", "tool_embeddings", "tool_ranking_weights",
            "conversations", "documents", "document_chunks", "document_embeddings",
            "alert_rules", "alerts", "user_feedback", "feedback_corrections",
            "dashboards", "report_schedules", "report_executions",
        ]:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    tables = [
        "report_executions", "report_schedules", "dashboard_widgets", "dashboards",
        "feedback_corrections", "user_feedback", "alerts", "alert_rules",
        "document_embeddings", "document_chunks", "documents",
        "conversation_turns", "conversations",
        "tool_ranking_weights", "tool_table_dependencies", "tool_embeddings", "tools",
        "knowledge_graph_edges", "knowledge_graph_nodes",
        "business_rules", "synonym_mappings", "business_glossary",
        "kpi_definitions", "semantic_attributes", "semantic_entities",
        "metadata_relations", "metadata_columns", "metadata_tables",
        "connections", "user_roles", "users", "role_permissions", "roles", "tenants",
    ]
    for table in tables:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DROP TABLE IF EXISTS audit_log CASCADE")
