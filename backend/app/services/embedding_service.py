"""Embedding-Service with provider abstraction and circuit-breaker.

Supports pluggable providers (default: Ollama nomic-embed-text 768d).
Circuit-breaker with adaptive exponential backoff prevents cascade failures.
Priority queue: on-write > batch > federation.
NULL-embedding = feature-degradation (semantic search disabled), not an error.
"""
from __future__ import annotations

import asyncio
import enum
import hashlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import httpx
from sqlalchemy import bindparam
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)

EMBEDDABLE_TABLES = {"skills", "wiki_articles", "epics", "docs", "code_nodes", "sync_outbox", "memory_entries", "memory_summaries"}
EMBEDDING_TEXT_COLS: dict[str, str] = {
    "epics": "COALESCE(title, '') || ' ' || COALESCE(description, '')",
    "skills": "COALESCE(title, '') || ' ' || COALESCE(content, '')",
    "wiki_articles": "COALESCE(title, '') || ' ' || COALESCE(content, '')",
    "docs": "COALESCE(title, '') || ' ' || COALESCE(content, '')",
    "memory_entries": "COALESCE(content, '') || ' ' || COALESCE(array_to_string(tags, ' '), '')",
    "memory_summaries": "COALESCE(content, '') || ' ' || COALESCE(array_to_string(open_questions, ' '), '')",
}


# ── Provider abstraction ─────────────────────────────────────────────────────


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    @abstractmethod
    async def embed(self, text_input: str) -> list[float]:
        """Generate embedding for a single text."""
        ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts."""
        ...


class OllamaProvider(EmbeddingProvider):
    """Ollama-backed embedding provider using nomic-embed-text (768d)."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
    ):
        self.base_url = (base_url or settings.hivemind_ollama_url).rstrip("/")
        self.model = model or settings.hivemind_embedding_model
        self.timeout = timeout

    async def embed(self, text_input: str) -> list[float]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text_input},
            )
            resp.raise_for_status()
            return resp.json()["embedding"]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        batch_size = settings.hivemind_embedding_batch_size
        for i in range(0, len(texts), batch_size):
            chunk = texts[i : i + batch_size]
            batch_results = await asyncio.gather(
                *(self.embed(t) for t in chunk), return_exceptions=True
            )
            for r in batch_results:
                if isinstance(r, BaseException):
                    raise r
                results.append(r)
        return results


# ── Circuit-Breaker ──────────────────────────────────────────────────────────


class CBState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Circuit-breaker with adaptive exponential backoff.

    - After `threshold` consecutive failures → OPEN
    - OPEN: requests return None immediately
    - Half-open probes: exponential backoff 60s → 120s → 240s → max 600s
    - Reset after 10 min stable CLOSED
    """

    threshold: int = settings.hivemind_embedding_cb_threshold
    backoff_base: int = settings.hivemind_embedding_cb_backoff_base
    backoff_max: int = settings.hivemind_embedding_cb_backoff_max
    reset_window: float = 600.0  # 10 minutes stable closed → reset backoff

    state: CBState = CBState.CLOSED
    consecutive_failures: int = 0
    backoff_multiplier: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    _closed_since: float = field(default_factory=time.monotonic)

    def record_success(self) -> None:
        """Record a successful call."""
        now = time.monotonic()
        self.consecutive_failures = 0
        self.last_success_time = now

        if self.state == CBState.HALF_OPEN:
            # Probe succeeded → go back to CLOSED
            logger.info("Circuit-breaker: HALF_OPEN → CLOSED (probe succeeded)")
            self.state = CBState.CLOSED
            self._closed_since = now

        # Reset backoff multiplier after stable CLOSED period
        if (
            self.state == CBState.CLOSED
            and self.backoff_multiplier > 0
            and (now - self._closed_since) >= self.reset_window
        ):
            logger.info("Circuit-breaker: backoff reset after stable CLOSED period")
            self.backoff_multiplier = 0

    def record_failure(self) -> None:
        """Record a failed call (timeout / error)."""
        now = time.monotonic()
        self.consecutive_failures += 1
        self.last_failure_time = now

        if self.state == CBState.HALF_OPEN:
            # Probe failed → back to OPEN with increased backoff
            self.backoff_multiplier += 1
            self.state = CBState.OPEN
            logger.warning(
                "Circuit-breaker: HALF_OPEN → OPEN (probe failed, backoff=%ds)",
                self._current_backoff(),
            )
            return

        if self.consecutive_failures >= self.threshold and self.state == CBState.CLOSED:
            self.state = CBState.OPEN
            logger.warning(
                "Circuit-breaker: CLOSED → OPEN after %d consecutive failures",
                self.consecutive_failures,
            )

    def allow_request(self) -> bool:
        """Check if a request should be allowed through."""
        if self.state == CBState.CLOSED:
            return True

        if self.state == CBState.OPEN:
            elapsed = time.monotonic() - self.last_failure_time
            backoff = self._current_backoff()
            if elapsed >= backoff:
                logger.info(
                    "Circuit-breaker: OPEN → HALF_OPEN (trying probe after %ds)",
                    backoff,
                )
                self.state = CBState.HALF_OPEN
                return True
            return False

        # HALF_OPEN: only one probe at a time
        return True

    # ── helpers ───────────────────────────────────────────────────────────

    def _current_backoff(self) -> float:
        return min(
            self.backoff_base * (2**self.backoff_multiplier),
            self.backoff_max,
        )

    def _max_multiplier(self) -> int:
        """Calculate max multiplier to keep backoff <= backoff_max."""
        m = 0
        while self.backoff_base * (2 ** (m + 1)) <= self.backoff_max:
            m += 1
        return m


# ── Priority Queue ───────────────────────────────────────────────────────────


class EmbeddingPriority(enum.IntEnum):
    """Lower value = higher priority."""

    ON_WRITE = 1
    BATCH = 2
    FEDERATION = 3


@dataclass(order=True)
class EmbeddingJob:
    available_at: float
    priority: int
    table: str = field(compare=False)
    record_id: str = field(compare=False)
    text: str = field(compare=False)
    attempts: int = field(default=0, compare=False)
    created_at: float = field(default_factory=time.monotonic, compare=False)


# ── Main service ─────────────────────────────────────────────────────────────


class EmbeddingService:
    """Facade: provider + circuit-breaker + priority queue."""

    def __init__(self, provider: EmbeddingProvider | None = None):
        self.provider: EmbeddingProvider = provider or OllamaProvider()
        self.circuit_breaker = CircuitBreaker()
        self._queue: asyncio.PriorityQueue[EmbeddingJob] = asyncio.PriorityQueue()
        self._running = False
        self._worker_task: asyncio.Task | None = None
        self._query_cache: dict[str, tuple[float, list[float]]] = {}

    # ── public API ────────────────────────────────────────────────────────

    async def embed(self, text_input: str) -> list[float] | None:
        """Generate embedding with circuit-breaker protection.

        Returns None when circuit-breaker is open (feature-degradation).
        """
        if not self.circuit_breaker.allow_request():
            logger.debug("Embedding skipped — circuit-breaker OPEN")
            return None

        try:
            result = await self.provider.embed(text_input)
            self.circuit_breaker.record_success()
            return result
        except Exception as exc:
            self.circuit_breaker.record_failure()
            logger.warning("Embedding failed (%s): %s", type(exc).__name__, exc)
            return None

    async def embed_batch(self, texts: list[str]) -> list[list[float] | None]:
        """Batch embedding with circuit-breaker protection."""
        if not self.circuit_breaker.allow_request():
            return [None] * len(texts)

        try:
            results = await self.provider.embed_batch(texts)
            self.circuit_breaker.record_success()
            return results
        except Exception as exc:
            self.circuit_breaker.record_failure()
            logger.warning("Batch embedding failed (%s): %s", type(exc).__name__, exc)
            return [None] * len(texts)

    async def enqueue(
        self,
        table: str,
        record_id: str,
        text_input: str,
        priority: EmbeddingPriority = EmbeddingPriority.ON_WRITE,
        *,
        attempts: int = 0,
        available_at: float | None = None,
    ) -> None:
        """Add an embedding job to the priority queue."""
        if table not in EMBEDDABLE_TABLES:
            raise ValueError(f"Unsupported embedding table: {table}")
        job = EmbeddingJob(
            available_at=available_at or time.monotonic(),
            priority=priority.value,
            table=table,
            record_id=record_id,
            text=text_input,
            attempts=attempts,
        )
        await self._queue.put(job)

    async def start_worker(self) -> None:
        """Start the background queue worker."""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._process_queue())
        logger.info("Embedding queue worker started")

    async def stop_worker(self) -> None:
        """Stop the background queue worker."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("Embedding queue worker stopped")

    async def enqueue_missing_embeddings(
        self,
        *,
        tables: list[str] | None = None,
        limit_per_table: int | None = None,
    ) -> dict[str, int]:
        """Scan for rows without embeddings and enqueue batch jobs."""
        from app.db import AsyncSessionLocal

        selected_tables = tables or list(EMBEDDING_TEXT_COLS.keys())
        counts: dict[str, int] = {}
        batch_limit = limit_per_table or settings.hivemind_embedding_backfill_limit

        async with AsyncSessionLocal() as db:
            for table in selected_tables:
                text_expr = EMBEDDING_TEXT_COLS.get(table)
                if not text_expr:
                    continue
                rows = (
                    await db.execute(
                        text(
                            f"SELECT id, {text_expr} AS txt "
                            f"FROM {table} "
                            "WHERE embedding IS NULL "
                            "LIMIT :limit"
                        ),
                        {"limit": batch_limit},
                    )
                ).all()
                queued = 0
                for row in rows:
                    text_input = (row.txt or "").strip()
                    if not text_input:
                        continue
                    await self.enqueue(
                        table,
                        str(row.id),
                        text_input,
                        priority=EmbeddingPriority.BATCH,
                    )
                    queued += 1
                counts[table] = queued
        return counts

    # ── on-write hooks ────────────────────────────────────────────────────

    async def on_skill_merge(self, db: AsyncSession, skill_id: str, text_input: str) -> None:
        """Hook: automatically compute embedding on skill merge."""
        embedding = await self.embed(text_input)
        await self._store_embedding(db, "skills", skill_id, embedding)

    async def on_wiki_create(self, db: AsyncSession, article_id: str, text_input: str) -> None:
        """Hook: automatically compute embedding on wiki article create."""
        embedding = await self.embed(text_input)
        await self._store_embedding(db, "wiki_articles", article_id, embedding)

    async def on_epic_create(self, db: AsyncSession, epic_id: str, text_input: str) -> None:
        """Hook: automatically compute embedding on epic create."""
        embedding = await self.embed(text_input)
        await self._store_embedding(db, "epics", epic_id, embedding)

    # ── similarity search ─────────────────────────────────────────────────

    async def search_similar(
        self,
        db: AsyncSession,
        table: str,
        query_text: str,
        limit: int = 5,
        candidate_ids: list[str] | None = None,
    ) -> list[dict]:
        """Semantic similarity search across any embedding-enabled table.

        Returns empty list when embeddings unavailable (feature-degradation).
        """
        if table not in EMBEDDABLE_TABLES:
            raise ValueError(f"Unsupported embedding table: {table}")
        query_embedding = await self.embed_query(query_text)
        if query_embedding is None:
            return []

        explicit_candidates = candidate_ids is not None
        candidate_ids = [str(candidate_id) for candidate_id in (candidate_ids or []) if str(candidate_id)]
        if explicit_candidates and not candidate_ids:
            return []
        if candidate_ids:
            stmt = text(f"""
                SELECT id, 1 - (embedding <=> CAST(:query AS vector)) AS similarity
                FROM {table}
                WHERE embedding IS NOT NULL
                  AND id::text IN :candidate_ids
                ORDER BY embedding <=> CAST(:query AS vector)
                LIMIT :limit
            """).bindparams(bindparam("candidate_ids", expanding=True))
            params = {
                "query": str(query_embedding),
                "limit": limit,
                "candidate_ids": candidate_ids,
            }
        else:
            stmt = text(f"""
                SELECT id, 1 - (embedding <=> CAST(:query AS vector)) AS similarity
                FROM {table}
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> CAST(:query AS vector)
                LIMIT :limit
            """)
            params = {
                "query": str(query_embedding),
                "limit": limit,
            }
        result = await db.execute(stmt, params)
        return [{"id": str(row.id), "similarity": float(row.similarity)} for row in result]

    async def embed_query(self, text_input: str) -> list[float] | None:
        """Embed query text with a small TTL cache to avoid repeated request blocking."""
        if not text_input.strip():
            return None

        now = time.monotonic()
        cache_key = hashlib.sha1(text_input.encode("utf-8")).hexdigest()
        cached = self._query_cache.get(cache_key)
        if cached and cached[0] > now:
            return cached[1]
        if cached and cached[0] <= now:
            self._query_cache.pop(cache_key, None)

        embedding = await self.embed(text_input)
        if embedding is None:
            return None

        self._query_cache[cache_key] = (
            now + settings.hivemind_embedding_query_cache_ttl,
            embedding,
        )
        self._trim_query_cache()
        return embedding

    # ── internal ──────────────────────────────────────────────────────────

    async def _store_embedding(
        self,
        db: AsyncSession,
        table: str,
        record_id: str,
        embedding: list[float] | None,
    ) -> None:
        """Persist embedding to the database (raw SQL for pgvector type)."""
        if embedding is not None:
            stmt = text(f"""
                UPDATE {table}
                SET embedding = CAST(:embedding AS vector), embedding_model = :model
                WHERE id = :id
            """)
            await db.execute(
                stmt,
                {
                    "embedding": str(embedding),
                    "model": settings.hivemind_embedding_model,
                    "id": record_id,
                },
            )
        else:
            # NULL-embedding: clear model info as well
            stmt = text(f"""
                UPDATE {table}
                SET embedding = NULL, embedding_model = NULL
                WHERE id = :id
            """)
            await db.execute(stmt, {"id": record_id})
        await db.commit()

    async def _process_queue(self) -> None:
        """Background worker processing the priority queue."""
        from app.db import AsyncSessionLocal

        while self._running:
            try:
                job = await asyncio.wait_for(self._queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            if job.available_at > time.monotonic():
                await self._queue.put(job)
                delay = max(job.available_at - time.monotonic(), 0.0)
                await asyncio.sleep(min(delay, 1.0))
                continue

            try:
                async with AsyncSessionLocal() as db:
                    await self._process_job(db, job)
            except Exception as exc:
                logger.error("Failed to process embedding job %s/%s: %s", job.table, job.record_id, exc)

    async def _process_job(self, db: AsyncSession, job: EmbeddingJob) -> None:
        embedding = await self.embed(job.text)
        if embedding is None:
            await self._retry_job(job, reason="embedding_unavailable")
            return

        await self._store_embedding(db, job.table, job.record_id, embedding)
        logger.debug(
            "Processed embedding job: %s/%s (prio=%d attempts=%d)",
            job.table,
            job.record_id,
            job.priority,
            job.attempts,
        )

    async def _retry_job(self, job: EmbeddingJob, *, reason: str) -> None:
        next_attempt = job.attempts + 1
        if next_attempt >= settings.hivemind_embedding_retry_max_attempts:
            logger.warning(
                "Dropping embedding job after %d attempts: %s/%s (%s)",
                next_attempt,
                job.table,
                job.record_id,
                reason,
            )
            return

        backoff_seconds = min(
            settings.hivemind_embedding_retry_backoff_base * (2 ** max(job.attempts, 0)),
            settings.hivemind_embedding_retry_backoff_max,
        )
        await self.enqueue(
            job.table,
            job.record_id,
            job.text,
            priority=EmbeddingPriority(job.priority),
            attempts=next_attempt,
            available_at=time.monotonic() + backoff_seconds,
        )
        logger.info(
            "Retrying embedding job in %ss: %s/%s (%s, attempt %d/%d)",
            backoff_seconds,
            job.table,
            job.record_id,
            reason,
            next_attempt + 1,
            settings.hivemind_embedding_retry_max_attempts,
        )

    def _trim_query_cache(self) -> None:
        max_entries = max(settings.hivemind_embedding_query_cache_size, 1)
        expired = [key for key, (expires_at, _) in self._query_cache.items() if expires_at <= time.monotonic()]
        for key in expired:
            self._query_cache.pop(key, None)
        while len(self._query_cache) > max_entries:
            oldest_key = next(iter(self._query_cache))
            self._query_cache.pop(oldest_key, None)


# ── Singleton ────────────────────────────────────────────────────────────────

_service: Optional[EmbeddingService] = None


def get_embedding_service(provider: EmbeddingProvider | None = None) -> EmbeddingService:
    """Get or create the singleton embedding service."""
    global _service
    if _service is None:
        _service = EmbeddingService(provider=provider)
    return _service
