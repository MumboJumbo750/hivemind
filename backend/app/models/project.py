import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    repo_host_path: Mapped[str | None] = mapped_column(Text)
    workspace_root: Mapped[str | None] = mapped_column(Text)
    workspace_mode: Mapped[str | None] = mapped_column(Text)
    onboarding_status: Mapped[str | None] = mapped_column(Text)
    default_branch: Mapped[str | None] = mapped_column(Text)
    remote_url: Mapped[str | None] = mapped_column(Text)
    detected_stack: Mapped[list[str] | None] = mapped_column(JSONB)
    agent_thread_overrides: Mapped[dict | None] = mapped_column(JSONB, server_default="{}")
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    members: Mapped[list["ProjectMember"]] = relationship(back_populates="project")
    epics: Mapped[list["Epic"]] = relationship(back_populates="project")  # type: ignore[name-defined]
    integrations: Mapped[list["ProjectIntegration"]] = relationship()  # type: ignore[name-defined]


class ProjectMember(Base):
    __tablename__ = "project_members"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default="developer")

    project: Mapped["Project"] = relationship(back_populates="members")
