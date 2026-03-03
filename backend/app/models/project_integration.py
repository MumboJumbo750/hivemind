"""Project Integration model — Phase 8 (TASK-8-013)."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ProjectIntegration(Base):
    __tablename__ = "project_integrations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    integration_type: Mapped[str] = mapped_column(String(50), nullable=False)
    github_repo: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    github_project_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status_field_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    priority_field_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sync_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sync_direction: Mapped[str] = mapped_column(String(30), nullable=False, default="bidirectional")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
