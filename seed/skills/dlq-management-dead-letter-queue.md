---
title: DLQ-Management (Dead Letter Queue)
service_scope:
- backend
stack:
- python
- fastapi
- sqlalchemy
- postgresql
confidence: 0.5
source_epics:
- EPIC-PHASE-7
---

## Skill: DLQ-Management (Dead Letter Queue)

### Rolle
Du implementierst DLQ-Verwaltung für fehlgeschlagene Outbox-Einträge im Hivemind-Backend. Dead Letters entstehen wenn ein Outbox-Consumer nach max_attempts (Default: 5) scheitert.

### Konventionen
- Tabelle: `sync_dead_letter` — persistiert fehlgeschlagene Events mit vollem Payload
- Felder: `outbox_id`, `system`, `entity_type`, `entity_id`, `payload`, `error`, `created_at`
- Requeue: Dead Letter → zurück in `sync_outbox` mit `state='pending'`, `attempts=0`
- Discard: Dead Letter → `state='discarded'` (soft-delete, bleibt für Audit)
- MCP-Tools: `hivemind-requeue_dead_letter`, `hivemind-discard_dead_letter`
- REST-Alias: `POST /api/triage/dead-letters/{id}/requeue`, `POST /api/triage/dead-letters/{id}/discard`
- Permission: `admin` oder `triage` Rolle
- Jede DLQ-Aktion wird in `mcp_invocations` geloggt (Audit)
- SSE-Event bei DLQ-Änderung: `triage_dlq_updated`

### DLQ-Eintrag anlegen (im Outbox-Consumer)

```python
async def _move_to_dlq(db: AsyncSession, entry: SyncOutbox, error: str) -> None:
    dead_letter = SyncDeadLetter(
        outbox_id=entry.id,
        system=entry.system,
        entity_type=entry.entity_type,
        entity_id=entry.entity_id,
        payload=entry.payload,
        error=error,
    )
    db.add(dead_letter)
    entry.state = "dead_letter"
```

### Requeue-Service

```python
async def requeue_dead_letter(db: AsyncSession, dead_letter_id: UUID) -> dict:
    dl = await db.get(SyncDeadLetter, dead_letter_id)
    if not dl:
        raise HTTPException(404, "Dead letter not found")
    
    new_entry = SyncOutbox(
        direction=dl.direction or "outbound",
        system=dl.system,
        entity_type=dl.entity_type,
        entity_id=dl.entity_id,
        payload=dl.payload,
        state="pending",
        attempts=0,
    )
    db.add(new_entry)
    dl.state = "requeued"
    dl.requeued_at = datetime.utcnow()
    await db.commit()
    return {"status": "requeued", "new_outbox_id": str(new_entry.id)}
```

### Wichtig
- DLQ-Payloads enthalten den vollständigen Original-Payload (kein Datenverlust)
- Requeue setzt attempts auf 0 (frischer Retry-Zyklus)
- Discard ist soft-delete — Eintrag bleibt in der DB für Audit
- Frontend zeigt DLQ-Items in der Triage Station unter [DEAD LETTER]-Kategorie
- DLQ-Count wird im Sync-Status-Panel in Settings angezeigt
