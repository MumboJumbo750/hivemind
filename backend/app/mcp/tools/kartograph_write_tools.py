"""MCP Kartograph Write-Tools — TASK-5-010.

Kartograph agent tools for wiki, epic-docs, and guard proposals:
- hivemind/create_wiki_article   — Create wiki article + set explored_at on code_nodes
- hivemind/update_wiki_article   — Update wiki article with versioning
- hivemind/create_epic_doc       — Create an epic-doc linked to an epic
- hivemind/link_wiki_to_epic     — Link a wiki article to an epic
- hivemind/propose_guard         — Propose a new guard (lifecycle=draft)
- hivemind/propose_guard_change  — Propose changes to an existing guard
- hivemind/submit_guard_proposal — Submit guard proposal for review (draft → pending_merge)
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone

from mcp.types import TextContent, Tool
from sqlalchemy import select, update
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


def _slugify(title: str) -> str:
    """Generate a URL-safe slug from a title."""
    slug = title.lower().strip()
    slug = re.sub(r'[äÄ]', 'ae', slug)
    slug = re.sub(r'[öÖ]', 'oe', slug)
    slug = re.sub(r'[üÜ]', 'ue', slug)
    slug = re.sub(r'[ß]', 'ss', slug)
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug or "untitled"


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/create_wiki_article  — create article + explored_at on code_nodes
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/create_wiki_article",
        description=(
            "Create a new wiki article. Optionally sets explored_at on provided "
            "code_node paths. Creates initial WikiVersion."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Article title"},
                "content": {"type": "string", "description": "Markdown content"},
                "tags": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Tags for categorization",
                },
                "category_id": {"type": "string", "description": "Wiki category UUID (optional)"},
                "code_node_paths": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Code node paths to mark as explored",
                },
            },
            "required": ["title", "content"],
        },
    ),
    handler=lambda args: _handle_create_wiki_article(args),
)


async def _handle_create_wiki_article(args: dict) -> list[TextContent]:
    from app.models.wiki import WikiArticle, WikiVersion
    from app.models.code_node import CodeNode

    title = args.get("title", "").strip()
    content = args.get("content", "").strip()
    if not title or not content:
        return _err("VALIDATION_ERROR", "title und content sind Pflichtfelder", 422)

    slug = _slugify(title)
    tags = args.get("tags", [])
    category_id = None
    if args.get("category_id"):
        try:
            category_id = uuid.UUID(args["category_id"])
        except ValueError:
            return _err("VALIDATION_ERROR", f"Ungültige category_id", 422)

    code_node_paths = args.get("code_node_paths", [])

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                # Check slug uniqueness — append suffix if needed
                existing = await db.execute(
                    select(WikiArticle).where(WikiArticle.slug == slug)
                )
                if existing.scalar_one_or_none():
                    slug = f"{slug}-{uuid.uuid4().hex[:6]}"

                article = WikiArticle(
                    title=title,
                    slug=slug,
                    content=content,
                    tags=tags,
                    category_id=category_id,
                    author_id=ADMIN_ID,
                    version=1,
                )
                db.add(article)
                await db.flush()
                await db.refresh(article)

                # Create initial version
                version = WikiVersion(
                    article_id=article.id,
                    version=1,
                    content=content,
                    changed_by=ADMIN_ID,
                )
                db.add(version)

                # Mark code_nodes as explored
                explored_count = 0
                for path in code_node_paths:
                    cn_result = await db.execute(
                        select(CodeNode).where(CodeNode.path == path)
                    )
                    cn = cn_result.scalar_one_or_none()
                    if cn:
                        cn.explored_at = datetime.now(timezone.utc)
                        cn.explored_by = ADMIN_ID
                        explored_count += 1

                await db.flush()

                return _ok({
                    "data": {
                        "article_id": str(article.id),
                        "slug": slug,
                        "title": title,
                        "version": 1,
                        "explored_nodes": explored_count,
                    },
                })
    except Exception as exc:
        logger.exception("create_wiki_article failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/update_wiki_article  — versioned update
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/update_wiki_article",
        description=(
            "Update an existing wiki article. Creates a new WikiVersion. "
            "Uses optimistic locking via expected version."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "article_id": {"type": "string", "description": "WikiArticle UUID"},
                "content": {"type": "string", "description": "New Markdown content"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Updated tags"},
                "version": {"type": "integer", "description": "Expected current version"},
            },
            "required": ["article_id", "content", "version"],
        },
    ),
    handler=lambda args: _handle_update_wiki_article(args),
)


async def _handle_update_wiki_article(args: dict) -> list[TextContent]:
    from app.models.wiki import WikiArticle, WikiVersion

    try:
        article_id = uuid.UUID(args["article_id"])
    except (KeyError, ValueError) as exc:
        return _err("VALIDATION_ERROR", f"Ungültige article_id: {exc}", 422)

    new_content = args.get("content", "").strip()
    if not new_content:
        return _err("VALIDATION_ERROR", "content darf nicht leer sein", 422)

    expected_version = args.get("version")
    if expected_version is None:
        return _err("VALIDATION_ERROR", "version ist Pflicht für Optimistic Locking", 422)

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                result = await db.execute(
                    select(WikiArticle).where(WikiArticle.id == article_id)
                )
                article = result.scalar_one_or_none()
                if not article:
                    return _err("ENTITY_NOT_FOUND", f"WikiArticle '{article_id}' nicht gefunden", 404)

                if article.version != expected_version:
                    return _err(
                        "VERSION_CONFLICT",
                        f"Version-Mismatch: erwartet {expected_version}, ist {article.version}",
                        409,
                    )

                new_version = article.version + 1
                article.content = new_content
                article.version = new_version
                if args.get("tags") is not None:
                    article.tags = args["tags"]

                # Create version record
                wiki_ver = WikiVersion(
                    article_id=article.id,
                    version=new_version,
                    content=new_content,
                    changed_by=ADMIN_ID,
                )
                db.add(wiki_ver)
                await db.flush()

                return _ok({
                    "data": {
                        "article_id": str(article.id),
                        "title": article.title,
                        "version": new_version,
                    },
                })
    except Exception as exc:
        logger.exception("update_wiki_article failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/create_epic_doc  — create an epic-linked doc
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/create_epic_doc",
        description="Create a new doc linked to an epic.",
        inputSchema={
            "type": "object",
            "properties": {
                "epic_key": {"type": "string", "description": "Epic key (e.g. 'EPIC-PHASE-5')"},
                "title": {"type": "string"},
                "content": {"type": "string", "description": "Markdown content"},
            },
            "required": ["epic_key", "title", "content"],
        },
    ),
    handler=lambda args: _handle_create_epic_doc(args),
)


async def _handle_create_epic_doc(args: dict) -> list[TextContent]:
    from app.models.doc import Doc
    from app.models.epic import Epic

    epic_key = args.get("epic_key", "")
    title = args.get("title", "").strip()
    content = args.get("content", "").strip()
    if not title or not content:
        return _err("VALIDATION_ERROR", "title und content sind Pflichtfelder", 422)

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                result = await db.execute(select(Epic).where(Epic.epic_key == epic_key))
                epic = result.scalar_one_or_none()
                if not epic:
                    return _err("ENTITY_NOT_FOUND", f"Epic '{epic_key}' nicht gefunden", 404)

                doc = Doc(
                    title=title,
                    content=content,
                    epic_id=epic.id,
                    updated_by=ADMIN_ID,
                )
                db.add(doc)
                await db.flush()
                await db.refresh(doc)

                return _ok({
                    "data": {
                        "doc_id": str(doc.id),
                        "epic_key": epic_key,
                        "title": title,
                        "version": doc.version,
                    },
                })
    except Exception as exc:
        logger.exception("create_epic_doc failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/link_wiki_to_epic  — link wiki article to epic
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/link_wiki_to_epic",
        description="Link a wiki article to an epic (appends to linked_epics array).",
        inputSchema={
            "type": "object",
            "properties": {
                "article_id": {"type": "string", "description": "WikiArticle UUID"},
                "epic_key": {"type": "string", "description": "Epic key"},
            },
            "required": ["article_id", "epic_key"],
        },
    ),
    handler=lambda args: _handle_link_wiki_to_epic(args),
)


async def _handle_link_wiki_to_epic(args: dict) -> list[TextContent]:
    from app.models.wiki import WikiArticle
    from app.models.epic import Epic

    try:
        article_id = uuid.UUID(args["article_id"])
    except (KeyError, ValueError):
        return _err("VALIDATION_ERROR", "Ungültige article_id", 422)

    epic_key = args.get("epic_key", "")

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                # Verify article
                a_result = await db.execute(
                    select(WikiArticle).where(WikiArticle.id == article_id)
                )
                article = a_result.scalar_one_or_none()
                if not article:
                    return _err("ENTITY_NOT_FOUND", f"WikiArticle '{article_id}' nicht gefunden", 404)

                # Verify epic
                e_result = await db.execute(select(Epic).where(Epic.epic_key == epic_key))
                epic = e_result.scalar_one_or_none()
                if not epic:
                    return _err("ENTITY_NOT_FOUND", f"Epic '{epic_key}' nicht gefunden", 404)

                # Append epic_id to linked_epics if not already present
                current = article.linked_epics or []
                if epic.id not in current:
                    article.linked_epics = current + [epic.id]
                    await db.flush()

                return _ok({
                    "data": {
                        "article_id": str(article_id),
                        "epic_key": epic_key,
                        "linked_epics_count": len(article.linked_epics or []),
                    },
                })
    except Exception as exc:
        logger.exception("link_wiki_to_epic failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/propose_guard  — propose new guard (lifecycle=draft)
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/propose_guard",
        description=(
            "Propose a new guard (lifecycle=draft). Kartograph discovers guards from "
            "the repository and proposes them for admin review."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Guard title"},
                "description": {"type": "string"},
                "type": {
                    "type": "string", "enum": ["executable", "manual"],
                    "description": "Guard type (default: executable)",
                },
                "command": {"type": "string", "description": "Command to execute (for executable guards)"},
                "condition": {"type": "string", "description": "Manual check condition text"},
                "skippable": {"type": "boolean", "description": "Whether the guard can be skipped (default: true)"},
                "project_id": {"type": "string", "description": "Project UUID (optional)"},
                "skill_id": {"type": "string", "description": "Skill UUID (optional)"},
            },
            "required": ["title"],
        },
    ),
    handler=lambda args: _handle_propose_guard(args),
)


async def _handle_propose_guard(args: dict) -> list[TextContent]:
    from app.models.guard import Guard

    title = args.get("title", "").strip()
    if not title:
        return _err("VALIDATION_ERROR", "title darf nicht leer sein", 422)

    project_id = None
    if args.get("project_id"):
        try:
            project_id = uuid.UUID(args["project_id"])
        except ValueError:
            return _err("VALIDATION_ERROR", "Ungültige project_id", 422)

    skill_id = None
    if args.get("skill_id"):
        try:
            skill_id = uuid.UUID(args["skill_id"])
        except ValueError:
            return _err("VALIDATION_ERROR", "Ungültige skill_id", 422)

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                guard = Guard(
                    title=title,
                    description=args.get("description"),
                    type=args.get("type", "executable"),
                    command=args.get("command"),
                    condition=args.get("condition"),
                    skippable=args.get("skippable", True),
                    lifecycle="draft",
                    project_id=project_id,
                    skill_id=skill_id,
                    created_by=ADMIN_ID,
                )
                db.add(guard)
                await db.flush()
                await db.refresh(guard)

                return _ok({
                    "data": {
                        "guard_id": str(guard.id),
                        "title": guard.title,
                        "lifecycle": "draft",
                        "type": guard.type,
                    },
                })
    except Exception as exc:
        logger.exception("propose_guard failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/propose_guard_change  — propose changes to an existing guard
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/propose_guard_change",
        description="Propose changes to an existing guard for admin review.",
        inputSchema={
            "type": "object",
            "properties": {
                "guard_id": {"type": "string", "description": "UUID of the guard to change"},
                "proposed_command": {"type": "string", "description": "New command"},
                "proposed_condition": {"type": "string", "description": "New condition"},
                "rationale": {"type": "string", "description": "Reason for the change"},
            },
            "required": ["guard_id", "rationale"],
        },
    ),
    handler=lambda args: _handle_propose_guard_change(args),
)


async def _handle_propose_guard_change(args: dict) -> list[TextContent]:
    from app.models.guard import Guard

    try:
        guard_id = uuid.UUID(args["guard_id"])
    except (KeyError, ValueError):
        return _err("VALIDATION_ERROR", "Ungültige guard_id", 422)

    rationale = args.get("rationale", "").strip()
    if not rationale:
        return _err("VALIDATION_ERROR", "rationale darf nicht leer sein", 422)

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                result = await db.execute(select(Guard).where(Guard.id == guard_id))
                guard = result.scalar_one_or_none()
                if not guard:
                    return _err("ENTITY_NOT_FOUND", f"Guard '{guard_id}' nicht gefunden", 404)

                # Create a draft copy with proposed changes
                new_guard = Guard(
                    title=f"[Change] {guard.title}",
                    description=f"Change-Proposal: {rationale}\n\nOriginal: {guard.id}",
                    type=guard.type,
                    command=args.get("proposed_command", guard.command),
                    condition=args.get("proposed_condition", guard.condition),
                    skippable=guard.skippable,
                    lifecycle="draft",
                    project_id=guard.project_id,
                    skill_id=guard.skill_id,
                    created_by=ADMIN_ID,
                )
                db.add(new_guard)
                await db.flush()
                await db.refresh(new_guard)

                return _ok({
                    "data": {
                        "change_proposal_id": str(new_guard.id),
                        "original_guard_id": str(guard_id),
                        "title": new_guard.title,
                        "lifecycle": "draft",
                    },
                })
    except Exception as exc:
        logger.exception("propose_guard_change failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/submit_guard_proposal  — draft → pending_merge
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/submit_guard_proposal",
        description="Submit a draft guard for admin review (draft → pending_merge).",
        inputSchema={
            "type": "object",
            "properties": {
                "guard_id": {"type": "string", "description": "UUID of the guard to submit"},
            },
            "required": ["guard_id"],
        },
    ),
    handler=lambda args: _handle_submit_guard_proposal(args),
)


async def _handle_submit_guard_proposal(args: dict) -> list[TextContent]:
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

                if guard.lifecycle != "draft":
                    return _err(
                        "INVALID_STATE_TRANSITION",
                        f"Guard muss draft sein, ist '{guard.lifecycle}'",
                        422,
                    )

                guard.lifecycle = "pending_merge"
                guard.version += 1
                await db.flush()

                return _ok({
                    "data": {
                        "guard_id": str(guard.id),
                        "title": guard.title,
                        "lifecycle": "pending_merge",
                        "version": guard.version,
                    },
                })
    except Exception as exc:
        logger.exception("submit_guard_proposal failed")
        return _err("INTERNAL_ERROR", str(exc), 500)
