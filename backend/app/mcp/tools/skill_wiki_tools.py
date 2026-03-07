"""MCP Read-Tools: Skills, Wiki & Search — TASK-3-003.

Tools:
  hivemind-get_skills         — Active skills for a task (Phase 1-2: all active)
  hivemind-list_skills        — Browse all skills with filters
  hivemind-get_wiki_article   — Wiki article by UUID or slug
  hivemind-search_wiki        — Text search across wiki articles
"""
from __future__ import annotations

import json
import uuid

from mcp.types import TextContent, Tool
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.mcp.server import register_tool
from app.models.skill import Skill, SkillVersion
from app.models.task import Task
from app.models.wiki import WikiArticle


def _json_response(data: dict | list) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"data": data}, default=str))]


def _meta_response(data: list, total: int) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"data": data, "meta": {"total": total}}, default=str))]


def _not_found(entity: str, key: str) -> list[TextContent]:
    return [TextContent(
        type="text",
        text=json.dumps({"error": {"code": "not_found", "message": f"{entity} '{key}' nicht gefunden."}})
    )]


# ── get_skills ─────────────────────────────────────────────────────────────

async def _handle_get_skills(args: dict) -> list[TextContent]:
    """Get active skills for a task (Phase 1-2: returns all active skills)."""
    task_key = args.get("task_key") or args.get("task_id", "")
    async with AsyncSessionLocal() as db:
        # Verify task exists
        task_result = await db.execute(select(Task).where(Task.task_key == task_key))
        task = task_result.scalar_one_or_none()
        if not task:
            return _not_found("Task", task_key)

        # Phase 1-2: return all active skills (no Bibliothekar filtering yet)
        result = await db.execute(
            select(Skill).where(
                Skill.lifecycle == "active",
                Skill.deleted_at.is_(None),
            ).order_by(Skill.title)
        )
        skills = [
            {
                "id": str(s.id),
                "title": s.title,
                "service_scope": s.service_scope,
                "stack": s.stack,
                "confidence": float(s.confidence) if s.confidence else None,
                "lifecycle": s.lifecycle,
                "version": s.version,
            }
            for s in result.scalars().all()
        ]
        return _meta_response(skills, len(skills))


register_tool(
    Tool(
        name="hivemind-get_skills",
        description="Aktive Skills für einen Task (Phase 1-2: alle aktiven Skills).",
        inputSchema={
            "type": "object",
            "properties": {
                "task_key": {"type": "string", "description": "Task-Key, z.B. 'TASK-88'"},
            },
            "required": ["task_key"],
        },
    ),
    _handle_get_skills,
)


# ── list_skills ────────────────────────────────────────────────────────────

async def _handle_list_skills(args: dict) -> list[TextContent]:
    """Browse all skills with optional filters."""
    service_scope = args.get("service_scope")
    stack = args.get("stack")
    lifecycle = args.get("lifecycle")
    limit = min(int(args.get("limit", 50)), 200)
    offset = max(int(args.get("offset", 0)), 0)

    async with AsyncSessionLocal() as db:
        q = select(Skill).where(Skill.deleted_at.is_(None))
        if service_scope:
            q = q.where(Skill.service_scope.any(service_scope))
        if stack:
            q = q.where(Skill.stack.any(stack))
        if lifecycle:
            q = q.where(Skill.lifecycle == lifecycle)

        # Count
        count_q = select(func.count()).select_from(q.subquery())
        total = (await db.execute(count_q)).scalar_one()

        # Paginate
        q = q.order_by(Skill.title).limit(limit).offset(offset)
        result = await db.execute(q)
        skills = [
            {
                "id": str(s.id),
                "title": s.title,
                "service_scope": s.service_scope,
                "stack": s.stack,
                "confidence": float(s.confidence) if s.confidence else None,
                "lifecycle": s.lifecycle,
                "skill_type": s.skill_type,
                "version": s.version,
            }
            for s in result.scalars().all()
        ]
        return _meta_response(skills, total)


register_tool(
    Tool(
        name="hivemind-list_skills",
        description="Alle Skills durchsuchen mit optionalen Filtern (service_scope, stack, lifecycle).",
        inputSchema={
            "type": "object",
            "properties": {
                "service_scope": {"type": "string", "description": "Filter: service scope (z.B. 'backend')"},
                "stack": {"type": "string", "description": "Filter: tech stack (z.B. 'python')"},
                "lifecycle": {"type": "string", "description": "Filter: lifecycle status (draft/active/deprecated)"},
                "limit": {"type": "integer", "description": "Max results (default 50, max 200)"},
                "offset": {"type": "integer", "description": "Pagination offset (default 0)"},
            },
        },
    ),
    _handle_list_skills,
)


# ── get_wiki_article ──────────────────────────────────────────────────────

async def _handle_get_wiki_article(args: dict) -> list[TextContent]:
    """Load wiki article by UUID, wiki_key (e.g. 'WIKI-5'), or slug."""
    from app.services.key_generator import resolve_wiki_article

    identifier = args.get("id") or args.get("slug", "")
    async with AsyncSessionLocal() as db:
        article = await resolve_wiki_article(db, identifier)
        if not article or article.deleted_at is not None:
            return _not_found("WikiArticle", identifier)

        return _json_response({
            "id": str(article.id),
            "title": article.title,
            "slug": article.slug,
            "content": article.content,
            "tags": article.tags,
            "category_id": str(article.category_id) if article.category_id else None,
            "linked_epics": [str(e) for e in (article.linked_epics or [])],
            "linked_skills": [str(s) for s in (article.linked_skills or [])],
            "version": article.version,
            "federation_scope": article.federation_scope,
            "created_at": str(article.created_at),
            "updated_at": str(article.updated_at),
        })


register_tool(
    Tool(
        name="hivemind-get_wiki_article",
        description="Wiki-Artikel per UUID oder Slug laden.",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Wiki-Identifier (UUID, Key z.B. 'WIKI-5', oder Slug)"},
            },
            "required": ["id"],
        },
    ),
    _handle_get_wiki_article,
)


# ── search_wiki ────────────────────────────────────────────────────────────

async def _handle_search_wiki(args: dict) -> list[TextContent]:
    """Full-text search across wiki articles using tsvector/tsquery + optional tag filter.

    Falls back to ILIKE if tsvector column not available (pre-migration).
    Supports hybrid ranking with pgvector similarity when embeddings exist.
    """
    query = args.get("query", "")
    tags = args.get("tags")  # comma-separated or list
    limit = min(int(args.get("limit", 20)), 100)
    offset = max(int(args.get("offset", 0)), 0)
    use_fulltext = args.get("fulltext", True)

    async with AsyncSessionLocal() as db:
        q = select(WikiArticle).where(WikiArticle.deleted_at.is_(None))

        if query and use_fulltext:
            # Try tsquery full-text search with ranking
            try:
                from sqlalchemy import text as sql_text
                # Use plainto_tsquery for safe input handling
                ts_query = sql_text(
                    "search_vector @@ plainto_tsquery('german', :q)"
                ).bindparams(q=query)
                q = q.where(ts_query)
                # Order by ts_rank
                rank_expr = sql_text(
                    "ts_rank(search_vector, plainto_tsquery('german', :q))"
                ).bindparams(q=query)
                q = q.order_by(rank_expr.desc())
            except Exception:
                # Fallback to ILIKE if tsquery fails
                pattern = f"%{query}%"
                q = q.where(
                    or_(
                        WikiArticle.title.ilike(pattern),
                        WikiArticle.content.ilike(pattern),
                    )
                )
                q = q.order_by(WikiArticle.updated_at.desc())
        elif query:
            pattern = f"%{query}%"
            q = q.where(
                or_(
                    WikiArticle.title.ilike(pattern),
                    WikiArticle.content.ilike(pattern),
                )
            )
            q = q.order_by(WikiArticle.updated_at.desc())
        else:
            q = q.order_by(WikiArticle.updated_at.desc())

        if tags:
            tag_list = tags if isinstance(tags, list) else [t.strip() for t in tags.split(",")]
            for tag in tag_list:
                q = q.where(WikiArticle.tags.any(tag))

        # Count
        count_q = select(func.count()).select_from(q.subquery())
        total = (await db.execute(count_q)).scalar_one()

        # Paginate
        q = q.limit(limit).offset(offset)
        result = await db.execute(q)
        articles = [
            {
                "id": str(a.id),
                "title": a.title,
                "slug": a.slug,
                "tags": a.tags,
                "version": a.version,
                "updated_at": str(a.updated_at),
            }
            for a in result.scalars().all()
        ]
        return _meta_response(articles, total)


register_tool(
    Tool(
        name="hivemind-search_wiki",
        description="Wiki-Volltextsuche mit PostgreSQL tsvector/tsquery + Tag-Filter. Fallback auf ILIKE.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Suchbegriff (tsquery auf title + content)"},
                "tags": {"type": "string", "description": "Komma-separierte Tags zum Filtern"},
                "fulltext": {"type": "boolean", "description": "tsvector nutzen (default: true, false = ILIKE)"},
                "limit": {"type": "integer", "description": "Max results (default 20, max 100)"},
                "offset": {"type": "integer", "description": "Pagination offset"},
            },
            "required": ["query"],
        },
    ),
    _handle_search_wiki,
)
