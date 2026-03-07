"""KPI aggregation service - TASK-7-013.

Computes 6 core KPIs with an in-memory hourly cache.
Cache is populated on first request (no empty response) and refreshed by APScheduler.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import text

from app.db import AsyncSessionLocal

logger = logging.getLogger(__name__)

# ── In-memory cache ────────────────────────────────────────────────────────

_kpi_cache: list[dict[str, Any]] = []
_computed_at: Optional[datetime] = None
_cache_lock = asyncio.Lock()


def get_cached_kpis() -> tuple[list[dict[str, Any]], Optional[datetime]]:
    return _kpi_cache, _computed_at


# ── KPI targets ───────────────────────────────────────────────────────────

_KPI_TARGETS: dict[str, float] = {
    "routing_precision": 85.0,
    "median_time_to_scoped_hours": 4.0,
    "tasks_no_reopen_pct": 80.0,
    "decision_requests_in_sla_pct": 95.0,
    "skill_proposals_72h_pct": 90.0,
    "unauthorized_writes_count": 0.0,
}


def _status(value: float, target: float, *, lower_is_better: bool = False) -> str:
    if lower_is_better:
        if value <= target:
            return "ok"
        if value <= target * 2:
            return "warn"
        return "critical"
    # Higher is better (percentage KPIs)
    if value >= target:
        return "ok"
    if value >= target * 0.8:
        return "warn"
    return "critical"


async def compute_kpis() -> list[dict[str, Any]]:
    """Run all KPI SQL queries and return result list."""
    now = datetime.now(UTC)
    cutoff_7d = now - timedelta(days=7)
    cutoff_30d = now - timedelta(days=30)

    async with AsyncSessionLocal() as db:
        results: list[dict[str, Any]] = []

        # 1. Routing precision: bugs with epic_id / total (last 7d)
        row = (
            await db.execute(
                text(
                    "SELECT "
                    "COUNT(*) FILTER (WHERE epic_id IS NOT NULL) AS routed, "
                    "COUNT(*) AS total "
                    "FROM node_bug_reports WHERE created_at >= :cutoff"
                ),
                {"cutoff": cutoff_7d},
            )
        ).first()
        total = int(row.total or 0) if row else 0
        routed = int(row.routed or 0) if row else 0
        routing_precision = round((routed / total * 100) if total else 0.0, 1)
        results.append({
            "kpi": "routing_precision",
            "value": routing_precision,
            "target": _KPI_TARGETS["routing_precision"],
            "status": _status(routing_precision, _KPI_TARGETS["routing_precision"]),
            "computed_at": now.isoformat(),
        })

        # 2. Median time to scoped (hours, last 30d)
        # scoped_at is derived from audit records (update_epic with state='scoped').
        median_row = (
            await db.execute(
                text(
                    "WITH scoped_events AS ("
                    "  SELECT epic_id, MIN(created_at) AS scoped_at "
                    "  FROM mcp_invocations "
                    "  WHERE epic_id IS NOT NULL "
                    "    AND tool_name IN ('update_epic', 'hivemind-update_epic_state') "
                    "    AND input_payload->>'state' = 'scoped' "
                    "  GROUP BY epic_id"
                    ") "
                    "SELECT PERCENTILE_CONT(0.5) WITHIN GROUP "
                    "(ORDER BY EXTRACT(EPOCH FROM (s.scoped_at - e.created_at)) / 3600) AS median_h "
                    "FROM epics e "
                    "JOIN scoped_events s ON s.epic_id = e.id "
                    "WHERE e.created_at >= :cutoff "
                    "  AND s.scoped_at >= e.created_at"
                ),
                {"cutoff": cutoff_30d},
            )
        ).first()
        median_h = round(float(median_row.median_h or 0.0), 1) if median_row and median_row.median_h else 0.0
        results.append({
            "kpi": "median_time_to_scoped_hours",
            "value": median_h,
            "target": _KPI_TARGETS["median_time_to_scoped_hours"],
            "status": _status(median_h, _KPI_TARGETS["median_time_to_scoped_hours"], lower_is_better=True),
            "computed_at": now.isoformat(),
        })

        # 3. Tasks without reopen: tasks done/cancelled without state going back to in_progress
        done_row = (
            await db.execute(
                text(
                    "SELECT COUNT(*) AS total FROM tasks "
                    "WHERE state IN ('done', 'cancelled') AND updated_at >= :cutoff"
                ),
                {"cutoff": cutoff_30d},
            )
        ).first()
        done_total = int(done_row.total or 0) if done_row else 0

        reopen_row = (
            await db.execute(
                text(
                    "SELECT COUNT(DISTINCT COALESCE("
                    "  NULLIF(input_payload->>'task_key', ''), "
                    "  NULLIF(target_id, ''), "
                    "  NULLIF(input_payload->>'task_id', '')"
                    ")) AS cnt "
                    "FROM mcp_invocations "
                    "WHERE created_at >= :cutoff "
                    "AND COALESCE("
                    "  NULLIF(input_payload->>'task_key', ''), "
                    "  NULLIF(target_id, ''), "
                    "  NULLIF(input_payload->>'task_id', '')"
                    ") IS NOT NULL "
                    "AND ("
                    "  tool_name IN ('hivemind-reenter_from_qa_failed', 'reenter_from_qa_failed') "
                    "  OR ("
                    "    tool_name IN ('hivemind-update_task_state', 'update_task_state') "
                    "    AND input_payload->>'target_state' = 'in_progress' "
                    "    AND ("
                    "      output_payload->>'preview' LIKE '%\"previous_state\": \"qa_failed\"%' "
                    "      OR output_payload->>'preview' LIKE '%\"previous_state\": \"done\"%'"
                    "    )"
                    "  )"
                    ")"
                ),
                {"cutoff": cutoff_30d},
            )
        ).first()
        reopened = int(reopen_row.cnt or 0) if reopen_row else 0
        no_reopen = done_total - min(reopened, done_total)
        no_reopen_pct = round((no_reopen / done_total * 100) if done_total else 100.0, 1)
        results.append({
            "kpi": "tasks_no_reopen_pct",
            "value": no_reopen_pct,
            "target": _KPI_TARGETS["tasks_no_reopen_pct"],
            "status": _status(no_reopen_pct, _KPI_TARGETS["tasks_no_reopen_pct"]),
            "computed_at": now.isoformat(),
        })

        # 4. Decision requests resolved within SLA
        dr_row = (
            await db.execute(
                text(
                    "SELECT "
                    "COUNT(*) FILTER ("
                    "  WHERE resolved_at IS NOT NULL "
                    "  AND (sla_due_at IS NULL OR resolved_at <= sla_due_at)"
                    ") AS in_sla, "
                    "COUNT(*) FILTER (WHERE resolved_at IS NOT NULL) AS resolved "
                    "FROM decision_requests WHERE resolved_at >= :cutoff"
                ),
                {"cutoff": cutoff_30d},
            )
        ).first()
        resolved = int(dr_row.resolved or 0) if dr_row else 0
        in_sla = int(dr_row.in_sla or 0) if dr_row else 0
        dr_pct = round((in_sla / resolved * 100) if resolved else 100.0, 1)
        results.append({
            "kpi": "decision_requests_in_sla_pct",
            "value": dr_pct,
            "target": _KPI_TARGETS["decision_requests_in_sla_pct"],
            "status": _status(dr_pct, _KPI_TARGETS["decision_requests_in_sla_pct"]),
            "computed_at": now.isoformat(),
        })

        # 5. Skill change proposals reviewed within 72h
        skill_row = (
            await db.execute(
                text(
                    "SELECT "
                    "COUNT(*) FILTER ("
                    "  WHERE state IN ('accepted', 'rejected') "
                    "  AND reviewed_at IS NOT NULL "
                    "  AND EXTRACT(EPOCH FROM (reviewed_at - created_at)) <= 72 * 3600"
                    ") AS fast, "
                    "COUNT(*) FILTER ("
                    "  WHERE state IN ('accepted', 'rejected') "
                    "  AND reviewed_at IS NOT NULL"
                    ") AS total "
                    "FROM skill_change_proposals "
                    "WHERE created_at >= :cutoff"
                ),
                {"cutoff": cutoff_30d},
            )
        ).first()
        sp_total = int(skill_row.total or 0) if skill_row else 0
        sp_fast = int(skill_row.fast or 0) if skill_row else 0
        sp_pct = round((sp_fast / sp_total * 100) if sp_total else 100.0, 1)
        results.append({
            "kpi": "skill_proposals_72h_pct",
            "value": sp_pct,
            "target": _KPI_TARGETS["skill_proposals_72h_pct"],
            "status": _status(sp_pct, _KPI_TARGETS["skill_proposals_72h_pct"]),
            "computed_at": now.isoformat(),
        })

        # 6. Unauthorized write attempts (RBAC errors in mcp_invocations, last 30d)
        unauth_row = (
            await db.execute(
                text(
                    "SELECT COUNT(*) AS cnt FROM mcp_invocations "
                    "WHERE created_at >= :cutoff "
                    "AND ("
                    "  COALESCE(output_payload->>'error', '') ILIKE '%permission%' "
                    "  OR COALESCE(output_payload->>'error', '') ILIKE '%unauthorized%' "
                    "  OR COALESCE(output_payload->>'error', '') ILIKE '%forbidden%' "
                    "  OR COALESCE(output_payload->>'error', '') LIKE '%403%' "
                    "  OR COALESCE(output_payload->>'preview', '') ILIKE '%permission%' "
                    "  OR COALESCE(output_payload->>'preview', '') ILIKE '%unauthorized%' "
                    "  OR COALESCE(output_payload->>'preview', '') ILIKE '%forbidden%' "
                    "  OR COALESCE(output_payload->>'preview', '') LIKE '%403%' "
                    "  OR COALESCE(output_payload->>'preview', '') ILIKE '%Unzureichende Rechte%'"
                    ")"
                ),
                {"cutoff": cutoff_30d},
            )
        ).first()
        unauth = int(unauth_row.cnt or 0) if unauth_row else 0
        results.append({
            "kpi": "unauthorized_writes_count",
            "value": float(unauth),
            "target": _KPI_TARGETS["unauthorized_writes_count"],
            "status": _status(float(unauth), _KPI_TARGETS["unauthorized_writes_count"], lower_is_better=True),
            "computed_at": now.isoformat(),
        })

        return results


async def refresh_kpi_cache() -> bool:
    """APScheduler job: refresh the KPI cache.

    Returns ``True`` on success and ``False`` on failure.
    """
    global _kpi_cache, _computed_at
    try:
        computed = await compute_kpis()
        if len(computed) != 6:
            raise RuntimeError(f"Expected 6 KPIs, got {len(computed)}")
        _kpi_cache = computed
        _computed_at = datetime.now(UTC)
        logger.info("KPI cache refreshed - %d KPIs computed", len(_kpi_cache))
        return True
    except Exception:
        logger.exception("KPI cache refresh failed")
        return False


async def get_or_compute_kpis() -> tuple[list[dict[str, Any]], Optional[datetime]]:
    """Return cached KPIs, computing them if the cache is empty."""
    global _kpi_cache, _computed_at
    if _kpi_cache:
        return _kpi_cache, _computed_at

    async with _cache_lock:
        if not _kpi_cache:
            ok = await refresh_kpi_cache()
            if not ok:
                raise RuntimeError("KPI cache is unavailable")
    return _kpi_cache, _computed_at
