"""Learning Artifact MCP Tools — TASK-AGENT-004.

hivemind-list_learning_artifacts  — Artefakte abfragen (Agents)
hivemind-submit_learning_signal   — Explizites Lernsignal einreichen (triage, stratege, architekt, ...)
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from mcp.types import TextContent, Tool

from app.db import AsyncSessionLocal
from app.mcp.server import register_tool

logger = logging.getLogger(__name__)


def _ok(data: Any) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"data": data}, default=str))]


def _err(msg: str, code: str = "error") -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"error": {"code": code, "message": msg}}))]


# ── hivemind-list_learning_artifacts ─────────────────────────────────────────

register_tool(
    Tool(
        name="hivemind-list_learning_artifacts",
        description=(
            "Query structured learning artifacts captured from past agent outputs. "
            "Use this to retrieve relevant patterns, reject reasons, skill candidates, "
            "guard failures, and routing hints before planning or executing work. "
            "Filter by audience to get role-specific learnings. "
            "Returns artifacts ordered by recency (newest first)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "audience": {
                    "type": "string",
                    "enum": ["worker", "reviewer", "gaertner", "triage", "stratege", "architekt"],
                    "description": "Target audience — returns learnings relevant to this role",
                },
                "kind": {
                    "type": "string",
                    "enum": [
                        "fix_pattern", "review_checklist", "reject_reason", "skill_candidate",
                        "resume_guidance", "guard_failure", "routing_hint", "planning_insight",
                    ],
                    "description": "Filter by learning kind (stored in detail.kind)",
                },
                "task_key": {
                    "type": "string",
                    "description": "Filter by task key (e.g. TASK-42)",
                },
                "epic_key": {
                    "type": "string",
                    "description": "Filter by epic key (e.g. EPIC-3)",
                },
                "min_confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Minimum confidence score (default: 0.70)",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50,
                    "description": "Maximum results to return (default: 20)",
                },
            },
            "required": [],
        },
    ),
    handler=lambda args: _handle_list_learning_artifacts(args),
)


async def _handle_list_learning_artifacts(args: dict) -> list[TextContent]:
    from sqlalchemy import select
    from app.models.learning_artifact import LearningArtifact
    from app.models.epic import Epic
    from app.models.task import Task

    audience = args.get("audience")
    kind = args.get("kind")
    task_key = args.get("task_key")
    epic_key = args.get("epic_key")
    min_confidence = float(args.get("min_confidence") or 0.70)
    limit = min(int(args.get("limit") or 20), 50)

    async with AsyncSessionLocal() as db:
        q = (
            select(LearningArtifact)
            .where(LearningArtifact.status != "suppressed")
            .where(LearningArtifact.confidence >= min_confidence)
            .order_by(LearningArtifact.created_at.desc())
            .limit(limit)
        )

        if task_key:
            task_row = (
                await db.execute(select(Task).where(Task.task_key == task_key))
            ).scalar_one_or_none()
            if task_row:
                q = q.where(LearningArtifact.task_id == task_row.id)

        if epic_key:
            epic_row = (
                await db.execute(select(Epic).where(Epic.epic_key == epic_key))
            ).scalar_one_or_none()
            if epic_row:
                q = q.where(LearningArtifact.epic_id == epic_row.id)

        rows = (await db.execute(q)).scalars().all()

        results = []
        for row in rows:
            detail = row.detail or {}
            # Audience filter: if audience given, check detail.audiences list
            if audience:
                audiences = detail.get("audiences") or []
                if audiences and audience not in audiences:
                    continue
            # Kind filter
            if kind and detail.get("kind") != kind:
                continue

            results.append({
                "id": str(row.id),
                "artifact_type": row.artifact_type,
                "status": row.status,
                "source_type": row.source_type,
                "agent_role": row.agent_role,
                "summary": row.summary,
                "confidence": row.confidence,
                "kind": detail.get("kind"),
                "audiences": detail.get("audiences"),
                "created_at": str(row.created_at),
            })

        return _ok({"artifacts": results, "count": len(results)})


# ── hivemind-submit_learning_signal ───────────────────────────────────────────

register_tool(
    Tool(
        name="hivemind-submit_learning_signal",
        description=(
            "Submit an explicit structured learning signal from agent observations. "
            "Use this when you observe a pattern, routing insight, planning decision, "
            "or other reusable knowledge that should be persisted for future agents. "
            "Supported kinds: routing_hint (triage), planning_insight (stratege/architekt), "
            "skill_candidate (gaertner/reviewer), guard_failure (worker/reviewer). "
            "Signals with confidence below threshold are stored as 'suppressed' "
            "and excluded from future prompt injections."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Concise human-readable summary of the learning (min 24 chars)",
                },
                "kind": {
                    "type": "string",
                    "enum": [
                        "routing_hint", "planning_insight", "skill_candidate",
                        "guard_failure", "fix_pattern", "review_checklist",
                    ],
                    "description": "Category of the learning signal",
                },
                "audiences": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Roles that should receive this learning (e.g. ['worker', 'gaertner'])",
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Confidence that this is a useful, generalisable learning",
                },
                "task_key": {
                    "type": "string",
                    "description": "Task key this learning is associated with (optional)",
                },
                "epic_key": {
                    "type": "string",
                    "description": "Epic key this learning is associated with (optional)",
                },
                "detail": {
                    "type": "object",
                    "description": "Additional structured data (free-form JSON object)",
                },
            },
            "required": ["summary", "kind", "confidence"],
        },
    ),
    handler=lambda args: _handle_submit_learning_signal(args),
)


async def _handle_submit_learning_signal(args: dict) -> list[TextContent]:
    from sqlalchemy import select
    from app.models.epic import Epic
    from app.models.task import Task
    from app.services.learning_artifacts import create_learning_artifact

    summary = (args.get("summary") or "").strip()
    if len(summary) < 24:
        return _err("summary must be at least 24 characters", "validation_error")

    kind = args.get("kind") or "fix_pattern"
    audiences = args.get("audiences") or []
    confidence = float(args.get("confidence") or 0.70)
    task_key = args.get("task_key")
    epic_key = args.get("epic_key")
    extra_detail = args.get("detail") or {}
    actor_role = str(args.get("_actor_role") or "unknown")

    # Map kind → artifact_type
    kind_to_type = {
        "routing_hint": "execution_learning",
        "planning_insight": "execution_learning",
        "skill_candidate": "execution_learning",
        "guard_failure": "execution_learning",
        "fix_pattern": "execution_learning",
        "review_checklist": "execution_learning",
    }
    artifact_type = kind_to_type.get(kind, "execution_learning")

    async with AsyncSessionLocal() as db:
        task_id: str | None = None
        epic_id: str | None = None

        if task_key:
            task_row = (
                await db.execute(select(Task).where(Task.task_key == task_key))
            ).scalar_one_or_none()
            if task_row:
                task_id = str(task_row.id)
                if not epic_id and task_row.epic_id:
                    epic_id = str(task_row.epic_id)

        if epic_key:
            epic_row = (
                await db.execute(select(Epic).where(Epic.epic_key == epic_key))
            ).scalar_one_or_none()
            if epic_row:
                epic_id = str(epic_row.id)

        source_ref = task_key or epic_key or f"agent:{actor_role}"
        detail = {
            "kind": kind,
            "audiences": audiences or _default_audiences(kind, actor_role),
            "occurrence_count": 1,
            "source_refs": [source_ref],
            "source_task_keys": [task_key] if task_key else [],
            **extra_detail,
            "effectiveness": {},
        }

        artifact = await create_learning_artifact(
            db,
            artifact_type=artifact_type,
            source_type=f"agent_signal:{kind}",
            source_ref=source_ref,
            summary=summary,
            detail=detail,
            agent_role=actor_role,
            task_id=task_id,
            epic_id=epic_id,
            confidence=confidence,
            merge_on_duplicate=True,
        )
        await db.commit()

        if artifact is None:
            return _err("Learning signal could not be persisted (duplicate or too short)")

        return _ok({
            "artifact_id": str(artifact.id),
            "status": artifact.status,
            "confidence": artifact.confidence,
            "summary": artifact.summary,
        })


def _default_audiences(kind: str, agent_role: str) -> list[str]:
    """Determine default audiences based on signal kind and submitting role."""
    defaults: dict[str, list[str]] = {
        "routing_hint": ["triage", "stratege"],
        "planning_insight": ["stratege", "architekt", "worker"],
        "skill_candidate": ["gaertner"],
        "guard_failure": ["worker", "reviewer"],
        "fix_pattern": ["worker", "gaertner"],
        "review_checklist": ["reviewer", "worker"],
    }
    return defaults.get(kind, [agent_role])
