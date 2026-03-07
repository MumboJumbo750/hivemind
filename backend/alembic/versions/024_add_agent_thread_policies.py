"""Add agent thread policies and sessions.

Revision ID: 024
Revises: 023
Create Date: 2026-03-07 14:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_provider_configs",
        sa.Column("thread_policy", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column(
            "agent_thread_overrides",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    op.create_table(
        "agent_thread_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thread_key", sa.String(length=255), nullable=False),
        sa.Column("agent_role", sa.String(length=50), nullable=False),
        sa.Column("thread_policy", sa.String(length=50), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("epic_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("dispatch_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("session_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["epic_id"], ["epics.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_key"),
    )
    op.create_index(
        "ix_agent_thread_sessions_role_status",
        "agent_thread_sessions",
        ["agent_role", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_agent_thread_sessions_role_status", table_name="agent_thread_sessions")
    op.drop_table("agent_thread_sessions")
    op.drop_column("projects", "agent_thread_overrides")
    op.drop_column("ai_provider_configs", "thread_policy")
