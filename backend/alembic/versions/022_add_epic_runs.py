"""022 - add epic_runs table

Revision: 022
Revises: 021
"""

from alembic import op
import sqlalchemy as sa


revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS epic_runs (
              id UUID PRIMARY KEY,
              epic_id UUID NOT NULL REFERENCES epics(id) ON DELETE CASCADE,
              started_by UUID NOT NULL REFERENCES users(id),
              status VARCHAR(30) NOT NULL,
              dry_run BOOLEAN NOT NULL DEFAULT false,
              config JSONB NOT NULL DEFAULT '{}'::jsonb,
              analysis JSONB NOT NULL DEFAULT '{}'::jsonb,
              started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              completed_at TIMESTAMPTZ
            )
            """
        )
    )
    conn.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_epic_runs_epic_started "
            "ON epic_runs (epic_id, started_at DESC)"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_epic_runs_epic_started"))
    conn.execute(sa.text("DROP TABLE IF EXISTS epic_runs"))
