"""PromptHistory model — TASK-3-005."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PromptHistory(Base):
    __tablename__ = "prompt_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id")
    )
    epic_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("epics.id")
    )
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id")
    )
    agent_type: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_type: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    override_text: Mapped[Optional[str]] = mapped_column(Text)
    context_refs: Mapped[list | None] = mapped_column(JSONB, server_default="[]")
    token_count: Mapped[Optional[int]] = mapped_column(Integer)
    token_count_minified: Mapped[Optional[int]] = mapped_column(Integer)
    generated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
