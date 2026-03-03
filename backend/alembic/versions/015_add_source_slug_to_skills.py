"""015 - Add source_slug column to skills table

Enables slug-based lookup of skills from task.pinned_skills JSONB array.
The source_slug corresponds to the seed filename stem (e.g. 'mcp-tool').

Revision: 015
Revises: 014
"""

import sqlalchemy as sa
from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "skills",
        sa.Column("source_slug", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_skills_source_slug",
        "skills",
        ["source_slug"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_skills_source_slug", table_name="skills")
    op.drop_column("skills", "source_slug")
