"""011 - epic_proposals: add raw_requirement column + draft state

Adds the raw_requirement text column and extends the state CHECK constraint
to include 'draft' (used by the requirement-capture flow).

Revision: 011
Revises: 010
"""

from alembic import op
import sqlalchemy as sa


revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Add raw_requirement column (stores the original free-text from the user)
    conn.execute(sa.text(
        "ALTER TABLE epic_proposals ADD COLUMN IF NOT EXISTS raw_requirement TEXT"
    ))

    # Extend state CHECK constraint to include 'draft'
    conn.execute(sa.text(
        "ALTER TABLE epic_proposals DROP CONSTRAINT IF EXISTS chk_epic_proposal_state"
    ))
    conn.execute(sa.text(
        "ALTER TABLE epic_proposals ADD CONSTRAINT chk_epic_proposal_state "
        "CHECK (state IN ('draft', 'proposed', 'accepted', 'rejected'))"
    ))


def downgrade() -> None:
    conn = op.get_bind()

    # Restore old constraint (draft rows will fail — acceptable for rollback)
    conn.execute(sa.text(
        "ALTER TABLE epic_proposals DROP CONSTRAINT IF EXISTS chk_epic_proposal_state"
    ))
    conn.execute(sa.text(
        "ALTER TABLE epic_proposals ADD CONSTRAINT chk_epic_proposal_state "
        "CHECK (state IN ('proposed', 'accepted', 'rejected'))"
    ))
    conn.execute(sa.text(
        "ALTER TABLE epic_proposals DROP COLUMN IF EXISTS raw_requirement"
    ))
