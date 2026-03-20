"""029 - Reintroduce memory ledger tables for MCP memory tools.

Revision: 029
Revises: 028
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS memory_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            actor_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            agent_role TEXT NOT NULL,
            scope TEXT NOT NULL,
            scope_id UUID,
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            ended_at TIMESTAMPTZ,
            entry_count INTEGER NOT NULL DEFAULT 0,
            compacted BOOLEAN NOT NULL DEFAULT false
        );
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_memory_sessions_scope ON memory_sessions(scope, scope_id, ended_at DESC);"))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS memory_summaries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            actor_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            agent_role TEXT NOT NULL,
            scope TEXT NOT NULL,
            scope_id UUID,
            session_id UUID REFERENCES memory_sessions(id) ON DELETE SET NULL,
            content TEXT NOT NULL,
            source_entry_ids UUID[] NOT NULL,
            source_fact_ids UUID[] NOT NULL DEFAULT '{}',
            source_count INTEGER NOT NULL DEFAULT 0,
            open_questions TEXT[] NOT NULL DEFAULT '{}',
            graduated BOOLEAN NOT NULL DEFAULT false,
            graduated_to JSONB,
            embedding vector(768),
            embedding_model TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_memory_summaries_scope ON memory_summaries(scope, scope_id, graduated, created_at DESC);"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_memory_summaries_embedding ON memory_summaries USING hnsw (embedding vector_cosine_ops);"))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS memory_entries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            actor_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            agent_role TEXT NOT NULL,
            scope TEXT NOT NULL,
            scope_id UUID,
            session_id UUID NOT NULL REFERENCES memory_sessions(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            tags TEXT[] NOT NULL DEFAULT '{}',
            embedding vector(768),
            embedding_model TEXT,
            covered_by UUID REFERENCES memory_summaries(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_memory_entries_scope ON memory_entries(scope, scope_id, created_at DESC);"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_memory_entries_uncovered ON memory_entries(scope, scope_id) WHERE covered_by IS NULL;"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_memory_entries_embedding ON memory_entries USING hnsw (embedding vector_cosine_ops);"))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS memory_facts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            entry_id UUID NOT NULL REFERENCES memory_entries(id) ON DELETE CASCADE,
            entity TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_memory_facts_entity ON memory_facts(entity);"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_memory_facts_entry ON memory_facts(entry_id);"))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DROP TABLE IF EXISTS memory_facts CASCADE;"))
    conn.execute(text("DROP TABLE IF EXISTS memory_entries CASCADE;"))
    conn.execute(text("DROP TABLE IF EXISTS memory_summaries CASCADE;"))
    conn.execute(text("DROP TABLE IF EXISTS memory_sessions CASCADE;"))