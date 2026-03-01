"""009 — add entity columns to notifications (TASK-6-001)

Adds entity_type + entity_id columns to notifications table
for dedup and linking. Adds index for dedup queries.

Revision: 009
Revises: 008
"""
from alembic import op
from sqlalchemy import text

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Add entity_type and entity_id columns
    conn.execute(text("""
        ALTER TABLE notifications
        ADD COLUMN IF NOT EXISTS entity_type TEXT,
        ADD COLUMN IF NOT EXISTS entity_id TEXT;
    """))

    # Index for dedup queries: (user_id, type, entity_id, created_at)
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_notifications_dedup
        ON notifications (user_id, type, entity_id, created_at)
        WHERE entity_id IS NOT NULL;
    """))

    # Index for user notification listing
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_notifications_user_read
        ON notifications (user_id, read, created_at DESC);
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DROP INDEX IF EXISTS ix_notifications_user_read;"))
    conn.execute(text("DROP INDEX IF EXISTS ix_notifications_dedup;"))
    conn.execute(text("""
        ALTER TABLE notifications
        DROP COLUMN IF EXISTS entity_type,
        DROP COLUMN IF EXISTS entity_id;
    """))
