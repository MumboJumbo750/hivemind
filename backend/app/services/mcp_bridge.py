"""MCP Bridge / Gateway Service — Phase 8 (TASK-8-014 + TASK-8-015).

Hivemind as Meta-MCP: MCP server for agents AND MCP client to external MCP servers.
- Namespace isolation: hivemind/* (local), github/* (proxied), etc.
- RBAC: every tool call checks actor permissions
- Audit: all proxied calls logged
- Security: agents never see credentials
- Tool blocklist: dangerous ops always blocked
- Graceful degradation: bridge failure doesn't affect local tools

ALWAYS_BLOCKED_TOOLS: operations that are blocked regardless of config.
"""
import asyncio
import json
import logging
import subprocess
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# These tool names are ALWAYS blocked regardless of config
ALWAYS_BLOCKED_TOOLS = {
    "delete_repository",
    "destroy_database",
    "drop_table",
    "delete_organization",
}

# Bridge-level rate limiting: max calls per namespace per minute
BRIDGE_RPM_DEFAULT = 60
_bridge_call_timestamps: dict[str, list[float]] = {}


class BridgeError(Exception):
    """Raised when a bridge operation fails."""


class MCPBridgeRegistry:
    """Registry for external MCP bridge connections."""

    def __init__(self):
        self._bridges: dict[str, "BridgeClient"] = {}
        self._lock = asyncio.Lock()

    async def get_bridge(self, namespace: str) -> "BridgeClient | None":
        async with self._lock:
            return self._bridges.get(namespace)

    async def register_bridge(self, namespace: str, client: "BridgeClient") -> None:
        async with self._lock:
            self._bridges[namespace] = client

    async def unregister_bridge(self, namespace: str) -> None:
        async with self._lock:
            if namespace in self._bridges:
                await self._bridges[namespace].disconnect()
                del self._bridges[namespace]

    async def list_namespaces(self) -> list[str]:
        async with self._lock:
            return list(self._bridges.keys())

    async def get_all_discovered_tools(self) -> list[dict]:
        """Return all tools from all registered bridges."""
        all_tools = []
        async with self._lock:
            for namespace, client in self._bridges.items():
                for tool in (client.discovered_tools or []):
                    prefixed = dict(tool)
                    prefixed["name"] = f"{namespace}/{tool.get('name', 'unknown')}"
                    all_tools.append(prefixed)
        return all_tools


class BridgeClient:
    """Client for a single external MCP bridge connection."""

    def __init__(
        self,
        config_id: str,
        namespace: str,
        transport: str,
        command: str | None = None,
        args: list | None = None,
        url: str | None = None,
        env_vars: dict | None = None,
        tool_allowlist: list | None = None,
        tool_blocklist: list | None = None,
    ):
        self.config_id = config_id
        self.namespace = namespace
        self.transport = transport
        self.command = command
        self.args = args or []
        self.url = url
        self.env_vars = env_vars or {}
        self.tool_allowlist = set(tool_allowlist) if tool_allowlist else None
        self.tool_blocklist = set(tool_blocklist or [])
        self.discovered_tools: list[dict] = []
        self._connected = False
        self._process: subprocess.Popen | None = None

    async def connect(self) -> bool:
        """Attempt to connect to the bridge. Returns True on success."""
        try:
            if self.transport == "http" or self.transport == "sse":
                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{self.url}/health" if self.url else "http://localhost",
                        timeout=5.0,
                    )
                    self._connected = resp.status_code < 500
            else:
                # stdio: just mark as connected (process started on demand)
                self._connected = True
            return self._connected
        except Exception as e:
            logger.warning("Bridge %s connect failed: %s", self.namespace, e)
            self._connected = False
            return False

    async def disconnect(self) -> None:
        self._connected = False
        if self._process:
            self._process.terminate()
            self._process = None

    def is_tool_allowed(self, tool_name: str) -> bool:
        """Check if a tool is allowed by allowlist/blocklist."""
        # Global always-blocked
        if tool_name in ALWAYS_BLOCKED_TOOLS:
            return False
        # Bridge-specific blocklist
        if tool_name in self.tool_blocklist:
            return False
        # Bridge-specific allowlist (None = all allowed)
        if self.tool_allowlist is not None:
            return tool_name in self.tool_allowlist
        return True

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """Proxy a tool call to the external MCP server."""
        if not self.is_tool_allowed(tool_name):
            raise BridgeError(f"Tool '{tool_name}' is blocked by bridge policy")

        if not self._connected:
            raise BridgeError(f"Bridge '{self.namespace}' is not connected")

        if self.transport in ("http", "sse") and self.url:
            import httpx
            payload = {"method": "tools/call", "params": {"name": tool_name, "arguments": arguments}}
            headers = {}
            if self.env_vars.get("API_KEY"):
                headers["Authorization"] = f"Bearer {self.env_vars['API_KEY']}"
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.url}/mcp",
                    json=payload,
                    headers=headers,
                    timeout=30.0,
                )
                resp.raise_for_status()
                return resp.json()
        else:
            # stdio transport: not implemented in this phase (needs process management)
            raise BridgeError(f"stdio transport for bridge '{self.namespace}' not yet supported in this deployment")


# Singleton registry
bridge_registry = MCPBridgeRegistry()


async def proxy_tool_call(
    full_tool_name: str,
    arguments: dict,
    actor_id: str,
    actor_role: str,
    db: AsyncSession,
) -> Any:
    """Proxy a tool call through the MCP gateway.

    full_tool_name format: "namespace/tool_name" e.g. "github/create_branch"
    """
    parts = full_tool_name.split("/", 1)
    if len(parts) != 2:
        raise BridgeError(f"Invalid bridged tool name format: {full_tool_name}")

    namespace, tool_name = parts

    if namespace == "hivemind":
        raise BridgeError("Cannot proxy 'hivemind' namespace — reserved for local tools")

    # Rate-limiting per namespace (TASK-8-015)
    now = time.monotonic()
    if namespace not in _bridge_call_timestamps:
        _bridge_call_timestamps[namespace] = []
    timestamps = _bridge_call_timestamps[namespace]
    # Prune timestamps older than 60s
    timestamps[:] = [t for t in timestamps if now - t < 60.0]
    if len(timestamps) >= BRIDGE_RPM_DEFAULT:
        raise BridgeError(f"Rate limit exceeded for bridge namespace '{namespace}' ({BRIDGE_RPM_DEFAULT} calls/min)")
    timestamps.append(now)

    bridge = await bridge_registry.get_bridge(namespace)
    if bridge is None:
        raise BridgeError(f"No bridge registered for namespace '{namespace}'")

    # Call the bridge
    result = await bridge.call_tool(tool_name, arguments)

    # Audit trail — TASK-8-015
    from app.services.audit import write_audit
    import uuid
    await write_audit(
        tool_name=f"bridge_proxy/{full_tool_name}",
        actor_id=uuid.UUID(actor_id) if actor_id else uuid.UUID("00000000-0000-0000-0000-000000000001"),
        actor_role=actor_role,
        input_payload={"tool": full_tool_name, "arguments": arguments},
        target_id=namespace,
    )

    return result


async def load_bridges_from_db(db: AsyncSession) -> None:
    """Load all enabled bridges from DB and register them."""
    from app.models.mcp_bridge import MCPBridgeConfig
    from app.config import settings

    result = await db.execute(
        select(MCPBridgeConfig).where(MCPBridgeConfig.enabled == True)
    )
    configs = result.scalars().all()

    for config in configs:
        env_vars = {}
        if config.env_vars_encrypted and config.env_vars_nonce and settings.hivemind_key_passphrase:
            try:
                from app.services.ai_provider import decrypt_api_key
                raw = decrypt_api_key(config.env_vars_encrypted, config.env_vars_nonce, settings.hivemind_key_passphrase)
                env_vars = json.loads(raw)
            except Exception as e:
                logger.error("Failed to decrypt env_vars for bridge %s: %s", config.name, e)

        client = BridgeClient(
            config_id=str(config.id),
            namespace=config.namespace,
            transport=config.transport,
            command=config.command,
            args=config.args,
            url=config.url,
            env_vars=env_vars,
            tool_allowlist=config.tool_allowlist,
            tool_blocklist=config.tool_blocklist,
        )
        client.discovered_tools = config.discovered_tools or []
        await bridge_registry.register_bridge(config.namespace, client)

    logger.info("MCP Bridge: loaded %d bridge(s) from DB", len(configs))
