---
title: "Webhook-Ingest (YouTrack/Sentry)"
service_scope: ["backend"]
stack: ["python", "fastapi", "pydantic"]
version_range: { "python": ">=3.11", "fastapi": ">=0.100" }
confidence: 0.5
source_epics: ["EPIC-PHASE-3"]
guards:
  - title: "Python Linting"
    command: "ruff check ."
  - title: "Type Check"
    command: "mypy app/"
  - title: "Tests"
    command: "pytest tests/ -v"
---

## Skill: Webhook-Ingest (YouTrack/Sentry)

### Rolle
Du implementierst Webhook-Endpoints die externe Events (YouTrack, Sentry) empfangen, validieren und als `direction='inbound'` Einträge in die `sync_outbox` schreiben. Die Events werden als `[UNROUTED]` markiert für die Triage Station.

### Konventionen
- Router: `app/routers/webhooks.py` mit Prefix `/api/webhooks`
- Endpoints: `POST /api/webhooks/youtrack`, `POST /api/webhooks/sentry`
- Webhook-Secret-Validierung: HMAC-SHA256 Signatur im Header prüfen
- Payload-Normalisierung: Rohes Webhook-JSON → normalisiertes internes Format
- Speicherung in `sync_outbox`:
  - `direction = 'inbound'`
  - `event_type = 'youtrack_issue_update' | 'sentry_error' | ...`
  - `routing_state = 'unrouted'` (Default für inbound)
  - `payload` = normalisiertes JSON
  - `raw_payload` = Original-Webhook-Body (für Debugging)
- Idempotenz: `idempotency_key` aus Webhook-Event-ID (Duplikate → Skip mit 200 OK)
- Rate-Limiting: Optional via Middleware (schutz gegen Webhook-Spam)

### Beispiel — Webhook-Endpoint

```python
import hashlib
import hmac

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.config import settings

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

@router.post("/youtrack")
async def youtrack_webhook(
    request: Request,
    x_hub_signature: str = Header(None),
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()

    # Signatur prüfen
    if settings.youtrack_webhook_secret:
        expected = hmac.new(
            settings.youtrack_webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(f"sha256={expected}", x_hub_signature or ""):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")

    payload = await request.json()
    event_id = payload.get("id") or payload.get("timestamp")

    # Idempotenz-Check
    existing = await check_idempotency(db, f"youtrack:{event_id}")
    if existing:
        return {"status": "duplicate", "id": str(existing.id)}

    # In sync_outbox schreiben
    entry = SyncOutbox(
        direction="inbound",
        event_type="youtrack_issue_update",
        routing_state="unrouted",
        payload=normalize_youtrack(payload),
        raw_payload=payload,
        idempotency_key=f"youtrack:{event_id}",
    )
    db.add(entry)
    await db.commit()

    return {"status": "accepted", "id": str(entry.id)}
```

### Beispiel — Payload-Normalisierung

```python
def normalize_youtrack(raw: dict) -> dict:
    """YouTrack-Webhook-Payload in internes Format normalisieren."""
    return {
        "source": "youtrack",
        "external_id": raw.get("issue", {}).get("id"),
        "summary": raw.get("issue", {}).get("summary"),
        "state": raw.get("issue", {}).get("state", {}).get("name"),
        "updated_by": raw.get("updatedBy", {}).get("login"),
        "changes": raw.get("fieldChanges", []),
        "timestamp": raw.get("timestamp"),
    }
```

### Wichtig
- Phase 1-2: Alle inbound Events sind `[UNROUTED]` (kein automatisches Routing)
- Ab Phase 7: pgvector-basiertes Auto-Routing ordnet Events automatisch Epics zu
- Webhook-Secrets werden über Env-Variablen konfiguriert (`HIVEMIND_YOUTRACK_WEBHOOK_SECRET`, `HIVEMIND_SENTRY_WEBHOOK_SECRET`)
- Raw-Payload wird für Dead Letter Queue (DLQ) Debugging aufbewahrt
