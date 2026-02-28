"""Schemas für project_members CRUD (TASK-2-008)."""
import uuid
from typing import Literal

from pydantic import BaseModel


class MemberAdd(BaseModel):
    user_id: uuid.UUID
    role: Literal["developer", "admin", "kartograph", "service"] = "developer"


class MemberUpdate(BaseModel):
    role: Literal["developer", "admin", "kartograph", "service"]


class MemberResponse(BaseModel):
    project_id: uuid.UUID
    user_id: uuid.UUID
    role: str

    model_config = {"from_attributes": True}
