"""Phase 1 — Vollständiges initiales Datenbankschema.

Alle Tabellen werden in Phase 1 angelegt (auch wenn viele Spalten erst später befüllt werden).
Keine späteren Migrations-Überraschungen.

Revision ID: 001
Revises: -
Create Date: 2026-02-27
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(text("""
        CREATE EXTENSION IF NOT EXISTS vector;
    """))

    # ─── FEDERATION ──────────────────────────────────────────────────────────

    conn.execute(text("""
        CREATE TABLE nodes (
          id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          node_name   TEXT NOT NULL,
          node_url    TEXT NOT NULL UNIQUE,
          public_key  TEXT UNIQUE,
          status      TEXT NOT NULL DEFAULT 'active',
          last_seen   TIMESTAMPTZ,
          deleted_at  TIMESTAMPTZ,
          created_at  TIMESTAMPTZ DEFAULT now()
        );
    """))

    conn.execute(text("""
        CREATE TABLE node_identity (
          node_id        UUID PRIMARY KEY REFERENCES nodes(id),
          singleton_guard BOOLEAN NOT NULL DEFAULT true UNIQUE CHECK (singleton_guard = true),
          node_name   TEXT NOT NULL,
          private_key TEXT NOT NULL,
          public_key  TEXT NOT NULL,
          previous_public_key TEXT,
          key_rotated_at TIMESTAMPTZ,
          created_at  TIMESTAMPTZ DEFAULT now()
        );
    """))

    # ─── CORE: Users ─────────────────────────────────────────────────────────

    conn.execute(text("""
        CREATE TABLE users (
          id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          username      TEXT NOT NULL UNIQUE,
          display_name  TEXT,
          email         TEXT UNIQUE,
          password_hash TEXT,
          api_key_hash  TEXT UNIQUE,
          role          TEXT NOT NULL DEFAULT 'developer',
          avatar_url    TEXT,
          avatar_frame  TEXT,
          bio           TEXT,
          preferred_theme TEXT DEFAULT 'space-neon',
          preferred_tone  TEXT DEFAULT 'game',
          notification_preferences JSONB DEFAULT '{}'::jsonb,
          exp_points    INT NOT NULL DEFAULT 0,
          created_at    TIMESTAMPTZ DEFAULT now(),
          CONSTRAINT valid_preferred_theme CHECK (preferred_theme IN ('space-neon', 'industrial-amber', 'operator-mono')),
          CONSTRAINT valid_preferred_tone  CHECK (preferred_tone  IN ('game', 'pro'))
        );
    """))

    # ─── SYSTEM CONFIGURATION ────────────────────────────────────────────────

    conn.execute(text("""
        CREATE TABLE app_settings (
          key        TEXT PRIMARY KEY,
          value      TEXT NOT NULL,
          version    INT NOT NULL DEFAULT 0,
          updated_by UUID REFERENCES users(id),
          updated_at TIMESTAMPTZ DEFAULT now()
        );
    """))

    # Bootstrap settings
    conn.execute(text("""
        INSERT INTO app_settings (key, value) VALUES
          ('hivemind_mode',               'solo'),
          ('current_phase',               '1'),
          ('federation_enabled',          'false'),
          ('token_budget_default',        '8000'),
          ('routing_threshold',           '0.85'),
          ('audit_retention_payload_days','90'),
          ('audit_retention_summary_days','365'),
          ('notification_retention_days', '90'),
          ('notification_mode',           'client'),
          ('backup_cron',                 '0 2 * * *'),
          ('backup_retention_daily',      '7'),
          ('backup_retention_weekly',     '4');
    """))

    # ─── AI PROVIDER CONFIGS ─────────────────────────────────────────────────

    conn.execute(text("""
        CREATE TABLE ai_provider_configs (
          agent_role        TEXT PRIMARY KEY,
          provider          TEXT NOT NULL,
          model             TEXT NOT NULL,
          endpoint          TEXT,
          endpoints         JSONB,
          pool_strategy     TEXT DEFAULT 'round_robin',
          api_key_encrypted TEXT,
          api_key_nonce     TEXT,
          token_budget      INT NOT NULL DEFAULT 8000,
          rpm_limit         INT NOT NULL DEFAULT 10,
          enabled           BOOLEAN NOT NULL DEFAULT true,
          updated_by        UUID REFERENCES users(id),
          updated_at        TIMESTAMPTZ DEFAULT now(),
          CONSTRAINT valid_agent_role    CHECK (agent_role IN ('kartograph','stratege','architekt','worker','gaertner','triage','reviewer')),
          CONSTRAINT valid_provider      CHECK (provider IN ('anthropic','openai','google','ollama','custom')),
          CONSTRAINT endpoint_required_for_local CHECK (
            (provider NOT IN ('ollama','custom')) OR (endpoint IS NOT NULL OR endpoints IS NOT NULL)
          ),
          CONSTRAINT valid_pool_strategy CHECK (pool_strategy IN ('round_robin','weighted','least_busy'))
        );
    """))

    # ─── CONDUCTOR DISPATCHES ────────────────────────────────────────────────

    conn.execute(text("""
        CREATE TABLE conductor_dispatches (
          id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          trigger_event   TEXT NOT NULL,
          trigger_entity_id UUID,
          agent_role      TEXT NOT NULL,
          prompt_type     TEXT NOT NULL,
          provider        TEXT,
          status          TEXT NOT NULL DEFAULT 'dispatched',
          error_message   TEXT,
          duration_ms     INT,
          idempotency_key TEXT NOT NULL UNIQUE,
          created_at      TIMESTAMPTZ DEFAULT now(),
          completed_at    TIMESTAMPTZ,
          CONSTRAINT valid_dispatch_status CHECK (status IN ('dispatched','completed','failed','vetoed'))
        );
    """))

    # ─── PROJECTS ────────────────────────────────────────────────────────────

    conn.execute(text("""
        CREATE TABLE projects (
          id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          name        TEXT NOT NULL,
          slug        TEXT NOT NULL UNIQUE,
          description TEXT,
          created_by  UUID NOT NULL REFERENCES users(id),
          created_at  TIMESTAMPTZ DEFAULT now()
        );
    """))

    conn.execute(text("""
        CREATE TABLE project_members (
          project_id  UUID NOT NULL REFERENCES projects(id),
          user_id     UUID NOT NULL REFERENCES users(id),
          role        TEXT NOT NULL DEFAULT 'developer',
          PRIMARY KEY (project_id, user_id)
        );
    """))

    # ─── GAMIFICATION ────────────────────────────────────────────────────────

    conn.execute(text("""
        CREATE TABLE level_thresholds (
          level        INT PRIMARY KEY,
          exp_required INT NOT NULL,
          rank_name    TEXT NOT NULL,
          unlocks      TEXT
        );
    """))

    conn.execute(text("""
        INSERT INTO level_thresholds VALUES
          (1,      0, 'Rookie Kommandant',    NULL),
          (2,    100, 'Einsatz-Kommandant',   NULL),
          (3,    250, 'Veteran',               NULL),
          (4,    500, 'Elite-Kommandant',      NULL),
          (5,   1000, 'Meister-Kommandant',    'avatar:silver-frame'),
          (6,   2000, 'Gilden-Ältester',       NULL),
          (7,   4000, 'Legenden-Kommandant',   'theme:operator-mono'),
          (8,   8000, 'Hivemind-Architekt',    'avatar:gold-frame'),
          (9,  15000, 'Sovereign',             NULL),
          (10, 30000, 'Grand Sovereign',       'avatar:holo-frame');
    """))

    conn.execute(text("""
        CREATE TABLE badge_definitions (
          badge_id        TEXT PRIMARY KEY,
          title           TEXT NOT NULL,
          description     TEXT NOT NULL,
          icon            TEXT,
          category        TEXT NOT NULL DEFAULT 'general',
          unlock_condition TEXT NOT NULL,
          exp_reward      INT NOT NULL DEFAULT 0,
          created_at      TIMESTAMPTZ DEFAULT now()
        );
    """))

    conn.execute(text("""
        INSERT INTO badge_definitions VALUES
          ('fog_clearer',       'Fog Clearer',       '500 Code-Nodes im Nexus Grid erkundet',              '🗺️', 'exploration',   'code_nodes_explored >= 500',          200),
          ('guild_contributor', 'Guild Contributor', '10 eigene Skills von Peers übernommen',               '⚔️', 'collaboration', 'skills_forked_by_peers >= 10',        150),
          ('master_architect',  'Master Architect',  '20 Epics erfolgreich abgeschlossen',                  '🏗️', 'quality',       'epics_completed >= 20',               300),
          ('sla_savior',        'SLA Savior',        '10 Eskalationen innerhalb SLA gelöst',                '⏱️', 'quality',       'escalations_resolved_in_sla >= 10',   100),
          ('first_blood',       'First Blood',       'Ersten Task abgeschlossen',                           '🎯', 'general',       'tasks_completed >= 1',                 25),
          ('cartographer',      'Cartographer',      '1000 Code-Nodes kartiert',                            '🌍', 'exploration',   'code_nodes_explored >= 1000',         500),
          ('skill_smith',       'Skill Smith',       '10 Skill-Proposals gemergt',                          '🔧', 'quality',       'skills_merged >= 10',                 200);
    """))

    conn.execute(text("""
        CREATE TABLE user_achievements (
          id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          badge_id    TEXT NOT NULL REFERENCES badge_definitions(badge_id),
          earned_at   TIMESTAMPTZ DEFAULT now(),
          UNIQUE(user_id, badge_id)
        );
    """))

    conn.execute(text("""
        CREATE TABLE exp_events (
          id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          user_id     UUID NOT NULL REFERENCES users(id),
          event_type  TEXT NOT NULL,
          entity_id   UUID,
          exp_awarded INTEGER NOT NULL,
          reason      TEXT,
          created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """))

    conn.execute(text("CREATE INDEX idx_exp_events_user ON exp_events (user_id, created_at DESC);"))

    # ─── EPICS & TASKS ────────────────────────────────────────────────────────

    conn.execute(text("CREATE SEQUENCE epic_key_seq;"))

    conn.execute(text("""
        CREATE TABLE epics (
          id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          epic_key        TEXT NOT NULL UNIQUE,
          project_id      UUID REFERENCES projects(id),
          external_id     TEXT UNIQUE,
          title           TEXT NOT NULL,
          description     TEXT,
          owner_id        UUID REFERENCES users(id),
          backup_owner_id UUID REFERENCES users(id),
          state           TEXT NOT NULL DEFAULT 'incoming',
          priority        TEXT DEFAULT 'medium',
          sla_due_at      TIMESTAMPTZ,
          dod_framework   JSONB,
          embedding       vector(768),
          embedding_model TEXT,
          version         INT NOT NULL DEFAULT 0,
          origin_node_id  UUID REFERENCES nodes(id),
          created_at      TIMESTAMPTZ DEFAULT now(),
          updated_at      TIMESTAMPTZ DEFAULT now(),
          CONSTRAINT chk_epic_priority CHECK (priority IN ('low','medium','high','critical')),
          CHECK (origin_node_id IS NOT NULL OR project_id IS NOT NULL),
          CHECK (origin_node_id IS NOT NULL OR owner_id IS NOT NULL)
        );
    """))

    conn.execute(text("""
        CREATE OR REPLACE FUNCTION prevent_epic_key_update()
        RETURNS trigger AS $$
        BEGIN
          IF NEW.epic_key IS DISTINCT FROM OLD.epic_key THEN
            RAISE EXCEPTION 'epic_key is immutable';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """))

    conn.execute(text("""
        CREATE TRIGGER trg_epics_epic_key_immutable
        BEFORE UPDATE ON epics
        FOR EACH ROW
        WHEN (OLD.epic_key IS DISTINCT FROM NEW.epic_key)
        EXECUTE FUNCTION prevent_epic_key_update();
    """))

    conn.execute(text("CREATE SEQUENCE task_key_seq;"))

    conn.execute(text("""
        CREATE TABLE tasks (
          id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          task_key           TEXT NOT NULL UNIQUE,
          epic_id            UUID NOT NULL REFERENCES epics(id),
          parent_task_id     UUID REFERENCES tasks(id),
          title              TEXT NOT NULL,
          description        TEXT,
          state              TEXT NOT NULL DEFAULT 'incoming',
          version            INT NOT NULL DEFAULT 0,
          definition_of_done JSONB,
          quality_gate       JSONB,
          assigned_to        UUID REFERENCES users(id),
          assigned_node_id   UUID REFERENCES nodes(id),
          pinned_skills      JSONB DEFAULT '[]',
          result             TEXT,
          artifacts          JSONB DEFAULT '[]',
          qa_failed_count    INT NOT NULL DEFAULT 0,
          review_comment     TEXT,
          external_id        TEXT UNIQUE,
          created_at         TIMESTAMPTZ DEFAULT now(),
          updated_at         TIMESTAMPTZ DEFAULT now()
        );
    """))

    conn.execute(text("""
        CREATE OR REPLACE FUNCTION prevent_task_key_update()
        RETURNS trigger AS $$
        BEGIN
          IF NEW.task_key IS DISTINCT FROM OLD.task_key THEN
            RAISE EXCEPTION 'task_key is immutable';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """))

    conn.execute(text("""
        CREATE TRIGGER trg_tasks_task_key_immutable
        BEFORE UPDATE ON tasks
        FOR EACH ROW
        WHEN (OLD.task_key IS DISTINCT FROM NEW.task_key)
        EXECUTE FUNCTION prevent_task_key_update();
    """))

    # ─── REVIEW RECOMMENDATIONS ──────────────────────────────────────────────

    conn.execute(text("""
        CREATE TABLE review_recommendations (
          id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          task_id         UUID NOT NULL REFERENCES tasks(id),
          recommendation  TEXT NOT NULL,
          confidence      FLOAT NOT NULL,
          summary         TEXT NOT NULL,
          checklist       JSONB NOT NULL DEFAULT '[]',
          concerns        JSONB NOT NULL DEFAULT '[]',
          grace_until     TIMESTAMPTZ,
          accepted_by     UUID REFERENCES users(id),
          accepted_at     TIMESTAMPTZ,
          overridden      BOOLEAN NOT NULL DEFAULT false,
          created_at      TIMESTAMPTZ DEFAULT now(),
          CONSTRAINT valid_recommendation CHECK (recommendation IN ('approve','reject','needs_human_review')),
          CONSTRAINT valid_confidence     CHECK (confidence >= 0.0 AND confidence <= 1.0)
        );
    """))

    conn.execute(text("CREATE INDEX idx_review_recommendations_task ON review_recommendations(task_id);"))
    conn.execute(text("""
        CREATE INDEX idx_review_recommendations_pending ON review_recommendations(grace_until)
          WHERE accepted_by IS NULL AND overridden = false AND grace_until IS NOT NULL;
    """))

    # ─── SKILLS ──────────────────────────────────────────────────────────────

    conn.execute(text("""
        CREATE TABLE skills (
          id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          project_id     UUID REFERENCES projects(id),
          title          TEXT NOT NULL,
          content        TEXT NOT NULL,
          service_scope  TEXT[] NOT NULL DEFAULT '{}',
          stack          TEXT[] NOT NULL DEFAULT '{}',
          version_range  JSONB,
          owner_id       UUID REFERENCES users(id),
          confidence     NUMERIC(3,2) DEFAULT 0.5,
          source_epics   TEXT[] DEFAULT '{}',
          skill_type     TEXT NOT NULL DEFAULT 'domain',
          lifecycle      TEXT NOT NULL DEFAULT 'draft',
          version        INT NOT NULL DEFAULT 1,
          embedding      vector(768),
          embedding_model TEXT,
          origin_node_id UUID REFERENCES nodes(id),
          federation_scope TEXT NOT NULL DEFAULT 'local',
          deleted_at     TIMESTAMPTZ,
          created_at     TIMESTAMPTZ DEFAULT now(),
          updated_at     TIMESTAMPTZ DEFAULT now(),
          CONSTRAINT chk_skill_type CHECK (skill_type IN ('system','domain')),
          CHECK (origin_node_id IS NOT NULL OR owner_id IS NOT NULL)
        );
    """))

    conn.execute(text("""
        CREATE TABLE skill_versions (
          id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          skill_id        UUID NOT NULL REFERENCES skills(id),
          version         INT NOT NULL,
          content         TEXT NOT NULL,
          parent_versions JSONB DEFAULT '[]',
          token_count     INT,
          changed_by      UUID NOT NULL REFERENCES users(id),
          created_at      TIMESTAMPTZ DEFAULT now(),
          UNIQUE(skill_id, version)
        );
    """))

    conn.execute(text("""
        CREATE TABLE skill_parents (
          child_id   UUID NOT NULL REFERENCES skills(id),
          parent_id  UUID NOT NULL REFERENCES skills(id),
          order_idx  INT NOT NULL DEFAULT 0,
          PRIMARY KEY (child_id, parent_id),
          CHECK (child_id != parent_id)
        );
    """))

    conn.execute(text("""
        CREATE TABLE skill_change_proposals (
          id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          skill_id     UUID NOT NULL REFERENCES skills(id),
          proposed_by  UUID NOT NULL REFERENCES users(id),
          diff         TEXT NOT NULL,
          rationale    TEXT NOT NULL,
          state        TEXT NOT NULL DEFAULT 'open',
          reviewed_by  UUID REFERENCES users(id),
          reviewed_at  TIMESTAMPTZ,
          review_note  TEXT,
          version      INT NOT NULL DEFAULT 0,
          created_at   TIMESTAMPTZ DEFAULT now()
        );
    """))

    # ─── DOCS & CONTEXT ──────────────────────────────────────────────────────

    conn.execute(text("""
        CREATE TABLE docs (
          id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          title       TEXT NOT NULL,
          content     TEXT NOT NULL,
          epic_id     UUID REFERENCES epics(id),
          embedding   vector(768),
          embedding_model TEXT,
          version     INT NOT NULL DEFAULT 0,
          updated_by  UUID REFERENCES users(id),
          created_at  TIMESTAMPTZ DEFAULT now(),
          updated_at  TIMESTAMPTZ DEFAULT now()
        );
    """))

    conn.execute(text("""
        CREATE TABLE context_boundaries (
          id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          task_id          UUID NOT NULL UNIQUE REFERENCES tasks(id),
          allowed_skills   UUID[] DEFAULT '{}',
          allowed_docs     UUID[] DEFAULT '{}',
          external_access  TEXT[] DEFAULT '{}',
          max_token_budget INT DEFAULT 8000,
          version          INT NOT NULL DEFAULT 0,
          set_by           UUID NOT NULL REFERENCES users(id),
          created_at       TIMESTAMPTZ DEFAULT now()
        );
    """))

    # ─── WIKI ─────────────────────────────────────────────────────────────────

    conn.execute(text("""
        CREATE TABLE wiki_categories (
          id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          parent_id   UUID REFERENCES wiki_categories(id),
          title       TEXT NOT NULL,
          slug        TEXT NOT NULL UNIQUE,
          sort_order  INT NOT NULL DEFAULT 0,
          created_at  TIMESTAMPTZ DEFAULT now()
        );
    """))

    conn.execute(text("""
        CREATE TABLE wiki_articles (
          id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          category_id   UUID REFERENCES wiki_categories(id),
          title         TEXT NOT NULL,
          slug          TEXT NOT NULL UNIQUE,
          content       TEXT NOT NULL,
          tags          TEXT[] NOT NULL DEFAULT '{}',
          linked_epics  UUID[] DEFAULT '{}',
          linked_skills UUID[] DEFAULT '{}',
          author_id         UUID REFERENCES users(id),
          embedding         vector(768),
          embedding_model   TEXT,
          version           INT NOT NULL DEFAULT 1,
          origin_node_id    UUID REFERENCES nodes(id),
          federation_scope  TEXT NOT NULL DEFAULT 'local',
          deleted_at        TIMESTAMPTZ,
          created_at        TIMESTAMPTZ DEFAULT now(),
          updated_at        TIMESTAMPTZ DEFAULT now(),
          CHECK (origin_node_id IS NOT NULL OR author_id IS NOT NULL)
        );
    """))

    conn.execute(text("""
        CREATE TABLE wiki_versions (
          id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          article_id  UUID NOT NULL REFERENCES wiki_articles(id),
          version     INT NOT NULL,
          content     TEXT NOT NULL,
          changed_by  UUID NOT NULL REFERENCES users(id),
          created_at  TIMESTAMPTZ DEFAULT now(),
          UNIQUE(article_id, version)
        );
    """))

    # ─── NEXUS GRID ──────────────────────────────────────────────────────────

    conn.execute(text("""
        CREATE TABLE code_nodes (
          id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          project_id  UUID REFERENCES projects(id),
          path        TEXT NOT NULL,
          node_type   TEXT NOT NULL,
          label       TEXT NOT NULL,
          explored_at TIMESTAMPTZ,
          explored_by UUID REFERENCES users(id),
          embedding   vector(768),
          embedding_model TEXT,
          metadata    JSONB,
          origin_node_id   UUID REFERENCES nodes(id),
          federation_scope TEXT NOT NULL DEFAULT 'federated',
          exploring_node_id UUID REFERENCES nodes(id),
          created_at  TIMESTAMPTZ DEFAULT now(),
          UNIQUE(project_id, path),
          CHECK (origin_node_id IS NOT NULL OR project_id IS NOT NULL)
        );
    """))

    conn.execute(text("""
        CREATE TABLE code_edges (
          id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          project_id     UUID REFERENCES projects(id),
          source_id      UUID NOT NULL REFERENCES code_nodes(id),
          target_id      UUID NOT NULL REFERENCES code_nodes(id),
          edge_type      TEXT NOT NULL,
          origin_node_id UUID REFERENCES nodes(id),
          created_at     TIMESTAMPTZ DEFAULT now(),
          UNIQUE(source_id, target_id, edge_type),
          CHECK (origin_node_id IS NOT NULL OR project_id IS NOT NULL)
        );
    """))

    conn.execute(text("""
        CREATE TABLE discovery_sessions (
          id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          project_id        UUID REFERENCES projects(id),
          area              TEXT NOT NULL,
          description       TEXT,
          exploring_node_id UUID NOT NULL REFERENCES nodes(id),
          exploring_user_id UUID NOT NULL REFERENCES users(id),
          status            TEXT NOT NULL DEFAULT 'active',
          started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
          ended_at          TIMESTAMPTZ,
          origin_node_id    UUID REFERENCES nodes(id),
          federation_scope  TEXT NOT NULL DEFAULT 'federated',
          created_at        TIMESTAMPTZ DEFAULT now()
        );
    """))

    conn.execute(text("""
        CREATE INDEX idx_discovery_sessions_active
          ON discovery_sessions(exploring_node_id) WHERE status = 'active';
    """))

    conn.execute(text("""
        CREATE TABLE node_bug_reports (
          id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          node_id    UUID NOT NULL REFERENCES code_nodes(id),
          sentry_id  TEXT,
          severity   TEXT,
          count      INT NOT NULL DEFAULT 1,
          last_seen  TIMESTAMPTZ,
          created_at TIMESTAMPTZ DEFAULT now()
        );
    """))

    conn.execute(text("""
        CREATE TABLE epic_node_links (
          epic_id UUID NOT NULL REFERENCES epics(id),
          node_id UUID NOT NULL REFERENCES code_nodes(id),
          PRIMARY KEY (epic_id, node_id)
        );
    """))

    conn.execute(text("""
        CREATE TABLE task_node_links (
          task_id UUID NOT NULL REFERENCES tasks(id),
          node_id UUID NOT NULL REFERENCES code_nodes(id),
          PRIMARY KEY (task_id, node_id)
        );
    """))

    # ─── PROMPT HISTORY ───────────────────────────────────────────────────────

    conn.execute(text("""
        CREATE TABLE prompt_history (
          id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          project_id   UUID REFERENCES projects(id),
          epic_id      UUID REFERENCES epics(id),
          task_id      UUID REFERENCES tasks(id),
          agent_type   TEXT NOT NULL,
          prompt_type  TEXT NOT NULL,
          prompt_text   TEXT NOT NULL,
          override_text TEXT,
          token_count   INT,
          token_count_minified INT,
          generated_by  UUID REFERENCES users(id),
          created_at    TIMESTAMPTZ DEFAULT now()
        );
    """))

    # ─── AUDIT & MCP ─────────────────────────────────────────────────────────

    conn.execute(text("""
        CREATE TABLE mcp_invocations (
          id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          request_id      UUID NOT NULL,
          idempotency_key UUID UNIQUE,
          actor_id        UUID NOT NULL REFERENCES users(id),
          actor_role      TEXT NOT NULL,
          tool_name       TEXT NOT NULL,
          epic_id         UUID,
          target_id       TEXT,
          input_payload   JSONB,
          output_payload  JSONB,
          status          TEXT NOT NULL,
          created_at      TIMESTAMPTZ DEFAULT now()
        );
    """))

    # ─── IDEMPOTENCY KEYS ────────────────────────────────────────────────────

    conn.execute(text("""
        CREATE TABLE idempotency_keys (
          key             UUID PRIMARY KEY,
          actor_id        UUID NOT NULL REFERENCES users(id),
          tool_name       TEXT NOT NULL,
          status          TEXT NOT NULL DEFAULT 'processing',
          response_status INT,
          response_body   JSONB,
          created_at      TIMESTAMPTZ DEFAULT now(),
          expires_at      TIMESTAMPTZ DEFAULT now() + interval '24 hours'
        );
    """))

    conn.execute(text("""
        CREATE INDEX idx_idempotency_keys_expires
          ON idempotency_keys(expires_at) WHERE status = 'completed';
    """))

    # ─── SYNC: Outbox & DLQ ──────────────────────────────────────────────────

    conn.execute(text("""
        CREATE TABLE sync_outbox (
          id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          dedup_key     TEXT UNIQUE,
          direction     TEXT NOT NULL DEFAULT 'inbound',
          system        TEXT NOT NULL,
          target_node_id UUID REFERENCES nodes(id),
          entity_type   TEXT NOT NULL,
          entity_id     TEXT NOT NULL,
          payload       JSONB NOT NULL,
          attempts      INT NOT NULL DEFAULT 0,
          next_retry_at TIMESTAMPTZ,
          state         TEXT NOT NULL DEFAULT 'pending',
          routing_state TEXT DEFAULT 'unrouted',
          embedding       vector(768),
          embedding_model TEXT,
          created_at      TIMESTAMPTZ DEFAULT now()
        );
    """))

    conn.execute(text("""
        CREATE TABLE sync_dead_letter (
          id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          outbox_id     UUID NOT NULL REFERENCES sync_outbox(id),
          system        TEXT NOT NULL,
          entity_type   TEXT NOT NULL,
          entity_id     TEXT NOT NULL,
          payload       JSONB NOT NULL,
          error         TEXT,
          failed_at     TIMESTAMPTZ DEFAULT now(),
          requeued_by   UUID REFERENCES users(id),
          requeued_at   TIMESTAMPTZ,
          discarded_by  UUID REFERENCES users(id),
          discarded_at  TIMESTAMPTZ
        );
    """))

    # ─── DECISIONS ───────────────────────────────────────────────────────────

    conn.execute(text("""
        CREATE TABLE decision_requests (
          id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          task_id         UUID NOT NULL REFERENCES tasks(id),
          epic_id         UUID NOT NULL REFERENCES epics(id),
          owner_id        UUID NOT NULL REFERENCES users(id),
          backup_owner_id UUID REFERENCES users(id),
          state           TEXT NOT NULL DEFAULT 'open',
          sla_due_at      TIMESTAMPTZ NOT NULL,
          version         INT NOT NULL DEFAULT 0,
          resolved_by     UUID REFERENCES users(id),
          resolved_at     TIMESTAMPTZ,
          payload         JSONB NOT NULL
        );
    """))

    conn.execute(text("""
        CREATE TABLE decision_records (
          id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          epic_id             UUID NOT NULL REFERENCES epics(id),
          decision_request_id UUID REFERENCES decision_requests(id),
          decision            TEXT NOT NULL,
          rationale           TEXT,
          decided_by          UUID NOT NULL REFERENCES users(id),
          created_at          TIMESTAMPTZ DEFAULT now()
        );
    """))

    # ─── EPIC PROPOSALS ──────────────────────────────────────────────────────

    conn.execute(text("""
        CREATE TABLE epic_proposals (
          id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          project_id          UUID NOT NULL REFERENCES projects(id),
          proposed_by         UUID NOT NULL REFERENCES users(id),
          title               TEXT NOT NULL,
          description         TEXT NOT NULL,
          rationale           TEXT NOT NULL,
          suggested_priority  TEXT DEFAULT 'medium',
          suggested_phase     INT,
          depends_on          UUID[] DEFAULT '{}',
          suggested_owner_id  UUID REFERENCES users(id),
          state               TEXT NOT NULL DEFAULT 'proposed',
          resulting_epic_id   UUID REFERENCES epics(id),
          reviewed_by         UUID REFERENCES users(id),
          review_reason       TEXT,
          reviewed_at         TIMESTAMPTZ,
          version             INT NOT NULL DEFAULT 0,
          created_at          TIMESTAMPTZ DEFAULT now()
        );
    """))

    # ─── EPIC RESTRUCTURE PROPOSALS ──────────────────────────────────────────

    conn.execute(text("""
        CREATE TABLE epic_restructure_proposals (
          id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          epic_id     UUID NOT NULL REFERENCES epics(id),
          proposed_by UUID NOT NULL REFERENCES users(id),
          rationale   TEXT NOT NULL,
          proposal    TEXT NOT NULL,
          state       TEXT NOT NULL DEFAULT 'proposed',
          version     INT NOT NULL DEFAULT 0,
          reviewed_by UUID REFERENCES users(id),
          reviewed_at TIMESTAMPTZ,
          applied_at  TIMESTAMPTZ,
          origin_node_id UUID REFERENCES nodes(id),
          created_at  TIMESTAMPTZ DEFAULT now(),
          CONSTRAINT valid_restructure_state CHECK (state IN ('proposed','accepted','applied','rejected'))
        );
    """))

    # ─── GUARDS ──────────────────────────────────────────────────────────────

    conn.execute(text("""
        CREATE TABLE guards (
          id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          project_id  UUID REFERENCES projects(id),
          skill_id    UUID REFERENCES skills(id),
          title       TEXT NOT NULL,
          description TEXT,
          type        TEXT NOT NULL DEFAULT 'executable',
          command     TEXT,
          condition   TEXT,
          scope       TEXT[] DEFAULT '{}',
          lifecycle   TEXT NOT NULL DEFAULT 'draft',
          skippable   BOOLEAN NOT NULL DEFAULT true,
          version     INT NOT NULL DEFAULT 0,
          created_by  UUID NOT NULL REFERENCES users(id),
          created_at  TIMESTAMPTZ DEFAULT now(),
          updated_at  TIMESTAMPTZ DEFAULT now()
        );
    """))

    conn.execute(text("""
        CREATE TABLE task_guards (
          id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          task_id    UUID NOT NULL REFERENCES tasks(id),
          guard_id   UUID NOT NULL REFERENCES guards(id),
          status     TEXT NOT NULL DEFAULT 'pending',
          result     TEXT,
          checked_at TIMESTAMPTZ,
          checked_by UUID REFERENCES users(id),
          UNIQUE(task_id, guard_id)
        );
    """))

    conn.execute(text("""
        CREATE TABLE guard_change_proposals (
          id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          guard_id     UUID NOT NULL REFERENCES guards(id),
          proposed_by  UUID NOT NULL REFERENCES users(id),
          diff         TEXT NOT NULL,
          rationale    TEXT NOT NULL,
          state        TEXT NOT NULL DEFAULT 'open',
          reviewed_by  UUID REFERENCES users(id),
          reviewed_at  TIMESTAMPTZ,
          review_note  TEXT,
          version      INT NOT NULL DEFAULT 0,
          created_at   TIMESTAMPTZ DEFAULT now()
        );
    """))

    # ─── NOTIFICATIONS ────────────────────────────────────────────────────────

    conn.execute(text("""
        CREATE TABLE notifications (
          id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          user_id    UUID NOT NULL REFERENCES users(id),
          type       TEXT NOT NULL,
          priority   TEXT NOT NULL DEFAULT 'fyi',
          title      TEXT NOT NULL,
          body       TEXT,
          link       TEXT,
          read       BOOLEAN DEFAULT false,
          created_at TIMESTAMPTZ DEFAULT now()
        );
    """))

    # ─── MEMORY LEDGER ───────────────────────────────────────────────────────

    conn.execute(text("""
        CREATE TABLE memory_sessions (
          id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          actor_id    UUID NOT NULL REFERENCES users(id),
          agent_role  TEXT NOT NULL,
          scope       TEXT NOT NULL,
          scope_id    UUID,
          started_at  TIMESTAMPTZ DEFAULT now(),
          ended_at    TIMESTAMPTZ,
          entry_count INT NOT NULL DEFAULT 0,
          compacted   BOOLEAN NOT NULL DEFAULT false
        );
    """))

    conn.execute(text("""
        CREATE TABLE memory_summaries (
          id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          actor_id        UUID NOT NULL REFERENCES users(id),
          agent_role      TEXT NOT NULL,
          scope           TEXT NOT NULL,
          scope_id        UUID,
          session_id      UUID REFERENCES memory_sessions(id),
          content         TEXT NOT NULL,
          source_entry_ids UUID[] NOT NULL,
          source_fact_ids  UUID[] NOT NULL DEFAULT '{}',
          source_count    INT NOT NULL,
          open_questions  TEXT[] NOT NULL DEFAULT '{}',
          graduated       BOOLEAN NOT NULL DEFAULT false,
          graduated_to    JSONB,
          embedding       vector(768),
          created_at      TIMESTAMPTZ DEFAULT now()
        );
    """))

    conn.execute(text("""
        CREATE TABLE memory_entries (
          id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          actor_id    UUID NOT NULL REFERENCES users(id),
          agent_role  TEXT NOT NULL,
          scope       TEXT NOT NULL,
          scope_id    UUID,
          session_id  UUID NOT NULL REFERENCES memory_sessions(id),
          content     TEXT NOT NULL,
          tags        TEXT[] NOT NULL DEFAULT '{}',
          embedding   vector(768),
          covered_by  UUID REFERENCES memory_summaries(id),
          created_at  TIMESTAMPTZ DEFAULT now()
        );
    """))

    conn.execute(text("""
        CREATE TABLE memory_facts (
          id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          entry_id    UUID NOT NULL REFERENCES memory_entries(id),
          entity      TEXT NOT NULL,
          key         TEXT NOT NULL,
          value       TEXT NOT NULL,
          confidence  FLOAT DEFAULT 1.0,
          created_at  TIMESTAMPTZ DEFAULT now()
        );
    """))

    # ─── PERFORMANCE INDEXES ─────────────────────────────────────────────────

    conn.execute(text("CREATE INDEX idx_tasks_state       ON tasks(state);"))
    conn.execute(text("CREATE INDEX idx_tasks_epic_id     ON tasks(epic_id);"))
    conn.execute(text("CREATE INDEX idx_tasks_assigned_to ON tasks(assigned_to);"))

    conn.execute(text("CREATE INDEX idx_epics_state      ON epics(state);"))
    conn.execute(text("CREATE INDEX idx_epics_project_id ON epics(project_id);"))
    conn.execute(text("CREATE INDEX idx_epics_owner_id   ON epics(owner_id);"))
    conn.execute(text("CREATE INDEX idx_epics_epic_key   ON epics(epic_key);"))
    conn.execute(text("""
        CREATE INDEX idx_epics_sla_due ON epics(sla_due_at)
          WHERE state NOT IN ('done', 'cancelled') AND sla_due_at IS NOT NULL;
    """))

    conn.execute(text("CREATE INDEX idx_skills_lifecycle   ON skills(lifecycle);"))
    conn.execute(text("CREATE INDEX idx_skills_project_id  ON skills(project_id);"))

    conn.execute(text("CREATE INDEX idx_epics_embedding         ON epics    USING hnsw (embedding vector_cosine_ops);"))
    conn.execute(text("CREATE INDEX idx_skills_embedding        ON skills   USING hnsw (embedding vector_cosine_ops);"))
    conn.execute(text("CREATE INDEX idx_wiki_articles_embedding ON wiki_articles USING hnsw (embedding vector_cosine_ops);"))
    conn.execute(text("CREATE INDEX idx_docs_embedding          ON docs         USING hnsw (embedding vector_cosine_ops);"))
    conn.execute(text("CREATE INDEX idx_code_nodes_embedding    ON code_nodes USING hnsw (embedding vector_cosine_ops);"))
    conn.execute(text("CREATE INDEX idx_sync_outbox_embedding   ON sync_outbox USING hnsw (embedding vector_cosine_ops);"))

    conn.execute(text("CREATE INDEX idx_sync_outbox_state          ON sync_outbox(state);"))
    conn.execute(text("CREATE INDEX idx_sync_outbox_routing_state  ON sync_outbox(routing_state);"))
    conn.execute(text("CREATE INDEX idx_sync_outbox_next_retry     ON sync_outbox(next_retry_at) WHERE state = 'pending';"))
    conn.execute(text("CREATE INDEX idx_sync_outbox_direction_state ON sync_outbox(direction, state);"))

    conn.execute(text("CREATE INDEX idx_notifications_user_unread  ON notifications(user_id) WHERE read = false;"))

    conn.execute(text("CREATE INDEX idx_skill_change_proposals_state    ON skill_change_proposals(state);"))
    conn.execute(text("CREATE INDEX idx_skill_change_proposals_skill_id ON skill_change_proposals(skill_id);"))
    conn.execute(text("CREATE INDEX idx_guard_change_proposals_state    ON guard_change_proposals(state);"))
    conn.execute(text("CREATE INDEX idx_guard_change_proposals_guard_id ON guard_change_proposals(guard_id);"))

    conn.execute(text("CREATE INDEX idx_guards_lifecycle   ON guards(lifecycle);"))
    conn.execute(text("CREATE INDEX idx_guards_project_id  ON guards(project_id);"))

    conn.execute(text("CREATE INDEX idx_mcp_invocations_actor_id  ON mcp_invocations(actor_id);"))
    conn.execute(text("CREATE INDEX idx_mcp_invocations_tool_name ON mcp_invocations(tool_name);"))
    conn.execute(text("CREATE INDEX idx_mcp_invocations_epic_id   ON mcp_invocations(epic_id);"))
    conn.execute(text("CREATE INDEX idx_mcp_invocations_created   ON mcp_invocations(created_at DESC);"))

    conn.execute(text("CREATE INDEX idx_decision_requests_task_id ON decision_requests(task_id);"))
    conn.execute(text("CREATE INDEX idx_decision_requests_state   ON decision_requests(state);"))
    conn.execute(text("CREATE INDEX idx_decision_requests_sla_due ON decision_requests(sla_due_at);"))
    conn.execute(text("""
        CREATE UNIQUE INDEX idx_decision_requests_one_open_per_task
          ON decision_requests(task_id) WHERE state = 'open';
    """))

    conn.execute(text("CREATE INDEX idx_epics_origin_node_id         ON epics(origin_node_id)        WHERE origin_node_id IS NOT NULL;"))
    conn.execute(text("CREATE INDEX idx_tasks_assigned_node_id       ON tasks(assigned_node_id)       WHERE assigned_node_id IS NOT NULL;"))
    conn.execute(text("CREATE INDEX idx_skills_origin_node_id        ON skills(origin_node_id)        WHERE origin_node_id IS NOT NULL;"))
    conn.execute(text("CREATE INDEX idx_skills_federation_scope      ON skills(federation_scope);"))
    conn.execute(text("CREATE INDEX idx_wiki_articles_origin_node_id ON wiki_articles(origin_node_id) WHERE origin_node_id IS NOT NULL;"))
    conn.execute(text("CREATE INDEX idx_sync_outbox_target_node_id   ON sync_outbox(target_node_id)   WHERE target_node_id IS NOT NULL;"))
    conn.execute(text("CREATE INDEX idx_nodes_status                 ON nodes(status);"))
    conn.execute(text("CREATE INDEX idx_code_nodes_origin_node_id    ON code_nodes(origin_node_id)    WHERE origin_node_id IS NOT NULL;"))
    conn.execute(text("CREATE INDEX idx_code_nodes_exploring_node_id ON code_nodes(exploring_node_id) WHERE exploring_node_id IS NOT NULL;"))
    conn.execute(text("CREATE INDEX idx_code_edges_project_id        ON code_edges(project_id);"))
    conn.execute(text("CREATE INDEX idx_code_edges_target_id         ON code_edges(target_id);"))
    conn.execute(text("CREATE INDEX idx_code_edges_origin_node_id    ON code_edges(origin_node_id)    WHERE origin_node_id IS NOT NULL;"))

    conn.execute(text("CREATE INDEX idx_wiki_categories_parent_id    ON wiki_categories(parent_id);"))
    conn.execute(text("CREATE INDEX idx_wiki_articles_category_id    ON wiki_articles(category_id)   WHERE category_id IS NOT NULL;"))

    conn.execute(text("CREATE INDEX idx_prompt_history_project_id    ON prompt_history(project_id);"))
    conn.execute(text("CREATE INDEX idx_prompt_history_task_id       ON prompt_history(task_id);"))
    conn.execute(text("CREATE INDEX idx_prompt_history_created       ON prompt_history(created_at DESC);"))

    conn.execute(text("CREATE INDEX idx_memory_entries_scope    ON memory_entries(scope, scope_id, created_at DESC);"))
    conn.execute(text("CREATE INDEX idx_memory_summaries_scope  ON memory_summaries(scope, scope_id, graduated, created_at DESC);"))
    conn.execute(text("CREATE INDEX idx_memory_sessions_scope   ON memory_sessions(scope, scope_id, ended_at DESC);"))
    conn.execute(text("CREATE INDEX idx_memory_entries_uncovered ON memory_entries(scope, scope_id) WHERE covered_by IS NULL;"))
    conn.execute(text("CREATE INDEX idx_memory_facts_entity      ON memory_facts(entity);"))
    conn.execute(text("CREATE INDEX idx_memory_facts_entry       ON memory_facts(entry_id);"))
    conn.execute(text("CREATE INDEX idx_memory_entries_embedding  ON memory_entries    USING hnsw (embedding vector_cosine_ops);"))
    conn.execute(text("CREATE INDEX idx_memory_summaries_embedding ON memory_summaries USING hnsw (embedding vector_cosine_ops);"))

    conn.execute(text("CREATE INDEX idx_conductor_dispatches_status  ON conductor_dispatches(status) WHERE status = 'dispatched';"))
    conn.execute(text("CREATE INDEX idx_conductor_dispatches_entity  ON conductor_dispatches(trigger_entity_id);"))
    conn.execute(text("CREATE INDEX idx_conductor_dispatches_created ON conductor_dispatches(created_at DESC);"))


def downgrade() -> None:
    conn = op.get_bind()

    # Drop in reverse order of creation (FK dependencies)
    tables = [
        "memory_facts", "memory_entries", "memory_summaries", "memory_sessions",
        "notifications",
        "guard_change_proposals", "task_guards", "guards",
        "epic_restructure_proposals", "epic_proposals",
        "decision_records", "decision_requests",
        "sync_dead_letter", "sync_outbox",
        "idempotency_keys",
        "mcp_invocations",
        "prompt_history",
        "task_node_links", "epic_node_links", "node_bug_reports",
        "discovery_sessions", "code_edges", "code_nodes",
        "wiki_versions", "wiki_articles", "wiki_categories",
        "context_boundaries", "docs",
        "skill_change_proposals", "skill_parents", "skill_versions", "skills",
        "review_recommendations",
        "tasks",
        "epics",
        "exp_events", "user_achievements", "badge_definitions", "level_thresholds",
        "project_members", "projects",
        "conductor_dispatches",
        "ai_provider_configs",
        "app_settings",
        "users",
        "node_identity", "nodes",
    ]
    for table in tables:
        conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE;"))

    conn.execute(text("DROP SEQUENCE IF EXISTS epic_key_seq;"))
    conn.execute(text("DROP SEQUENCE IF EXISTS task_key_seq;"))
    conn.execute(text("DROP FUNCTION IF EXISTS prevent_epic_key_update() CASCADE;"))
    conn.execute(text("DROP FUNCTION IF EXISTS prevent_task_key_update() CASCADE;"))
    conn.execute(text("DROP EXTENSION IF EXISTS vector;"))
