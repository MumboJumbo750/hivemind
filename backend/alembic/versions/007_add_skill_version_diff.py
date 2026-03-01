"""007 — add diff_from_previous to skill_versions

Adds `diff_from_previous` TEXT column to the `skill_versions` table
for storing unified diff between consecutive versions.

Revision: 007
Revises: 006
"""
from alembic import op
from sqlalchemy import text

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        ALTER TABLE skill_versions
        ADD COLUMN IF NOT EXISTS diff_from_previous TEXT;
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        ALTER TABLE skill_versions
        DROP COLUMN IF EXISTS diff_from_previous;
    """))
