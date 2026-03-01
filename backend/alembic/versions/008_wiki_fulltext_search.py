"""008 — add tsvector column + GIN index to wiki_articles (TASK-5-015)

Adds `search_vector` tsvector column and GIN index for full-text
search on wiki_articles. Also creates trigger to auto-update
the tsvector on INSERT/UPDATE.

Revision: 008
Revises: 007
"""
from alembic import op
from sqlalchemy import text

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        ALTER TABLE wiki_articles
        ADD COLUMN IF NOT EXISTS search_vector tsvector;
    """))

    # Populate search_vector for existing rows
    conn.execute(text("""
        UPDATE wiki_articles
        SET search_vector = to_tsvector('german', coalesce(title, '') || ' ' || coalesce(content, ''))
        WHERE search_vector IS NULL;
    """))

    # Create GIN index
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_wiki_articles_search_vector
        ON wiki_articles USING GIN (search_vector);
    """))

    # Create trigger to auto-update search_vector
    conn.execute(text("""
        CREATE OR REPLACE FUNCTION wiki_articles_search_update()
        RETURNS trigger AS $$
        BEGIN
            NEW.search_vector := to_tsvector('german', coalesce(NEW.title, '') || ' ' || coalesce(NEW.content, ''));
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql;
    """))

    conn.execute(text("""
        DROP TRIGGER IF EXISTS trg_wiki_articles_search ON wiki_articles;
        CREATE TRIGGER trg_wiki_articles_search
        BEFORE INSERT OR UPDATE OF title, content ON wiki_articles
        FOR EACH ROW
        EXECUTE FUNCTION wiki_articles_search_update();
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DROP TRIGGER IF EXISTS trg_wiki_articles_search ON wiki_articles;"))
    conn.execute(text("DROP FUNCTION IF EXISTS wiki_articles_search_update();"))
    conn.execute(text("DROP INDEX IF EXISTS idx_wiki_articles_search_vector;"))
    conn.execute(text("ALTER TABLE wiki_articles DROP COLUMN IF EXISTS search_vector;"))
