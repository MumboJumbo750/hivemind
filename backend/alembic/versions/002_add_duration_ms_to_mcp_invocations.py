"""Phase 2 — duration_ms Spalte zu mcp_invocations hinzufügen.

Revision ID: 002
Revises: 001
Create Date: 2026-02-28
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        ALTER TABLE mcp_invocations
        ADD COLUMN IF NOT EXISTS duration_ms INT;
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        ALTER TABLE mcp_invocations
        DROP COLUMN IF EXISTS duration_ms;
    """))
