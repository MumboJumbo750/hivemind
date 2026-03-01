---
title: "Wiki-Volltextsuche mit PostgreSQL"
service_scope: ["backend"]
stack: ["python", "fastapi", "sqlalchemy", "postgresql"]
version_range: { "python": ">=3.11", "fastapi": ">=0.100", "postgresql": ">=16" }
confidence: 0.8
source_epics: ["EPIC-PHASE-5"]
guards:
  - title: "Python Linting"
    command: "ruff check ."
  - title: "Type Check"
    command: "mypy app/"
  - title: "Tests"
    command: "pytest tests/ -v"
---

## Skill: Wiki-Volltextsuche mit PostgreSQL

### Rolle
Du implementierst die Volltextsuche für Wiki-Artikel mit PostgreSQL tsvector/tsquery,
optional hybrid mit pgvector-Embeddings für semantische Relevanz.

### Kontext

Wiki-Artikel in Hivemind brauchen eine performante Suche über `title` + `content`.
Ab Phase 3 stehen pgvector-Embeddings zur Verfügung — die Suche kombiniert dann
lexikalische Treffer (tsvector) mit semantischer Ähnlichkeit (pgvector).

### Konventionen

- **tsvector** über `title` (Gewicht A) + `content` (Gewicht B) — `'german'` Konfiguration
- **GIN-Index** auf die generierte tsvector-Spalte (Alembic-Migration)
- **Tag-Filterung** als Pre-Filter vor der Textsuche (Array-Overlap `&&`)
- **Hybrid-Ranking:** `0.6 * ts_rank + 0.4 * (1 - cosine_distance)` wenn Embedding vorhanden
- Suche über REST: `GET /api/wiki/search?q=...&tags=...`
- Suche über MCP: `hivemind/search_wiki { "query": "...", "tags": [...] }`
- Beide Endpoints nutzen denselben `WikiSearchService`

### Alembic-Migration

```python
"""add wiki fulltext search"""

def upgrade() -> None:
    # 1. tsvector-Spalte als Generated Column
    op.execute("""
        ALTER TABLE wiki_articles
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('german', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('german', coalesce(content, '')), 'B')
        ) STORED;
    """)

    # 2. GIN-Index
    op.execute("""
        CREATE INDEX idx_wiki_search_vector
        ON wiki_articles USING GIN (search_vector);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_wiki_search_vector;")
    op.execute("ALTER TABLE wiki_articles DROP COLUMN IF EXISTS search_vector;")
```

### Service-Implementierung

```python
class WikiSearchService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def search(
        self,
        query: str,
        tags: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[WikiSearchResult]:
        # 1. Basis-Query mit tsvector
        ts_query = func.plainto_tsquery("german", query)
        ts_rank = func.ts_rank(WikiArticle.search_vector, ts_query)

        stmt = (
            select(WikiArticle, ts_rank.label("rank"))
            .where(WikiArticle.search_vector.op("@@")(ts_query))
        )

        # 2. Tag-Filter (Pre-Filter)
        if tags:
            stmt = stmt.where(WikiArticle.tags.overlap(tags))

        # 3. Hybrid-Ranking (wenn pgvector verfügbar)
        if self._has_embeddings():
            query_embedding = await self._get_embedding(query)
            cosine_sim = 1 - WikiArticle.embedding.cosine_distance(query_embedding)

            stmt = select(
                WikiArticle,
                (0.6 * ts_rank + 0.4 * cosine_sim).label("rank")
            ).where(
                or_(
                    WikiArticle.search_vector.op("@@")(ts_query),
                    WikiArticle.embedding.cosine_distance(query_embedding) < 0.5,
                )
            )
            if tags:
                stmt = stmt.where(WikiArticle.tags.overlap(tags))

        # 4. Sortierung + Paginierung
        stmt = stmt.order_by(desc("rank")).limit(limit).offset(offset)

        result = await self.db.execute(stmt)
        return [WikiSearchResult(article=row[0], rank=row[1]) for row in result]
```

### REST-Endpoint

```python
@router.get("/wiki/search", response_model=WikiSearchResponse)
async def search_wiki(
    q: str = Query(..., min_length=1, max_length=200),
    tags: list[str] | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    service = WikiSearchService(db)
    results = await service.search(q, tags=tags, limit=limit, offset=offset)
    return WikiSearchResponse(
        results=[r.to_dict() for r in results],
        total=len(results),
        query=q,
    )
```

### Performance-Hinweise

- GIN-Index macht Volltextsuche performant auch bei >10k Artikeln
- Tag-Overlap-Filter reduziert die Ergebnismenge **vor** dem Ranking
- `plainto_tsquery` für User-Input (sicherer als `to_tsquery`, kein SQL-Injection-Risiko)
- Bei Hybrid: `LIMIT` auf DB-Ebene, nicht in Python

### Fehler-Typen

| Code | HTTP | Wann |
| --- | --- | --- |
| `INVALID_QUERY` | 400 | Leerer Suchbegriff |
| `SEARCH_ERROR` | 500 | DB-Fehler bei Suche |

### Verfügbare Tools
- `hivemind/search_wiki` — Wiki-Suche (Volltextsuche + Tags)
- `hivemind/get_wiki_article` — Einzelnen Artikel laden (per ID oder Slug)
