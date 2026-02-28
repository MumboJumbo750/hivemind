"""Pydantic schemas for Wiki articles, Guards, Code-Nodes, Docs — TASK-3-010."""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ── Wiki Articles ──────────────────────────────────────────────────────────

class WikiArticleCreate(BaseModel):
    title: str
    slug: str
    content: str
    category_id: Optional[uuid.UUID] = None
    tags: list[str] = []
    linked_epics: list[uuid.UUID] = []
    linked_skills: list[uuid.UUID] = []


class WikiArticleUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category_id: Optional[uuid.UUID] = None
    tags: Optional[list[str]] = None
    linked_epics: Optional[list[uuid.UUID]] = None
    linked_skills: Optional[list[uuid.UUID]] = None
    expected_version: Optional[int] = None


class WikiArticleResponse(BaseModel):
    id: uuid.UUID
    title: str
    slug: str
    content: str
    category_id: Optional[uuid.UUID]
    tags: list[str]
    linked_epics: Optional[list[uuid.UUID]]
    linked_skills: Optional[list[uuid.UUID]]
    version: int
    federation_scope: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Guards ─────────────────────────────────────────────────────────────────

class GuardCreate(BaseModel):
    title: str
    description: Optional[str] = None
    type: str = "executable"
    command: Optional[str] = None
    condition: Optional[str] = None
    scope: list[str] = []
    project_id: Optional[uuid.UUID] = None
    skill_id: Optional[uuid.UUID] = None
    skippable: bool = True


class GuardUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    command: Optional[str] = None
    condition: Optional[str] = None
    scope: Optional[list[str]] = None
    skippable: Optional[bool] = None
    lifecycle: Optional[str] = None
    expected_version: Optional[int] = None


class GuardResponse(BaseModel):
    id: uuid.UUID
    project_id: Optional[uuid.UUID]
    skill_id: Optional[uuid.UUID]
    title: str
    description: Optional[str]
    type: str
    command: Optional[str]
    condition: Optional[str]
    scope: list[str]
    lifecycle: str
    skippable: bool
    version: int
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Code Nodes ─────────────────────────────────────────────────────────────

class CodeNodeCreate(BaseModel):
    path: str
    node_type: str
    label: str
    project_id: Optional[uuid.UUID] = None
    metadata: Optional[dict] = None


class CodeNodeUpdate(BaseModel):
    label: Optional[str] = None
    node_type: Optional[str] = None
    metadata: Optional[dict] = None


class CodeNodeResponse(BaseModel):
    id: uuid.UUID
    project_id: Optional[uuid.UUID]
    path: str
    node_type: str
    label: str
    explored_at: Optional[datetime]
    federation_scope: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Docs (Epic Docs) ──────────────────────────────────────────────────────

class DocCreate(BaseModel):
    title: str
    content: str


class DocResponse(BaseModel):
    id: uuid.UUID
    title: str
    content: str
    epic_id: Optional[uuid.UUID]
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
