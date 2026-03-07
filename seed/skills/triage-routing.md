---
title: "Triage-Routing & Event-Klassifizierung"
service_scope: ["backend"]
stack: ["python", "fastapi", "sqlalchemy"]
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

## Skill: Triage-Routing & Event-Klassifizierung

### Rolle
Du implementierst die Triage-Logik — das Routing von `[UNROUTED]` Events aus der `sync_outbox` zu Epics/Tasks. Die MCP-Write-Tools `hivemind-route_event` und `hivemind-ignore_event` ermöglichen manuelle Triage-Entscheidungen.

### Konventionen
- Service: `app/services/triage_service.py`
- MCP-Tools: `hivemind-route_event`, `hivemind-ignore_event` (admin-only, `triage`-Permission)
- MCP-Read: `hivemind-get_triage { "state": "unrouted|escalated|dead|all" }`
- Routing-States in `sync_outbox.routing_state`:
  - `unrouted` — neu eingetroffen, noch nicht zugeordnet
  - `routed` — einem Epic/Task zugeordnet
  - `ignored` — bewusst verworfen (kein Handlungsbedarf)
  - `escalated` — automatisch eskaliert (SLA, ab Phase 6)
  - `dead` — Dead Letter (DLQ, ab Phase 7)
- Jede Routing-Entscheidung wird im Audit-Log protokolliert
- Triage-Events über SSE-Kanal `/events/triage` an Frontend gestreamt

### Beispiel — Route-Event MCP-Tool

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.models.sync_outbox import SyncOutbox

async def handle_route_event(arguments: dict, db: AsyncSession, actor_id: str) -> dict:
    event_id = arguments["event_id"]
    target_epic_id = arguments["epic_id"]

    # Event laden
    stmt = select(SyncOutbox).where(
        SyncOutbox.id == event_id,
        SyncOutbox.routing_state == "unrouted",
    )
    event = (await db.execute(stmt)).scalar_one_or_none()
    if not event:
        return {"error": "Event nicht gefunden oder bereits geroutet"}

    # Routing setzen
    event.routing_state = "routed"
    event.routed_to_epic_id = target_epic_id
    event.routed_by = actor_id
    event.routed_at = datetime.utcnow()

    # Audit-Log
    await audit_log(db, "route_event", actor_id, {
        "event_id": str(event_id),
        "epic_id": target_epic_id,
    })

    # SSE-Event publizieren
    await event_bus.publish("triage_routed", {
        "event_id": str(event_id),
        "epic_id": target_epic_id,
    })

    await db.commit()
    return {"status": "routed", "event_id": str(event_id)}
```

### Beispiel — Ignore-Event MCP-Tool

```python
async def handle_ignore_event(arguments: dict, db: AsyncSession, actor_id: str) -> dict:
    event_id = arguments["event_id"]
    reason = arguments.get("reason", "")

    stmt = select(SyncOutbox).where(
        SyncOutbox.id == event_id,
        SyncOutbox.routing_state == "unrouted",
    )
    event = (await db.execute(stmt)).scalar_one_or_none()
    if not event:
        return {"error": "Event nicht gefunden oder bereits geroutet"}

    event.routing_state = "ignored"
    event.ignored_reason = reason

    await audit_log(db, "ignore_event", actor_id, {
        "event_id": str(event_id),
        "reason": reason,
    })

    await event_bus.publish("triage_ignored", {"event_id": str(event_id)})
    await db.commit()
    return {"status": "ignored", "event_id": str(event_id)}
```

### Wichtig
- Phase 1-3: Alles manuelles Routing (kein Auto-Routing)
- Ab Phase 7: pgvector-Similarity ermöglicht Routing-Vorschläge (Precision >= 85% Ziel-KPI)
- Triage Station (Frontend) zeigt `[UNROUTED]`-Items mit "Warum jetzt?"-Badges: `ESCALATED`, `DECISION OFFEN`, `SLA <4h`, `FOLLOW-UP`
- Federation-Events (discovery_session, peer_online, peer_offline, federation_error) erscheinen ebenfalls in der Triage
