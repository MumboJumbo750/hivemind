"""NodeBugReport ORM model — Phase 7 (TASK-7-005).

Table ``node_bug_reports`` was created in Migration 001 (basic columns) and
extended in Migration 010 (Phase 7 columns: sentry enrichment + routing).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class NodeBugReport(Base):
    __tablename__ = "node_bug_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    # FK on code_nodes.id (NOT nodes.id!)
    node_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("code_nodes.id", ondelete="SET NULL"), nullable=True
    )
    sentry_id: Mapped[Optional[str]] = mapped_column(Text)
    severity: Mapped[Optional[str]] = mapped_column(Text)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Phase 7 columns (Migration 010)
    sentry_issue_id: Mapped[Optional[str]] = mapped_column(Text)
    stack_trace_hash: Mapped[Optional[str]] = mapped_column(Text)
    first_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    epic_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("epics.id", ondelete="SET NULL"), nullable=True
    )
    manually_routed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    manually_routed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    manually_routed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
