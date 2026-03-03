"""014 - Add ai_credentials table and credential_id FK on ai_provider_configs

Revision: 014
Revises: 013
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_credentials",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("provider_type", sa.String(50), nullable=False),
        sa.Column("api_key_encrypted", sa.LargeBinary, nullable=True),
        sa.Column("api_key_nonce", sa.LargeBinary, nullable=True),
        sa.Column("endpoint", sa.String(500), nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.add_column(
        "ai_provider_configs",
        sa.Column(
            "credential_id",
            UUID(as_uuid=True),
            sa.ForeignKey("ai_credentials.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("ai_provider_configs", "credential_id")
    op.drop_table("ai_credentials")
