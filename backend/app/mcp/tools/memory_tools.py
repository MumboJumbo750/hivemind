"""MCP Memory Ledger tools for long-running agent work."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from mcp.types import TextContent, Tool
from sqlalchemy import func, or_, select, text

from app.db import AsyncSessionLocal
from app.mcp.server import register_tool
from app.models.epic import Epic
from app.models.memory import MemoryEntry, MemoryFact, MemorySession, MemorySummary
from app.models.project import Project
from app.models.task import Task


VALID_SCOPES = {"global", "project", "epic", "task"}
ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
logger = logging.getLogger(__name__)


def _ok(data: Any) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"data": data}, default=str))]


def _err(message: str, code: str = "validation_error", status: int = 400) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"error": {"code": code, "message": message, "status": status}}))]


def _actor_uuid(args: dict) -> uuid.UUID:
    raw = args.get("_actor_id")
    if not raw:
        return ADMIN_ID
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        return ADMIN_ID


def _actor_role(args: dict) -> str:
    return str(args.get("_actor_role") or "admin")


def _estimate_tokens(text_value: str) -> int:
    return max(1, int(len((text_value or "").split()) * 1.3))


def _is_uuid(value: str | None) -> bool:
    if not value:
        return False
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False


async def _resolve_scope_id(db: Any, scope: str, raw_scope_id: str | None) -> uuid.UUID | None:
    if scope == "global":
        return None
    if not raw_scope_id:
        raise ValueError(f"scope_id ist für Scope '{scope}' erforderlich")

    if scope == "project":
        if not _is_uuid(raw_scope_id):
            raise ValueError("project scope_id muss eine UUID sein")
        row = await db.execute(select(Project.id).where(Project.id == uuid.UUID(raw_scope_id)))
        project_id = row.scalar_one_or_none()
        if project_id is None:
            raise ValueError(f"Project '{raw_scope_id}' nicht gefunden")
        return project_id

    if scope == "epic":
        stmt = select(Epic.id).where(Epic.id == uuid.UUID(raw_scope_id)) if _is_uuid(raw_scope_id) else select(Epic.id).where(Epic.epic_key == raw_scope_id)
        row = await db.execute(stmt)
        epic_id = row.scalar_one_or_none()
        if epic_id is None:
            raise ValueError(f"Epic '{raw_scope_id}' nicht gefunden")
        return epic_id

    if scope == "task":
        stmt = select(Task.id).where(Task.id == uuid.UUID(raw_scope_id)) if _is_uuid(raw_scope_id) else select(Task.id).where(Task.task_key == raw_scope_id)
        row = await db.execute(stmt)
        task_id = row.scalar_one_or_none()
        if task_id is None:
            raise ValueError(f"Task '{raw_scope_id}' nicht gefunden")
        return task_id

    raise ValueError(f"Ungültiger Scope '{scope}'")


def _scope_filters(model: Any, scope: str, scope_id: uuid.UUID | None) -> list[Any]:
    filters = [model.scope == scope]
    if scope == "global":
        filters.append(model.scope_id.is_(None))
    else:
        filters.append(model.scope_id == scope_id)
    return filters


async def _get_or_create_session(
    db: Any,
    *,
    actor_id: uuid.UUID,
    agent_role: str,
    scope: str,
    scope_id: uuid.UUID | None,
) -> MemorySession:
    result = await db.execute(
        select(MemorySession)
        .where(MemorySession.actor_id == actor_id)
        .where(MemorySession.agent_role == agent_role)
        .where(*_scope_filters(MemorySession, scope, scope_id))
        .where(MemorySession.ended_at.is_(None))
        .order_by(MemorySession.started_at.desc())
        .limit(1)
    )
    session = result.scalar_one_or_none()
    if session is not None:
        return session

    session = MemorySession(
        actor_id=actor_id,
        agent_role=agent_role,
        scope=scope,
        scope_id=scope_id,
        started_at=datetime.now(UTC),
        entry_count=0,
        compacted=False,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return session


def _entry_embedding_text(content: str, tags: list[str]) -> str:
    tags_text = " ".join(tags)
    return f"{content}\n{tags_text}".strip()


def _summary_embedding_text(summary: str, open_questions: list[str]) -> str:
    return f"{summary}\n{' '.join(open_questions)}".strip()


def _normalize_tags(raw_tags: Any) -> list[str]:
    if not raw_tags:
        return []
    if isinstance(raw_tags, str):
        raw_tags = [part.strip() for part in raw_tags.split(",") if part.strip()]
    if not isinstance(raw_tags, list):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for tag in raw_tags:
        value = str(tag).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _text_match_score(query: str, *parts: str) -> float:
    normalized_query = " ".join(query.lower().split())
    searchable = " ".join(str(part or "") for part in parts).lower().strip()
    if not normalized_query or not searchable:
        return 0.0
    if searchable == normalized_query:
        return 1.0
    if searchable.startswith(normalized_query):
        return 0.97
    if normalized_query in searchable:
        return 0.9
    query_terms = [term for term in normalized_query.split() if term]
    if query_terms and all(term in searchable for term in query_terms):
        return 0.8
    return 0.6


def _set_rank_score(payload: dict[str, Any], score: float) -> None:
    payload["_score"] = max(float(payload.get("_score") or 0.0), float(score))


async def _safe_semantic_rows(
    db: Any,
    *,
    table: str,
    query: str,
    limit: int,
    candidate_ids: list[str] | None,
) -> list[dict[str, Any]]:
    from app.services.embedding_service import get_embedding_service

    try:
        return await get_embedding_service().search_similar(
            db,
            table,
            query,
            limit=limit,
            candidate_ids=candidate_ids,
        )
    except Exception as exc:
        logger.warning("Semantic memory search degraded for %s: %s", table, exc)
        return []


register_tool(
    Tool(
        name="hivemind-save_memory",
        description="Persist a raw memory entry for a long-running task/session. Use for working memory, observations, blockers, or intermediate findings.",
        inputSchema={
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["global", "project", "epic", "task"]},
                "scope_id": {"type": "string", "description": "UUID or key for project/epic/task scope"},
                "content": {"type": "string", "description": "Raw observation or working-memory note"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags, e.g. ['debug', 'skill-candidate']"},
            },
            "required": ["scope", "content"],
        },
    ),
    handler=lambda args: _handle_save_memory(args),
)


async def _handle_save_memory(args: dict) -> list[TextContent]:
    from app.services.embedding_service import EmbeddingPriority, get_embedding_service

    scope = str(args.get("scope") or "").strip().lower()
    content = str(args.get("content") or "").strip()
    tags = _normalize_tags(args.get("tags"))
    if scope not in VALID_SCOPES:
        return _err("scope muss global|project|epic|task sein")
    if not content:
        return _err("content ist ein Pflichtfeld")

    actor_id = _actor_uuid(args)
    actor_role = _actor_role(args)

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                scope_id = await _resolve_scope_id(db, scope, args.get("scope_id"))
                session = await _get_or_create_session(
                    db,
                    actor_id=actor_id,
                    agent_role=actor_role,
                    scope=scope,
                    scope_id=scope_id,
                )
                entry = MemoryEntry(
                    actor_id=actor_id,
                    agent_role=actor_role,
                    scope=scope,
                    scope_id=scope_id,
                    session_id=session.id,
                    content=content,
                    tags=tags,
                )
                db.add(entry)
                session.entry_count += 1
                await db.flush()
                await db.refresh(entry)
                await get_embedding_service().enqueue(
                    "memory_entries",
                    str(entry.id),
                    _entry_embedding_text(content, tags),
                    priority=EmbeddingPriority.ON_WRITE,
                )

                return _ok({
                    "entry_id": str(entry.id),
                    "session_id": str(session.id),
                    "scope": scope,
                    "scope_id": str(scope_id) if scope_id else None,
                    "tags": tags,
                    "created_at": str(entry.created_at),
                })
    except ValueError as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(str(exc), code="internal_error", status=500)


register_tool(
    Tool(
        name="hivemind-extract_facts",
        description="Extract structured facts from raw memory entries. Use this to preserve exact entities and relationships before summarisation.",
        inputSchema={
            "type": "object",
            "properties": {
                "entry_ids": {"type": "array", "items": {"type": "string"}, "description": "Memory entry UUIDs"},
                "facts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "entry_id": {"type": "string", "description": "Optional explicit source entry id when multiple entry_ids are used"},
                            "entity": {"type": "string"},
                            "key": {"type": "string"},
                            "value": {"type": "string"},
                            "confidence": {"type": "number"},
                        },
                        "required": ["entity", "key", "value"],
                    },
                },
            },
            "required": ["entry_ids", "facts"],
        },
    ),
    handler=lambda args: _handle_extract_facts(args),
)


async def _handle_extract_facts(args: dict) -> list[TextContent]:
    raw_entry_ids = args.get("entry_ids") or []
    fact_defs = args.get("facts") or []
    if not raw_entry_ids or not isinstance(raw_entry_ids, list):
        return _err("entry_ids darf nicht leer sein")
    if not fact_defs or not isinstance(fact_defs, list):
        return _err("facts darf nicht leer sein")

    try:
        entry_ids = [uuid.UUID(str(raw_id)) for raw_id in raw_entry_ids]
    except ValueError:
        return _err("entry_ids müssen gültige UUIDs sein")

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                entries = (
                    await db.execute(select(MemoryEntry).where(MemoryEntry.id.in_(entry_ids)))
                ).scalars().all()
                entry_map = {entry.id: entry for entry in entries}
                if len(entry_map) != len(set(entry_ids)):
                    return _err("mindestens ein entry_id wurde nicht gefunden", code="not_found", status=404)

                created_ids: list[str] = []
                for fact_def in fact_defs:
                    target_entry_id = fact_def.get("entry_id")
                    if target_entry_id:
                        try:
                            entry_id = uuid.UUID(str(target_entry_id))
                        except ValueError:
                            return _err("fact.entry_id muss eine gültige UUID sein")
                    elif len(entry_ids) == 1:
                        entry_id = entry_ids[0]
                    else:
                        return _err("Bei mehreren entry_ids muss jedes Fact ein entry_id Feld angeben")

                    if entry_id not in entry_map:
                        return _err("fact.entry_id verweist auf keinen geladenen Memory Entry", code="not_found", status=404)

                    fact = MemoryFact(
                        entry_id=entry_id,
                        entity=str(fact_def.get("entity") or "").strip(),
                        key=str(fact_def.get("key") or "").strip(),
                        value=str(fact_def.get("value") or "").strip(),
                        confidence=float(fact_def.get("confidence") or 1.0),
                    )
                    if not fact.entity or not fact.key or not fact.value:
                        return _err("entity, key und value sind für jeden Fact Pflichtfelder")
                    db.add(fact)
                    await db.flush()
                    created_ids.append(str(fact.id))

                return _ok({"fact_ids": created_ids, "count": len(created_ids)})
    except Exception as exc:
        return _err(str(exc), code="internal_error", status=500)


register_tool(
    Tool(
        name="hivemind-compact_memories",
        description="Create a compact summary from raw memory entries. Marks source entries as covered, but keeps them append-only for audit/history.",
        inputSchema={
            "type": "object",
            "properties": {
                "entry_ids": {"type": "array", "items": {"type": "string"}},
                "summary": {"type": "string"},
                "open_questions": {"type": "array", "items": {"type": "string"}},
                "graduated": {"type": "boolean", "default": False},
            },
            "required": ["entry_ids", "summary"],
        },
    ),
    handler=lambda args: _handle_compact_memories(args),
)


async def _handle_compact_memories(args: dict) -> list[TextContent]:
    from app.services.embedding_service import EmbeddingPriority, get_embedding_service

    raw_entry_ids = args.get("entry_ids") or []
    summary_text = str(args.get("summary") or "").strip()
    open_questions = [str(item).strip() for item in (args.get("open_questions") or []) if str(item).strip()]
    graduated = bool(args.get("graduated") or False)
    if not raw_entry_ids or not isinstance(raw_entry_ids, list):
        return _err("entry_ids darf nicht leer sein")
    if not summary_text:
        return _err("summary ist ein Pflichtfeld")

    try:
        entry_ids = [uuid.UUID(str(raw_id)) for raw_id in raw_entry_ids]
    except ValueError:
        return _err("entry_ids müssen gültige UUIDs sein")

    actor_id = _actor_uuid(args)
    actor_role = _actor_role(args)

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                entries = (
                    await db.execute(select(MemoryEntry).where(MemoryEntry.id.in_(entry_ids)).order_by(MemoryEntry.created_at.asc()))
                ).scalars().all()
                if len(entries) != len(set(entry_ids)):
                    return _err("mindestens ein entry_id wurde nicht gefunden", code="not_found", status=404)

                first = entries[0]
                for entry in entries[1:]:
                    if entry.scope != first.scope or entry.scope_id != first.scope_id:
                        return _err("Alle entry_ids müssen zum selben Scope gehören")

                fact_rows = (
                    await db.execute(select(MemoryFact.id).where(MemoryFact.entry_id.in_(entry_ids)))
                ).scalars().all()
                summary = MemorySummary(
                    actor_id=actor_id,
                    agent_role=actor_role,
                    scope=first.scope,
                    scope_id=first.scope_id,
                    session_id=first.session_id,
                    content=summary_text,
                    source_entry_ids=[entry.id for entry in entries],
                    source_fact_ids=list(fact_rows),
                    source_count=len(entries),
                    open_questions=open_questions,
                    graduated=graduated,
                    graduated_to=None,
                )
                db.add(summary)
                await db.flush()
                await db.refresh(summary)

                for entry in entries:
                    entry.covered_by = summary.id

                session = await db.get(MemorySession, first.session_id)
                if session is not None:
                    session.compacted = True

                await get_embedding_service().enqueue(
                    "memory_summaries",
                    str(summary.id),
                    _summary_embedding_text(summary_text, open_questions),
                    priority=EmbeddingPriority.ON_WRITE,
                )

                return _ok({
                    "summary_id": str(summary.id),
                    "scope": summary.scope,
                    "scope_id": str(summary.scope_id) if summary.scope_id else None,
                    "source_count": summary.source_count,
                    "open_questions": open_questions,
                    "graduated": summary.graduated,
                })
    except Exception as exc:
        return _err(str(exc), code="internal_error", status=500)


register_tool(
    Tool(
        name="hivemind-graduate_memory",
        description="Mark a memory summary as graduated into a longer-lived knowledge target such as wiki, skill, or doc.",
        inputSchema={
            "type": "object",
            "properties": {
                "summary_id": {"type": "string"},
                "target": {"type": "string", "enum": ["wiki", "skill", "doc"]},
                "target_id": {"type": "string"},
            },
            "required": ["summary_id", "target", "target_id"],
        },
    ),
    handler=lambda args: _handle_graduate_memory(args),
)


async def _handle_graduate_memory(args: dict) -> list[TextContent]:
    try:
        summary_id = uuid.UUID(str(args.get("summary_id") or ""))
    except ValueError:
        return _err("summary_id muss eine gültige UUID sein")

    target = str(args.get("target") or "").strip().lower()
    target_id = str(args.get("target_id") or "").strip()
    if target not in {"wiki", "skill", "doc"}:
        return _err("target muss wiki|skill|doc sein")
    if not target_id:
        return _err("target_id ist ein Pflichtfeld")

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                summary = await db.get(MemorySummary, summary_id)
                if summary is None:
                    return _err("Memory Summary nicht gefunden", code="not_found", status=404)
                summary.graduated = True
                summary.graduated_to = {
                    "target": target,
                    "target_id": target_id,
                    "graduated_at": datetime.now(UTC).isoformat(),
                }
                return _ok({
                    "summary_id": str(summary.id),
                    "graduated": summary.graduated,
                    "graduated_to": summary.graduated_to,
                })
    except Exception as exc:
        return _err(str(exc), code="internal_error", status=500)


register_tool(
    Tool(
        name="hivemind-get_memory_context",
        description="Load the most relevant working-memory context for a scope. Best for resuming a long-running or multi-session task.",
        inputSchema={
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["global", "project", "epic", "task"]},
                "scope_id": {"type": "string"},
                "max_tokens": {"type": "integer", "default": 2000},
            },
            "required": ["scope"],
        },
    ),
    handler=lambda args: _handle_get_memory_context(args),
)


async def _handle_get_memory_context(args: dict) -> list[TextContent]:
    scope = str(args.get("scope") or "").strip().lower()
    if scope not in VALID_SCOPES:
        return _err("scope muss global|project|epic|task sein")
    max_tokens = max(200, min(int(args.get("max_tokens") or 2000), 8000))

    try:
        async with AsyncSessionLocal() as db:
            scope_id = await _resolve_scope_id(db, scope, args.get("scope_id"))
            summary_rows = (
                await db.execute(
                    select(MemorySummary)
                    .where(*_scope_filters(MemorySummary, scope, scope_id))
                    .where(MemorySummary.graduated.is_(False))
                    .order_by(MemorySummary.created_at.desc())
                    .limit(8)
                )
            ).scalars().all()
            fact_rows = (
                await db.execute(
                    select(MemoryFact, MemoryEntry)
                    .join(MemoryEntry, MemoryFact.entry_id == MemoryEntry.id)
                    .where(*_scope_filters(MemoryEntry, scope, scope_id))
                    .order_by(MemoryFact.created_at.desc())
                    .limit(40)
                )
            ).all()
            uncovered_rows = (
                await db.execute(
                    select(MemoryEntry)
                    .where(*_scope_filters(MemoryEntry, scope, scope_id))
                    .where(MemoryEntry.covered_by.is_(None))
                    .order_by(MemoryEntry.created_at.desc())
                    .limit(5)
                )
            ).scalars().all()

            token_used = 0
            summaries: list[dict[str, Any]] = []
            for row in summary_rows:
                payload = {
                    "id": str(row.id),
                    "content": row.content,
                    "open_questions": row.open_questions or [],
                    "created_at": str(row.created_at),
                }
                item_tokens = _estimate_tokens(row.content + " " + " ".join(row.open_questions or []))
                if summaries and token_used + item_tokens > max_tokens:
                    break
                token_used += item_tokens
                summaries.append(payload)

            facts: list[dict[str, Any]] = []
            for fact, entry in fact_rows:
                payload = {
                    "id": str(fact.id),
                    "entry_id": str(fact.entry_id),
                    "entity": fact.entity,
                    "key": fact.key,
                    "value": fact.value,
                    "confidence": fact.confidence,
                    "source_tags": entry.tags or [],
                }
                item_tokens = _estimate_tokens(f"{fact.entity} {fact.key} {fact.value}")
                if facts and token_used + item_tokens > max_tokens:
                    break
                token_used += item_tokens
                facts.append(payload)

            open_questions: list[str] = []
            for summary in summaries:
                for question in summary.get("open_questions", []):
                    if question not in open_questions:
                        open_questions.append(question)

            return _ok({
                "scope": scope,
                "scope_id": str(scope_id) if scope_id else None,
                "max_tokens": max_tokens,
                "token_estimate": token_used,
                "summaries": summaries,
                "facts": facts,
                "open_questions": open_questions,
                "integrity_warnings": {
                    "uncovered_entries": len(uncovered_rows),
                },
                "uncovered_entries_preview": [
                    {
                        "id": str(entry.id),
                        "content": entry.content,
                        "tags": entry.tags or [],
                        "created_at": str(entry.created_at),
                    }
                    for entry in uncovered_rows
                ],
            })
    except ValueError as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(str(exc), code="internal_error", status=500)


register_tool(
    Tool(
        name="hivemind-search_memories",
        description="Search memory ledger content across raw entries, facts, and summaries. Supports text search now and semantic enhancement via embeddings when available later.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "scope": {"type": "string", "enum": ["global", "project", "epic", "task"]},
                "scope_id": {"type": "string"},
                "level": {"type": "string", "enum": ["L0", "L1", "L2", "all"], "default": "all"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["query"],
        },
    ),
    handler=lambda args: _handle_search_memories(args),
)


async def _handle_search_memories(args: dict) -> list[TextContent]:
    query = str(args.get("query") or "").strip()
    if not query:
        return _err("query ist ein Pflichtfeld")
    scope = str(args.get("scope") or "").strip().lower() if args.get("scope") else None
    level = str(args.get("level") or "all").strip()
    tags = _normalize_tags(args.get("tags"))
    limit = max(1, min(int(args.get("limit") or 20), 50))
    if scope and scope not in VALID_SCOPES:
        return _err("scope muss global|project|epic|task sein")
    if level not in {"L0", "L1", "L2", "all"}:
        return _err("level muss L0|L1|L2|all sein")

    try:
        async with AsyncSessionLocal() as db:
            scope_id = await _resolve_scope_id(db, scope, args.get("scope_id")) if scope else None
            pattern = f"%{query}%"
            results: dict[tuple[str, str], dict[str, Any]] = {}

            entry_candidate_ids: list[str] | None = None
            summary_candidate_ids: list[str] | None = None
            if scope or tags:
                entry_candidate_query = select(MemoryEntry.id)
                if scope:
                    entry_candidate_query = entry_candidate_query.where(*_scope_filters(MemoryEntry, scope, scope_id))
                if tags:
                    entry_candidate_query = entry_candidate_query.where(MemoryEntry.tags.overlap(tags))
                entry_candidate_ids = [
                    str(item)
                    for item in (
                        await db.execute(entry_candidate_query)
                    ).scalars().all()
                ]
            if scope:
                summary_candidate_ids = [
                    str(item)
                    for item in (
                        await db.execute(select(MemorySummary.id).where(*_scope_filters(MemorySummary, scope, scope_id)))
                    ).scalars().all()
                ]

            if level in {"L0", "all"}:
                entry_query = select(MemoryEntry).where(MemoryEntry.content.ilike(pattern))
                if scope:
                    entry_query = entry_query.where(*_scope_filters(MemoryEntry, scope, scope_id))
                if tags:
                    entry_query = entry_query.where(MemoryEntry.tags.overlap(tags))
                entry_rows = (await db.execute(entry_query.order_by(MemoryEntry.created_at.desc()).limit(limit))).scalars().all()
                for entry in entry_rows:
                    results[("L0", str(entry.id))] = {
                        "level": "L0",
                        "id": str(entry.id),
                        "scope": entry.scope,
                        "scope_id": str(entry.scope_id) if entry.scope_id else None,
                        "content": entry.content,
                        "tags": entry.tags or [],
                        "created_at": str(entry.created_at),
                        "search_mode": "text",
                    }
                    _set_rank_score(results[("L0", str(entry.id))], _text_match_score(query, entry.content, " ".join(entry.tags or [])))

                semantic_rows = await _safe_semantic_rows(
                    db,
                    table="memory_entries",
                    query=query,
                    limit=limit,
                    candidate_ids=entry_candidate_ids,
                )
                if semantic_rows:
                    semantic_ids = [uuid.UUID(row["id"]) for row in semantic_rows]
                    semantic_entries = (
                        await db.execute(select(MemoryEntry).where(MemoryEntry.id.in_(semantic_ids)))
                    ).scalars().all()
                    semantic_map = {str(entry.id): entry for entry in semantic_entries}
                    for row in semantic_rows:
                        entry = semantic_map.get(row["id"])
                        if entry is None:
                            continue
                        key = ("L0", row["id"])
                        payload = results.get(key, {
                            "level": "L0",
                            "id": str(entry.id),
                            "scope": entry.scope,
                            "scope_id": str(entry.scope_id) if entry.scope_id else None,
                            "content": entry.content,
                            "tags": entry.tags or [],
                            "created_at": str(entry.created_at),
                            "search_mode": "semantic",
                        })
                        payload["similarity"] = row["similarity"]
                        payload["search_mode"] = "hybrid" if key in results else "semantic"
                        score = float(row["similarity"] or 0.0)
                        if payload["search_mode"] == "hybrid":
                            score += 1.0
                        _set_rank_score(payload, score)
                        results[key] = payload

            if level in {"L1", "all"}:
                fact_query = (
                    select(MemoryFact, MemoryEntry)
                    .join(MemoryEntry, MemoryFact.entry_id == MemoryEntry.id)
                    .where(or_(MemoryFact.entity.ilike(pattern), MemoryFact.key.ilike(pattern), MemoryFact.value.ilike(pattern)))
                )
                if scope:
                    fact_query = fact_query.where(*_scope_filters(MemoryEntry, scope, scope_id))
                if tags:
                    fact_query = fact_query.where(MemoryEntry.tags.overlap(tags))
                fact_rows = (await db.execute(fact_query.order_by(MemoryFact.created_at.desc()).limit(limit))).all()
                for fact, entry in fact_rows:
                    results[("L1", str(fact.id))] = {
                        "level": "L1",
                        "id": str(fact.id),
                        "entry_id": str(fact.entry_id),
                        "entity": fact.entity,
                        "key": fact.key,
                        "value": fact.value,
                        "confidence": fact.confidence,
                        "source_tags": entry.tags or [],
                        "created_at": str(fact.created_at),
                        "search_mode": "text",
                    }
                    _set_rank_score(results[("L1", str(fact.id))], _text_match_score(query, fact.entity, fact.key, fact.value))

            if level in {"L2", "all"}:
                summary_query = select(MemorySummary).where(
                    or_(
                        MemorySummary.content.ilike(pattern),
                        func.array_to_string(MemorySummary.open_questions, " ").ilike(pattern),
                    )
                )
                if scope:
                    summary_query = summary_query.where(*_scope_filters(MemorySummary, scope, scope_id))
                summary_rows = (await db.execute(summary_query.order_by(MemorySummary.created_at.desc()).limit(limit))).scalars().all()
                for summary in summary_rows:
                    results[("L2", str(summary.id))] = {
                        "level": "L2",
                        "id": str(summary.id),
                        "scope": summary.scope,
                        "scope_id": str(summary.scope_id) if summary.scope_id else None,
                        "content": summary.content,
                        "open_questions": summary.open_questions or [],
                        "graduated": summary.graduated,
                        "created_at": str(summary.created_at),
                        "search_mode": "text",
                    }
                    _set_rank_score(results[("L2", str(summary.id))], _text_match_score(query, summary.content, " ".join(summary.open_questions or [])))

                semantic_rows = await _safe_semantic_rows(
                    db,
                    table="memory_summaries",
                    query=query,
                    limit=limit,
                    candidate_ids=summary_candidate_ids,
                )
                if semantic_rows:
                    semantic_ids = [uuid.UUID(row["id"]) for row in semantic_rows]
                    semantic_summaries = (
                        await db.execute(select(MemorySummary).where(MemorySummary.id.in_(semantic_ids)))
                    ).scalars().all()
                    semantic_map = {str(summary.id): summary for summary in semantic_summaries}
                    for row in semantic_rows:
                        summary = semantic_map.get(row["id"])
                        if summary is None:
                            continue
                        key = ("L2", row["id"])
                        payload = results.get(key, {
                            "level": "L2",
                            "id": str(summary.id),
                            "scope": summary.scope,
                            "scope_id": str(summary.scope_id) if summary.scope_id else None,
                            "content": summary.content,
                            "open_questions": summary.open_questions or [],
                            "graduated": summary.graduated,
                            "created_at": str(summary.created_at),
                            "search_mode": "semantic",
                        })
                        payload["similarity"] = row["similarity"]
                        payload["search_mode"] = "hybrid" if key in results else "semantic"
                        score = float(row["similarity"] or 0.0)
                        if payload["search_mode"] == "hybrid":
                            score += 1.0
                        _set_rank_score(payload, score)
                        results[key] = payload

            ordered_results = sorted(
                results.values(),
                key=lambda item: (float(item.get("_score") or 0.0), float(item.get("similarity") or 0.0), item.get("created_at", "")),
                reverse=True,
            )
            final_results = [
                {key: value for key, value in item.items() if key != "_score"}
                for item in ordered_results[:limit]
            ]
            return _ok({"results": final_results, "count": len(final_results)})
    except ValueError as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(str(exc), code="internal_error", status=500)


register_tool(
    Tool(
        name="hivemind-get_uncovered_entries",
        description="Return raw memory entries that are not yet covered by any summary.",
        inputSchema={
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["global", "project", "epic", "task"]},
                "scope_id": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["scope"],
        },
    ),
    handler=lambda args: _handle_get_uncovered_entries(args),
)


async def _handle_get_uncovered_entries(args: dict) -> list[TextContent]:
    scope = str(args.get("scope") or "").strip().lower()
    if scope not in VALID_SCOPES:
        return _err("scope muss global|project|epic|task sein")
    limit = max(1, min(int(args.get("limit") or 20), 50))

    try:
        async with AsyncSessionLocal() as db:
            scope_id = await _resolve_scope_id(db, scope, args.get("scope_id"))
            rows = (
                await db.execute(
                    select(MemoryEntry)
                    .where(*_scope_filters(MemoryEntry, scope, scope_id))
                    .where(MemoryEntry.covered_by.is_(None))
                    .order_by(MemoryEntry.created_at.desc())
                    .limit(limit)
                )
            ).scalars().all()
            return _ok({
                "entries": [
                    {
                        "id": str(entry.id),
                        "content": entry.content,
                        "tags": entry.tags or [],
                        "created_at": str(entry.created_at),
                    }
                    for entry in rows
                ],
                "count": len(rows),
            })
    except ValueError as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(str(exc), code="internal_error", status=500)


register_tool(
    Tool(
        name="hivemind-get_open_questions",
        description="Return all open questions from active memory summaries in a scope.",
        inputSchema={
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["global", "project", "epic", "task"]},
                "scope_id": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["scope"],
        },
    ),
    handler=lambda args: _handle_get_open_questions(args),
)


async def _handle_get_open_questions(args: dict) -> list[TextContent]:
    scope = str(args.get("scope") or "").strip().lower()
    if scope not in VALID_SCOPES:
        return _err("scope muss global|project|epic|task sein")
    limit = max(1, min(int(args.get("limit") or 20), 50))

    try:
        async with AsyncSessionLocal() as db:
            scope_id = await _resolve_scope_id(db, scope, args.get("scope_id"))
            rows = (
                await db.execute(
                    select(MemorySummary)
                    .where(*_scope_filters(MemorySummary, scope, scope_id))
                    .where(func.cardinality(MemorySummary.open_questions) > 0)
                    .where(MemorySummary.graduated.is_(False))
                    .order_by(MemorySummary.created_at.desc())
                    .limit(limit)
                )
            ).scalars().all()

            questions = []
            for row in rows:
                for question in row.open_questions or []:
                    questions.append({
                        "summary_id": str(row.id),
                        "question": question,
                        "created_at": str(row.created_at),
                    })
            return _ok({"questions": questions[:limit], "count": min(len(questions), limit)})
    except ValueError as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(str(exc), code="internal_error", status=500)