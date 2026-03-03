"""MCP Bridge Config model — Phase 8 (TASK-8-014)."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, LargeBinary, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MCPBridgeConfig(Base):
    __tablename__ = "mcp_bridge_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    namespace: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    transport: Mapped[str] = mapped_column(String(20), nullable=False)  # stdio | sse | http
    command: Mapped[str | None] = mapped_column(String(500), nullable=True)
    args: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    env_vars_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    env_vars_nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tool_allowlist: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    tool_blocklist: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    discovered_tools: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
