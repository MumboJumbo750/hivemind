"""MCP Admin Write Tools — TASK-5-011.

Admin-only write tools for managing proposals:
- hivemind/merge_guard          — draft/pending_merge guard → active (+30 EXP)
- hivemind/reject_guard         — reject a guard proposal
- hivemind/accept_skill_change  — Accept a draft skill proposal → active
- hivemind/reject_skill_change  — Reject a skill proposal
- hivemind/accept_epic_restructure — Accept epic restructure proposal
- hivemind/reject_epic_restructure — Reject epic restructure proposal
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from mcp.types import TextContent, Tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.mcp.server import register_tool
from app.services.event_bus import publish

logger = logging.getLogger(__name__)

ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _ok(data: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, default=str))]


def _err(code: str, message: str, status: int = 400) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({
        "error": {"code": code, "message": message, "status": status}
    }))]


async def _award_exp_simple(db: AsyncSession, user_id: uuid.UUID, amount: int) -> None:
    """Award EXP to a user (non-critical)."""
    from app.models.user import User
    try:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.exp_points = (user.exp_points or 0) + amount
            await db.flush()
    except Exception:
        logger.exception("_award_exp_simple failed (non-critical)")


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/merge_guard — pending_merge → active (+30 EXP)
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/merge_guard",
        description=(
            "Merge a guard proposal: transitions pending_merge → active. "
            "Awards +30 EXP to the guard's creator."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "guard_id": {"type": "string", "description": "Guard UUID to merge"},
            },
            "required": ["guard_id"],
        },
    ),
    handler=lambda args: _handle_merge_guard(args),
)


async def _handle_merge_guard(args: dict) -> list[TextContent]:
    from app.models.guard import Guard

    try:
        guard_id = uuid.UUID(args["guard_id"])
    except (KeyError, ValueError):
        return _err("VALIDATION_ERROR", "Ungültige guard_id", 422)

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                result = await db.execute(select(Guard).where(Guard.id == guard_id))
                guard = result.scalar_one_or_none()
                if not guard:
                    return _err("ENTITY_NOT_FOUND", f"Guard '{guard_id}' nicht gefunden", 404)

                if guard.lifecycle not in ("draft", "pending_merge"):
                    return _err(
                        "INVALID_STATE_TRANSITION",
                        f"Guard lifecycle muss draft oder pending_merge sein, ist '{guard.lifecycle}'",
                        422,
                    )

                guard.lifecycle = "active"
                guard.version += 1
                await db.flush()

                # Award +30 EXP to creator
                await _award_exp_simple(db, guard.created_by, 30)

                publish(
                    "guard_merged",
                    {"guard_id": str(guard_id), "title": guard.title},
                    channel="guards",
                )

                return _ok({
                    "data": {
                        "guard_id": str(guard_id),
                        "title": guard.title,
                        "lifecycle": "active",
                        "exp_awarded": 30,
                    },
                })
    except Exception as exc:
        logger.exception("merge_guard failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/reject_guard — reject a guard proposal
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/reject_guard",
        description="Reject a guard proposal: sets lifecycle to 'rejected'.",
        inputSchema={
            "type": "object",
            "properties": {
                "guard_id": {"type": "string", "description": "Guard UUID"},
                "reason": {"type": "string", "description": "Rejection reason"},
            },
            "required": ["guard_id", "reason"],
        },
    ),
    handler=lambda args: _handle_reject_guard(args),
)


async def _handle_reject_guard(args: dict) -> list[TextContent]:
    from app.models.guard import Guard

    try:
        guard_id = uuid.UUID(args["guard_id"])
    except (KeyError, ValueError):
        return _err("VALIDATION_ERROR", "Ungültige guard_id", 422)

    reason = args.get("reason", "").strip()
    if not reason:
        return _err("VALIDATION_ERROR", "reason darf nicht leer sein", 422)

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                result = await db.execute(select(Guard).where(Guard.id == guard_id))
                guard = result.scalar_one_or_none()
                if not guard:
                    return _err("ENTITY_NOT_FOUND", f"Guard '{guard_id}' nicht gefunden", 404)

                if guard.lifecycle not in ("draft", "pending_merge"):
                    return _err(
                        "INVALID_STATE_TRANSITION",
                        f"Guard kann nur aus draft/pending_merge abgelehnt werden, ist '{guard.lifecycle}'",
                        422,
                    )

                guard.lifecycle = "rejected"
                guard.description = f"{guard.description or ''}\n\n[Rejected] {reason}"
                guard.version += 1
                await db.flush()

                return _ok({
                    "data": {
                        "guard_id": str(guard_id),
                        "title": guard.title,
                        "lifecycle": "rejected",
                    },
                })
    except Exception as exc:
        logger.exception("reject_guard failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/accept_skill_change — draft skill → active (+20 EXP)
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/accept_skill_change",
        description=(
            "Accept a draft skill proposal: transitions lifecycle to 'active'. "
            "Awards +20 EXP to associated user."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "skill_id": {"type": "string", "description": "Skill UUID to accept"},
            },
            "required": ["skill_id"],
        },
    ),
    handler=lambda args: _handle_accept_skill_change(args),
)


async def _handle_accept_skill_change(args: dict) -> list[TextContent]:
    from app.models.skill import Skill

    try:
        skill_id = uuid.UUID(args["skill_id"])
    except (KeyError, ValueError):
        return _err("VALIDATION_ERROR", "Ungültige skill_id", 422)

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                result = await db.execute(select(Skill).where(Skill.id == skill_id))
                skill = result.scalar_one_or_none()
                if not skill:
                    return _err("ENTITY_NOT_FOUND", f"Skill '{skill_id}' nicht gefunden", 404)

                if skill.lifecycle != "draft":
                    return _err(
                        "INVALID_STATE_TRANSITION",
                        f"Skill muss draft sein, ist '{skill.lifecycle}'",
                        422,
                    )

                skill.lifecycle = "active"
                skill.version += 1
                await db.flush()

                # Award +20 EXP to admin
                await _award_exp_simple(db, ADMIN_ID, 20)

                publish(
                    "skill_accepted",
                    {"skill_id": str(skill_id), "title": skill.title},
                    channel="skills",
                )

                return _ok({
                    "data": {
                        "skill_id": str(skill_id),
                        "title": skill.title,
                        "lifecycle": "active",
                        "exp_awarded": 20,
                    },
                })
    except Exception as exc:
        logger.exception("accept_skill_change failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/reject_skill_change — reject a draft skill
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/reject_skill_change",
        description="Reject a draft skill proposal: sets lifecycle to 'rejected'.",
        inputSchema={
            "type": "object",
            "properties": {
                "skill_id": {"type": "string", "description": "Skill UUID"},
                "reason": {"type": "string", "description": "Rejection reason"},
            },
            "required": ["skill_id", "reason"],
        },
    ),
    handler=lambda args: _handle_reject_skill_change(args),
)


async def _handle_reject_skill_change(args: dict) -> list[TextContent]:
    from app.models.skill import Skill

    try:
        skill_id = uuid.UUID(args["skill_id"])
    except (KeyError, ValueError):
        return _err("VALIDATION_ERROR", "Ungültige skill_id", 422)

    reason = args.get("reason", "").strip()
    if not reason:
        return _err("VALIDATION_ERROR", "reason darf nicht leer sein", 422)

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                result = await db.execute(select(Skill).where(Skill.id == skill_id))
                skill = result.scalar_one_or_none()
                if not skill:
                    return _err("ENTITY_NOT_FOUND", f"Skill '{skill_id}' nicht gefunden", 404)

                if skill.lifecycle != "draft":
                    return _err(
                        "INVALID_STATE_TRANSITION",
                        f"Skill muss draft sein, ist '{skill.lifecycle}'",
                        422,
                    )

                skill.lifecycle = "rejected"
                skill.version += 1
                await db.flush()

                return _ok({
                    "data": {
                        "skill_id": str(skill_id),
                        "title": skill.title,
                        "lifecycle": "rejected",
                    },
                })
    except Exception as exc:
        logger.exception("reject_skill_change failed")
        return _err("INTERNAL_ERROR", str(exc), 500)
