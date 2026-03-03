"""013 - Add 'runtime' to skill_type CHECK constraint

Revision: 013
Revises: 012
"""

from alembic import op


revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("chk_skill_type", "skills", type_="check")
    op.create_check_constraint(
        "chk_skill_type",
        "skills",
        "skill_type IN ('system', 'domain', 'runtime')",
    )


def downgrade() -> None:
    op.drop_constraint("chk_skill_type", "skills", type_="check")
    op.create_check_constraint(
        "chk_skill_type",
        "skills",
        "skill_type IN ('system', 'domain')",
    )
