"""016 - Unified Key System

Add sequence-based human-readable keys for all entity types:
- skill_key (SKILL-{n}) on skills
- wiki_key (WIKI-{n}) on wiki_articles
- guard_key (GUARD-{n}) on guards
- doc_key (DOC-{n}) on docs

Creates new sequences and backfills existing rows.
Advances epic_key_seq and task_key_seq past existing seed data.

Revision: 016
Revises: 015
"""

import sqlalchemy as sa
from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Create new sequences ───────────────────────────────────────────────
    conn.execute(sa.text("CREATE SEQUENCE IF NOT EXISTS skill_key_seq;"))
    conn.execute(sa.text("CREATE SEQUENCE IF NOT EXISTS wiki_key_seq;"))
    conn.execute(sa.text("CREATE SEQUENCE IF NOT EXISTS guard_key_seq;"))
    conn.execute(sa.text("CREATE SEQUENCE IF NOT EXISTS doc_key_seq;"))

    # ── 2. Add key columns (nullable initially for backfill) ──────────────────
    op.add_column("skills", sa.Column("skill_key", sa.Text(), nullable=True))
    op.add_column("wiki_articles", sa.Column("wiki_key", sa.Text(), nullable=True))
    op.add_column("guards", sa.Column("guard_key", sa.Text(), nullable=True))
    op.add_column("docs", sa.Column("doc_key", sa.Text(), nullable=True))

    # ── 3. Backfill existing rows with sequence-generated keys ────────────────
    conn.execute(sa.text("""
        UPDATE skills SET skill_key = 'SKILL-' || nextval('skill_key_seq')
        WHERE skill_key IS NULL;
    """))
    conn.execute(sa.text("""
        UPDATE wiki_articles SET wiki_key = 'WIKI-' || nextval('wiki_key_seq')
        WHERE wiki_key IS NULL;
    """))
    conn.execute(sa.text("""
        UPDATE guards SET guard_key = 'GUARD-' || nextval('guard_key_seq')
        WHERE guard_key IS NULL;
    """))
    conn.execute(sa.text("""
        UPDATE docs SET doc_key = 'DOC-' || nextval('doc_key_seq')
        WHERE doc_key IS NULL;
    """))

    # ── 4. Add UNIQUE constraints ─────────────────────────────────────────────
    op.create_unique_constraint("uq_skills_skill_key", "skills", ["skill_key"])
    op.create_unique_constraint("uq_wiki_articles_wiki_key", "wiki_articles", ["wiki_key"])
    op.create_unique_constraint("uq_guards_guard_key", "guards", ["guard_key"])
    op.create_unique_constraint("uq_docs_doc_key", "docs", ["doc_key"])

    # ── 5. Advance epic_key_seq and task_key_seq past existing data ───────────
    # This ensures sequences don't generate keys that collide with seed data.
    conn.execute(sa.text("""
        SELECT setval('epic_key_seq',
            GREATEST(
                (SELECT COALESCE(MAX(
                    CASE WHEN epic_key ~ '^EPIC-[0-9]+$'
                         THEN CAST(SUBSTRING(epic_key FROM 'EPIC-([0-9]+)') AS INTEGER)
                         ELSE 0
                    END
                ), 0) FROM epics),
                (SELECT last_value FROM epic_key_seq)
            )
        );
    """))
    conn.execute(sa.text("""
        SELECT setval('task_key_seq',
            GREATEST(
                (SELECT COALESCE(MAX(
                    CASE WHEN task_key ~ '^TASK-[0-9]+$'
                         THEN CAST(SUBSTRING(task_key FROM 'TASK-([0-9]+)') AS INTEGER)
                         ELSE 0
                    END
                ), 0) FROM tasks),
                (SELECT last_value FROM task_key_seq)
            )
        );
    """))

    # ── 6. Immutability triggers ──────────────────────────────────────────────
    for table, col in [
        ("skills", "skill_key"),
        ("wiki_articles", "wiki_key"),
        ("guards", "guard_key"),
        ("docs", "doc_key"),
    ]:
        conn.execute(sa.text(f"""
            CREATE OR REPLACE FUNCTION prevent_{col}_update()
            RETURNS trigger AS $$
            BEGIN
              IF NEW.{col} IS DISTINCT FROM OLD.{col} AND OLD.{col} IS NOT NULL THEN
                RAISE EXCEPTION '{col} is immutable';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """))
        conn.execute(sa.text(f"""
            CREATE TRIGGER trg_{table}_{col}_immutable
            BEFORE UPDATE ON {table}
            FOR EACH ROW
            WHEN (OLD.{col} IS NOT NULL AND OLD.{col} IS DISTINCT FROM NEW.{col})
            EXECUTE FUNCTION prevent_{col}_update();
        """))


def downgrade() -> None:
    conn = op.get_bind()

    # Drop triggers
    for table, col in [
        ("skills", "skill_key"),
        ("wiki_articles", "wiki_key"),
        ("guards", "guard_key"),
        ("docs", "doc_key"),
    ]:
        conn.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{table}_{col}_immutable ON {table};"))
        conn.execute(sa.text(f"DROP FUNCTION IF EXISTS prevent_{col}_update();"))

    # Drop constraints and columns
    op.drop_constraint("uq_docs_doc_key", "docs", type_="unique")
    op.drop_constraint("uq_guards_guard_key", "guards", type_="unique")
    op.drop_constraint("uq_wiki_articles_wiki_key", "wiki_articles", type_="unique")
    op.drop_constraint("uq_skills_skill_key", "skills", type_="unique")

    op.drop_column("docs", "doc_key")
    op.drop_column("guards", "guard_key")
    op.drop_column("wiki_articles", "wiki_key")
    op.drop_column("skills", "skill_key")

    # Drop sequences
    conn.execute(sa.text("DROP SEQUENCE IF EXISTS doc_key_seq;"))
    conn.execute(sa.text("DROP SEQUENCE IF EXISTS guard_key_seq;"))
    conn.execute(sa.text("DROP SEQUENCE IF EXISTS wiki_key_seq;"))
    conn.execute(sa.text("DROP SEQUENCE IF EXISTS skill_key_seq;"))
