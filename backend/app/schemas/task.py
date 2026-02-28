import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    assigned_to: Optional[uuid.UUID] = None
    definition_of_done: Optional[Any] = None
    parent_task_id: Optional[uuid.UUID] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assigned_to: Optional[uuid.UUID] = None
    definition_of_done: Optional[Any] = None
    result: Optional[str] = None
    # Optimistic Locking + Idempotenz (TASK-2-005)
    expected_version: Optional[int] = None
    idempotency_key: Optional[uuid.UUID] = None


class TaskStateTransition(BaseModel):
    state: str
    comment: Optional[str] = None  # populated on reject


class TaskReview(BaseModel):
    action: str  # "approve" | "reject"
    comment: Optional[str] = None


class TaskResponse(BaseModel):
    id: uuid.UUID
    task_key: str
    epic_id: uuid.UUID
    parent_task_id: Optional[uuid.UUID]
    title: str
    description: Optional[str]
    state: str
    version: int
    definition_of_done: Optional[Any]
    assigned_to: Optional[uuid.UUID]
    assigned_node_id: Optional[uuid.UUID] = None
    assigned_node_name: Optional[str] = None
    pinned_skills: list
    result: Optional[str]
    artifacts: list
    qa_failed_count: int
    review_comment: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
