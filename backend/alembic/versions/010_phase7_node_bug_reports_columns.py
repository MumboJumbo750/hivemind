"""010 - add phase 7 columns to node_bug_reports (TASK-7-001)

Adds Phase 7 enrichment columns used for Sentry aggregation and epic routing.

Revision: 010
Revises: 009
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("node_bug_reports", sa.Column("sentry_issue_id", sa.Text(), nullable=True))
    op.add_column("node_bug_reports", sa.Column("stack_trace_hash", sa.Text(), nullable=True))
    op.add_column("node_bug_reports", sa.Column("first_seen", sa.DateTime(timezone=True), nullable=True))
    op.add_column("node_bug_reports", sa.Column("raw_payload", postgresql.JSONB(), nullable=True))
    op.add_column(
        "node_bug_reports",
        sa.Column(
            "epic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("epics.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "node_bug_reports",
        sa.Column("manually_routed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "node_bug_reports",
        sa.Column(
            "manually_routed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("node_bug_reports", sa.Column("manually_routed_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index(
        "idx_node_bug_reports_sentry_issue",
        "node_bug_reports",
        ["sentry_issue_id"],
        unique=True,
        postgresql_where=sa.text("sentry_issue_id IS NOT NULL"),
    )
    op.create_index(
        "idx_node_bug_reports_epic",
        "node_bug_reports",
        ["epic_id"],
        unique=False,
        postgresql_where=sa.text("epic_id IS NOT NULL"),
    )
    op.create_index(
        "idx_node_bug_reports_unrouted",
        "node_bug_reports",
        ["node_id"],
        unique=False,
        postgresql_where=sa.text("epic_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_node_bug_reports_unrouted", table_name="node_bug_reports")
    op.drop_index("idx_node_bug_reports_epic", table_name="node_bug_reports")
    op.drop_index("idx_node_bug_reports_sentry_issue", table_name="node_bug_reports")

    op.drop_column("node_bug_reports", "manually_routed_at")
    op.drop_column("node_bug_reports", "manually_routed_by")
    op.drop_column("node_bug_reports", "manually_routed")
    op.drop_column("node_bug_reports", "epic_id")
    op.drop_column("node_bug_reports", "raw_payload")
    op.drop_column("node_bug_reports", "first_seen")
    op.drop_column("node_bug_reports", "stack_trace_hash")
    op.drop_column("node_bug_reports", "sentry_issue_id")
