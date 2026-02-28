"""SSE (Server-Sent Events) endpoints — TASK-F-015 + TASK-3-013.

Three dedicated channels:
  - /events/notifications — general notifications
  - /events/tasks — task state changes
  - /events/triage — triage events

Plus legacy /events — all events (backward compat).
Stream-Token handshake via POST /api/auth/stream-token (60s TTL).
Heartbeat every 15s.
"""
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from starlette.responses import StreamingResponse

from app.routers.deps import CurrentActor, get_current_actor
from app.services.event_bus import (
    CHANNELS,
    generate_stream_token,
    subscribe,
    unsubscribe,
    validate_stream_token,
)

router = APIRouter(tags=["events"])


async def _sse_generator(channel: str | None = None, heartbeat_sec: float = 15.0):
    """Create an SSE event generator for a specific channel or all events."""
    q = subscribe(channel)
    try:
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=heartbeat_sec)
                event_type = msg["event"]
                data = json.dumps(msg["data"])
                event_id = msg.get("id", "")
                yield f"event: {event_type}\ndata: {data}\nid: {event_id}\n\n"
            except asyncio.TimeoutError:
                yield ":keepalive\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        unsubscribe(q, channel)


def _sse_response(channel: str | None = None):
    return StreamingResponse(
        _sse_generator(channel),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Stream Token ──────────────────────────────────────────────────────────

@router.post("/auth/stream-token")
async def create_stream_token(actor: CurrentActor = Depends(get_current_actor)):
    """Generate a short-lived stream token (60s TTL) for SSE connections."""
    token = generate_stream_token()
    return {"stream_token": token, "ttl": 60}


# ── Channel SSE endpoints ─────────────────────────────────────────────────

@router.get("/events/notifications")
async def sse_notifications(
    stream_token: str = Query(None),
    actor: CurrentActor = Depends(get_current_actor),
):
    """SSE stream for notification events."""
    return _sse_response("notifications")


@router.get("/events/tasks")
async def sse_tasks(
    stream_token: str = Query(None),
    actor: CurrentActor = Depends(get_current_actor),
):
    """SSE stream for task state change events."""
    return _sse_response("tasks")


@router.get("/events/triage")
async def sse_triage(
    stream_token: str = Query(None),
    actor: CurrentActor = Depends(get_current_actor),
):
    """SSE stream for triage events."""
    return _sse_response("triage")


# ── Legacy global endpoint (backward compat) ──────────────────────────────

@router.get("/events")
async def sse_events():
    """Server-Sent Events stream — all events (legacy, backward compat)."""
    return _sse_response(None)
