"""Add composite index on learning_artifacts (agent_role, artifact_type, created_at)

Improves query performance for agent-role-specific learning artifact lookups
used in prompt generation and MCP tool responses.

Revision ID: 028
Revises: 027
Create Date: 2026-03-07
"""

from alembic import op

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_learning_artifacts_role_type_created",
        "learning_artifacts",
        ["agent_role", "artifact_type", "created_at"],
        postgresql_ops={"created_at": "DESC"},
    )


def downgrade() -> None:
    op.drop_index("ix_learning_artifacts_role_type_created", table_name="learning_artifacts")
