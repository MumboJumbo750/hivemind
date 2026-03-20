from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import delete

from app.db import AsyncSessionLocal
from app.models.memory import MemoryEntry, MemorySession, MemorySummary


@pytest.mark.asyncio
async def test_memory_router_lists_entries_sessions_and_summaries(client) -> None:
    session_id: uuid.UUID | None = None
    entry_id: uuid.UUID | None = None
    summary_id: uuid.UUID | None = None
    actor_id = uuid.UUID('00000000-0000-0000-0000-000000000001')
    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                session = MemorySession(actor_id=actor_id, agent_role='admin', scope='global', scope_id=None, entry_count=1, compacted=True)
                db.add(session)
                await db.flush()
                entry = MemoryEntry(actor_id=actor_id, agent_role='admin', scope='global', scope_id=None, session_id=session.id, content='router-test entry', tags=['router'])
                db.add(entry)
                await db.flush()
                summary = MemorySummary(actor_id=actor_id, agent_role='admin', scope='global', scope_id=None, session_id=session.id, content='router-test summary', source_entry_ids=[entry.id], source_fact_ids=[], source_count=1, open_questions=['still open'], graduated=False)
                db.add(summary)
                await db.flush()
                entry.covered_by = summary.id
                session_id = session.id
                entry_id = entry.id
                summary_id = summary.id

        sessions_resp = await client.get('/api/admin/memory/sessions')
        assert sessions_resp.status_code == 200
        assert any(item['id'] == str(session_id) for item in sessions_resp.json()['data'])

        entries_resp = await client.get('/api/admin/memory/entries')
        assert entries_resp.status_code == 200
        assert any(item['id'] == str(entry_id) for item in entries_resp.json()['data'])

        summaries_resp = await client.get('/api/admin/memory/summaries')
        assert summaries_resp.status_code == 200
        assert any(item['id'] == str(summary_id) for item in summaries_resp.json()['data'])
    finally:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                if summary_id:
                    await db.execute(delete(MemorySummary).where(MemorySummary.id == summary_id))
                if entry_id:
                    await db.execute(delete(MemoryEntry).where(MemoryEntry.id == entry_id))
                if session_id:
                    await db.execute(delete(MemorySession).where(MemorySession.id == session_id))


@pytest.mark.asyncio
async def test_search_memories_returns_semantic_memory_results(client) -> None:
    entry_id: str | None = None
    session_id: str | None = None
    try:
        create_resp = await client.post(
            '/api/mcp/call',
            json={
                'tool': 'hivemind-save_memory',
                'arguments': {'scope': 'global', 'content': 'semantic router signal for memory search', 'tags': ['semantic']},
            },
        )
        payload = create_resp.json()['result'][0]['text']
        data = json.loads(payload)['data']
        entry_id = data['entry_id']
        session_id = data['session_id']

        async def fake_search_similar(db, table, query_text, limit=5, candidate_ids=None):
            if table == 'memory_entries':
                return [{'id': entry_id, 'similarity': 0.93}]
            return []

        class FakeService:
            search_similar = staticmethod(fake_search_similar)

        from unittest.mock import patch

        with patch('app.services.embedding_service.get_embedding_service', return_value=FakeService()):
            search_resp = await client.post(
                '/api/mcp/call',
                json={'tool': 'hivemind-search_memories', 'arguments': {'query': 'semantic signal', 'scope': 'global', 'level': 'L0', 'limit': 10}},
            )

        result_payload = json.loads(search_resp.json()['result'][0]['text'])['data']
        assert any(item['id'] == entry_id and item['search_mode'] in {'semantic', 'hybrid'} for item in result_payload['results'])
    finally:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                if entry_id:
                    await db.execute(delete(MemoryEntry).where(MemoryEntry.id == uuid.UUID(entry_id)))
                if session_id:
                    await db.execute(delete(MemorySession).where(MemorySession.id == uuid.UUID(session_id)))


@pytest.mark.asyncio
async def test_search_memories_respects_tag_filtered_semantic_candidates_and_ranks_hybrid_first(client) -> None:
    keep_entry_id: str | None = None
    plain_entry_id: str | None = None
    session_ids: list[str] = []
    seen_candidate_ids: list[str] | None = None
    try:
        keep_resp = await client.post(
            '/api/mcp/call',
            json={
                'tool': 'hivemind-save_memory',
                'arguments': {'scope': 'global', 'content': 'hybrid ranking candidate for semantic signal', 'tags': ['keep', 'semantic']},
            },
        )
        keep_data = json.loads(keep_resp.json()['result'][0]['text'])['data']
        keep_entry_id = keep_data['entry_id']
        session_ids.append(keep_data['session_id'])

        plain_resp = await client.post(
            '/api/mcp/call',
            json={
                'tool': 'hivemind-save_memory',
                'arguments': {'scope': 'global', 'content': 'semantic signal plain text match', 'tags': ['plain']},
            },
        )
        plain_data = json.loads(plain_resp.json()['result'][0]['text'])['data']
        plain_entry_id = plain_data['entry_id']
        session_ids.append(plain_data['session_id'])

        async def fake_search_similar(db, table, query_text, limit=5, candidate_ids=None):
            nonlocal seen_candidate_ids
            seen_candidate_ids = candidate_ids
            assert table == 'memory_entries'
            return [{'id': keep_entry_id, 'similarity': 0.91}]

        class FakeService:
            search_similar = staticmethod(fake_search_similar)

        from unittest.mock import patch

        with patch('app.services.embedding_service.get_embedding_service', return_value=FakeService()):
            search_resp = await client.post(
                '/api/mcp/call',
                json={
                    'tool': 'hivemind-search_memories',
                    'arguments': {'query': 'semantic signal', 'scope': 'global', 'level': 'L0', 'tags': ['keep'], 'limit': 10},
                },
            )

        result_payload = json.loads(search_resp.json()['result'][0]['text'])['data']
        assert seen_candidate_ids == [keep_entry_id]
        assert result_payload['results'][0]['id'] == keep_entry_id
        assert result_payload['results'][0]['search_mode'] == 'hybrid'
        assert all(item['id'] != plain_entry_id for item in result_payload['results'])
    finally:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                if keep_entry_id:
                    await db.execute(delete(MemoryEntry).where(MemoryEntry.id == uuid.UUID(keep_entry_id)))
                if plain_entry_id:
                    await db.execute(delete(MemoryEntry).where(MemoryEntry.id == uuid.UUID(plain_entry_id)))
                for session_id in session_ids:
                    await db.execute(delete(MemorySession).where(MemorySession.id == uuid.UUID(session_id)))


@pytest.mark.asyncio
async def test_search_memories_falls_back_to_text_results_when_semantic_search_fails(client) -> None:
    entry_id: str | None = None
    session_id: str | None = None
    try:
        create_resp = await client.post(
            '/api/mcp/call',
            json={
                'tool': 'hivemind-save_memory',
                'arguments': {'scope': 'global', 'content': 'degraded semantic search keeps text results stable', 'tags': ['degraded']},
            },
        )
        data = json.loads(create_resp.json()['result'][0]['text'])['data']
        entry_id = data['entry_id']
        session_id = data['session_id']

        async def failing_search_similar(db, table, query_text, limit=5, candidate_ids=None):
            raise RuntimeError('embedding backend unavailable')

        class FakeService:
            search_similar = staticmethod(failing_search_similar)

        from unittest.mock import patch

        with patch('app.services.embedding_service.get_embedding_service', return_value=FakeService()):
            search_resp = await client.post(
                '/api/mcp/call',
                json={'tool': 'hivemind-search_memories', 'arguments': {'query': 'keeps text results', 'scope': 'global', 'level': 'L0', 'limit': 10}},
            )

        assert search_resp.status_code == 200
        result_payload = json.loads(search_resp.json()['result'][0]['text'])['data']
        assert any(item['id'] == entry_id and item['search_mode'] == 'text' for item in result_payload['results'])
    finally:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                if entry_id:
                    await db.execute(delete(MemoryEntry).where(MemoryEntry.id == uuid.UUID(entry_id)))
                if session_id:
                    await db.execute(delete(MemorySession).where(MemorySession.id == uuid.UUID(session_id)))