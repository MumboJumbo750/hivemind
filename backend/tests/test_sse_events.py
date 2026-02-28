"""Tests for event bus + SSE endpoint — TASK-F-015."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.event_bus import publish, subscribe, unsubscribe


# ─── Event Bus Unit Tests ────────────────────────────────────────────────────

def test_subscribe_and_publish():
    """Published events arrive in the subscriber's queue."""
    q = subscribe()
    try:
        publish("node_status", {"node_id": "abc", "status": "active"})
        assert not q.empty()
        msg = q.get_nowait()
        assert msg["event"] == "node_status"
        assert msg["data"]["status"] == "active"
    finally:
        unsubscribe(q)


def test_unsubscribe():
    """After unsubscribe, no more events are received."""
    q = subscribe()
    unsubscribe(q)
    publish("node_status", {"node_id": "abc", "status": "active"})
    assert q.empty()


def test_publish_multiple_subscribers():
    """Multiple subscribers all receive the same event."""
    q1 = subscribe()
    q2 = subscribe()
    try:
        publish("federation_skill", {"skill_id": "s1", "title": "Test"})
        assert not q1.empty()
        assert not q2.empty()
        msg1 = q1.get_nowait()
        msg2 = q2.get_nowait()
        assert msg1 == msg2
    finally:
        unsubscribe(q1)
        unsubscribe(q2)


def test_publish_full_queue():
    """When a queue is full, the event is silently dropped (no exception)."""
    q = subscribe()
    try:
        # Fill the queue to capacity (256)
        for i in range(256):
            publish("test", {"i": i})
        # This should not raise
        publish("test", {"i": 999})
        assert q.qsize() == 256
    finally:
        unsubscribe(q)


# ─── SSE Endpoint Tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sse_endpoint_returns_streaming():
    """SSE endpoint returns a StreamingResponse."""
    from app.routers.events import sse_events

    resp = await sse_events()
    assert resp.media_type == "text/event-stream"
    assert resp.headers.get("Cache-Control") == "no-cache"


@pytest.mark.asyncio
async def test_sse_receives_published_event():
    """SSE stream yields events published on the bus."""
    from app.routers.events import sse_events
    from app.services.event_bus import publish, subscribe, unsubscribe

    resp = await sse_events()
    gen = resp.body_iterator

    # Give the generator a moment to start its wait_for loop,
    # then publish while it's blocked waiting
    async def delayed_publish():
        await asyncio.sleep(0.1)
        publish("node_status", {"node_id": "x", "node_name": "alpha", "status": "active", "last_seen": None})

    # Schedule both in parallel
    pub_task = asyncio.create_task(delayed_publish())
    chunk = await gen.__anext__()
    await pub_task

    assert "event: node_status" in chunk
    assert '"node_name": "alpha"' in chunk or '"node_name":"alpha"' in chunk

    # Cleanup
    await gen.aclose()
