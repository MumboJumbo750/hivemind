"""Audit Log Viewer Endpoint — TASK-4-007.

GET /api/audit with filtering, pagination, truncation, and RBAC.
Admin sees all entries; developer sees only own entries.
"""
import json
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.audit import McpInvocation
from app.models.user import User
from app.routers.deps import get_current_actor
from app.schemas.auth import CurrentActor

router = APIRouter(prefix="/audit", tags=["audit"])

TRUNCATE_LIMIT = 2000


# ── Schemas ───────────────────────────────────────────────────────────────────

class AuditEntryResponse(BaseModel):
    id: uuid.UUID
    actor_id: uuid.UUID
    actor_username: Optional[str] = None
    actor_role: str
    tool_name: str
    epic_id: Optional[uuid.UUID] = None
    target_id: Optional[str] = None
    input_snapshot: Optional[dict] = None
    input_truncated: bool = False
    output_snapshot: Optional[dict] = None
    output_truncated: bool = False
    duration_ms: Optional[int] = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditListResponse(BaseModel):
    data: list[AuditEntryResponse]
    total_count: int
    has_more: bool
    page: int
    page_size: int


# ── Helpers ───────────────────────────────────────────────────────────────────

def _truncate_payload(payload: dict | None) -> tuple[dict | None, bool]:
    """Truncate JSON payload to TRUNCATE_LIMIT chars. Returns (payload, truncated)."""
    if payload is None:
        return None, False
    text = json.dumps(payload, default=str)
    if len(text) <= TRUNCATE_LIMIT:
        return payload, False
    # Return a truncated representation
    truncated_text = text[:TRUNCATE_LIMIT]
    return {"_truncated": truncated_text, "_original_length": len(text)}, True


# ── GET /api/audit ────────────────────────────────────────────────────────────

@router.get("", response_model=AuditListResponse)
async def list_audit_entries(
    actor_id: Optional[uuid.UUID] = Query(None, description="Filter by actor UUID"),
    tool_name: Optional[str] = Query(None, description="Filter by MCP tool name"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type (derived from tool_name prefix)"),
    target_id: Optional[str] = Query(None, description="Filter by target entity ID"),
    from_date: Optional[datetime] = Query(None, alias="from", description="Start of time range (ISO)"),
    to_date: Optional[datetime] = Query(None, alias="to", description="End of time range (ISO)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> AuditListResponse:
    """List audit log entries with filtering and pagination.

    RBAC: admin sees all, developer sees only own entries.
    """
    base = select(McpInvocation)

    # RBAC: developer can only see own entries
    if actor.role not in ("admin", "triage"):
        base = base.where(McpInvocation.actor_id == actor.id)

    # Filters
    if actor_id:
        base = base.where(McpInvocation.actor_id == actor_id)
    if tool_name:
        base = base.where(McpInvocation.tool_name == tool_name)
    if target_id:
        base = base.where(McpInvocation.target_id == target_id)
    if entity_type:
        # entity_type maps to tool_name patterns (e.g., "task" → tools containing "task")
        base = base.where(McpInvocation.tool_name.ilike(f"%{entity_type}%"))
    if from_date:
        base = base.where(McpInvocation.created_at >= from_date)
    if to_date:
        base = base.where(McpInvocation.created_at <= to_date)

    # Total count
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Paginated results (newest first)
    offset = (page - 1) * page_size
    query = base.order_by(McpInvocation.created_at.desc()).limit(page_size).offset(offset)
    result = await db.execute(query)
    entries = list(result.scalars().all())

    # Resolve usernames
    user_ids = {e.actor_id for e in entries}
    umap: dict[uuid.UUID, str] = {}
    if user_ids:
        u_result = await db.execute(select(User).where(User.id.in_(user_ids)))
        umap = {u.id: u.username for u in u_result.scalars().all()}

    # Build response with truncation
    data = []
    for e in entries:
        inp, inp_trunc = _truncate_payload(e.input_payload)
        out, out_trunc = _truncate_payload(e.output_payload)
        data.append(AuditEntryResponse(
            id=e.id,
            actor_id=e.actor_id,
            actor_username=umap.get(e.actor_id),
            actor_role=e.actor_role,
            tool_name=e.tool_name,
            epic_id=e.epic_id,
            target_id=e.target_id,
            input_snapshot=inp,
            input_truncated=inp_trunc,
            output_snapshot=out,
            output_truncated=out_trunc,
            duration_ms=e.duration_ms,
            status=e.status,
            created_at=e.created_at,
        ))

    return AuditListResponse(
        data=data,
        total_count=total,
        has_more=(offset + page_size) < total,
        page=page,
        page_size=page_size,
    )
