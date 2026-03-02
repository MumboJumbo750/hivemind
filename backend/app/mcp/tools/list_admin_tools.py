"""MCP Read-Tools: Lists & Admin — TASK-3-004.

List-Tools (developer role):
  hivemind/list_projects       — Paginated project list
  hivemind/list_epics          — Epics with state filter
  hivemind/list_tasks          — Tasks with multi-filter
  hivemind/get_project_members — Project members with roles
  hivemind/list_peers          — Federation peer nodes

Admin-only Tools:
  hivemind/get_triage          — Unrouted/escalated/dead events
  hivemind/get_audit_log       — MCP invocations with filters
"""
from __future__ import annotations

import json
import uuid

from mcp.types import TextContent, Tool
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.mcp.server import register_tool
from app.models.audit import McpInvocation
from app.models.epic import Epic
from app.models.federation import Node
from app.models.project import Project, ProjectMember
from app.models.sync import SyncOutbox
from app.models.task import Task
from app.models.user import User


def _json_response(data: dict | list) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"data": data}, default=str))]


def _meta_response(data: list, total: int) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"data": data, "meta": {"total": total}}, default=str))]


def _error(code: str, message: str) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"error": {"code": code, "message": message}}))]


# ── list_projects ──────────────────────────────────────────────────────────

async def _handle_list_projects(args: dict) -> list[TextContent]:
    limit = min(int(args.get("limit", 50)), 200)
    offset = max(int(args.get("offset", 0)), 0)
    async with AsyncSessionLocal() as db:
        count_q = select(func.count()).select_from(Project)
        total = (await db.execute(count_q)).scalar_one()
        result = await db.execute(
            select(Project).order_by(Project.created_at.desc()).limit(limit).offset(offset)
        )
        projects = [
            {
                "id": str(p.id),
                "name": p.name,
                "description": p.description,
                "created_at": str(p.created_at),
            }
            for p in result.scalars().all()
        ]
        return _meta_response(projects, total)


register_tool(
    Tool(
        name="hivemind/list_projects",
        description="Paginierte Liste aller Projekte.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max results (default 50)"},
                "offset": {"type": "integer", "description": "Pagination offset"},
            },
        },
    ),
    _handle_list_projects,
)


# ── list_epics ─────────────────────────────────────────────────────────────

async def _handle_list_epics(args: dict) -> list[TextContent]:
    project_id_raw = args.get("project_id", "")
    state = args.get("state")
    limit = min(int(args.get("limit", 50)), 200)
    offset = max(int(args.get("offset", 0)), 0)

    async with AsyncSessionLocal() as db:
        q = select(Epic)
        if project_id_raw:
            try:
                q = q.where(Epic.project_id == uuid.UUID(project_id_raw))
            except ValueError:
                return _error("invalid_param", f"Invalid project_id: {project_id_raw}")
        if state:
            q = q.where(Epic.state == state)

        count_q = select(func.count()).select_from(q.subquery())
        total = (await db.execute(count_q)).scalar_one()

        q = q.order_by(Epic.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(q)
        epics = [
            {
                "id": str(e.id),
                "epic_key": e.epic_key,
                "title": e.title,
                "state": e.state,
                "priority": e.priority,
                "version": e.version,
                "created_at": str(e.created_at),
            }
            for e in result.scalars().all()
        ]
        return _meta_response(epics, total)


register_tool(
    Tool(
        name="hivemind/list_epics",
        description="Epics auflisten mit optionalem State- und Projekt-Filter.",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project UUID filter"},
                "state": {"type": "string", "description": "State filter (incoming/scoped/in_progress/done/...)"},
                "limit": {"type": "integer"},
                "offset": {"type": "integer"},
            },
        },
    ),
    _handle_list_epics,
)


# ── list_tasks ─────────────────────────────────────────────────────────────

async def _handle_list_tasks(args: dict) -> list[TextContent]:
    epic_id_raw = args.get("epic_id")
    state = args.get("state")
    assigned_to_raw = args.get("assigned_to")
    limit = min(int(args.get("limit", 50)), 200)
    offset = max(int(args.get("offset", 0)), 0)

    async with AsyncSessionLocal() as db:
        q = select(Task)
        if epic_id_raw:
            try:
                q = q.where(Task.epic_id == uuid.UUID(epic_id_raw))
            except ValueError:
                return _error("invalid_param", f"Invalid epic_id: {epic_id_raw}")
        if state:
            q = q.where(Task.state == state)
        if assigned_to_raw:
            try:
                q = q.where(Task.assigned_to == uuid.UUID(assigned_to_raw))
            except ValueError:
                pass

        count_q = select(func.count()).select_from(q.subquery())
        total = (await db.execute(count_q)).scalar_one()

        q = q.order_by(Task.created_at.asc()).limit(limit).offset(offset)
        result = await db.execute(q)
        tasks = [
            {
                "id": str(t.id),
                "task_key": t.task_key,
                "epic_id": str(t.epic_id),
                "title": t.title,
                "state": t.state,
                "assigned_to": str(t.assigned_to) if t.assigned_to else None,
                "version": t.version,
                "created_at": str(t.created_at),
            }
            for t in result.scalars().all()
        ]
        return _meta_response(tasks, total)


register_tool(
    Tool(
        name="hivemind/list_tasks",
        description="Tasks auflisten mit Filtern (epic_id, state, assigned_to).",
        inputSchema={
            "type": "object",
            "properties": {
                "epic_id": {"type": "string", "description": "Epic UUID filter"},
                "state": {"type": "string", "description": "State filter"},
                "assigned_to": {"type": "string", "description": "User UUID filter"},
                "limit": {"type": "integer"},
                "offset": {"type": "integer"},
            },
        },
    ),
    _handle_list_tasks,
)


# ── get_project_members ───────────────────────────────────────────────────

async def _handle_get_project_members(args: dict) -> list[TextContent]:
    project_id_raw = args.get("project_id", "")
    try:
        project_id = uuid.UUID(project_id_raw)
    except (ValueError, AttributeError):
        return _error("invalid_param", f"Invalid project_id: {project_id_raw}")

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ProjectMember, User)
            .join(User, ProjectMember.user_id == User.id)
            .where(ProjectMember.project_id == project_id)
        )
        members = [
            {
                "user_id": str(pm.user_id),
                "username": u.username,
                "display_name": u.display_name,
                "role": pm.role,
            }
            for pm, u in result.all()
        ]
        return _json_response(members)


register_tool(
    Tool(
        name="hivemind/get_project_members",
        description="Projekt-Mitglieder mit Rollen.",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project UUID"},
            },
            "required": ["project_id"],
        },
    ),
    _handle_get_project_members,
)


# ── list_peers ─────────────────────────────────────────────────────────────

async def _handle_list_peers(args: dict) -> list[TextContent]:
    state = args.get("state")
    async with AsyncSessionLocal() as db:
        q = select(Node).where(Node.deleted_at.is_(None))
        if state:
            q = q.where(Node.status == state)
        result = await db.execute(q.order_by(Node.created_at.desc()))
        peers = [
            {
                "id": str(n.id),
                "node_name": n.node_name,
                "node_url": n.node_url,
                "status": n.status,
                "last_seen": str(n.last_seen) if n.last_seen else None,
                "created_at": str(n.created_at),
            }
            for n in result.scalars().all()
        ]
        return _meta_response(peers, len(peers))


register_tool(
    Tool(
        name="hivemind/list_peers",
        description="Federation Peer-Nodes auflisten.",
        inputSchema={
            "type": "object",
            "properties": {
                "state": {"type": "string", "description": "Status filter (active/inactive)"},
            },
        },
    ),
    _handle_list_peers,
)


# ── get_triage (admin) ────────────────────────────────────────────────────

async def _handle_get_triage(args: dict) -> list[TextContent]:
    """Admin-only: show unrouted/escalated/dead events from sync_outbox."""
    state_filter = args.get("state", "unrouted")
    limit = min(int(args.get("limit", 50)), 200)
    offset = max(int(args.get("offset", 0)), 0)

    async with AsyncSessionLocal() as db:
        q = select(SyncOutbox).where(SyncOutbox.direction == "inbound")

        if state_filter == "all":
            pass
        elif state_filter == "dead_letter":
            q = q.where(SyncOutbox.state == "dead_letter")
        elif state_filter == "escalated":
            q = q.where(SyncOutbox.routing_state == "escalated")
        else:  # unrouted (default)
            q = q.where(SyncOutbox.routing_state == "unrouted")

        count_q = select(func.count()).select_from(q.subquery())
        total = (await db.execute(count_q)).scalar_one()

        q = q.order_by(SyncOutbox.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(q)
        items = [
            {
                "id": str(o.id),
                "system": o.system,
                "entity_type": o.entity_type,
                "entity_id": o.entity_id,
                "routing_state": o.routing_state,
                "state": o.state,
                "payload": o.payload,
                "created_at": str(o.created_at),
            }
            for o in result.scalars().all()
        ]
        return _meta_response(items, total)


register_tool(
    Tool(
        name="hivemind/get_triage",
        description="Triage: Unrouted/Escalated/Dead Events anzeigen (Admin only).",
        inputSchema={
            "type": "object",
            "properties": {
                "state": {"type": "string", "description": "Filter: unrouted|escalated|dead_letter|all", "enum": ["unrouted", "escalated", "dead_letter", "all"]},
                "limit": {"type": "integer"},
                "offset": {"type": "integer"},
            },
        },
    ),
    _handle_get_triage,
)


# ── get_audit_log (admin) ─────────────────────────────────────────────────

async def _handle_get_audit_log(args: dict) -> list[TextContent]:
    """Admin-only: paginated audit log with filters."""
    epic_id_raw = args.get("epic_id")
    actor_id_raw = args.get("actor_id")
    tool_name = args.get("tool_name")
    limit = min(int(args.get("limit", 50)), 200)
    offset = max(int(args.get("offset", 0)), 0)

    async with AsyncSessionLocal() as db:
        q = select(McpInvocation)
        if epic_id_raw:
            try:
                q = q.where(McpInvocation.epic_id == uuid.UUID(epic_id_raw))
            except ValueError:
                pass
        if actor_id_raw:
            try:
                q = q.where(McpInvocation.actor_id == uuid.UUID(actor_id_raw))
            except ValueError:
                pass
        if tool_name:
            q = q.where(McpInvocation.tool_name == tool_name)

        count_q = select(func.count()).select_from(q.subquery())
        total = (await db.execute(count_q)).scalar_one()

        q = q.order_by(McpInvocation.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(q)
        entries = [
            {
                "id": str(a.id),
                "tool_name": a.tool_name,
                "actor_id": str(a.actor_id),
                "actor_role": a.actor_role,
                "epic_id": str(a.epic_id) if a.epic_id else None,
                "target_id": a.target_id,
                "input_payload": a.input_payload,
                "output_payload": a.output_payload,
                "duration_ms": a.duration_ms,
                "status": a.status,
                "created_at": str(a.created_at),
            }
            for a in result.scalars().all()
        ]
        return _meta_response(entries, total)


register_tool(
    Tool(
        name="hivemind/get_audit_log",
        description="Audit-Log durchsuchen mit Filtern (Admin only).",
        inputSchema={
            "type": "object",
            "properties": {
                "epic_id": {"type": "string", "description": "Epic UUID filter"},
                "actor_id": {"type": "string", "description": "Actor UUID filter"},
                "tool_name": {"type": "string", "description": "Tool name filter"},
                "limit": {"type": "integer"},
                "offset": {"type": "integer"},
            },
        },
    ),
    _handle_get_audit_log,
)
