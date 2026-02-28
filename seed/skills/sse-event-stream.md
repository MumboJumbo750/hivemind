---
title: "SSE Event-Stream & Event-Bus"
service_scope: ["backend", "frontend"]
stack: ["python", "fastapi", "vue", "typescript"]
version_range: { "python": ">=3.11", "fastapi": ">=0.100" }
confidence: 0.5
source_epics: ["EPIC-PHASE-F"]
guards:
  - title: "Python Linting"
    command: "ruff check ."
  - title: "Type Check Backend"
    command: "mypy app/"
  - title: "Type Check Frontend"
    command: "npx vue-tsc --noEmit"
  - title: "Tests"
    command: "pytest tests/ -v"
---

## Skill: SSE Event-Stream & Event-Bus

### Rolle
Du implementierst Server-Sent Events (SSE) für Echtzeit-Notifications im Hivemind-System — Backend-Event-Bus + SSE-Endpoint + Frontend-EventSource-Client.

### Konventionen

#### Backend
- SSE-Endpoint als `StreamingResponse` mit `text/event-stream` Content-Type
- In-Memory Event-Bus über `asyncio.Queue` — eine Queue pro verbundenem Client
- Event-Bus als Singleton-Service (`app/services/event_bus.py`)
- Event-Format: `event: {type}\ndata: {json}\n\n`
- Heartbeat: alle 30s ein `:keepalive\n\n` Comment senden (verhindert Proxy-Timeouts)
- Client-Disconnect: Queue aufräumen (kein Memory Leak)

#### Frontend
- `EventSource` API für SSE-Verbindung
- Reconnect mit exponential Backoff bei Verbindungsabbruch
- Events an Pinia Store dispatchen für reaktive UI-Updates
- Toast-Notifications für relevante Events

### Beispiel — Event-Bus (Backend)

```python
import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

@dataclass
class EventBus:
    """In-Memory Event-Bus für SSE-Clients."""
    _subscribers: list[asyncio.Queue] = field(default_factory=list)

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.remove(queue)

    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        payload = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        for queue in self._subscribers:
            await queue.put(payload)

event_bus = EventBus()
```

### Beispiel — SSE-Endpoint (Backend)

```python
import asyncio

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.services.event_bus import event_bus

router = APIRouter(tags=["events"])

@router.get("/api/events")
async def sse_stream():
    queue = event_bus.subscribe()
    try:
        async def generate():
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield payload
                except asyncio.TimeoutError:
                    yield ":keepalive\n\n"
        return StreamingResponse(generate(), media_type="text/event-stream")
    except asyncio.CancelledError:
        event_bus.unsubscribe(queue)
        raise
```

### Beispiel — EventSource-Client (Frontend)

```typescript
import { ref } from 'vue'

const BASE_URL = import.meta.env.VITE_API_URL ?? ''

export function useSSE() {
  const connected = ref(false)
  let eventSource: EventSource | null = null
  let retryDelay = 1000

  function connect() {
    eventSource = new EventSource(`${BASE_URL}/api/events`)

    eventSource.onopen = () => {
      connected.value = true
      retryDelay = 1000 // Reset backoff
    }

    eventSource.onerror = () => {
      connected.value = false
      eventSource?.close()
      // Exponential backoff: 1s, 2s, 4s, 8s, max 30s
      setTimeout(connect, retryDelay)
      retryDelay = Math.min(retryDelay * 2, 30_000)
    }

    eventSource.addEventListener('node_status', (e) => {
      const data = JSON.parse(e.data)
      // → Pinia Store update + Toast
    })

    eventSource.addEventListener('federation_skill', (e) => {
      const data = JSON.parse(e.data)
      // → Toast: "Neuer Skill von [node-name]: [title]"
    })
  }

  function disconnect() {
    eventSource?.close()
    connected.value = false
  }

  return { connected, connect, disconnect }
}
```

### Wichtig
- Event-Bus ist In-Memory — bei Server-Restart gehen gepufferte Events verloren (akzeptabel)
- Queue-Cleanup bei Client-Disconnect ist kritisch (Memory Leak verhindern)
- Frontend muss Reconnect mit Backoff implementieren (kein sofortiger Retry-Storm)
- SSE ist unidirektional (Server → Client) — für Client → Server: REST-Calls verwenden
