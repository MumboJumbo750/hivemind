"""Node and NodeIdentity models for federation."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    node_name: Mapped[str] = mapped_column(Text, nullable=False)
    node_url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    public_key: Mapped[Optional[str]] = mapped_column(Text, unique=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class NodeIdentity(Base):
    """Singleton — stores the local node's Ed25519 keypair. Max one row (singleton_guard)."""

    __tablename__ = "node_identity"

    node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("nodes.id"), primary_key=True
    )
    singleton_guard: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", unique=True
    )
    node_name: Mapped[str] = mapped_column(Text, nullable=False)
    private_key: Mapped[str] = mapped_column(Text, nullable=False)
    public_key: Mapped[str] = mapped_column(Text, nullable=False)
    previous_public_key: Mapped[Optional[str]] = mapped_column(Text)
    key_rotated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
