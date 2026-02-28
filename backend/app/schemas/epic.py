import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class EpicCreate(BaseModel):
    title: str
    description: Optional[str] = None
    owner_id: Optional[uuid.UUID] = None
    priority: str = "medium"
    sla_due_at: Optional[datetime] = None
    dod_framework: Optional[Any] = None


class EpicUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    state: Optional[str] = None
    owner_id: Optional[uuid.UUID] = None
    backup_owner_id: Optional[uuid.UUID] = None
    priority: Optional[str] = None
    sla_due_at: Optional[datetime] = None
    dod_framework: Optional[Any] = None
    # Optimistic Locking + Idempotenz (TASK-2-005)
    expected_version: Optional[int] = None
    idempotency_key: Optional[uuid.UUID] = None


class EpicResponse(BaseModel):
    id: uuid.UUID
    epic_key: str
    project_id: Optional[uuid.UUID]
    title: str
    description: Optional[str]
    owner_id: Optional[uuid.UUID]
    backup_owner_id: Optional[uuid.UUID]
    state: str
    priority: Optional[str]
    sla_due_at: Optional[datetime]
    dod_framework: Optional[Any]
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Epic Share (Federation) ─────────────────────────────────────────────────

class EpicShareRequest(BaseModel):
    """Request to share an epic with a peer node."""
    peer_node_id: uuid.UUID
    task_ids: Optional[list[uuid.UUID]] = None


class EpicShareResponse(BaseModel):
    """Response after submitting an epic share to the outbox."""
    outbox_id: uuid.UUID
    epic_key: str
    peer_node_id: uuid.UUID
    task_count: int
