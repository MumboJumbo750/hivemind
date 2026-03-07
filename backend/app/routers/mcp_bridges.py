"""MCP Bridge Admin API — Phase 8 (TASK-8-015).

Admin-only endpoints for managing MCP bridge connections.
"""
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.routers.deps import get_current_actor, require_role
from app.schemas.auth import CurrentActor
from app.services.mcp_bridge import bridge_registry, BridgeClient, BridgeError

router = APIRouter(prefix="/admin/mcp-bridges", tags=["mcp-bridges"])


class MCPBridgeIn(BaseModel):
    name: str
    namespace: str
    transport: str  # stdio | sse | http
    command: str | None = None
    args: list[str] | None = None
    url: str | None = None
    env_vars: dict[str, str] | None = None  # plaintext — encrypted server-side
    enabled: bool = True
    tool_allowlist: list[str] | None = None
    tool_blocklist: list[str] | None = None


class MCPBridgeOut(BaseModel):
    id: str
    name: str
    namespace: str
    transport: str
    url: str | None
    command: str | None
    enabled: bool
    tool_allowlist: list[str] | None
    tool_blocklist: list[str] | None
    discovered_tools_count: int
    status: str  # connected | disconnected | error

    class Config:
        from_attributes = True


@router.get("", response_model=list[MCPBridgeOut])
async def list_bridges(
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin")),
):
    """List all MCP bridge configurations (admin only)."""
    from app.services.mcp_bridge import list_bridge_configs

    bridges = await list_bridge_configs(db)
    out = []
    for b in bridges:
        registered = await bridge_registry.get_bridge(b.namespace)
        bridge_status = "connected" if (registered and registered._connected) else "disconnected"
        out.append(MCPBridgeOut(
            id=str(b.id),
            name=b.name,
            namespace=b.namespace,
            transport=b.transport,
            url=b.url,
            command=b.command,
            enabled=b.enabled,
            tool_allowlist=b.tool_allowlist,
            tool_blocklist=b.tool_blocklist,
            discovered_tools_count=len(b.discovered_tools or []),
            status=bridge_status,
        ))
    return out


@router.post("", response_model=MCPBridgeOut, status_code=status.HTTP_201_CREATED)
async def create_bridge(
    data: MCPBridgeIn,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin")),
):
    """Create a new MCP bridge configuration."""
    if data.namespace == "hivemind":
        raise HTTPException(status_code=400, detail="Namespace 'hivemind' is reserved")

    # Check for duplicate
    from app.services.mcp_bridge import create_bridge_config, get_bridge_config_by_namespace

    if await get_bridge_config_by_namespace(db, data.namespace):
        raise HTTPException(status_code=409, detail=f"Namespace '{data.namespace}' already exists")

    # Encrypt env_vars if provided
    encrypted_env = None
    env_nonce = None
    if data.env_vars:
        from app.config import settings
        from app.services.ai_provider import encrypt_api_key
        import json
        if settings.hivemind_key_passphrase:
            encrypted_env, env_nonce = encrypt_api_key(json.dumps(data.env_vars), settings.hivemind_key_passphrase)

    config = await create_bridge_config(
        db,
        id=uuid.uuid4(),
        name=data.name,
        namespace=data.namespace,
        transport=data.transport,
        command=data.command,
        args=data.args,
        url=data.url,
        env_vars_encrypted=encrypted_env,
        env_vars_nonce=env_nonce,
        enabled=data.enabled,
        tool_allowlist=data.tool_allowlist,
        tool_blocklist=data.tool_blocklist,
    )

    return MCPBridgeOut(
        id=str(config.id),
        name=config.name,
        namespace=config.namespace,
        transport=config.transport,
        url=config.url,
        command=config.command,
        enabled=config.enabled,
        tool_allowlist=config.tool_allowlist,
        tool_blocklist=config.tool_blocklist,
        discovered_tools_count=0,
        status="disconnected",
    )


@router.post("/{bridge_id}/test")
async def test_bridge(
    bridge_id: str,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin")),
):
    """Test bridge connectivity."""
    from app.services.mcp_bridge import get_bridge_config_by_id

    config = await get_bridge_config_by_id(db, uuid.UUID(bridge_id))
    if not config:
        raise HTTPException(status_code=404, detail="Bridge not found")

    client = BridgeClient(
        config_id=str(config.id),
        namespace=config.namespace,
        transport=config.transport,
        command=config.command,
        url=config.url,
    )
    connected = await client.connect()
    return {"status": "connected" if connected else "error", "namespace": config.namespace}


@router.get("/{bridge_id}/tools")
async def get_bridge_tools(
    bridge_id: str,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin")),
):
    """Get discovered tools for a bridge."""
    from app.services.mcp_bridge import get_bridge_config_by_id

    config = await get_bridge_config_by_id(db, uuid.UUID(bridge_id))
    if not config:
        raise HTTPException(status_code=404, detail="Bridge not found")
    return {"tools": config.discovered_tools or [], "namespace": config.namespace}


@router.delete("/{bridge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bridge(
    bridge_id: str,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin")),
):
    """Delete a bridge configuration."""
    from app.services.mcp_bridge import delete_bridge_config, get_bridge_config_by_id

    config = await get_bridge_config_by_id(db, uuid.UUID(bridge_id))
    if not config:
        raise HTTPException(status_code=404, detail="Bridge not found")

    await delete_bridge_config(db, config)
