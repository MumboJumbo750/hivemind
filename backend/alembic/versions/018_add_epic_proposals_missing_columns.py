"""018 - Add missing columns to epic_proposals

Additive migration that adds the two columns which were present in the
005_add_epic_proposals CREATE TABLE statement but missing from the original
001_initial_schema definition:

  - epic_proposals.rejection_reason  (TEXT, nullable)
  - epic_proposals.updated_at        (TIMESTAMPTZ, nullable, default now())

Root cause: 005 used CREATE TABLE IF NOT EXISTS — the table already existed
from 001 so the columns were never added.

Revision: 018
Revises: 017
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(text("""
        ALTER TABLE epic_proposals
            ADD COLUMN IF NOT EXISTS rejection_reason TEXT,
            ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();
    """))

    # Back-fill updated_at for existing rows so it is never NULL
    conn.execute(text("""
        UPDATE epic_proposals
        SET updated_at = created_at
        WHERE updated_at IS NULL;
    """))


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(text("""
        ALTER TABLE epic_proposals
            DROP COLUMN IF EXISTS rejection_reason,
            DROP COLUMN IF EXISTS updated_at;
    """))
