"""Integration tests for MCP memory ledger tools."""
from __future__ import annotations

import json
import uuid
from uuid import uuid4

import pytest
from sqlalchemy import delete, text

from app.db import AsyncSessionLocal
from app.models.memory import MemoryEntry, MemoryFact, MemorySession, MemorySummary


def _call_result(response) -> dict:
    resp_json = response.json()
    assert "result" in resp_json, f"Kein 'result' in Response: {resp_json}"
    text_payload = resp_json["result"][0]["text"]
    return json.loads(text_payload)


def _ok(response) -> dict:
    payload = _call_result(response)
    assert "error" not in payload, f"Unerwarteter Fehler: {payload}"
    return payload["data"]


@pytest.mark.asyncio
async def test_memory_save_and_context_roundtrip(client) -> None:
    marker = f"memory-it-{uuid4()}"
    entry_id = None
    session_id = None
    try:
        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind-save_memory", "arguments": {
                "scope": "global",
                "content": f"{marker} raw observation for a long running task",
                "tags": ["integration", "debug"],
            }},
        )
        assert response.status_code == 200
        save_data = _ok(response)
        entry_id = save_data["entry_id"]
        session_id = save_data["session_id"]

        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind-get_memory_context", "arguments": {
                "scope": "global",
                "max_tokens": 1200,
            }},
        )
        assert response.status_code == 200
        context_data = _ok(response)
        assert context_data["scope"] == "global"
        assert any(marker in item["content"] for item in context_data["uncovered_entries_preview"])
        assert context_data["integrity_warnings"]["uncovered_entries"] >= 1

        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind-get_uncovered_entries", "arguments": {"scope": "global"}},
        )
        uncovered_data = _ok(response)
        assert any(item["id"] == entry_id for item in uncovered_data["entries"])
    finally:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                if entry_id:
                    entry_uuid = uuid.UUID(entry_id)
                    await db.execute(delete(MemoryFact).where(MemoryFact.entry_id == entry_uuid))
                    await db.execute(delete(MemoryEntry).where(MemoryEntry.id == entry_uuid))
                if session_id:
                    await db.execute(delete(MemorySession).where(MemorySession.id == uuid.UUID(session_id)))


@pytest.mark.asyncio
async def test_memory_fact_compaction_and_graduation_flow(client) -> None:
    marker = f"memory-it-{uuid4()}"
    entry_id = None
    session_id = None
    summary_id = None
    fact_ids: list[str] = []
    try:
        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind-save_memory", "arguments": {
                "scope": "global",
                "content": f"{marker} observed JWT refresh handling gap",
                "tags": ["integration", "auth", "skill-candidate"],
            }},
        )
        save_data = _ok(response)
        entry_id = save_data["entry_id"]
        session_id = save_data["session_id"]

        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind-extract_facts", "arguments": {
                "entry_ids": [entry_id],
                "facts": [
                    {"entity": "auth/jwt", "key": "issue", "value": f"{marker} refresh missing", "confidence": 0.9}
                ],
            }},
        )
        fact_data = _ok(response)
        fact_ids = fact_data["fact_ids"]
        assert fact_data["count"] == 1

        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind-compact_memories", "arguments": {
                "entry_ids": [entry_id],
                "summary": f"{marker} summary: JWT refresh handling needs a retry-safe sequence.",
                "open_questions": [f"{marker} why is refresh disabled?"],
            }},
        )
        summary_data = _ok(response)
        summary_id = summary_data["summary_id"]
        assert summary_data["source_count"] == 1

        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind-get_open_questions", "arguments": {"scope": "global"}},
        )
        questions_data = _ok(response)
        assert any(marker in item["question"] for item in questions_data["questions"])

        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind-graduate_memory", "arguments": {
                "summary_id": summary_id,
                "target": "doc",
                "target_id": "DOC-TEST",
            }},
        )
        graduate_data = _ok(response)
        assert graduate_data["graduated"] is True
        assert graduate_data["graduated_to"]["target"] == "doc"
    finally:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                if fact_ids:
                    await db.execute(delete(MemoryFact).where(MemoryFact.id.in_([uuid.UUID(item) for item in fact_ids])))
                if summary_id:
                    await db.execute(delete(MemorySummary).where(MemorySummary.id == uuid.UUID(summary_id)))
                if entry_id:
                    await db.execute(delete(MemoryEntry).where(MemoryEntry.id == uuid.UUID(entry_id)))
                if session_id:
                    await db.execute(delete(MemorySession).where(MemorySession.id == uuid.UUID(session_id)))


@pytest.mark.asyncio
async def test_memory_search_finds_entry_fact_and_summary(client) -> None:
    marker = f"memory-it-{uuid4()}"
    entry_id = None
    session_id = None
    summary_id = None
    fact_ids: list[str] = []
    try:
        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind-save_memory", "arguments": {
                "scope": "global",
                "content": f"{marker} repo analysis note for search coverage",
                "tags": ["integration", "searchable"],
            }},
        )
        save_data = _ok(response)
        entry_id = save_data["entry_id"]
        session_id = save_data["session_id"]

        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind-extract_facts", "arguments": {
                "entry_ids": [entry_id],
                "facts": [{"entity": marker, "key": "kind", "value": "integration-search"}],
            }},
        )
        fact_ids = _ok(response)["fact_ids"]

        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind-compact_memories", "arguments": {
                "entry_ids": [entry_id],
                "summary": f"{marker} compacted summary for lookup",
            }},
        )
        summary_id = _ok(response)["summary_id"]

        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind-search_memories", "arguments": {
                "query": marker,
                "scope": "global",
                "level": "all",
                "limit": 10,
            }},
        )
        data = _ok(response)
        levels = {item["level"] for item in data["results"]}
        assert "L0" in levels
        assert "L1" in levels
        assert "L2" in levels
    finally:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                if fact_ids:
                    await db.execute(delete(MemoryFact).where(MemoryFact.id.in_([uuid.UUID(item) for item in fact_ids])))
                if summary_id:
                    await db.execute(delete(MemorySummary).where(MemorySummary.id == uuid.UUID(summary_id)))
                if entry_id:
                    await db.execute(delete(MemoryEntry).where(MemoryEntry.id == uuid.UUID(entry_id)))
                if session_id:
                    await db.execute(delete(MemorySession).where(MemorySession.id == uuid.UUID(session_id)))