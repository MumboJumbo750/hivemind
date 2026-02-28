---
title: "Async HTTP-Client mit httpx"
service_scope: ["backend"]
stack: ["python", "httpx"]
version_range: { "python": ">=3.11", "httpx": ">=0.25" }
confidence: 0.5
source_epics: ["EPIC-PHASE-F"]
guards:
  - title: "Python Linting"
    command: "ruff check ."
  - title: "Type Check"
    command: "mypy app/"
  - title: "Tests"
    command: "pytest tests/ -v"
---

## Skill: Async HTTP-Client mit httpx

### Rolle
Du implementierst ausgehende HTTP-Requests im Hivemind-Backend mit `httpx.AsyncClient` — primär für Federation-Kommunikation zwischen Peer-Nodes.

### Konventionen
- `httpx.AsyncClient` verwenden (nicht `requests` oder `aiohttp`)
- Client als Context Manager oder als Singleton mit Lifecycle-Management
- Timeouts explizit setzen (Default: 10s für Federation, 5s für Ping)
- Fehlerhandling: `httpx.HTTPStatusError`, `httpx.ConnectError`, `httpx.TimeoutException`
- Retry-Logik gehört in den Aufrufer (Outbox-Consumer), nicht in den Client
- Signed Requests: `X-Node-ID` + `X-Node-Signature` Header bei Federation-Calls
- Content-Type: `application/json`

### Beispiel — Federation-Request senden

```python
import httpx

from app.config import settings
from app.services.signing import sign_request

async def send_federation_request(
    peer_url: str,
    endpoint: str,
    payload: dict,
    node_id: str,
    private_pem: bytes,
) -> httpx.Response:
    """Sendet signierten HTTP POST an einen Peer-Node."""
    url = f"{peer_url.rstrip('/')}/federation/{endpoint}"
    body = httpx.Request("POST", url, json=payload).content

    signature = sign_request(body, private_pem, settings.key_passphrase)

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            url,
            json=payload,
            headers={
                "X-Node-ID": node_id,
                "X-Node-Signature": signature,
            },
        )
        response.raise_for_status()
        return response
```

### Beispiel — Ping mit kurzem Timeout

```python
import httpx
import logging

logger = logging.getLogger(__name__)

async def ping_peer(peer_url: str) -> dict | None:
    """Pingt einen Peer-Node. Gibt Response-Dict oder None bei Fehler zurück."""
    url = f"{peer_url.rstrip('/')}/federation/ping"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        logger.warning("Peer unreachable: %s — %s", peer_url, exc)
        return None
    except httpx.HTTPStatusError as exc:
        logger.warning("Peer error: %s — HTTP %d", peer_url, exc.response.status_code)
        return None
```

### Wichtig
- Ping-Requests werden **nicht** signiert (Ping-Endpoint ist öffentlich)
- Bei Verbindungsfehler: nie crashen, immer `None` oder Exception zurückgeben
- Payload als `json=` Parameter (nicht `content=`) für automatische Serialisierung
- `response.raise_for_status()` für sauberes Fehlerhandling
- In Tests: `httpx.MockTransport` oder `respx` für Request-Mocking
