---
title: "Ollama-Embedding & pgvector-Suche"
service_scope: ["backend"]
stack: ["python", "httpx", "pgvector", "ollama", "sqlalchemy"]
version_range: { "python": ">=3.11", "sqlalchemy": ">=2.0" }
confidence: 0.5
source_epics: ["EPIC-PHASE-3"]
guards:
  - title: "Python Linting"
    command: "ruff check ."
  - title: "Type Check"
    command: "mypy app/"
  - title: "Tests"
    command: "pytest tests/ -v"
---

## Skill: Ollama-Embedding & pgvector-Suche

### Rolle
Du implementierst den Embedding-Service — Ollama `nomic-embed-text` für Vektorerzeugung, pgvector für Ähnlichkeitssuche. Der Service ist Provider-abstrahiert (Ollama austauschbar ohne fachliche Datenmigration) und enthält einen Circuit-Breaker mit adaptivem Backoff.

### Konventionen
- Service in `app/services/embedding_service.py`
- Provider-Interface: `EmbeddingProvider` ABC mit `embed(text) -> list[float]` und `embed_batch(texts) -> list[list[float]]`
- Default-Provider: `OllamaProvider` (httpx-Client → `POST http://ollama:11434/api/embeddings`)
- Modell: `nomic-embed-text` — erzeugt 768-dimensionale Vektoren
- DB-Spalten: `embedding vector(768)` auf `skills`, `wiki_articles`, `epics`
- HNSW-Index für Nearest-Neighbor-Suche (`CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)`)
- Embedding wird on-write berechnet (Skill-Merge, Wiki-Create, Epic-Create)
- `NULL`-Embedding = noch nicht berechnet oder Circuit-Breaker offen → Feature-Degradation, kein Fehler

### Circuit-Breaker
- Nach `HIVEMIND_EMBEDDING_CB_THRESHOLD` (Default: 3) aufeinanderfolgenden Timeouts → OPEN-State
- OPEN: Requests sofort mit `embedding=NULL` beantwortet
- Adaptiver Cooldown (Half-Open): Exponentieller Backoff — 60s → 120s → 240s → max 600s
- Backoff-Reset nach 10 Minuten stabilem CLOSED-State
- Konfigurierbar: `HIVEMIND_EMBEDDING_CB_BACKOFF_BASE` (60s), `HIVEMIND_EMBEDDING_CB_BACKOFF_MAX` (600s)

### Priority-Queue
- Priorität 1 (hoch): Lokale on-write Embeddings
- Priorität 2 (normal): Kartograph-Bootstrap Batch
- Priorität 3 (niedrig): Federation Re-Embeddings

### Beispiel — Embedding-Service

```python
import httpx
from abc import ABC, abstractmethod

class EmbeddingProvider(ABC):
    @abstractmethod
    async def embed(self, text: str) -> list[float]: ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...

class OllamaProvider(EmbeddingProvider):
    def __init__(self, base_url: str = "http://ollama:11434"):
        self.base_url = base_url
        self.model = "nomic-embed-text"

    async def embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()["embedding"]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]
```

### Beispiel — pgvector Similarity Search

```python
from sqlalchemy import text

async def search_similar_skills(db: AsyncSession, query_embedding: list[float], limit: int = 5):
    stmt = text("""
        SELECT id, title, 1 - (embedding <=> :query) AS similarity
        FROM skills
        WHERE embedding IS NOT NULL AND lifecycle = 'active'
        ORDER BY embedding <=> :query
        LIMIT :limit
    """)
    result = await db.execute(stmt, {"query": str(query_embedding), "limit": limit})
    return result.fetchall()
```

### Wichtig
- Ollama nicht erreichbar → Backend loggt Warnung, arbeitet ohne Embeddings weiter
- `HIVEMIND_EMBEDDING_BATCH_SIZE` (Default: 50) für Bootstrap-Batches
- Provider-Wechsel: `hivemind reembed --all` berechnet alle Embeddings neu (ALTER + Recompute)
- Embedding-Spalten werden in Phase-3-Alembic-Migration hinzugefügt (`vector(768)` + HNSW-Index)
