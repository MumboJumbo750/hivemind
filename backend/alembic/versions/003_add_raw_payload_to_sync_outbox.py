"""Phase 3 — raw_payload Spalte zu sync_outbox hinzufügen (TASK-3-011).

Revision ID: 003
Revises: 002
Create Date: 2026-03-01
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        ALTER TABLE sync_outbox
        ADD COLUMN IF NOT EXISTS raw_payload JSONB;
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        ALTER TABLE sync_outbox
        DROP COLUMN IF EXISTS raw_payload;
    """))
