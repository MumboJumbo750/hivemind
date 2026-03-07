"""021 - agent loop governance recommendations and learning artifacts

Revision: 021
Revises: 020
"""

from alembic import op
import sqlalchemy as sa


revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS governance_recommendations (
              id UUID PRIMARY KEY,
              governance_type VARCHAR(50) NOT NULL,
              governance_level VARCHAR(20) NOT NULL,
              target_type VARCHAR(50) NOT NULL,
              target_ref VARCHAR(200) NOT NULL,
              status VARCHAR(30) NOT NULL DEFAULT 'pending_human',
              agent_role VARCHAR(50) NOT NULL,
              prompt_type VARCHAR(100),
              action VARCHAR(50),
              confidence FLOAT,
              rationale TEXT,
              payload JSONB,
              fingerprint VARCHAR(64) NOT NULL UNIQUE,
              dispatch_id UUID REFERENCES conductor_dispatches(id) ON DELETE SET NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              executed_at TIMESTAMPTZ
            )
            """
        )
    )
    conn.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_governance_recommendations_lookup "
            "ON governance_recommendations (governance_type, target_type, target_ref, status, created_at DESC)"
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS learning_artifacts (
              id UUID PRIMARY KEY,
              artifact_type VARCHAR(50) NOT NULL,
              status VARCHAR(30) NOT NULL DEFAULT 'observation',
              source_type VARCHAR(50) NOT NULL,
              source_ref VARCHAR(200) NOT NULL,
              source_dispatch_id UUID REFERENCES conductor_dispatches(id) ON DELETE SET NULL,
              agent_role VARCHAR(50),
              project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
              epic_id UUID REFERENCES epics(id) ON DELETE SET NULL,
              task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
              summary TEXT NOT NULL,
              detail JSONB,
              confidence FLOAT,
              fingerprint VARCHAR(64) NOT NULL UNIQUE,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    )
    conn.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_learning_artifacts_source "
            "ON learning_artifacts (source_type, source_ref, created_at DESC)"
        )
    )
    conn.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_learning_artifacts_scope "
            "ON learning_artifacts (project_id, epic_id, task_id, status, created_at DESC)"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_learning_artifacts_scope"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_learning_artifacts_source"))
    conn.execute(sa.text("DROP TABLE IF EXISTS learning_artifacts"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_governance_recommendations_lookup"))
    conn.execute(sa.text("DROP TABLE IF EXISTS governance_recommendations"))
