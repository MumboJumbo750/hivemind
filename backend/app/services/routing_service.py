"""pgvector Auto-Routing Service — TASK-7-006.

Routes inbound bug reports to epics via cosine-similarity on embeddings.
Threshold is read from app_settings with a 60-second in-memory cache.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import has_routing_threshold_env_override, settings
from app.db import AsyncSessionLocal
from app.models.node_bug_report import NodeBugReport
from app.models.settings import AppSettings
from app.services import event_bus
from app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

# 60-second TTL cache for routing threshold
_threshold_cache: dict[str, float] = {}
_threshold_cache_ts: float = 0.0
_THRESHOLD_TTL = 60.0

EMBEDDING_SVC = EmbeddingService()


@dataclass
class RoutingResult:
    bug_report_id: uuid.UUID
    epic_id: Optional[uuid.UUID]
    score: float
    threshold: float
    routed: bool


async def _load_threshold(db: AsyncSession) -> float:
    """Load routing threshold from DB with 60s cache. ENV overrides DB."""
    global _threshold_cache_ts

    # ENV override always wins
    if has_routing_threshold_env_override():
        return settings.hivemind_routing_threshold

    now = time.monotonic()
    if _threshold_cache and (now - _threshold_cache_ts) < _THRESHOLD_TTL:
        return _threshold_cache.get("value", 0.85)

    result = await db.execute(
        select(AppSettings).where(AppSettings.key == "routing_threshold")
    )
    row = result.scalar_one_or_none()
    try:
        value = float(row.value) if row else 0.85
    except (ValueError, TypeError):
        value = 0.85

    _threshold_cache["value"] = value
    _threshold_cache_ts = now
    return value


def invalidate_threshold_cache() -> None:
    """Invalidate the threshold cache (call after PATCH /settings/routing-threshold)."""
    global _threshold_cache_ts
    _threshold_cache.clear()
    _threshold_cache_ts = 0.0


async def route_bug_to_epic(
    bug_report_id: uuid.UUID,
    text_for_embedding: str,
) -> RoutingResult:
    """Compute cosine-similarity against epic embeddings, assign epic_id if above threshold."""
    async with AsyncSessionLocal() as db:
        threshold = await _load_threshold(db)

        def _publish_unrouted(score: float, reason: str | None = None) -> None:
            payload = {
                "bug_report_id": str(bug_report_id),
                "score": score,
                "threshold": threshold,
            }
            if reason:
                payload["reason"] = reason
            event_bus.publish("bug_unrouted", payload, channel="triage")

        try:
            embedding = await EMBEDDING_SVC.embed(text_for_embedding)
        except Exception as exc:
            logger.warning("Embedding failed for bug %s: %s", bug_report_id, exc)
            _publish_unrouted(score=0.0, reason="embedding_error")
            return RoutingResult(
                bug_report_id=bug_report_id,
                epic_id=None,
                score=0.0,
                threshold=threshold,
                routed=False,
            )

        if not embedding:
            logger.info("Embedding unavailable for bug %s (feature degradation)", bug_report_id)
            _publish_unrouted(score=0.0, reason="embedding_unavailable")
            return RoutingResult(
                bug_report_id=bug_report_id,
                epic_id=None,
                score=0.0,
                threshold=threshold,
                routed=False,
            )

        # Find best-matching epic by cosine similarity
        vec_literal = "[" + ",".join(str(v) for v in embedding) + "]"
        row = (
            await db.execute(
                text(
                    "SELECT id, 1 - (embedding <=> (:vec)::vector) AS score "
                    "FROM epics WHERE embedding IS NOT NULL "
                    "ORDER BY score DESC LIMIT 1"
                ),
                {"vec": vec_literal},
            )
        ).first()

        score = float(row.score) if row else 0.0
        epic_id: Optional[uuid.UUID] = uuid.UUID(str(row.id)) if (row and score >= threshold) else None
        routed = epic_id is not None

        if routed and epic_id:
            result = await db.execute(
                select(NodeBugReport).where(NodeBugReport.id == bug_report_id)
            )
            report = result.scalar_one_or_none()
            if report:
                report.epic_id = epic_id
                await db.commit()

                event_bus.publish(
                    "bug_routed",
                    {
                        "bug_report_id": str(bug_report_id),
                        "epic_id": str(epic_id),
                        "score": score,
                    },
                    channel="triage",
                )
        else:
            await db.rollback()
            _publish_unrouted(score=score)

        return RoutingResult(
            bug_report_id=bug_report_id,
            epic_id=epic_id,
            score=score,
            threshold=threshold,
            routed=routed,
        )
