import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


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


class EpicStartRequest(BaseModel):
    dry_run: bool = False
    max_parallel_workers: int = Field(default=1, ge=1, le=32)
    execution_mode_preference: Optional[
        Literal["local", "ide", "github_actions", "byoai"]
    ] = None
    respect_file_claims: bool = True
    auto_resume_on_qa_failed: bool = False


class EpicStartBlocker(BaseModel):
    code: str
    message: str


class EpicStartResponse(BaseModel):
    run_id: uuid.UUID
    epic_key: str
    status: str
    dry_run: bool
    startable: bool
    epic_state: str
    config: dict[str, Any]
    blockers: list[EpicStartBlocker]
    analysis: dict[str, Any]


class EpicRunResponse(BaseModel):
    id: uuid.UUID
    epic_id: uuid.UUID
    started_by: uuid.UUID
    status: str
    dry_run: bool
    config: dict[str, Any]
    analysis: dict[str, Any]
    started_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class EpicRunArtifactResponse(BaseModel):
    id: uuid.UUID
    epic_run_id: uuid.UUID
    epic_id: uuid.UUID
    task_id: Optional[uuid.UUID] = None
    task_key: Optional[str] = None
    artifact_type: str
    state: str
    source_role: Optional[str] = None
    target_role: Optional[str] = None
    title: str
    summary: Optional[str] = None
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    released_at: Optional[datetime] = None
