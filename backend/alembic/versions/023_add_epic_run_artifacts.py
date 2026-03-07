"""023 - add epic_run_artifacts table

Revision: 023
Revises: 022
"""

from alembic import op
import sqlalchemy as sa


revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS epic_run_artifacts (
              id UUID PRIMARY KEY,
              epic_run_id UUID NOT NULL REFERENCES epic_runs(id) ON DELETE CASCADE,
              epic_id UUID NOT NULL REFERENCES epics(id) ON DELETE CASCADE,
              task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
              artifact_type VARCHAR(40) NOT NULL,
              state VARCHAR(20) NOT NULL DEFAULT 'active',
              source_role VARCHAR(40),
              target_role VARCHAR(40),
              title TEXT NOT NULL,
              summary TEXT,
              payload JSONB NOT NULL DEFAULT '{}'::jsonb,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              released_at TIMESTAMPTZ
            )
            """
        )
    )
    conn.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_epic_run_artifacts_run_type_state "
            "ON epic_run_artifacts (epic_run_id, artifact_type, state, created_at DESC)"
        )
    )
    conn.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_epic_run_artifacts_task "
            "ON epic_run_artifacts (task_id, artifact_type, state)"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_epic_run_artifacts_task"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_epic_run_artifacts_run_type_state"))
    conn.execute(sa.text("DROP TABLE IF EXISTS epic_run_artifacts"))
