---
title: "Outbox-Pattern & Consumer"
service_scope: ["backend"]
stack: ["python", "sqlalchemy", "httpx"]
version_range: { "python": ">=3.11" }
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

## Skill: Outbox-Pattern & Consumer

### Rolle
Du implementierst das Outbox-Pattern für zuverlässige asynchrone Zustellung von Federation-Events an Peer-Nodes im Hivemind-Backend.

### Konventionen
- **Outbox schreiben:** Innerhalb der gleichen DB-Transaktion wie die Business-Logik
- **Outbox lesen:** Im separaten Scheduled-Job (APScheduler, siehe `scheduled-job` Skill)
- Tabelle: `sync_outbox` mit `direction='peer_outbound'`
- Deduplizierung via `dedup_key` (z.B. `skill:{skill_id}:{peer_node_id}`)
- Batch-Verarbeitung: max 50 Einträge pro Run (konfigurierbar)
- Retry: `attempts` inkrementieren bei Fehler
- DLQ: nach `max_attempts` (Default: 5) → in `sync_dead_letter` verschieben
- Älteste Einträge zuerst (FIFO-Ordering)

### Beispiel — Outbox-Eintrag anlegen (im Service-Layer)

```python
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync import SyncOutbox

async def enqueue_federation_event(
    session: AsyncSession,
    event_type: str,
    target_node_id: UUID,
    payload: dict,
    dedup_key: str,
) -> SyncOutbox:
    """Legt einen Outbox-Eintrag für einen Peer an. Innerhalb bestehender Transaktion aufrufen."""
    entry = SyncOutbox(
        direction="peer_outbound",
        event_type=event_type,
        target_node_id=target_node_id,
        payload=payload,
        dedup_key=dedup_key,
        attempts=0,
    )
    session.add(entry)
    # Kein commit — wird von der umgebenden Transaktion committed
    return entry
```

### Beispiel — Outbox-Consumer (Scheduled Job)

```python
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import async_session_factory
from app.models.sync import SyncOutbox, SyncDeadLetter
from app.services.federation_client import send_federation_request

logger = logging.getLogger(__name__)

BATCH_SIZE = 50

async def process_outbox():
    """Verarbeitet ausstehende peer_outbound Outbox-Einträge."""
    async with async_session_factory() as session:
        stmt = (
            select(SyncOutbox)
            .where(SyncOutbox.direction == "peer_outbound")
            .where(SyncOutbox.attempts < settings.dlq_max_attempts)
            .order_by(SyncOutbox.created_at.asc())
            .limit(BATCH_SIZE)
        )
        entries = (await session.execute(stmt)).scalars().all()

        for entry in entries:
            try:
                await send_federation_request(
                    peer_url=entry.target_node.node_url,
                    endpoint=entry.event_type,
                    payload=entry.payload,
                )
                await session.delete(entry)
            except Exception as exc:
                entry.attempts += 1
                if entry.attempts >= settings.dlq_max_attempts:
                    dead = SyncDeadLetter(
                        original_id=entry.id,
                        direction=entry.direction,
                        event_type=entry.event_type,
                        payload=entry.payload,
                        last_error=str(exc),
                    )
                    session.add(dead)
                    await session.delete(entry)
                    logger.error("Outbox → DLQ: %s — %s", entry.id, exc)
                else:
                    logger.warning("Outbox retry %d/%d: %s", entry.attempts, settings.dlq_max_attempts, exc)

        await session.commit()
```

### Beispiel — Publish-Trigger (Service-Layer-Hook)

```python
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.node import Node

async def publish_skill_to_federation(session: AsyncSession, skill_id: UUID, skill_payload: dict):
    """Legt Outbox-Einträge für alle aktiven Peers an (Fan-out)."""
    peers = (await session.execute(
        select(Node).where(Node.status == "active", Node.is_self == False)
    )).scalars().all()

    for peer in peers:
        await enqueue_federation_event(
            session=session,
            event_type="skill/publish",
            target_node_id=peer.id,
            payload=skill_payload,
            dedup_key=f"skill:{skill_id}:{peer.id}",
        )
```

### Wichtig
- Outbox-Einträge **immer** in der gleichen Transaktion wie die Business-Operation anlegen
- Consumer erzeugt eigene DB-Session (läuft im Scheduler, nicht im Request)
- DLQ-Einträge behalten den vollständigen `payload` für manuelles Replay
- `dedup_key` verhindert doppelte Outbox-Einträge bei wiederholten Trigger-Aufrufen
- Fan-out: ein Eintrag pro Peer-Node, nicht ein Eintrag für alle Peers
