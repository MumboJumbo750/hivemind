"""Phase 4 — Add lifecycle columns to skills table (TASK-4-005).

Adds token_count, proposed_by, rejection_rationale to skills for
Skill Lab lifecycle support.

Revision ID: 006
Revises: 005
Create Date: 2026-02-28
"""
from alembic import op
from sqlalchemy import text

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Add token_count column to skills
    conn.execute(text("""
        ALTER TABLE skills ADD COLUMN IF NOT EXISTS token_count INTEGER;
    """))

    # Add proposed_by (FK to users) — who created/proposed this skill
    conn.execute(text("""
        ALTER TABLE skills ADD COLUMN IF NOT EXISTS proposed_by UUID
            REFERENCES users(id);
    """))

    # Add rejection_rationale for rejected skills
    conn.execute(text("""
        ALTER TABLE skills ADD COLUMN IF NOT EXISTS rejection_rationale TEXT;
    """))

    # Index on lifecycle for fast filter queries
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_skills_lifecycle ON skills (lifecycle);
    """))

    # Index on (project_id, lifecycle) for Skill Lab queries
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_skills_project_lifecycle
            ON skills (project_id, lifecycle);
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DROP INDEX IF EXISTS ix_skills_project_lifecycle;"))
    conn.execute(text("DROP INDEX IF EXISTS ix_skills_lifecycle;"))
    conn.execute(text("ALTER TABLE skills DROP COLUMN IF EXISTS rejection_rationale;"))
    conn.execute(text("ALTER TABLE skills DROP COLUMN IF EXISTS proposed_by;"))
    conn.execute(text("ALTER TABLE skills DROP COLUMN IF EXISTS token_count;"))
