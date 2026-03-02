"""Pydantic schemas for Epic Proposals — TASK-4-004."""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class EpicProposalCreate(BaseModel):
    project_id: uuid.UUID
    title: str
    description: str
    rationale: Optional[str] = None
    depends_on: Optional[list[uuid.UUID]] = None


class EpicProposalUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    rationale: Optional[str] = None
    depends_on: Optional[list[uuid.UUID]] = None
    expected_version: Optional[int] = None


class EpicProposalReject(BaseModel):
    reason: str


class EpicProposalResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    proposed_by: uuid.UUID
    proposed_by_username: Optional[str] = None
    title: str
    description: str
    rationale: Optional[str]
    state: str
    depends_on: Optional[list[uuid.UUID]]
    resulting_epic_id: Optional[uuid.UUID]
    rejection_reason: Optional[str]
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EpicProposalListResponse(BaseModel):
    data: list[EpicProposalResponse]
    total_count: int
    has_more: bool


# ─── Requirement Draft ────────────────────────────────────────────────────────

class RequirementDraftRequest(BaseModel):
    project_id: uuid.UUID
    text: str
    priority_hint: Optional[str] = None
    tags: Optional[list[str]] = None


class RequirementDraftResponse(BaseModel):
    prompt: str
    token_count: int
    draft_id: uuid.UUID
    enrichment: dict
