"""Pydantic schemas for Skills — TASK-4-005."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


# ── Create ────────────────────────────────────────────────────────────────────

class SkillCreate(BaseModel):
    project_id: Optional[uuid.UUID] = None
    title: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1)
    service_scope: list[str] = Field(default_factory=list)
    stack: list[str] = Field(default_factory=list)
    version_range: Optional[dict] = None
    skill_type: str = "domain"


# ── Update (draft only) ──────────────────────────────────────────────────────

class SkillUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    content: Optional[str] = Field(None, min_length=1)
    service_scope: Optional[list[str]] = None
    stack: Optional[list[str]] = None
    version_range: Optional[dict] = None
    version: int  # optimistic locking


# ── Reject ────────────────────────────────────────────────────────────────────

class SkillReject(BaseModel):
    rationale: str = Field(..., min_length=1, max_length=2000)


# ── Response ──────────────────────────────────────────────────────────────────

class SkillResponse(BaseModel):
    id: uuid.UUID
    project_id: Optional[uuid.UUID] = None
    title: str
    content: str
    service_scope: list[str] = []
    stack: list[str] = []
    version_range: Optional[dict] = None
    owner_id: Optional[uuid.UUID] = None
    proposed_by: Optional[uuid.UUID] = None
    proposed_by_username: Optional[str] = None
    confidence: Optional[Decimal] = None
    skill_type: str
    lifecycle: str
    version: int
    token_count: Optional[int] = None
    rejection_rationale: Optional[str] = None
    federation_scope: str = "local"
    origin_node_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SkillListResponse(BaseModel):
    data: list[SkillResponse]
    total_count: int
    has_more: bool


# ── Skill Version ─────────────────────────────────────────────────────────────

class SkillVersionResponse(BaseModel):
    id: uuid.UUID
    skill_id: uuid.UUID
    version: int
    content: str
    token_count: Optional[int] = None
    changed_by: uuid.UUID
    changed_by_username: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
