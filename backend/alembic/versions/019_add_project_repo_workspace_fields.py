"""019 - Add repo/workspace fields to projects

Revision: 019
Revises: 018
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(text("""
        ALTER TABLE projects
            ADD COLUMN IF NOT EXISTS repo_host_path TEXT,
            ADD COLUMN IF NOT EXISTS workspace_root TEXT,
            ADD COLUMN IF NOT EXISTS workspace_mode TEXT,
            ADD COLUMN IF NOT EXISTS onboarding_status TEXT,
            ADD COLUMN IF NOT EXISTS default_branch TEXT,
            ADD COLUMN IF NOT EXISTS remote_url TEXT,
            ADD COLUMN IF NOT EXISTS detected_stack JSONB;
    """))


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(text("""
        ALTER TABLE projects
            DROP COLUMN IF EXISTS detected_stack,
            DROP COLUMN IF EXISTS remote_url,
            DROP COLUMN IF EXISTS default_branch,
            DROP COLUMN IF EXISTS onboarding_status,
            DROP COLUMN IF EXISTS workspace_mode,
            DROP COLUMN IF EXISTS workspace_root,
            DROP COLUMN IF EXISTS repo_host_path;
    """))
