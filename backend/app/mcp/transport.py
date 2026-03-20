"""MCP Standard-Compliant HTTP/SSE Transport (MCP 1.0).

Provides the official MCP SSE transport endpoints:
  - ``GET  /api/mcp/sse``       — SSE stream (JSON-RPC 2.0 responses)
  - ``POST /api/mcp/message``   — JSON-RPC 2.0 requests (initialize, tools/list, tools/call)

Plus convenience endpoints for the Hivemind frontend:
  - ``GET  /api/mcp/tools``     — flat JSON tools list
  - ``POST /api/mcp/call``      — simple tool call (no JSON-RPC overhead)

External MCP clients (Cursor, Claude Desktop HTTP, Continue) connect via /sse + /message.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from mcp.types import (
    CallToolResult,
    GetPromptResult,
    Implementation,
    InitializeResult,
    ListPromptsResult,
    ListResourcesResult,
    ListToolsResult,
    ReadResourceResult,
    TextResourceContents,
)
from pydantic import BaseModel
from starlette.datastructures import Headers
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from mcp.server.sse import SseServerTransport

from app.config import settings
from app.db import AsyncSessionLocal
from app.mcp.server import server, _tool_definitions, _tool_handlers, call_tool
import app.mcp.tools  # noqa: F401 — ensure all tools are registered
import app.mcp.prompts  # noqa: F401 — register MCP prompt capability (TASK-IDE-002)
import app.mcp.resources  # noqa: F401 — register MCP resource capability (TASK-IDE-007)
from app.routers.deps import CurrentActor, _get_app_mode, _resolve_solo_actor, get_current_actor
from app.schemas.auth import CurrentActor as CurrentActorSchema
from app.services import auth_service
from app.services.auth_service import decode_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])

# ── Standard MCP SSE Transport ─────────────────────────────────────────────

_sse_transport = SseServerTransport("/api/mcp/message")

# Track active sessions for status
_active_sessions: list[asyncio.Task] = []

_JSONRPC_VERSION = "2.0"
_DEFAULT_PROTOCOL_VERSION = "2024-11-05"
_TEST_ACTOR = CurrentActorSchema(
    id="00000000-0000-0000-0000-000000000001",
    username="solo",
    role="admin",
)


def _dump_model(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    if isinstance(value, list):
        return [_dump_model(item) for item in value]
    if isinstance(value, dict):
        return {key: _dump_model(item) for key, item in value.items()}
    return value


def _jsonrpc_result(request_id: Any, result: Any) -> dict[str, Any]:
    return {
        "jsonrpc": _JSONRPC_VERSION,
        "id": request_id,
        "result": _dump_model(result),
    }


def _jsonrpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": _JSONRPC_VERSION,
        "id": request_id,
        "error": {"code": code, "message": message},
    }


async def _read_request_body(receive: Receive) -> bytes:
    body = bytearray()
    while True:
        message = await receive()
        if message["type"] != "http.request":
            continue
        body.extend(message.get("body", b""))
        if not message.get("more_body", False):
            break
    return bytes(body)


def _make_replay_receive(body: bytes) -> Receive:
    sent = False

    async def _receive() -> dict[str, Any]:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    return _receive


def _is_missing_session_response(events: list[dict[str, Any]]) -> bool:
    status_code = None
    body_parts: list[bytes] = []
    for event in events:
        if event["type"] == "http.response.start":
            status_code = event.get("status")
        elif event["type"] == "http.response.body":
            body_parts.append(event.get("body", b""))
    body = b"".join(body_parts)
    return status_code in {400, 404} and b"session" in body.lower()


async def _send_json_response(send: Send, status_code: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": body,
            "more_body": False,
        }
    )


async def _send_empty_response(send: Send, status_code: int) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": [],
        }
    )
    await send({"type": "http.response.body", "body": b"", "more_body": False})


async def _resolve_actor_for_raw_request(scope: Scope) -> CurrentActor:
    if settings.testing:
        return _TEST_ACTOR

    headers = Headers(scope=scope)
    async with AsyncSessionLocal() as db:
        mode = await _get_app_mode(db)
        if mode == "solo":
            return await _resolve_solo_actor(db)

        authorization = headers.get("authorization")
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Nicht authentifiziert",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = authorization.split(" ", 1)[1].strip()
        try:
            payload = decode_token(token)
            user_id = payload.get("sub")
            role = payload.get("role")
            if not user_id or not role:
                raise JWTError("Fehlende Claims")
        except JWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Ungültiger Token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

        user = await auth_service.get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User nicht (mehr) gefunden",
            )

        return CurrentActorSchema(id=user.id, username=user.username, role=role)


def _normalize_tool_name(tool_name: str) -> str:
    if tool_name.startswith("hivemind/"):
        return tool_name.replace("hivemind/", "hivemind-", 1)
    return tool_name


def _tool_call_is_error(content: list[Any]) -> bool:
    if len(content) != 1:
        return False
    first = content[0]
    if getattr(first, "type", None) != "text":
        return False
    try:
        payload = json.loads(first.text)
    except Exception:
        return False
    return isinstance(payload, dict) and isinstance(payload.get("error"), dict)


async def _handle_stateless_jsonrpc(request: dict[str, Any], scope: Scope) -> tuple[int, dict[str, Any] | None]:
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params")

    if not isinstance(method, str) or not method:
        return 400, _jsonrpc_error(request_id, -32600, "Invalid Request")

    if params is None:
        params = {}
    if not isinstance(params, dict):
        return 400, _jsonrpc_error(request_id, -32602, "Invalid params")

    if method.startswith("notifications/"):
        return 202, None

    if method == "ping":
        return 200, _jsonrpc_result(request_id, {})

    if method == "initialize":
        options = server.create_initialization_options()
        protocol_version = params.get("protocolVersion") or _DEFAULT_PROTOCOL_VERSION
        result = InitializeResult(
            protocolVersion=protocol_version,
            capabilities=options.capabilities,
            serverInfo=Implementation(name=options.server_name, version=options.server_version),
        )
        return 200, _jsonrpc_result(request_id, result)

    if method == "tools/list":
        return 200, _jsonrpc_result(request_id, ListToolsResult(tools=list(_tool_definitions)))

    if method == "tools/call":
        tool_name = params.get("name")
        if not isinstance(tool_name, str) or not tool_name:
            return 400, _jsonrpc_error(request_id, -32602, "Missing tool name")
        actor = await _resolve_actor_for_raw_request(scope)
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return 400, _jsonrpc_error(request_id, -32602, "Invalid tool arguments")
        content = await call_tool(
            _normalize_tool_name(tool_name),
            {
                **arguments,
                "_actor_id": str(actor.id),
                "_actor_role": actor.role,
            },
        )
        result = CallToolResult(content=content, isError=_tool_call_is_error(content))
        return 200, _jsonrpc_result(request_id, result)

    if method == "resources/list":
        resources = await app.mcp.resources.list_resources()
        return 200, _jsonrpc_result(request_id, ListResourcesResult(resources=resources))

    if method == "resources/read":
        uri = params.get("uri")
        if not isinstance(uri, str) or not uri:
            return 400, _jsonrpc_error(request_id, -32602, "Missing resource uri")
        content = await app.mcp.resources.read_resource(uri)
        result = ReadResourceResult(contents=[TextResourceContents(uri=uri, text=content)])
        return 200, _jsonrpc_result(request_id, result)

    if method == "prompts/list":
        prompts = await app.mcp.prompts.list_prompts()
        return 200, _jsonrpc_result(request_id, ListPromptsResult(prompts=prompts))

    if method == "prompts/get":
        prompt_name = params.get("name")
        if not isinstance(prompt_name, str) or not prompt_name:
            return 400, _jsonrpc_error(request_id, -32602, "Missing prompt name")
        prompt_arguments = params.get("arguments") or {}
        if not isinstance(prompt_arguments, dict):
            return 400, _jsonrpc_error(request_id, -32602, "Invalid prompt arguments")
        result: GetPromptResult = await app.mcp.prompts.get_prompt(prompt_name, prompt_arguments)
        return 200, _jsonrpc_result(request_id, result)

    return 404, _jsonrpc_error(request_id, -32601, f"Method not found: {method}")


class _SseApp:
    """Raw ASGI app for the MCP SSE endpoint.

    Uses a class so Starlette ``Route`` treats it as a raw ASGI app
    (bypasses ``request_response`` wrapper which would choke on None return).
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async with _sse_transport.connect_sse(scope, receive, send) as streams:
            read_stream, write_stream = streams
            init_options = server.create_initialization_options()
            task = asyncio.current_task()
            if task:
                _active_sessions.append(task)
            try:
                await server.run(read_stream, write_stream, init_options)
            except asyncio.CancelledError:
                pass
            finally:
                if task and task in _active_sessions:
                    _active_sessions.remove(task)


class _MessageApp:
    """Raw ASGI app for the MCP JSON-RPC message endpoint.

    ``handle_post_message`` sends the 202 response internally via ASGI,
    so this must NOT be wrapped in ``request_response``.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        body = await _read_request_body(receive)
        replay_receive = _make_replay_receive(body)
        events: list[dict[str, Any]] = []

        async def _capture_send(message: dict[str, Any]) -> None:
            events.append(message)

        await _sse_transport.handle_post_message(scope, replay_receive, _capture_send)

        if not _is_missing_session_response(events):
            for event in events:
                await send(event)
            return

        logger.warning("MCP SSE session missing for /api/mcp/message, using stateless JSON-RPC fallback")

        try:
            request = json.loads(body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            await _send_json_response(send, 400, _jsonrpc_error(None, -32700, "Parse error"))
            return

        if not isinstance(request, dict):
            await _send_json_response(send, 400, _jsonrpc_error(None, -32600, "Invalid Request"))
            return

        try:
            status_code, payload = await _handle_stateless_jsonrpc(request, scope)
        except HTTPException as exc:
            await _send_json_response(send, exc.status_code, _jsonrpc_error(request.get("id"), -32001, str(exc.detail)))
            return
        except Exception as exc:
            logger.exception("Stateless MCP JSON-RPC fallback failed")
            await _send_json_response(send, 500, _jsonrpc_error(request.get("id"), -32603, str(exc)))
            return

        if payload is None:
            await _send_empty_response(send, status_code)
            return
        await _send_json_response(send, status_code, payload)


# These are added as raw Starlette routes (not FastAPI) because the SDK
# needs raw ASGI scope/receive/send access for SSE streaming.
# Using class instances as endpoints prevents the request_response wrapper.
mcp_standard_routes = [
    Route("/api/mcp/sse", endpoint=_SseApp()),
    Route("/api/mcp/message", endpoint=_MessageApp(), methods=["POST"]),
]


# ── Convenience Endpoints (Hivemind Frontend) ──────────────────────────────

class McpCallRequest(BaseModel):
    """HTTP envelope for a single MCP tool call."""
    tool: str
    arguments: dict | None = None


class McpCallResponse(BaseModel):
    """HTTP response for a single MCP tool call."""
    result: list[dict]


@router.get("/tools")
async def list_mcp_tools(actor: CurrentActor = Depends(get_current_actor)):
    """List all available MCP tools (convenience endpoint for frontend)."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "inputSchema": t.inputSchema,
        }
        for t in _tool_definitions
    ]


@router.post("/call", response_model=McpCallResponse)
async def call_mcp_tool(
    body: McpCallRequest,
    actor: CurrentActor = Depends(get_current_actor),
):
    """Execute a single MCP tool call (convenience endpoint for frontend).

    Wraps the internal call_tool function — no JSON-RPC overhead.
    """
    # Backward compat: accept legacy "hivemind/xxx" names, normalize to "hivemind-xxx"
    tool_name = body.tool.replace("hivemind/", "hivemind-", 1) if body.tool.startswith("hivemind/") else body.tool

    if tool_name not in _tool_handlers:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{tool_name}' not found",
        )

    args = dict(body.arguments or {})
    args["_actor_id"] = str(actor.id)
    args["_actor_role"] = actor.role

    result = await call_tool(tool_name, args)
    return McpCallResponse(result=[{"type": r.type, "text": r.text} for r in result])


# ── Discovery Endpoint ─────────────────────────────────────────────────────

@router.get("/discovery")
async def mcp_discovery():
    """Return MCP config snippets for all supported IDE clients.

    No auth required — useful for automated setup scripts.
    Includes workspace configuration for external repo setup.
    """
    base_url = "http://localhost:8000"
    sse_url = f"{base_url}/api/mcp/sse"
    deny_patterns = [
        p.strip()
        for p in settings.hivemind_fs_deny_list.split(",")
        if p.strip()
    ]
    return {
        "server_name": "hivemind",
        "sse_url": sse_url,
        "workspace": {
            "root": settings.hivemind_workspace_root,
            "deny_patterns": deny_patterns,
            "init_hint": "python scripts/hivemind_init.py --workspace /path/to/your/repo",
        },
        "clients": {
            "vscode": {
                "description": "VS Code / Copilot Agent Mode (.vscode/mcp.json — bereits im Repo)",
                "config_path": ".vscode/mcp.json",
                "config": {
                    "servers": {
                        "hivemind": {"type": "sse", "url": sse_url}
                    }
                },
            },
            "copilot_cli": {
                "description": "GitHub Copilot CLI (~/.copilot/mcp-config.json)",
                "config_path": "~/.copilot/mcp-config.json",
                "cli_command": f"gh copilot mcp add hivemind --type sse --url {sse_url}",
                "config": {
                    "mcpServers": {
                        "hivemind": {"type": "sse", "url": sse_url, "tools": ["*"]}
                    }
                },
            },
            "claude_desktop": {
                "description": "Claude Desktop (claude_desktop_config.json)",
                "config_path_windows": "~/AppData/Roaming/Claude/claude_desktop_config.json",
                "config_path_macos": "~/Library/Application Support/Claude/claude_desktop_config.json",
                "config": {
                    "mcpServers": {
                        "hivemind": {
                            "command": "npx",
                            "args": ["-y", "mcp-remote", sse_url],
                        }
                    }
                },
            },
            "cursor": {
                "description": "Cursor IDE (.cursor/mcp.json)",
                "config_path": ".cursor/mcp.json",
                "config": {
                    "mcpServers": {
                        "hivemind": {"type": "sse", "url": sse_url}
                    }
                },
            },
        },
    }


# ── Status Endpoint ────────────────────────────────────────────────────────

@router.get("/status")
async def mcp_status(actor: CurrentActor = Depends(get_current_actor)):
    """Return MCP server status and capabilities."""
    return {
        "protocol": "MCP 1.0",
        "transport": "sse",
        "tools_count": len(_tool_definitions),
        "connected_sessions": len(_active_sessions),
        "endpoints": {
            "sse": "/api/mcp/sse",
            "message": "/api/mcp/message",
            "tools": "/api/mcp/tools",
            "call": "/api/mcp/call",
            "discovery": "/api/mcp/discovery",
        },
    }

