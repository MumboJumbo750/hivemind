import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    task_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    epic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("epics.id"), nullable=False
    )
    parent_task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default="incoming")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    definition_of_done: Mapped[Optional[dict]] = mapped_column(JSONB)
    quality_gate: Mapped[Optional[dict]] = mapped_column(JSONB)
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    assigned_node_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("nodes.id")
    )
    pinned_skills: Mapped[list] = mapped_column(JSONB, server_default="[]")
    result: Mapped[Optional[str]] = mapped_column(Text)
    artifacts: Mapped[list] = mapped_column(JSONB, server_default="[]")
    qa_failed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    review_comment: Mapped[Optional[str]] = mapped_column(Text)
    external_id: Mapped[Optional[str]] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    epic: Mapped["Epic"] = relationship(back_populates="tasks")  # type: ignore[name-defined]
