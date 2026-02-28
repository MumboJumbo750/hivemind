---
title: "APScheduler-Job in FastAPI"
service_scope: ["backend"]
stack: ["python", "fastapi", "apscheduler"]
version_range: { "python": ">=3.11", "apscheduler": ">=3.10" }
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

## Skill: APScheduler-Job in FastAPI

### Rolle
Du implementierst periodische Background-Jobs im Hivemind-Backend mittels APScheduler, integriert in den FastAPI-Lifespan.

### Konventionen
- `AsyncIOScheduler` verwenden (kompatibel mit FastAPI async)
- Scheduler-Start/Stop im FastAPI `lifespan` Context Manager
- Ein gemeinsamer Scheduler für alle Jobs (kein Scheduler pro Job)
- Job-Intervalle über Environment-Variablen konfigurierbar
- Jobs müssen idempotent sein (kein Zustand zwischen Runs)
- Fehler in Jobs: loggen + weiterlaufen (kein Scheduler-Crash)
- Feature-Flag prüfen: Jobs nur registrieren wenn Feature aktiv (`HIVEMIND_FEDERATION_ENABLED`)

### Beispiel — Scheduler im FastAPI Lifespan

```python
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from app.config import settings

scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    if settings.federation_enabled:
        from app.services.outbox import process_outbox
        from app.services.heartbeat import check_peers

        scheduler.add_job(
            process_outbox,
            "interval",
            seconds=settings.outbox_interval,
            id="outbox_consumer",
            replace_existing=True,
        )
        scheduler.add_job(
            check_peers,
            "interval",
            seconds=settings.heartbeat_interval,
            id="heartbeat",
            replace_existing=True,
        )
        scheduler.start()

    yield

    # Shutdown
    if scheduler.running:
        scheduler.shutdown(wait=False)

app = FastAPI(lifespan=lifespan)
```

### Beispiel — Job-Funktion

```python
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session_factory

logger = logging.getLogger(__name__)

async def process_outbox():
    """Verarbeitet ausstehende Outbox-Einträge. Idempotent, fehlertolerant."""
    try:
        async with async_session_factory() as session:
            # Batch laden, verarbeiten, committen
            ...
    except Exception:
        logger.exception("Outbox processing failed")
```

### Wichtig
- `replace_existing=True` bei `add_job` verhindert Duplikate bei Restart
- Scheduler **nicht** in Tests starten — in `conftest.py` mocken oder überspringen
- Job-Funktionen erzeugen eigene DB-Sessions (nicht die Request-Session verwenden)
- Graceful Shutdown: `scheduler.shutdown(wait=False)` im Lifespan-Teardown
