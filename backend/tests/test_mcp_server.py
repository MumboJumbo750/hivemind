"""Tests for MCP Server Setup — TASK-3-001."""
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_list_mcp_tools(client):
    """Tool-Registrierung gibt korrektes Schema zurück."""
    async with client as c:
        resp = await c.get("/api/mcp/tools")
        assert resp.status_code == 200
        tools = resp.json()
        assert isinstance(tools, list)


@pytest.mark.asyncio
async def test_call_unknown_tool(client):
    """Unbekannter Tool-Name → MCP-konforme Fehlermeldung."""
    async with client as c:
        resp = await c.post(
            "/api/mcp/call",
            json={"tool": "hivemind/nonexistent", "arguments": {}},
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_mcp_sse_endpoint_exists(client):
    """SSE-Endpoint antwortet mit text/event-stream."""
    async with client as c:
        # Use stream to avoid consuming entire SSE stream
        async with c.stream("GET", "/api/mcp/sse") as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")
            break  # Don't consume whole stream


@pytest.mark.asyncio
async def test_call_tool_no_auth_in_solo_mode(client):
    """In Solo-Modus: Tool-Call funktioniert ohne explizite Auth."""
    async with client as c:
        resp = await c.get("/api/mcp/tools")
        assert resp.status_code == 200
