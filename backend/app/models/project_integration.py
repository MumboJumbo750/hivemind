"""Project Integration model — Phase 8 (TASK-8-013)."""
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
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
    display_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    integration_key: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    base_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    external_project_key: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    project_selector: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    status_mapping: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    routing_hints: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    config: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    webhook_secret: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    github_repo: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    github_project_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status_field_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    priority_field_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sync_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sync_direction: Mapped[str] = mapped_column(String(30), nullable=False, default="bidirectional")
    last_health_state: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    last_health_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    health_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_event_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
