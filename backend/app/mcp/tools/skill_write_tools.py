"""MCP Skill Write-Tools — TASK-4-006.

MCP tools for the Skill Lifecycle workflow:
- hivemind-submit_skill_proposal  (draft → pending_merge)
- hivemind-merge_skill            (pending_merge → active)
- hivemind-reject_skill           (pending_merge → rejected)
"""
from __future__ import annotations

import difflib
import json
import logging
import time
import uuid

from mcp.types import TextContent, Tool

from app.db import AsyncSessionLocal
from app.mcp.server import register_tool
from app.services.audit import write_audit

logger = logging.getLogger(__name__)

ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _ok(data: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"data": data}, default=str))]


def _err(code: str, message: str, status: int = 400) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({
        "error": {"code": code, "message": message, "status": status}
    }))]


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind-submit_skill_proposal
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind-submit_skill_proposal",
        description=(
            "Submit a draft skill for review (draft → pending_merge). "
            "Only the skill owner or admin may submit."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "skill_id": {
                    "type": "string",
                    "description": "Skill-Identifier (UUID oder Key, z.B. 'SKILL-7')",
                },
            },
            "required": ["skill_id"],
        },
    ),
    handler=lambda args: _handle_submit_skill_proposal(args),
)


async def _handle_submit_skill_proposal(args: dict) -> list[TextContent]:
    t0 = time.perf_counter()

    from app.models.skill import Skill
    from app.schemas.auth import CurrentActor
    from app.services.key_generator import resolve_skill
    from app.services.skill_service import SkillService

    async with AsyncSessionLocal() as session:
        svc = SkillService(session)
        actor = CurrentActor(id=ADMIN_ID, username="solo", role="admin")

        # Resolve skill by UUID or skill_key
        skill = await resolve_skill(session, args.get("skill_id", ""))
        if not skill:
            return _err("not_found", f"Skill '{args.get('skill_id')}' nicht gefunden", 404)
        skill_id = skill.id

        # Check ownership (non-admin must own the skill)
        if actor.role != "admin" and skill.owner_id != actor.id:
            return _err("forbidden", "Nur der Ersteller oder Admin darf diesen Skill einreichen", 403)

        # Enforce state machine
        from app.services.skill_service import SKILL_TRANSITIONS
        allowed = SKILL_TRANSITIONS.get(skill.lifecycle, set())
        if "pending_merge" not in allowed:
            return _err(
                "INVALID_STATE_TRANSITION",
                f"Transition '{skill.lifecycle}' → 'pending_merge' nicht erlaubt. "
                f"Erlaubt: {sorted(allowed)}",
                422,
            )

        try:
            skill = await svc.submit(skill_id, actor)
            await session.commit()
        except Exception as exc:
            return _err("internal_error", str(exc))

        duration = int((time.perf_counter() - t0) * 1000)
        await write_audit(
            tool_name="hivemind-submit_skill_proposal",
            actor_id=actor.id,
            actor_role=actor.role,
            input_payload=args,
            output_payload={"skill_id": str(skill.id), "lifecycle": skill.lifecycle},
            target_id=str(skill.id),
            duration_ms=duration,
        )

        return _ok({
            "skill_id": str(skill.id),
            "title": skill.title,
            "lifecycle": skill.lifecycle,
            "version": skill.version,
        })


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind-merge_skill
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind-merge_skill",
        description=(
            "Merge a pending skill proposal (pending_merge → active). "
            "Admin only. Creates a skill_version entry with diff_from_previous."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "skill_id": {
                    "type": "string",
                    "description": "Skill-Identifier (UUID oder Key, z.B. 'SKILL-7')",
                },
                "version": {
                    "type": "integer",
                    "description": "Current version for optimistic locking",
                },
            },
            "required": ["skill_id"],
        },
    ),
    handler=lambda args: _handle_merge_skill(args),
)


async def _handle_merge_skill(args: dict) -> list[TextContent]:
    t0 = time.perf_counter()

    from sqlalchemy import select

    from app.models.skill import Skill, SkillVersion
    from app.schemas.auth import CurrentActor
    from app.services.key_generator import resolve_skill
    from app.services.locking import check_version
    from app.services.skill_service import SKILL_TRANSITIONS, SkillService

    async with AsyncSessionLocal() as session:
        svc = SkillService(session)
        actor = CurrentActor(id=ADMIN_ID, username="solo", role="admin")

        # Resolve skill by UUID or skill_key
        skill = await resolve_skill(session, args.get("skill_id", ""))
        if not skill:
            return _err("not_found", f"Skill '{args.get('skill_id')}' nicht gefunden", 404)
        skill_id = skill.id

        # RBAC: admin only
        if actor.role != "admin":
            return _err("forbidden", "Nur Admin darf Skills mergen", 403)

        # Optimistic locking (optional parameter)
        if "version" in args:
            try:
                check_version(skill, args["version"])
            except Exception:
                return _err(
                    "VERSION_CONFLICT",
                    f"Version-Mismatch: erwartet {args['version']}, ist {skill.version}",
                    409,
                )

        # Enforce state machine
        allowed = SKILL_TRANSITIONS.get(skill.lifecycle, set())
        if "active" not in allowed:
            return _err(
                "INVALID_STATE_TRANSITION",
                f"Transition '{skill.lifecycle}' → 'active' nicht erlaubt. "
                f"Erlaubt: {sorted(allowed)}",
                422,
            )

        # Get previous version content for diff
        prev_version_result = await session.execute(
            select(SkillVersion)
            .where(SkillVersion.skill_id == skill_id)
            .order_by(SkillVersion.version.desc())
            .limit(1)
        )
        prev_sv = prev_version_result.scalar_one_or_none()
        prev_content = prev_sv.content if prev_sv else ""

        try:
            skill = await svc.merge(skill_id, actor)
            await session.flush()

            # Compute diff and update the newly created version entry
            diff_text = _compute_diff(prev_content, skill.content, skill.title)
            latest_result = await session.execute(
                select(SkillVersion)
                .where(SkillVersion.skill_id == skill_id)
                .order_by(SkillVersion.version.desc())
                .limit(1)
            )
            latest_sv = latest_result.scalar_one_or_none()
            if latest_sv and diff_text:
                latest_sv.diff_from_previous = diff_text

            await session.commit()
        except Exception as exc:
            return _err("internal_error", str(exc))

        duration = int((time.perf_counter() - t0) * 1000)
        await write_audit(
            tool_name="hivemind-merge_skill",
            actor_id=actor.id,
            actor_role=actor.role,
            input_payload=args,
            output_payload={
                "skill_id": str(skill.id),
                "lifecycle": skill.lifecycle,
                "version": skill.version,
            },
            target_id=str(skill.id),
            duration_ms=duration,
        )

        return _ok({
            "skill_id": str(skill.id),
            "title": skill.title,
            "lifecycle": skill.lifecycle,
            "version": skill.version,
        })


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind-reject_skill
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind-reject_skill",
        description=(
            "Reject a pending skill proposal (pending_merge → rejected). "
            "Admin only. Sends SkillRejectedEvent with rationale to proposed_by."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "skill_id": {
                    "type": "string",
                    "description": "Skill-Identifier (UUID oder Key, z.B. 'SKILL-7')",
                },
                "rationale": {
                    "type": "string",
                    "description": "Reason for rejection (required)",
                },
                "version": {
                    "type": "integer",
                    "description": "Current version for optimistic locking",
                },
            },
            "required": ["skill_id", "rationale"],
        },
    ),
    handler=lambda args: _handle_reject_skill(args),
)


async def _handle_reject_skill(args: dict) -> list[TextContent]:
    t0 = time.perf_counter()

    rationale = args.get("rationale", "").strip()
    if not rationale:
        return _err("validation_error", "rationale ist Pflichtfeld")

    from app.models.skill import Skill
    from app.schemas.auth import CurrentActor
    from app.schemas.skill import SkillReject
    from app.services.key_generator import resolve_skill
    from app.services.locking import check_version
    from app.services.skill_service import SKILL_TRANSITIONS, SkillService

    async with AsyncSessionLocal() as session:
        svc = SkillService(session)
        actor = CurrentActor(id=ADMIN_ID, username="solo", role="admin")

        # Resolve skill by UUID or skill_key
        skill = await resolve_skill(session, args.get("skill_id", ""))
        if not skill:
            return _err("not_found", f"Skill '{args.get('skill_id')}' nicht gefunden", 404)
        skill_id = skill.id

        # RBAC: admin only
        if actor.role != "admin":
            return _err("forbidden", "Nur Admin darf Skills ablehnen", 403)

        # Optimistic locking (optional)
        if "version" in args:
            try:
                check_version(skill, args["version"])
            except Exception:
                return _err(
                    "VERSION_CONFLICT",
                    f"Version-Mismatch: erwartet {args['version']}, ist {skill.version}",
                    409,
                )

        # Enforce state machine
        allowed = SKILL_TRANSITIONS.get(skill.lifecycle, set())
        if "rejected" not in allowed:
            return _err(
                "INVALID_STATE_TRANSITION",
                f"Transition '{skill.lifecycle}' → 'rejected' nicht erlaubt. "
                f"Erlaubt: {sorted(allowed)}",
                422,
            )

        try:
            reject_data = SkillReject(rationale=rationale)
            skill = await svc.reject(skill_id, reject_data, actor)
            await session.commit()
        except Exception as exc:
            return _err("internal_error", str(exc))

        duration = int((time.perf_counter() - t0) * 1000)
        await write_audit(
            tool_name="hivemind-reject_skill",
            actor_id=actor.id,
            actor_role=actor.role,
            input_payload=args,
            output_payload={
                "skill_id": str(skill.id),
                "lifecycle": skill.lifecycle,
                "rejection_rationale": skill.rejection_rationale,
            },
            target_id=str(skill.id),
            duration_ms=duration,
        )

        return _ok({
            "skill_id": str(skill.id),
            "title": skill.title,
            "lifecycle": skill.lifecycle,
            "rejection_rationale": skill.rejection_rationale,
            "version": skill.version,
        })


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _compute_diff(old_content: str, new_content: str, title: str) -> str:
    """Compute a unified diff between old and new content."""
    old_lines = (old_content or "").splitlines(keepends=True)
    new_lines = (new_content or "").splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"{title} (previous)",
        tofile=f"{title} (merged)",
    )
    return "".join(diff)
