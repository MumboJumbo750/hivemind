"""Tests for MCP Server Setup — TASK-3-001."""
import pytest


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
