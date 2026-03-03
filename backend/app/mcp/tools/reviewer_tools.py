"""Reviewer Agent MCP Tools — Phase 8 (TASK-8-007).

submit_review_recommendation: AI Reviewer submits review result.

IMPORTANT:
- This tool NEVER directly changes Task state.
- It only creates a ReviewRecommendation record.
- Governance level determines what happens next:
  - manual:   Human reviews recommendation and decides
  - assisted: Human 1-click approve/reject with AI recommendation shown
  - auto:     Grace period starts → auto-approve if confidence ≥ threshold
- Auto-reject is NEVER allowed — reject always requires human confirmation.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from mcp.types import TextContent, Tool

from app.db import AsyncSessionLocal
from app.mcp.server import register_tool

logger = logging.getLogger(__name__)


def _ok(data: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, default=str))]


def _err(msg: str) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"error": msg}))]

TOOLS = [
    {
        "name": "hivemind/submit_review_recommendation",
        "description": (
            "Submit an AI review recommendation for a task. "
            "Does NOT change task state directly. "
            "recommendation must be: 'approve', 'reject', or 'needs_human_review'. "
            "confidence is 0.0–1.0. "
            "checklist is a list of {item, passed, comment} objects. "
            "Auto-reject is never auto-executed — always requires human confirmation."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_key": {
                    "type": "string",
                    "description": "The task key (e.g. TASK-8-001)",
                },
                "recommendation": {
                    "type": "string",
                    "enum": ["approve", "reject", "needs_human_review"],
                    "description": "Review recommendation",
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Confidence score 0.0–1.0",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Explanation of the recommendation",
                },
                "checklist": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "item": {"type": "string"},
                            "passed": {"type": "boolean"},
                            "comment": {"type": "string"},
                        },
                    },
                    "description": "DoD checklist items with pass/fail",
                },
                "reviewer_dispatch_id": {
                    "type": "string",
                    "description": "Optional: conductor dispatch ID that triggered this review",
                },
            },
            "required": ["task_key", "recommendation", "confidence", "reasoning"],
        },
    },
    {
        "name": "hivemind/veto_auto_review",
        "description": "Veto a pending auto-review recommendation during the grace period.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "recommendation_id": {
                    "type": "string",
                    "description": "UUID of the ReviewRecommendation to veto",
                },
            },
            "required": ["recommendation_id"],
        },
    },
    {
        "name": "hivemind/get_review_recommendations",
        "description": "Get review recommendations for a task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_key": {"type": "string"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["task_key"],
        },
    },
]


async def handle_submit_review_recommendation(
    task_key: str,
    recommendation: str,
    confidence: float,
    reasoning: str,
    checklist: list | None,
    reviewer_dispatch_id: str | None,
    db: Any,
    actor_id: str,
) -> dict:
    """Create a ReviewRecommendation. Never changes task state directly."""
    from sqlalchemy import select
    from app.models.task import Task
    from app.models.review import ReviewRecommendation
    from app.config import settings
    from app.services.governance import get_governance_level

    # Resolve task
    result = await db.execute(select(Task).where(Task.task_key == task_key))
    task = result.scalar_one_or_none()
    if not task:
        return {"error": f"Task '{task_key}' not found"}

    # Get governance level
    review_level = await get_governance_level(db, "review")
    grace_period_until = None
    if review_level == "auto" and recommendation == "approve":
        grace_minutes = settings.hivemind_auto_review_grace_minutes
        grace_period_until = datetime.now(UTC) + timedelta(minutes=grace_minutes)

    # SAFEGUARD: auto-reject is never allowed
    # Even if recommendation is 'reject', grace_period_until stays None
    # → requires human confirmation

    dispatch_id = None
    if reviewer_dispatch_id:
        try:
            dispatch_id = uuid.UUID(reviewer_dispatch_id)
        except ValueError:
            pass

    rec = ReviewRecommendation(
        id=uuid.uuid4(),
        task_id=task.id,
        reviewer_dispatch_id=dispatch_id,
        recommendation=recommendation,
        confidence=confidence,
        checklist=checklist or [],
        reasoning=reasoning,
        grace_period_until=grace_period_until,
        auto_approved=False,
        created_at=datetime.now(UTC),
    )
    db.add(rec)
    await db.flush()
    await db.refresh(rec)
    await db.commit()

    logger.info(
        "ReviewRecommendation created: task=%s, recommendation=%s, confidence=%.2f, level=%s",
        task_key, recommendation, confidence, review_level,
    )

    return {
        "recommendation_id": str(rec.id),
        "task_key": task_key,
        "recommendation": recommendation,
        "confidence": confidence,
        "governance_level": review_level,
        "grace_period_until": grace_period_until.isoformat() if grace_period_until else None,
        "message": (
            "Auto-approve scheduled after grace period"
            if grace_period_until
            else "Awaiting human review"
            if review_level == "manual"
            else "AI recommendation recorded — human confirmation required for reject"
        ),
    }


async def handle_veto_auto_review(
    recommendation_id: str,
    db: Any,
    actor_id: str,
) -> dict:
    """Veto an auto-review recommendation during grace period."""
    from sqlalchemy import select
    from app.models.review import ReviewRecommendation

    result = await db.execute(
        select(ReviewRecommendation).where(
            ReviewRecommendation.id == uuid.UUID(recommendation_id),
            ReviewRecommendation.auto_approved == False,
            ReviewRecommendation.vetoed_at.is_(None),
        )
    )
    rec = result.scalar_one_or_none()
    if not rec:
        return {"error": "Recommendation not found or already processed"}

    rec.vetoed_by = uuid.UUID(actor_id) if actor_id else None
    rec.vetoed_at = datetime.now(UTC)
    await db.commit()

    return {
        "recommendation_id": recommendation_id,
        "vetoed": True,
        "message": "Auto-review vetoed — awaiting manual decision",
    }


async def handle_get_review_recommendations(
    task_key: str,
    limit: int,
    db: Any,
) -> dict:
    """Get review recommendations for a task."""
    from sqlalchemy import select
    from app.models.task import Task
    from app.models.review import ReviewRecommendation

    result = await db.execute(select(Task).where(Task.task_key == task_key))
    task = result.scalar_one_or_none()
    if not task:
        return {"error": f"Task '{task_key}' not found"}

    result = await db.execute(
        select(ReviewRecommendation)
        .where(ReviewRecommendation.task_id == task.id)
        .order_by(ReviewRecommendation.created_at.desc())
        .limit(limit)
    )
    recs = result.scalars().all()

    return {
        "task_key": task_key,
        "recommendations": [
            {
                "id": str(r.id),
                "recommendation": r.recommendation,
                "confidence": r.confidence,
                "reasoning": r.reasoning,
                "checklist": r.checklist,
                "grace_period_until": r.grace_period_until.isoformat() if r.grace_period_until else None,
                "auto_approved": r.auto_approved,
                "vetoed_at": r.vetoed_at.isoformat() if r.vetoed_at else None,
                "created_at": r.created_at.isoformat(),
            }
            for r in recs
        ],
    }


# ── MCP Tool Registration ─────────────────────────────────────────────────────

async def _submit_review_handler(args: dict) -> list[TextContent]:
    actor_id = args.get("_actor_id", "00000000-0000-0000-0000-000000000001")
    async with AsyncSessionLocal() as db:
        result = await handle_submit_review_recommendation(
            task_key=args["task_key"],
            recommendation=args["recommendation"],
            confidence=float(args["confidence"]),
            reasoning=args.get("reasoning", ""),
            checklist=args.get("checklist"),
            reviewer_dispatch_id=args.get("reviewer_dispatch_id"),
            db=db,
            actor_id=actor_id,
        )
    return _ok(result) if "error" not in result else _err(result["error"])


async def _veto_review_handler(args: dict) -> list[TextContent]:
    actor_id = args.get("_actor_id", "00000000-0000-0000-0000-000000000001")
    async with AsyncSessionLocal() as db:
        result = await handle_veto_auto_review(
            recommendation_id=args["recommendation_id"],
            db=db,
            actor_id=actor_id,
        )
    return _ok(result) if "error" not in result else _err(result["error"])


async def _get_reviews_handler(args: dict) -> list[TextContent]:
    async with AsyncSessionLocal() as db:
        result = await handle_get_review_recommendations(
            task_key=args["task_key"],
            limit=int(args.get("limit", 5)),
            db=db,
        )
    return _ok(result) if "error" not in result else _err(result["error"])


register_tool(
    Tool(
        name="hivemind/submit_review_recommendation",
        description=(
            "Submit an AI review recommendation for a task. "
            "NEVER changes task state directly. "
            "recommendation: 'approve' | 'reject' | 'needs_human_review'. "
            "Auto-reject is never auto-executed."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_key": {"type": "string"},
                "recommendation": {"type": "string", "enum": ["approve", "reject", "needs_human_review"]},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "reasoning": {"type": "string"},
                "checklist": {"type": "array", "items": {"type": "object"}},
                "reviewer_dispatch_id": {"type": "string"},
            },
            "required": ["task_key", "recommendation", "confidence", "reasoning"],
        },
    ),
    _submit_review_handler,
)

register_tool(
    Tool(
        name="hivemind/veto_auto_review",
        description="Veto a pending auto-review recommendation during the grace period.",
        inputSchema={
            "type": "object",
            "properties": {
                "recommendation_id": {"type": "string"},
            },
            "required": ["recommendation_id"],
        },
    ),
    _veto_review_handler,
)

register_tool(
    Tool(
        name="hivemind/get_review_recommendations",
        description="Get AI review recommendations for a task (read-only).",
        inputSchema={
            "type": "object",
            "properties": {
                "task_key": {"type": "string"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["task_key"],
        },
    ),
    _get_reviews_handler,
)
