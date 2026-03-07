"""017 - Drop orphaned tables

Remove 11 truly orphaned tables — no active code references confirmed.
Based on inventory from TASK-3-020 (corrected after QA review):

  DROPPED (verified no app-code references):
    badge_definitions, user_achievements, exp_events, level_thresholds,
    task_node_links, epic_node_links, memory_facts, memory_entries,
    memory_summaries, epic_restructure_proposals, memory_sessions

  KEPT (actively used tables — excluded after QA failure):
    decision_requests    → escalation_tools.py, kpi_service.py, epic_service.py
    decision_records     → models/decision.py
    review_recommendations → reviewer_tools.py, models/review.py
    conductor_dispatches → conductor service/router, FK in review_recommendations
    mcp_bridge_configs   → mcp_bridge.py, routers/mcp_bridges.py
    project_integrations → github_projects.py

Drop order respects FK dependencies (leaf tables first).
Downgrade recreates all dropped tables with original schema.

Revision: 017
Revises: 016
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── Layer 0: Leaf tables with FK on other orphaned tables ─────────────────
    # user_achievements → badge_definitions
    conn.execute(text("DROP TABLE IF EXISTS user_achievements CASCADE;"))
    # memory_facts → memory_entries
    conn.execute(text("DROP TABLE IF EXISTS memory_facts CASCADE;"))

    # ── Layer 1: Leaf tables (no incoming FKs from other orphaned tables) ─────
    conn.execute(text("DROP TABLE IF EXISTS task_node_links CASCADE;"))
    conn.execute(text("DROP TABLE IF EXISTS epic_node_links CASCADE;"))
    conn.execute(text("DROP TABLE IF EXISTS exp_events CASCADE;"))
    conn.execute(text("DROP TABLE IF EXISTS level_thresholds CASCADE;"))

    # ── Layer 2: Tables with FKs to root orphaned tables ──────────────────────
    # memory_entries → memory_sessions, memory_summaries
    conn.execute(text("DROP TABLE IF EXISTS memory_entries CASCADE;"))
    # memory_summaries → memory_sessions
    conn.execute(text("DROP TABLE IF EXISTS memory_summaries CASCADE;"))
    # epic_restructure_proposals → epics, users, nodes (non-orphaned, no active code)
    conn.execute(text("DROP TABLE IF EXISTS epic_restructure_proposals CASCADE;"))

    # ── Layer 3: Root orphaned tables ─────────────────────────────────────────
    conn.execute(text("DROP TABLE IF EXISTS memory_sessions CASCADE;"))
    conn.execute(text("DROP TABLE IF EXISTS badge_definitions CASCADE;"))


def downgrade() -> None:
    """Recreate the 11 orphaned tables that were dropped in upgrade()."""
    conn = op.get_bind()

    # ── Root tables first ─────────────────────────────────────────────────────

    conn.execute(text("""
        CREATE TABLE badge_definitions (
            badge_id         TEXT PRIMARY KEY,
            title            TEXT NOT NULL,
            description      TEXT NOT NULL,
            icon             TEXT,
            category         TEXT NOT NULL DEFAULT 'general',
            unlock_condition TEXT NOT NULL,
            exp_reward       INTEGER NOT NULL DEFAULT 0,
            created_at       TIMESTAMPTZ DEFAULT now()
        );
    """))

    conn.execute(text("""
        CREATE TABLE memory_sessions (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            actor_id    UUID NOT NULL REFERENCES users(id),
            agent_role  TEXT NOT NULL,
            scope       TEXT NOT NULL,
            scope_id    UUID,
            started_at  TIMESTAMPTZ DEFAULT now(),
            ended_at    TIMESTAMPTZ,
            entry_count INTEGER NOT NULL DEFAULT 0,
            compacted   BOOLEAN NOT NULL DEFAULT false
        );
        CREATE INDEX idx_memory_sessions_scope
            ON memory_sessions (scope, scope_id, ended_at DESC);
    """))

    conn.execute(text("""
        CREATE TABLE level_thresholds (
            level     INTEGER PRIMARY KEY,
            min_exp   INTEGER NOT NULL,
            title     TEXT NOT NULL
        );
    """))

    # ── Layer 2: Tables with FKs to root orphaned tables ──────────────────────

    conn.execute(text("""
        CREATE TABLE memory_summaries (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            actor_id         UUID NOT NULL REFERENCES users(id),
            agent_role       TEXT NOT NULL,
            scope            TEXT NOT NULL,
            scope_id         UUID,
            session_id       UUID REFERENCES memory_sessions(id),
            content          TEXT NOT NULL,
            source_entry_ids UUID[] NOT NULL,
            source_fact_ids  UUID[] NOT NULL DEFAULT '{}',
            source_count     INTEGER NOT NULL,
            open_questions   TEXT[] NOT NULL DEFAULT '{}',
            graduated        BOOLEAN NOT NULL DEFAULT false,
            graduated_to     JSONB,
            embedding        vector(768),
            created_at       TIMESTAMPTZ DEFAULT now()
        );
        CREATE INDEX idx_memory_summaries_embedding
            ON memory_summaries USING hnsw (embedding vector_cosine_ops);
        CREATE INDEX idx_memory_summaries_scope
            ON memory_summaries (scope, scope_id, graduated, created_at DESC);
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
        CREATE INDEX idx_memory_entries_embedding
            ON memory_entries USING hnsw (embedding vector_cosine_ops);
        CREATE INDEX idx_memory_entries_scope
            ON memory_entries (scope, scope_id, created_at DESC);
        CREATE INDEX idx_memory_entries_uncovered
            ON memory_entries (scope, scope_id) WHERE (covered_by IS NULL);
    """))

    conn.execute(text("""
        CREATE TABLE epic_restructure_proposals (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            epic_id        UUID NOT NULL REFERENCES epics(id),
            proposed_by    UUID NOT NULL REFERENCES users(id),
            rationale      TEXT NOT NULL,
            proposal       TEXT NOT NULL,
            state          TEXT NOT NULL DEFAULT 'proposed',
            version        INTEGER NOT NULL DEFAULT 0,
            reviewed_by    UUID REFERENCES users(id),
            reviewed_at    TIMESTAMPTZ,
            applied_at     TIMESTAMPTZ,
            origin_node_id UUID REFERENCES nodes(id),
            created_at     TIMESTAMPTZ DEFAULT now(),
            CONSTRAINT valid_restructure_state CHECK (
                state IN ('proposed', 'accepted', 'applied', 'rejected')
            )
        );
    """))

    # ── Layer 1: Leaf tables ──────────────────────────────────────────────────

    conn.execute(text("""
        CREATE TABLE memory_facts (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            entry_id    UUID NOT NULL REFERENCES memory_entries(id),
            entity      TEXT NOT NULL,
            key         TEXT NOT NULL,
            value       TEXT NOT NULL,
            confidence  DOUBLE PRECISION DEFAULT 1.0,
            created_at  TIMESTAMPTZ DEFAULT now()
        );
        CREATE INDEX idx_memory_facts_entity ON memory_facts (entity);
        CREATE INDEX idx_memory_facts_entry  ON memory_facts (entry_id);
    """))

    conn.execute(text("""
        CREATE TABLE task_node_links (
            task_id UUID NOT NULL REFERENCES tasks(id),
            node_id UUID NOT NULL REFERENCES code_nodes(id),
            PRIMARY KEY (task_id, node_id)
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
        CREATE TABLE exp_events (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     UUID NOT NULL REFERENCES users(id),
            event_type  TEXT NOT NULL,
            entity_id   UUID,
            exp_awarded INTEGER NOT NULL,
            reason      TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_exp_events_user ON exp_events (user_id, created_at DESC);
    """))

    # ── Layer 0: FK-dependent on orphaned root tables ─────────────────────────

    conn.execute(text("""
        CREATE TABLE user_achievements (
            id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id   UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            badge_id  TEXT NOT NULL REFERENCES badge_definitions(badge_id),
            earned_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE (user_id, badge_id)
        );
    """))
