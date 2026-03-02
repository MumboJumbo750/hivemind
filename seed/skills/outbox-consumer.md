---
title: "Outbox-Pattern & Consumer"
service_scope: ["backend"]
stack: ["python", "sqlalchemy", "httpx"]
version_range: { "python": ">=3.11" }
confidence: 0.9
source_epics: ["EPIC-PHASE-F"]
guards:
  - title: "Python Linting"
    command: "ruff check ."
  - title: "Type Check"
    command: "mypy app/"
  - title: "Tests"
    command: "pytest tests/ -v"
---

## Skill: Outbox-Pattern & Consumer

### Rolle
Du implementierst das Outbox-Pattern für zuverlässige asynchrone Zustellung von Events im Hivemind-Backend.
Es gibt drei Consumer-Typen:

| Consumer | Richtung | Funktion |
|---|---|---|
| `process_outbox()` | `peer_outbound` | Federation-Events an Peer-Nodes |
| `process_outbound()` | `outbound` | YouTrack/Sentry Sync (extern) |
| `process_inbound()` | `inbound` | Webhooks von YouTrack/Sentry verarbeiten |

### State-Konventionen (KRITISCH)

- **Nur zwei gültige `state`-Werte:** `'pending'` und `'dead_letter'`
- Kein `'delivered'`, `'failed'`, `'dead'`
- **Outbound-Erfolg:** `db.delete(entry)` — Eintrag wird gelöscht
- **Inbound-Erfolg:** `entry.routing_state = 'routed'` — Eintrag bleibt als Audit-Record
- **DLQ:** `entry.state = 'dead_letter'` + neuen `SyncDeadLetter`-Eintrag anlegen — Outbox-Eintrag bleibt

### Beispiel — Outbox-Eintrag anlegen (im Service-Layer)

```python
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync import SyncOutbox


async def enqueue_federation_event(
    session: AsyncSession,
    entity_type: str,
    target_node_id: UUID,
    payload: dict,
    dedup_key: str,
) -> SyncOutbox:
    """Legt einen Outbox-Eintrag für einen Peer an. Innerhalb bestehender Transaktion aufrufen."""
    entry = SyncOutbox(
        direction="peer_outbound",
        system="federation",
        entity_type=entity_type,
        target_node_id=target_node_id,
        payload=payload,
        dedup_key=dedup_key,
        attempts=0,
        state="pending",
    )
    session.add(entry)
    # Kein commit — wird von der umgebenden Transaktion committed
    return entry
```

### Beispiel — Outbox-Consumer (Scheduled Job)

```python
import logging

from sqlalchemy import select

from app.config import settings
from app.db import AsyncSessionLocal
from app.models.sync import SyncDeadLetter, SyncOutbox

logger = logging.getLogger(__name__)

BATCH_SIZE = 50


async def process_outbox():
    """Verarbeitet ausstehende peer_outbound Outbox-Einträge."""
    if not settings.hivemind_federation_enabled:
        return

    async with AsyncSessionLocal() as db:
        stmt = (
            select(SyncOutbox)
            .where(
                SyncOutbox.direction == "peer_outbound",
                SyncOutbox.state == "pending",
                SyncOutbox.attempts < settings.hivemind_dlq_max_attempts,
            )
            .order_by(SyncOutbox.created_at.asc())
            .limit(BATCH_SIZE)
        )
        entries = list((await db.execute(stmt)).scalars().all())

        for entry in entries:
            try:
                await _send_to_peer(entry)
                await db.delete(entry)  # Erfolg: Eintrag löschen
            except Exception as exc:
                entry.attempts += 1
                if entry.attempts >= settings.hivemind_dlq_max_attempts:
                    dead = SyncDeadLetter(
                        outbox_id=entry.id,
                        system=entry.system,
                        entity_type=entry.entity_type,
                        entity_id=entry.entity_id,
                        payload=entry.payload,
                        error=str(exc),
                    )
                    db.add(dead)
                    entry.state = "dead_letter"  # Eintrag BLEIBT, State auf dead_letter
                    logger.error("Outbox → DLQ: %s — %s", entry.id, exc)
                else:
                    logger.warning("Outbox retry %d/%d: %s", entry.attempts, settings.hivemind_dlq_max_attempts, exc)

        await db.commit()
```

### Beispiel — Publish-Trigger (Service-Layer-Hook)

```python
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.federation import Node


async def publish_skill_to_federation(session: AsyncSession, skill_id: UUID, skill_payload: dict):
    """Legt Outbox-Einträge für alle aktiven Peers an (Fan-out)."""
    peers = (await session.execute(
        select(Node).where(Node.status == "active", Node.is_self == False)
    )).scalars().all()

    for peer in peers:
        await enqueue_federation_event(
            session=session,
            entity_type="skill_published",
            target_node_id=peer.id,
            payload=skill_payload,
            dedup_key=f"skill:{skill_id}:{peer.id}",
        )
```

### Wichtig
- Outbox-Einträge **immer** in der gleichen Transaktion wie die Business-Operation anlegen
- Consumer erzeugt eigene DB-Session via `AsyncSessionLocal()` (läuft im Scheduler, nicht im Request)
- DLQ-Einträge behalten den vollständigen `payload` für manuelles Replay
- `dedup_key` verhindert doppelte Outbox-Einträge bei wiederholten Trigger-Aufrufen
- Fan-out: ein Eintrag pro Peer-Node, nicht ein Eintrag für alle Peers
- Backoff: `min(2 ** attempts * 60, MAX_BACKOFF_SECONDS)` Sekunden, gesetzt in `next_retry_at`
