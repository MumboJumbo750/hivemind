"""Expand conductor_dispatches.status column from VARCHAR(20) to VARCHAR(50)

New status values added in dispatch policy enforcement can exceed the old 20-char
limit (e.g. 'parallel_limit_exceeded' = 23 chars).

Revision ID: 027
Revises: 026
Create Date: 2026-03-07
"""

from alembic import op
import sqlalchemy as sa

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "conductor_dispatches",
        "status",
        existing_type=sa.String(20),
        type_=sa.String(50),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Truncate any values that exceed 20 chars before shrinking
    op.execute(
        "UPDATE conductor_dispatches SET status = LEFT(status, 20) WHERE length(status) > 20"
    )
    op.alter_column(
        "conductor_dispatches",
        "status",
        existing_type=sa.String(50),
        type_=sa.String(20),
        existing_nullable=False,
    )
