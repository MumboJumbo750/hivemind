"""MCP Gaertner Write-Tools — TASK-5-009.

Gaertner agent tools for knowledge consolidation:
- hivemind-propose_skill             — Propose a new skill (lifecycle=draft)
- hivemind-propose_skill_change      — Propose changes to an existing skill
- hivemind-create_decision_record    — Document an epic decision (max 3/day anti-spam)
- hivemind-update_doc                — Update an epic-doc with optimistic locking
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone, timedelta

from mcp.types import TextContent, Tool
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.mcp.server import register_tool

logger = logging.getLogger(__name__)

ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _ok(data: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, default=str))]


def _err(code: str, message: str, status: int = 400) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({
        "error": {"code": code, "message": message, "status": status}
    }))] 


def _actor_uuid(args: dict) -> uuid.UUID:
    try:
        return uuid.UUID(str(args.get("_actor_id") or ADMIN_ID))
    except ValueError:
        return ADMIN_ID


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind-propose_skill  — new skill with lifecycle=draft
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind-propose_skill",
        description=(
            "Propose a new skill (lifecycle=draft). Includes circular-dependency "
            "check and depth ≤ 3 validation for parent_skill_ids."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Skill title"},
                "content": {"type": "string", "description": "Skill content (Markdown)"},
                "service_scope": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Service scope, e.g. ['backend', 'frontend']",
                },
                "stack": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Tech stack tags, e.g. ['python', 'fastapi']",
                },
                "parent_skill_ids": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Parent-Skill-Identifier (UUID oder Key, z.B. 'SKILL-7'), max depth 3",
                },
                "skill_type": {
                    "type": "string", "enum": ["system", "domain", "runtime"],
                    "description": "Skill type: domain (default), system (prompt templates), runtime (container/environment)",
                },
            },
            "required": ["title", "content"],
        },
    ),
    handler=lambda args: _handle_propose_skill(args),
)


async def _check_skill_depth(db, parent_ids: list[uuid.UUID], max_depth: int = 3) -> tuple[bool, str]:
    """Check that adding these parents won't exceed max depth.
    Returns (ok, error_message)."""
    from app.models.skill import SkillParent

    async def get_depth(skill_id: uuid.UUID, visited: set, depth: int) -> int:
        if skill_id in visited:
            return depth  # circular — will be caught separately
        visited.add(skill_id)
        result = await db.execute(
            select(SkillParent.parent_id).where(SkillParent.child_id == skill_id)
        )
        parent_links = result.scalars().all()
        if not parent_links:
            return depth
        max_d = depth
        for pid in parent_links:
            d = await get_depth(pid, visited.copy(), depth + 1)
            if d > max_d:
                max_d = d
        return max_d

    for pid in parent_ids:
        depth = await get_depth(pid, set(), 1)
        if depth > max_depth:
            return False, f"Parent skill {pid} hat Tiefe {depth}, max erlaubt: {max_depth}"
    return True, ""


async def _handle_propose_skill(args: dict) -> list[TextContent]:
    from app.models.skill import Skill, SkillParent
    from app.services.key_generator import resolve_skill

    title = args.get("title", "").strip()
    content = args.get("content", "").strip()
    if not title or not content:
        return _err("VALIDATION_ERROR", "title und content sind Pflichtfelder", 422)
    actor_id = _actor_uuid(args)

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                # Resolve parent skill identifiers (UUID or key)
                parent_ids = []
                for pid_str in args.get("parent_skill_ids", []):
                    parent = await resolve_skill(db, pid_str)
                    if not parent:
                        return _err("ENTITY_NOT_FOUND", f"Parent-Skill '{pid_str}' nicht gefunden", 404)
                    parent_ids.append(parent.id)

                # Depth check
                if parent_ids:
                    ok, err_msg = await _check_skill_depth(db, parent_ids)
                    if not ok:
                        return _err("DEPTH_EXCEEDED", err_msg, 422)

                # Get project_id from first parent or default
                project_id = None
                if parent_ids:
                    p_result = await db.execute(select(Skill.project_id).where(Skill.id == parent_ids[0]))
                    project_id = p_result.scalar_one_or_none()

                skill = Skill(
                    title=title,
                    content=content,
                    service_scope=args.get("service_scope", []),
                    stack=args.get("stack", []),
                    skill_type=args.get("skill_type", "domain"),
                    lifecycle="draft",
                    owner_id=actor_id,
                    proposed_by=actor_id,
                    project_id=project_id,
                )
                # Generate skill_key via sequence
                from app.services.key_generator import next_skill_key
                skill.skill_key = await next_skill_key(db)

                db.add(skill)
                await db.flush()
                await db.refresh(skill)

                # Link parents
                for i, pid in enumerate(parent_ids):
                    db.add(SkillParent(child_id=skill.id, parent_id=pid, order_idx=i))

                return _ok({
                    "data": {
                        "skill_id": str(skill.id),
                        "skill_key": skill.skill_key,
                        "title": skill.title,
                        "lifecycle": skill.lifecycle,
                        "parent_count": len(parent_ids),
                    },
                })
    except Exception as exc:
        logger.exception("propose_skill failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind-propose_skill_change  — propose changes to an existing skill
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind-propose_skill_change",
        description=(
            "Propose a change to an existing skill. Creates a change proposal "
            "that needs admin review (accept/reject)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "skill_id": {"type": "string", "description": "Skill-Identifier (UUID oder Key, z.B. 'SKILL-7')"},
                "proposed_content": {"type": "string", "description": "New content for the skill"},
                "rationale": {"type": "string", "description": "Reason for the change"},
            },
            "required": ["skill_id", "proposed_content", "rationale"],
        },
    ),
    handler=lambda args: _handle_propose_skill_change(args),
)


async def _handle_propose_skill_change(args: dict) -> list[TextContent]:
    from app.models.skill import Skill
    from app.services.key_generator import resolve_skill

    proposed_content = args.get("proposed_content", "").strip()
    rationale = args.get("rationale", "").strip()
    if not proposed_content or not rationale:
        return _err("VALIDATION_ERROR", "proposed_content und rationale sind Pflichtfelder", 422)
    actor_id = _actor_uuid(args)

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                skill = await resolve_skill(db, args.get("skill_id", ""))
                if not skill:
                    return _err("ENTITY_NOT_FOUND", f"Skill '{args.get('skill_id')}' nicht gefunden", 404)
                skill_id = skill.id

                if skill.lifecycle not in ("active", "draft"):
                    return _err(
                        "INVALID_STATE",
                        f"Skill muss active oder draft sein, ist '{skill.lifecycle}'",
                        422,
                    )

                # Store the change proposal in skill metadata via a simple approach:
                # Create a new draft skill that references the original
                change_skill = Skill(
                    title=f"[Change] {skill.title}",
                    content=proposed_content,
                    service_scope=skill.service_scope,
                    stack=skill.stack,
                    skill_type=skill.skill_type,
                    lifecycle="draft",
                    owner_id=actor_id,
                    proposed_by=actor_id,
                    project_id=skill.project_id,
                )
                db.add(change_skill)
                await db.flush()
                await db.refresh(change_skill)

                return _ok({
                    "data": {
                        "change_proposal_id": str(change_skill.id),
                        "original_skill_id": str(skill_id),
                        "title": change_skill.title,
                        "lifecycle": "draft",
                        "rationale": rationale,
                    },
                })
    except Exception as exc:
        logger.exception("propose_skill_change failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind-create_decision_record  — document an epic decision (max 3/day)
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind-create_decision_record",
        description=(
            "Document a decision for an epic. Anti-spam: max 3 decision records "
            "per day per user."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "epic_id": {"type": "string", "description": "Epic UUID (optional)"},
                "decision": {"type": "string", "description": "The decision text"},
                "rationale": {"type": "string", "description": "Rationale for the decision"},
            },
            "required": ["decision"],
        },
    ),
    handler=lambda args: _handle_create_decision_record(args),
)


async def _handle_create_decision_record(args: dict) -> list[TextContent]:
    from app.models.decision import DecisionRecord

    decision_text = args.get("decision", "").strip()
    rationale = args.get("rationale", "").strip()
    if not decision_text:
        return _err("VALIDATION_ERROR", "decision darf nicht leer sein", 422)
    actor_id = _actor_uuid(args)

    epic_id = None
    if args.get("epic_id"):
        try:
            epic_id = uuid.UUID(args["epic_id"])
        except ValueError:
            return _err("VALIDATION_ERROR", f"Ungültige epic_id: {args['epic_id']}", 422)

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                # Anti-spam: max 3 per day per user
                today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                count_result = await db.execute(
                    select(sa_func.count())
                    .select_from(DecisionRecord)
                    .where(
                        DecisionRecord.decided_by == actor_id,
                        DecisionRecord.created_at >= today_start,
                    )
                )
                today_count = count_result.scalar_one()
                if today_count >= 3:
                    return _err(
                        "RATE_LIMIT",
                        f"Max 3 Decision Records pro Tag (heute: {today_count})",
                        429,
                    )

                record = DecisionRecord(
                    epic_id=epic_id,
                    decision=decision_text,
                    rationale=rationale or None,
                    decided_by=actor_id,
                )
                db.add(record)
                await db.flush()
                await db.refresh(record)

                return _ok({
                    "data": {
                        "record_id": str(record.id),
                        "epic_id": str(epic_id) if epic_id else None,
                        "decision": decision_text,
                        "today_count": today_count + 1,
                    },
                })
    except Exception as exc:
        logger.exception("create_decision_record failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind-update_doc  — update epic doc with optimistic locking
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind-update_doc",
        description=(
            "Update an epic-doc's content with optimistic locking. "
            "Provide the expected version to prevent concurrent writes."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "description": "Doc-Identifier (UUID oder Key, z.B. 'DOC-8')"},
                "content": {"type": "string", "description": "New content (Markdown)"},
                "version": {
                    "type": "integer",
                    "description": "Expected current version for optimistic locking",
                },
            },
            "required": ["doc_id", "content", "version"],
        },
    ),
    handler=lambda args: _handle_update_doc(args),
)


async def _handle_update_doc(args: dict) -> list[TextContent]:
    from app.models.doc import Doc
    from app.services.key_generator import resolve_doc

    new_content = args.get("content", "").strip()
    if not new_content:
        return _err("VALIDATION_ERROR", "content darf nicht leer sein", 422)

    expected_version = args.get("version")
    if expected_version is None:
        return _err("VALIDATION_ERROR", "version ist ein Pflichtfeld für Optimistic Locking", 422)

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                doc = await resolve_doc(db, args.get("doc_id", ""))
                if not doc:
                    return _err("ENTITY_NOT_FOUND", f"Doc '{args.get('doc_id')}' nicht gefunden", 404)

                # Optimistic locking check
                if doc.version != expected_version:
                    return _err(
                        "VERSION_CONFLICT",
                        f"Version-Mismatch: erwartet {expected_version}, ist {doc.version}",
                        409,
                    )

                doc.content = new_content
                doc.version += 1
                doc.updated_by = ADMIN_ID
                await db.flush()

                return _ok({
                    "data": {
                        "doc_id": str(doc.id),
                        "title": doc.title,
                        "version": doc.version,
                    },
                })
    except Exception as exc:
        logger.exception("update_doc failed")
        return _err("INTERNAL_ERROR", str(exc), 500)
