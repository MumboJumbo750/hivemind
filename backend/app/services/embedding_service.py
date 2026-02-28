"""Embedding-Service with provider abstraction and circuit-breaker.

Supports pluggable providers (default: Ollama nomic-embed-text 768d).
Circuit-breaker with adaptive exponential backoff prevents cascade failures.
Priority queue: on-write > batch > federation.
NULL-embedding = feature-degradation (semantic search disabled), not an error.
"""
from __future__ import annotations

import asyncio
import enum
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)


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
    priority: int
    table: str = field(compare=False)
    record_id: str = field(compare=False)
    text: str = field(compare=False)
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
    ) -> None:
        """Add an embedding job to the priority queue."""
        job = EmbeddingJob(
            priority=priority.value,
            table=table,
            record_id=record_id,
            text=text_input,
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
    ) -> list[dict]:
        """Semantic similarity search across any embedding-enabled table.

        Returns empty list when embeddings unavailable (feature-degradation).
        """
        query_embedding = await self.embed(query_text)
        if query_embedding is None:
            return []

        stmt = text(f"""
            SELECT id, 1 - (embedding <=> :query::vector) AS similarity
            FROM {table}
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> :query::vector
            LIMIT :limit
        """)
        result = await db.execute(
            stmt, {"query": str(query_embedding), "limit": limit}
        )
        return [{"id": str(row.id), "similarity": float(row.similarity)} for row in result]

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
                SET embedding = :embedding::vector, embedding_model = :model
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

            embedding = await self.embed(job.text)
            try:
                async with AsyncSessionLocal() as db:
                    await self._store_embedding(db, job.table, job.record_id, embedding)
                logger.debug(
                    "Processed embedding job: %s/%s (prio=%d)",
                    job.table,
                    job.record_id,
                    job.priority,
                )
            except Exception as exc:
                logger.error("Failed to store embedding: %s", exc)


# ── Singleton ────────────────────────────────────────────────────────────────

_service: Optional[EmbeddingService] = None


def get_embedding_service(provider: EmbeddingProvider | None = None) -> EmbeddingService:
    """Get or create the singleton embedding service."""
    global _service
    if _service is None:
        _service = EmbeddingService(provider=provider)
    return _service
