"""Enhanced SSE Event-Bus with channels, event IDs, and heartbeat — TASK-3-013.

Extends the Phase-F event bus with:
- Dedicated channels: notifications, tasks, triage
- Monotonically increasing event IDs for Last-Event-ID reconnect
- Per-channel subscription
- Stream-Token validation (short-lived 60s tokens)
- Heartbeat (15s keepalive)
"""
from __future__ import annotations

import asyncio
import itertools
import json
import logging
import secrets
import time
from typing import Any

logger = logging.getLogger(__name__)

# ── Event ID counter ──────────────────────────────────────────────────────
_event_id_counter = itertools.count(1)

# ── Channel definitions ───────────────────────────────────────────────────
CHANNELS = {"notifications", "tasks", "triage"}

# Canonical event types
EVENT_TYPES = {
    "task_state_changed",
    "task_assigned",
    "notification_created",
    "triage_routed",
    "triage_ignored",
    "triage_dlq_updated",
    "dlq_requeued",
    "dlq_discarded",
    "node_status",
    "federation_skill",
}

# ── Per-channel subscribers ───────────────────────────────────────────────
_channel_subscribers: dict[str, list[asyncio.Queue]] = {ch: [] for ch in CHANNELS}

# Global subscribers (legacy — receive ALL events)
_global_subscribers: list[asyncio.Queue] = []


# ── Stream tokens (short-lived, 60s TTL) ─────────────────────────────────
_stream_tokens: dict[str, float] = {}  # token → expiry timestamp


def generate_stream_token() -> str:
    """Generate a short-lived stream token (60s TTL)."""
    token = secrets.token_urlsafe(32)
    _stream_tokens[token] = time.time() + 60.0
    # Cleanup expired tokens
    now = time.time()
    expired = [t for t, exp in _stream_tokens.items() if exp < now]
    for t in expired:
        _stream_tokens.pop(t, None)
    return token


def validate_stream_token(token: str) -> bool:
    """Validate a stream token. Returns True if valid and not expired."""
    expiry = _stream_tokens.pop(token, None)  # one-time use
    if expiry is None:
        return False
    return time.time() < expiry


def subscribe(channel: str | None = None) -> asyncio.Queue:
    """Register a new SSE client. If channel is None, subscribe to all events."""
    q: asyncio.Queue = asyncio.Queue(maxsize=256)
    if channel is None:
        _global_subscribers.append(q)
    else:
        if channel not in CHANNELS:
            raise ValueError(f"Unknown channel: {channel}. Valid: {CHANNELS}")
        _channel_subscribers[channel].append(q)
    return q


def unsubscribe(q: asyncio.Queue, channel: str | None = None) -> None:
    """Remove an SSE client queue."""
    if channel is None:
        try:
            _global_subscribers.remove(q)
        except ValueError:
            pass
    else:
        try:
            _channel_subscribers.get(channel, []).remove(q)
        except ValueError:
            pass


def publish(event_type: str, data: dict[str, Any], channel: str | None = None) -> None:
    """Broadcast an event to subscribers.

    If channel is specified, sends to channel subscribers + global subscribers.
    If channel is None, sends to global subscribers only.
    """
    event_id = next(_event_id_counter)
    msg = {"event": event_type, "data": data, "id": event_id}

    targets: list[asyncio.Queue] = list(_global_subscribers)
    if channel and channel in _channel_subscribers:
        targets.extend(_channel_subscribers[channel])

    for q in targets:
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            pass  # slow client — drop event
