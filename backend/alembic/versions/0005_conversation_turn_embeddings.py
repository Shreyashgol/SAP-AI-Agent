"""Add conversation_turn_embeddings for cross-conversation recall (long-term memory).

Stores a 1024-dim bge-large embedding per conversation turn, scoped to
tenant + user, with an HNSW cosine index for semantic recall over the user's
full conversation history.

Revision ID: 0005
Revises: 0004
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS conversation_turn_embeddings (
            id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id     UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            -- No FK to conversation_turns: it has a composite PK (id, created_at)
            -- for partitioning. conversation_id CASCADE handles cleanup.
            turn_id       UUID NOT NULL UNIQUE,
            content       TEXT NOT NULL,
            embedding     vector(1024) NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_conv_turn_emb_tenant "
        "ON conversation_turn_embeddings (tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_conv_turn_emb_user "
        "ON conversation_turn_embeddings (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_conv_turn_emb_conversation "
        "ON conversation_turn_embeddings (conversation_id)"
    )
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_conv_turn_emb_hnsw
        ON conversation_turn_embeddings USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 128)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS conversation_turn_embeddings")
