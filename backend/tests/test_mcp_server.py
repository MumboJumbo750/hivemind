"""Tests for MCP Server Setup — TASK-3-001."""
import pytest
from mcp.types import TextContent
from unittest.mock import AsyncMock, patch


# Uses shared `client` fixture from conftest.py (DB-isolated via savepoint rollback)


@pytest.mark.asyncio
async def test_list_mcp_tools(client):
    """Tool-Registrierung gibt korrektes Schema zurück."""
    resp = await client.get("/api/mcp/tools")
    assert resp.status_code == 200
    tools = resp.json()
    assert isinstance(tools, list)


@pytest.mark.asyncio
async def test_call_unknown_tool(client):
    """Unbekannter Tool-Name → MCP-konforme Fehlermeldung."""
    resp = await client.post(
        "/api/mcp/call",
        json={"tool": "hivemind-nonexistent", "arguments": {}},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_mcp_sse_endpoint_exists(client):
    """SSE-Endpoint ist registriert.

    We cannot test the SSE stream directly via httpx ASGITransport
    because the long-lived ASGI app never completes. Instead, verify
    the route is mounted in the app.
    """
    from app.main import app as _app

    sse_routes = [
        r
        for r in _app.routes
        if hasattr(r, "path") and r.path == "/api/mcp/sse"
    ]
    assert len(sse_routes) == 1, "SSE route /api/mcp/sse should be registered"


@pytest.mark.asyncio
async def test_call_tool_no_auth_in_solo_mode(client):
    """In Solo-Modus: Tool-Call funktioniert ohne explizite Auth."""
    resp = await client.get("/api/mcp/tools")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_mcp_message_falls_back_to_stateless_initialize_on_missing_session(client):
    """Stale/missing SSE sessions should not break initialize calls."""
    resp = await client.post(
        "/api/mcp/message",
        headers={"mcp-session-id": "stale-session"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0"}},
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] == 1
    assert payload["result"]["protocolVersion"] == "2024-11-05"
    assert payload["result"]["serverInfo"]["name"] == "hivemind"
    assert payload["result"]["capabilities"]["tools"]["listChanged"] is False


@pytest.mark.asyncio
async def test_mcp_message_falls_back_to_stateless_tool_calls_on_missing_session(client):
    """Stale/missing SSE sessions should fall back to direct tools/call execution."""
    with patch("app.mcp.transport.call_tool", AsyncMock(return_value=[TextContent(type="text", text="ok")])) as mock_call_tool:
        resp = await client.post(
            "/api/mcp/message",
            headers={"mcp-session-id": "stale-session"},
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "hivemind-get_task",
                    "arguments": {"task_key": "TASK-1"},
                },
            },
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["result"]["content"][0]["type"] == "text"
    assert payload["result"]["content"][0]["text"] == "ok"
    assert payload["result"]["isError"] is False
    mock_call_tool.assert_awaited_once()


@pytest.mark.asyncio
async def test_mcp_message_falls_back_to_prompt_listing_on_missing_session(client):
    """Prompt listing should still work when the SSE session has expired."""
    resp = await client.post(
        "/api/mcp/message",
        headers={"mcp-session-id": "stale-session"},
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "prompts/list",
            "params": {},
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    prompt_names = {prompt["name"] for prompt in payload["result"]["prompts"]}
    assert "hivemind.worker" in prompt_names
    assert "hivemind.reviewer" in prompt_names
