"""012 - Phase 8: Autonomy tables (ai_provider_configs, conductor_dispatches, review_recommendations, mcp_bridge_configs, project_integrations)

Revision: 012
Revises: 011
"""

from alembic import op
import sqlalchemy as sa


revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Drop old pre-migration versions of these tables (different schema, not tracked by alembic 011)
    conn.execute(sa.text("DROP TABLE IF EXISTS review_recommendations CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS conductor_dispatches CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS ai_provider_configs CASCADE"))

    # 1. ai_provider_configs
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS ai_provider_configs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_role VARCHAR(50) NOT NULL,
            provider VARCHAR(50) NOT NULL,
            model VARCHAR(200),
            endpoint VARCHAR(500),
            endpoints JSONB,
            pool_strategy VARCHAR(20) NOT NULL DEFAULT 'round_robin',
            api_key_encrypted BYTEA,
            api_key_nonce BYTEA,
            rpm_limit INTEGER,
            tpm_limit INTEGER,
            token_budget_daily INTEGER,
            enabled BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_ai_provider_configs_agent_role UNIQUE (agent_role)
        )
    """))

    # 2. conductor_dispatches
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS conductor_dispatches (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            trigger_type VARCHAR(50) NOT NULL,
            trigger_id VARCHAR(200) NOT NULL,
            trigger_detail VARCHAR(500),
            agent_role VARCHAR(50) NOT NULL,
            prompt_type VARCHAR(100),
            execution_mode VARCHAR(20) NOT NULL DEFAULT 'local',
            status VARCHAR(20) NOT NULL DEFAULT 'dispatched',
            cooldown_key VARCHAR(300),
            result JSONB,
            dispatched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ
        )
    """))
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_conductor_dispatches_trigger
            ON conductor_dispatches (trigger_type, trigger_id)
    """))
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_conductor_dispatches_role_time
            ON conductor_dispatches (agent_role, dispatched_at)
    """))
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_conductor_dispatches_cooldown
            ON conductor_dispatches (cooldown_key)
            WHERE status = 'dispatched'
    """))

    # 3. review_recommendations
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS review_recommendations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            reviewer_dispatch_id UUID REFERENCES conductor_dispatches(id) ON DELETE SET NULL,
            recommendation VARCHAR(30) NOT NULL,
            confidence FLOAT NOT NULL,
            checklist JSONB,
            reasoning TEXT,
            grace_period_until TIMESTAMPTZ,
            auto_approved BOOLEAN NOT NULL DEFAULT false,
            vetoed_by UUID REFERENCES users(id) ON DELETE SET NULL,
            vetoed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_review_recommendations_task_created
            ON review_recommendations (task_id, created_at DESC)
    """))
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_review_recommendations_grace
            ON review_recommendations (grace_period_until)
            WHERE auto_approved = false AND vetoed_at IS NULL
    """))

    # 4. mcp_bridge_configs
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS mcp_bridge_configs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(100) NOT NULL,
            namespace VARCHAR(50) NOT NULL,
            transport VARCHAR(20) NOT NULL,
            command VARCHAR(500),
            args JSONB,
            url VARCHAR(500),
            env_vars_encrypted BYTEA,
            env_vars_nonce BYTEA,
            enabled BOOLEAN NOT NULL DEFAULT true,
            tool_allowlist JSONB,
            tool_blocklist JSONB,
            discovered_tools JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_mcp_bridge_configs_name UNIQUE (name),
            CONSTRAINT uq_mcp_bridge_configs_namespace UNIQUE (namespace),
            CONSTRAINT chk_mcp_bridge_namespace_not_hivemind CHECK (namespace != 'hivemind')
        )
    """))

    # 5. project_integrations
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS project_integrations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            integration_type VARCHAR(50) NOT NULL,
            github_repo VARCHAR(200),
            github_project_id VARCHAR(100),
            status_field_id VARCHAR(100),
            priority_field_id VARCHAR(100),
            sync_enabled BOOLEAN NOT NULL DEFAULT true,
            sync_direction VARCHAR(30) NOT NULL DEFAULT 'bidirectional',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_project_integrations_project_type UNIQUE (project_id, integration_type)
        )
    """))

    # 6. governance default in app_settings
    conn.execute(sa.text("""
        INSERT INTO app_settings (key, value)
        VALUES ('governance', '{"review":"manual","epic_proposal":"manual","epic_scoping":"manual","skill_merge":"manual","guard_merge":"manual","decision_request":"manual","escalation":"manual"}')
        ON CONFLICT (key) DO NOTHING
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM app_settings WHERE key = 'governance'"))
    conn.execute(sa.text("DROP TABLE IF EXISTS project_integrations"))
    conn.execute(sa.text("DROP TABLE IF EXISTS mcp_bridge_configs"))
    conn.execute(sa.text("DROP TABLE IF EXISTS review_recommendations"))
    conn.execute(sa.text("DROP TABLE IF EXISTS conductor_dispatches"))
    conn.execute(sa.text("DROP TABLE IF EXISTS ai_provider_configs"))
