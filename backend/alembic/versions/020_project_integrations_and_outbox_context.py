"""020 - project integrations and inbound project context

Revision: 020
Revises: 019
"""

from alembic import op
import sqlalchemy as sa


revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    for statement in (
        "ALTER TABLE project_integrations ADD COLUMN IF NOT EXISTS display_name VARCHAR(120)",
        "ALTER TABLE project_integrations ADD COLUMN IF NOT EXISTS integration_key VARCHAR(120)",
        "ALTER TABLE project_integrations ADD COLUMN IF NOT EXISTS base_url VARCHAR(500)",
        "ALTER TABLE project_integrations ADD COLUMN IF NOT EXISTS external_project_key VARCHAR(200)",
        "ALTER TABLE project_integrations ADD COLUMN IF NOT EXISTS project_selector JSONB",
        "ALTER TABLE project_integrations ADD COLUMN IF NOT EXISTS status_mapping JSONB",
        "ALTER TABLE project_integrations ADD COLUMN IF NOT EXISTS routing_hints JSONB",
        "ALTER TABLE project_integrations ADD COLUMN IF NOT EXISTS config JSONB",
        "ALTER TABLE project_integrations ADD COLUMN IF NOT EXISTS webhook_secret TEXT",
        "ALTER TABLE project_integrations ADD COLUMN IF NOT EXISTS access_token TEXT",
        "ALTER TABLE project_integrations ADD COLUMN IF NOT EXISTS last_health_state VARCHAR(30)",
        "ALTER TABLE project_integrations ADD COLUMN IF NOT EXISTS last_health_detail TEXT",
        "ALTER TABLE project_integrations ADD COLUMN IF NOT EXISTS health_checked_at TIMESTAMPTZ",
        "ALTER TABLE project_integrations ADD COLUMN IF NOT EXISTS last_event_at TIMESTAMPTZ",
        "ALTER TABLE project_integrations ADD COLUMN IF NOT EXISTS last_error_at TIMESTAMPTZ",
        "ALTER TABLE project_integrations ADD COLUMN IF NOT EXISTS last_error_detail TEXT",
        "ALTER TABLE sync_outbox ADD COLUMN IF NOT EXISTS project_id UUID REFERENCES projects(id)",
        "ALTER TABLE sync_outbox ADD COLUMN IF NOT EXISTS integration_id UUID REFERENCES project_integrations(id)",
        "ALTER TABLE sync_outbox ADD COLUMN IF NOT EXISTS routing_detail JSONB",
    ):
        conn.execute(sa.text(statement))

    conn.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_project_integrations_integration_key "
            "ON project_integrations (integration_key) "
            "WHERE integration_key IS NOT NULL"
        )
    )
    conn.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_sync_outbox_project_direction "
            "ON sync_outbox (project_id, direction, routing_state)"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_sync_outbox_project_direction"))
    conn.execute(sa.text("DROP INDEX IF EXISTS uq_project_integrations_integration_key"))

    for statement in (
        "ALTER TABLE sync_outbox DROP COLUMN IF EXISTS routing_detail",
        "ALTER TABLE sync_outbox DROP COLUMN IF EXISTS integration_id",
        "ALTER TABLE sync_outbox DROP COLUMN IF EXISTS project_id",
        "ALTER TABLE project_integrations DROP COLUMN IF EXISTS last_error_detail",
        "ALTER TABLE project_integrations DROP COLUMN IF EXISTS last_error_at",
        "ALTER TABLE project_integrations DROP COLUMN IF EXISTS last_event_at",
        "ALTER TABLE project_integrations DROP COLUMN IF EXISTS health_checked_at",
        "ALTER TABLE project_integrations DROP COLUMN IF EXISTS last_health_detail",
        "ALTER TABLE project_integrations DROP COLUMN IF EXISTS last_health_state",
        "ALTER TABLE project_integrations DROP COLUMN IF EXISTS access_token",
        "ALTER TABLE project_integrations DROP COLUMN IF EXISTS webhook_secret",
        "ALTER TABLE project_integrations DROP COLUMN IF EXISTS config",
        "ALTER TABLE project_integrations DROP COLUMN IF EXISTS routing_hints",
        "ALTER TABLE project_integrations DROP COLUMN IF EXISTS status_mapping",
        "ALTER TABLE project_integrations DROP COLUMN IF EXISTS project_selector",
        "ALTER TABLE project_integrations DROP COLUMN IF EXISTS external_project_key",
        "ALTER TABLE project_integrations DROP COLUMN IF EXISTS base_url",
        "ALTER TABLE project_integrations DROP COLUMN IF EXISTS integration_key",
        "ALTER TABLE project_integrations DROP COLUMN IF EXISTS display_name",
    ):
        conn.execute(sa.text(statement))
