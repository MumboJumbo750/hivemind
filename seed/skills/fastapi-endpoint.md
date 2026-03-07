---
title: "FastAPI Endpoint erstellen"
service_scope: ["backend"]
stack: ["python", "fastapi", "sqlalchemy"]
version_range: { "python": ">=3.11", "fastapi": ">=0.100" }
confidence: 0.5
source_epics: ["EPIC-PHASE-1A"]
guards:
  - title: "Python Linting"
    command: "ruff check ."
  - title: "Type Check"
    command: "mypy app/"
---

## Skill: FastAPI Endpoint erstellen

### Rolle
Du erstellst einen neuen FastAPI-Endpoint für das Hivemind-Backend.

### Konventionen
- Router-Dateien liegen in `app/routers/`
- Pydantic v2 für Request/Response-Models in `app/schemas/`
- Service-Layer in `app/services/` — keine Business-Logik im Router
- Dependency Injection via `Depends()` für DB-Sessions
- Async/Await durchgängig (asyncpg)
- Response-Models explizit angeben (`response_model=...`)
- HTTP-Statuscodes korrekt: 201 für Create, 200 für Read/Update, 204 für Delete

### Beispiel

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas.task import TaskCreate, TaskResponse
from app.services.task_service import TaskService

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_db)):
    service = TaskService(db)
    return await service.create(body)
```

### Verfügbare Tools
- `hivemind-get_task` — Task-Details laden
- `hivemind-submit_result` — Ergebnis schreiben
