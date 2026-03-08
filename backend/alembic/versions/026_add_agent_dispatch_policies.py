"""026 - Add agent_dispatch_policies table (TASK-AGENT-003).

Revision: 026
Revises: 025
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_dispatch_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_role", sa.String(50), nullable=False),
        sa.Column("preferred_execution_mode", sa.String(20), nullable=False, server_default="local"),
        sa.Column("fallback_chain", postgresql.JSONB(), nullable=True),
        sa.Column("rpm_limit", sa.Integer(), nullable=True),
        sa.Column("token_budget", sa.Integer(), nullable=True),
        sa.Column("max_parallel", sa.Integer(), nullable=True),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("agent_role", name="uq_agent_dispatch_policies_role"),
    )
    op.create_index(
        "ix_agent_dispatch_policies_role",
        "agent_dispatch_policies",
        ["agent_role"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_agent_dispatch_policies_role", table_name="agent_dispatch_policies")
    op.drop_table("agent_dispatch_policies")
