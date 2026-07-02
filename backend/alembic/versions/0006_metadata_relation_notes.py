"""Add notes column to metadata_relations for join purpose hints.

The ERPRef prior (SAP B1 warm-start) carries a plain-English purpose for each
join ("Get customer name, address, payment terms"). Persisting it here lets the
runtime text-to-SQL path surface why a relationship exists, so the model picks
the right join — without reading the reference files in the hot path.

Revision ID: 0006
Revises: 0005
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE metadata_relations ADD COLUMN IF NOT EXISTS notes TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE metadata_relations DROP COLUMN IF EXISTS notes")
