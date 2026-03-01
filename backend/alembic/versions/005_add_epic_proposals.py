"""Phase 4 — epic_proposals table for Epic-Proposal workflow.

Revision ID: 005
Revises: 004
Create Date: 2026-02-28
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # ─── epic_proposals table ────────────────────────────────────────────────
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS epic_proposals (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id        UUID NOT NULL REFERENCES projects(id),
            proposed_by       UUID NOT NULL REFERENCES users(id),
            title             TEXT NOT NULL,
            description       TEXT NOT NULL,
            rationale         TEXT,
            state             TEXT NOT NULL DEFAULT 'proposed',
            depends_on        UUID[],
            resulting_epic_id UUID REFERENCES epics(id),
            rejection_reason  TEXT,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            version           INT NOT NULL DEFAULT 1,
            CONSTRAINT chk_epic_proposal_state CHECK (state IN ('proposed', 'accepted', 'rejected'))
        );
    """))

    # ─── Indexes for fast Triage queries ─────────────────────────────────────
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_epic_proposals_project_state ON epic_proposals (project_id, state);
    """))
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_epic_proposals_proposed_by ON epic_proposals (proposed_by);
    """))

    # ─── context_boundaries table (used by TASK-4-002: set_context_boundary) ─
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS context_boundaries (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            task_id           UUID NOT NULL REFERENCES tasks(id) UNIQUE,
            allowed_skills    UUID[],
            allowed_docs      UUID[],
            max_token_budget  INT,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """))

    # ─── task_skills table (used by TASK-4-002: link_skill) ──────────────────
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS task_skills (
            task_id            UUID NOT NULL REFERENCES tasks(id),
            skill_id           UUID NOT NULL REFERENCES skills(id),
            pinned_version_id  UUID REFERENCES skill_versions(id),
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (task_id, skill_id)
        );
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DROP TABLE IF EXISTS task_skills;"))
    conn.execute(text("DROP TABLE IF EXISTS context_boundaries;"))
    conn.execute(text("DROP TABLE IF EXISTS epic_proposals;"))
