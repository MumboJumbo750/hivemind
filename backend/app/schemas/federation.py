"""Pydantic schemas for Federation Protocol API — TASK-F-004."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ─── /federation/ping ──────────────────────────────────────────────────────────

class PingResponse(BaseModel):
    node_id: uuid.UUID
    node_name: str
    public_key: str
    version: str = "0.1.0"


# ─── /federation/skill/publish ────────────────────────────────────────────────

class FederatedSkillPublish(BaseModel):
    external_id: Optional[str] = None
    title: str
    content: str
    service_scope: list[str] = Field(default_factory=list)
    stack: list[str] = Field(default_factory=list)
    skill_type: str = "domain"
    lifecycle: str = "active"
    tags: list[str] = Field(default_factory=list)
    version: int = 1


class FederatedSkillResponse(BaseModel):
    id: uuid.UUID
    title: str
    origin_node_id: Optional[uuid.UUID] = None
    federation_scope: str
    created: bool = False  # True if newly created, False if updated

    model_config = {"from_attributes": True}


# ─── /federation/wiki/publish ─────────────────────────────────────────────────

class FederatedWikiPublish(BaseModel):
    title: str
    slug: str
    content: str
    tags: list[str] = Field(default_factory=list)
    version: int = 1


class FederatedWikiResponse(BaseModel):
    id: uuid.UUID
    title: str
    origin_node_id: Optional[uuid.UUID] = None
    federation_scope: str
    created: bool = False

    model_config = {"from_attributes": True}


# ─── /federation/epic/share ───────────────────────────────────────────────────

class FederatedTaskSpec(BaseModel):
    external_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    state: str = "incoming"
    definition_of_done: Optional[dict] = None
    pinned_skills: list = Field(default_factory=list)
    assigned_node_id: Optional[uuid.UUID] = None


class FederatedEpicShare(BaseModel):
    external_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    definition_of_done: Optional[dict] = None
    tags: list[str] = Field(default_factory=list)
    tasks: list[FederatedTaskSpec] = Field(default_factory=list)


class FederatedEpicResponse(BaseModel):
    id: uuid.UUID
    epic_key: str
    title: str
    origin_node_id: Optional[uuid.UUID] = None
    task_count: int = 0

    model_config = {"from_attributes": True}


# ─── /federation/task/update ──────────────────────────────────────────────────

class FederatedTaskUpdate(BaseModel):
    external_id: str
    state: str
    result: Optional[str] = None


class FederatedTaskUpdateResponse(BaseModel):
    task_key: str
    state: str
    updated: bool = True

    model_config = {"from_attributes": True}


# ─── /federation/sync (bulk) ─────────────────────────────────────────────────

class FederatedSyncItem(BaseModel):
    """A single item in a bulk sync payload."""
    type: str  # "skill" | "wiki" | "epic" | "task_update"
    payload: dict


class FederatedSyncRequest(BaseModel):
    items: list[FederatedSyncItem]


class FederatedSyncResponse(BaseModel):
    processed: int = 0
    errors: int = 0
    details: list[str] = Field(default_factory=list)
