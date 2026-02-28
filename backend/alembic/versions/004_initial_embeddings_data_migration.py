"""Phase-3 data migration — compute initial embeddings for existing entities.

Re-runnable: only processes records where embedding IS NULL.
Requires Ollama to be running (--profile ai). If unavailable, logs warning
and skips — embeddings will be computed on next write or manual reembed.

Phase-gate: only runs when app_settings.current_phase >= 3.

Revision ID: 004
Revises: 003
Create Date: 2026-02-27
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tables that have embedding vector(768) columns
EMBEDDING_TABLES = {
    "skills": "title || ' ' || content",
    "wiki_articles": "title || ' ' || content",
    "epics": "title || ' ' || COALESCE(description, '')",
}

BATCH_SIZE = 50


def upgrade() -> None:
    conn = op.get_bind()

    # ── Phase-gate check ─────────────────────────────────────────────────
    result = conn.execute(
        text("SELECT value FROM app_settings WHERE key = 'current_phase'")
    )
    row = result.fetchone()
    current_phase = int(row[0]) if row else 1

    if current_phase < 3:
        print("[004] Phase-gate: current_phase=%d < 3 — updating to 3" % current_phase)
        conn.execute(
            text("UPDATE app_settings SET value = '3' WHERE key = 'current_phase'")
        )

    # ── Verify schema prerequisites ──────────────────────────────────────
    # embedding columns + HNSW indexes were created in 001_initial_schema
    # Just verify pgvector extension is active
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    # ── Data migration: compute initial embeddings ───────────────────────
    # This requires Ollama to be running. If not, we skip gracefully.
    import httpx

    ollama_url = "http://ollama:11434"
    model = "nomic-embed-text"

    # Test Ollama connectivity
    try:
        resp = httpx.get(f"{ollama_url}/api/tags", timeout=5.0)
        resp.raise_for_status()
        print("[004] Ollama reachable — computing initial embeddings")
    except Exception as exc:
        print(
            f"[004] WARNING: Ollama not reachable ({exc}). "
            "Skipping initial embedding computation. "
            "Embeddings will be computed on next write or via 'hivemind reembed --all'."
        )
        return

    total_embedded = 0

    for table_name, text_expr in EMBEDDING_TABLES.items():
        # Count NULL-embedding records
        count_result = conn.execute(
            text(f"SELECT COUNT(*) FROM {table_name} WHERE embedding IS NULL")
        )
        null_count = count_result.scalar()

        if null_count == 0:
            print(f"[004] {table_name}: no records with NULL embedding — skipping")
            continue

        print(f"[004] {table_name}: computing embeddings for {null_count} records...")

        # Process in batches
        offset = 0
        while True:
            rows = conn.execute(
                text(
                    f"SELECT id, {text_expr} AS embed_text "
                    f"FROM {table_name} "
                    f"WHERE embedding IS NULL "
                    f"ORDER BY created_at "
                    f"LIMIT :batch OFFSET :offset"
                ),
                {"batch": BATCH_SIZE, "offset": offset},
            ).fetchall()

            if not rows:
                break

            for row in rows:
                record_id, embed_text = row
                try:
                    resp = httpx.post(
                        f"{ollama_url}/api/embeddings",
                        json={"model": model, "prompt": embed_text[:8000]},
                        timeout=30.0,
                    )
                    resp.raise_for_status()
                    embedding = resp.json()["embedding"]

                    conn.execute(
                        text(
                            f"UPDATE {table_name} "
                            f"SET embedding = :embedding::vector, "
                            f"    embedding_model = :model "
                            f"WHERE id = :id"
                        ),
                        {
                            "embedding": str(embedding),
                            "model": model,
                            "id": str(record_id),
                        },
                    )
                    total_embedded += 1
                except Exception as exc:
                    print(
                        f"[004] WARNING: Failed to embed {table_name}/{record_id}: {exc}"
                    )
                    # Continue with next record — don't fail the migration
                    continue

            offset += BATCH_SIZE

        print(f"[004] {table_name}: done")

    print(f"[004] Initial embedding computation complete: {total_embedded} records embedded")


def downgrade() -> None:
    # Data migration — downgrade clears computed embeddings
    conn = op.get_bind()
    for table_name in EMBEDDING_TABLES:
        conn.execute(
            text(
                f"UPDATE {table_name} SET embedding = NULL, embedding_model = NULL"
            )
        )
