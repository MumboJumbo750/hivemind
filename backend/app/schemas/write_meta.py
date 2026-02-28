"""MCP Write-Pflichtfelder-Schema (TASK-2-005)."""
import uuid
from typing import Optional

from pydantic import BaseModel, Field


class WriteRequestMeta(BaseModel):
    """Pflichtfelder für alle mutierenden Write-Requests."""

    request_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    actor_id: uuid.UUID
    actor_role: str
    epic_id: Optional[uuid.UUID] = None  # nur bei Epic/Task-scoped Writes
    idempotency_key: uuid.UUID = Field(default_factory=uuid.uuid4)
    expected_version: int
