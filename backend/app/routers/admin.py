"""Admin endpoints — sync monitoring + embedding recompute (TASK-7-012)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Literal

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import AsyncSessionLocal, get_db
from app.routers.deps import require_role
from app.schemas.auth import CurrentActor
from app.services import event_bus
from app.services.dlq_service import (
    get_admin_dead_letter_rows,
    get_admin_delivered_rows,
    get_admin_retry_rows,
    get_queue_stats,
)
from app.services.embedding_service import EMBEDDING_TEXT_COLS

router = APIRouter(prefix="/admin", tags=["admin"])

PING_TIMEOUT_SECONDS = 4.0


class QueueOverview(BaseModel):
    pending_outbound: int
    pending_inbound: int
    dead_letters: int
    delivered_today: int


class DeliveredSyncItem(BaseModel):
    id: str
    timestamp: datetime
    direction: str
    payload_type: str
    duration_ms: int | None = None


class FailedSyncItem(BaseModel):
    id: str
    timestamp: datetime
    attempts: int
    last_error: str
    dlq_url: str


class ProviderStatus(BaseModel):
    state: Literal["online", "degraded", "offline", "not_configured"]
    detail: str | None = None
    checked_at: datetime


class ProviderOverview(BaseModel):
    ollama: ProviderStatus
    youtrack: ProviderStatus


class SyncStatusResponse(BaseModel):
    queue: QueueOverview
    recent_delivered: list[DeliveredSyncItem]
    recent_failed: list[FailedSyncItem]
    providers: ProviderOverview
    checked_at: datetime


@router.get("/sync-status", response_model=SyncStatusResponse)
async def get_sync_status(
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin")),
) -> SyncStatusResponse:
    """Return queue metrics, last sync activity, and provider health checks."""
    del actor  # Dependency enforces RBAC.
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    stats = await get_queue_stats(db, today_start)
    delivered_rows = await get_admin_delivered_rows(db, limit=10)
    dead_letter_rows = await get_admin_dead_letter_rows(db, limit=5)
    retry_rows = await get_admin_retry_rows(db, limit=5)

    recent_delivered = [
        DeliveredSyncItem(
            id=str(row.id),
            timestamp=row.created_at or now,
            direction=row.direction,
            payload_type=row.entity_type,
            duration_ms=None,
        )
        for row in delivered_rows
    ]

    failed_candidates = [
        FailedSyncItem(
            id=str(row.id),
            timestamp=row.failed_at or now,
            attempts=int(row.attempts or settings.hivemind_dlq_max_attempts),
            last_error=_preview_error(row.error),
            dlq_url=f"/triage?dead_letter={row.id}",
        )
        for row in dead_letter_rows
    ]
    failed_candidates.extend(
        FailedSyncItem(
            id=str(row.id),
            timestamp=row.created_at or now,
            attempts=int(row.attempts or 0),
            last_error="Retry pending (last error not persisted)",
            dlq_url="/triage",
        )
        for row in retry_rows
    )
    recent_failed = sorted(
        failed_candidates,
        key=lambda entry: entry.timestamp,
        reverse=True,
    )[:5]

    ollama_status, youtrack_status = await asyncio.gather(
        _check_ollama_status(),
        _check_youtrack_status(),
    )

    return SyncStatusResponse(
        queue=QueueOverview(
            pending_outbound=stats["pending_outbound"],
            pending_inbound=stats["pending_inbound"],
            dead_letters=stats["dead_letters"],
            delivered_today=stats["delivered_today"],
        ),
        recent_delivered=recent_delivered,
        recent_failed=recent_failed,
        providers=ProviderOverview(
            ollama=ollama_status,
            youtrack=youtrack_status,
        ),
        checked_at=now,
    )


def _preview_error(error: str | None, max_length: int = 160) -> str:
    if not error:
        return "Unknown sync error"
    compact = " ".join(error.split())
    if len(compact) <= max_length:
        return compact
    return f"{compact[:max_length]}..."


async def _check_ollama_status() -> ProviderStatus:
    checked_at = datetime.now(UTC)
    base_url = settings.hivemind_ollama_url.strip()
    if not base_url:
        return ProviderStatus(
            state="not_configured",
            detail="HIVEMIND_OLLAMA_URL missing",
            checked_at=checked_at,
        )

    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=PING_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
        if 200 <= response.status_code < 300:
            return ProviderStatus(state="online", detail="reachable", checked_at=checked_at)
        return ProviderStatus(
            state="degraded",
            detail=f"HTTP {response.status_code}",
            checked_at=checked_at,
        )
    except Exception as exc:
        return ProviderStatus(
            state="offline",
            detail=str(exc),
            checked_at=checked_at,
        )


async def _check_youtrack_status() -> ProviderStatus:
    checked_at = datetime.now(UTC)
    base_url = settings.hivemind_youtrack_url.strip()
    token = settings.hivemind_youtrack_token.strip()
    if not base_url:
        return ProviderStatus(
            state="not_configured",
            detail="HIVEMIND_YOUTRACK_URL missing",
            checked_at=checked_at,
        )
    if not token:
        return ProviderStatus(
            state="not_configured",
            detail="HIVEMIND_YOUTRACK_TOKEN missing",
            checked_at=checked_at,
        )

    url = f"{base_url.rstrip('/')}/api/admin/projects?fields=id&$top=1"
    try:
        async with httpx.AsyncClient(timeout=PING_TIMEOUT_SECONDS) as client:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
            )
        if 200 <= response.status_code < 300:
            return ProviderStatus(state="online", detail="reachable", checked_at=checked_at)
        if response.status_code in (401, 403):
            return ProviderStatus(
                state="degraded",
                detail=f"auth failed (HTTP {response.status_code})",
                checked_at=checked_at,
            )
        return ProviderStatus(
            state="degraded",
            detail=f"HTTP {response.status_code}",
            checked_at=checked_at,
        )
    except Exception as exc:
        return ProviderStatus(
            state="offline",
            detail=str(exc),
            checked_at=checked_at,
        )


# ── Embedding Recompute (TASK-7-012) ─────────────────────────────────────────

EMBEDDABLE_ENTITIES = tuple(EMBEDDING_TEXT_COLS.keys())


class EmbeddingStatusItem(BaseModel):
    entity_type: str
    total: int
    with_embedding: int
    without_embedding: int


class EmbeddingStatusResponse(BaseModel):
    entities: list[EmbeddingStatusItem]
    checked_at: datetime


class RecomputeRequest(BaseModel):
    entity_types: list[str] = list(EMBEDDABLE_ENTITIES)
    force: bool = False


class RecomputeResponse(BaseModel):
    job_id: str
    entity_types: list[str]
    force: bool
    started_at: datetime


@router.get("/embeddings/status", response_model=EmbeddingStatusResponse)
async def get_embedding_status(
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin")),
) -> EmbeddingStatusResponse:
    del actor
    now = datetime.now(UTC)
    entities: list[EmbeddingStatusItem] = []

    for entity_type, text_expr in EMBEDDING_TEXT_COLS.items():
        table = entity_type
        total_row = await db.execute(text(f"SELECT COUNT(*) FROM {table}"))  # noqa: S608
        total = int(total_row.scalar_one() or 0)
        with_emb_row = await db.execute(
            text(f"SELECT COUNT(*) FROM {table} WHERE embedding IS NOT NULL")  # noqa: S608
        )
        with_embedding = int(with_emb_row.scalar_one() or 0)
        entities.append(
            EmbeddingStatusItem(
                entity_type=entity_type,
                total=total,
                with_embedding=with_embedding,
                without_embedding=total - with_embedding,
            )
        )

    return EmbeddingStatusResponse(entities=entities, checked_at=now)


@router.post("/embeddings/recompute", response_model=RecomputeResponse)
async def recompute_embeddings(
    body: RecomputeRequest,
    background_tasks: BackgroundTasks,
    actor: CurrentActor = Depends(require_role("admin")),
) -> RecomputeResponse:
    del actor
    invalid = [et for et in body.entity_types if et not in EMBEDDABLE_ENTITIES]
    if invalid:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"Unknown entity types: {invalid}")

    job_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    background_tasks.add_task(
        _run_reembedding,
        entity_types=body.entity_types,
        force=body.force,
        job_id=job_id,
    )
    return RecomputeResponse(
        job_id=job_id,
        entity_types=body.entity_types,
        force=body.force,
        started_at=now,
    )


async def _run_reembedding(entity_types: list[str], force: bool, job_id: str) -> None:
    """Background task: recompute embeddings for selected entity types."""
    from app.services.embedding_service import EmbeddingService

    svc = EmbeddingService()

    for entity_type in entity_types:
        table = entity_type
        text_expr = EMBEDDING_TEXT_COLS[entity_type]
        async with AsyncSessionLocal() as db:
            if force:
                rows = (
                    await db.execute(text(f"SELECT id, {text_expr} AS txt FROM {table}"))  # noqa: S608
                ).all()
            else:
                rows = (
                    await db.execute(
                        text(f"SELECT id, {text_expr} AS txt FROM {table} WHERE embedding IS NULL")  # noqa: S608
                    )
                ).all()

            total = len(rows)
            done = 0
            errors = 0
            batch_size = settings.hivemind_embedding_batch_size

            for i in range(0, total, batch_size):
                batch = rows[i : i + batch_size]
                for row in batch:
                    try:
                        vec = await svc.embed(row.txt or "")
                        if vec:
                            vec_str = "[" + ",".join(str(v) for v in vec) + "]"
                            await db.execute(
                                text(
                                    f"UPDATE {table} SET embedding = CAST(:vec AS vector), "  # noqa: S608
                                    "embedding_model = :model WHERE id = :id"
                                ),
                                {
                                    "vec": vec_str,
                                    "model": settings.hivemind_embedding_model,
                                    "id": row.id,
                                },
                            )
                            done += 1
                        else:
                            errors += 1
                    except Exception:
                        errors += 1
                await db.commit()

                event_bus.publish(
                    "reembedding_progress",
                    {
                        "job_id": job_id,
                        "entity_type": entity_type,
                        "done": done,
                        "total": total,
                        "errors": errors,
                    },
                    channel="triage",
                )
