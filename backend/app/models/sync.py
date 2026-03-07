"""SyncOutbox and SyncDeadLetter models for the Outbox Pattern."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class SyncOutbox(Base):
    __tablename__ = "sync_outbox"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    dedup_key: Mapped[Optional[str]] = mapped_column(Text, unique=True)
    direction: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="inbound"
    )
    system: Mapped[str] = mapped_column(Text, nullable=False)
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True
    )
    integration_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project_integrations.id"), nullable=True
    )
    target_node_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("nodes.id")
    )
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    routing_state: Mapped[Optional[str]] = mapped_column(
        Text, server_default="unrouted"
    )
    routing_detail: Mapped[Optional[dict]] = mapped_column(JSONB)
    # embedding column omitted from ORM (managed by raw SQL, pgvector type)
    embedding_model: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    target_node: Mapped[Optional["Node"]] = relationship()  # type: ignore[name-defined]
    dead_letters: Mapped[list["SyncDeadLetter"]] = relationship(back_populates="outbox_entry")


class SyncDeadLetter(Base):
    __tablename__ = "sync_dead_letter"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    outbox_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sync_outbox.id"), nullable=False
    )
    system: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text)
    failed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    requeued_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    requeued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    discarded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    discarded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    outbox_entry: Mapped["SyncOutbox"] = relationship(back_populates="dead_letters")
