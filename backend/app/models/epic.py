import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Epic(Base):
    __tablename__ = "epics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    epic_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id")
    )
    external_id: Mapped[Optional[str]] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    backup_owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default="incoming")
    priority: Mapped[Optional[str]] = mapped_column(Text, server_default="medium")
    sla_due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    dod_framework: Mapped[Optional[dict]] = mapped_column(JSONB)
    # embedding column omitted from ORM (managed by raw SQL migration, pgvector type)
    embedding_model: Mapped[Optional[str]] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    origin_node_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("nodes.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'critical')",
            name="chk_epic_priority",
        ),
    )

    project: Mapped[Optional["Project"]] = relationship(back_populates="epics")  # type: ignore[name-defined]
    tasks: Mapped[list["Task"]] = relationship(back_populates="epic")  # type: ignore[name-defined]
