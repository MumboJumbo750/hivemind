"""Pydantic-Schemas für Auth-Endpoints (TASK-2-002)."""
import uuid
from typing import Literal

from pydantic import BaseModel, Field


class AuthRegister(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8)
    display_name: str | None = None
    email: str | None = None
    role: Literal["developer", "admin", "service", "kartograph"] = "developer"


class AuthLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # Sekunden


class CurrentActor(BaseModel):
    id: uuid.UUID
    username: str
    role: str
