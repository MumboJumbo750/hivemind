"""Add prompt_history context refs.

Revision ID: 025
Revises: 024
Create Date: 2026-03-07 15:10:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "prompt_history",
        sa.Column(
            "context_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("prompt_history", "context_refs")
