---
title: "Optimistic Locking + Idempotenz (FastAPI)"
service_scope: ["backend"]
stack: ["python", "fastapi", "sqlalchemy", "postgresql"]
version_range: { "python": ">=3.11", "fastapi": ">=0.100" }
confidence: 0.9
source_epics: ["EPIC-PHASE-2"]
guards:
  - title: "Python Linting"
    command: "ruff check ."
  - title: "Concurrency Tests"
    command: "pytest tests/test_locking.py -v"
---

## Skill: Optimistic Locking + Idempotenz (FastAPI)

### Rolle
Du implementierst Optimistic Locking via `expected_version` und Idempotenz via `idempotency_key` auf allen mutierenden Endpoints im Hivemind-Backend.

### Konzept

**Optimistic Locking:** Jede Entität hat ein `version`-Feld (Integer, Default 1). Bei jedem Write muss der Client das aktuelle `expected_version` mitsenden. Stimmt es nicht mit dem DB-Stand überein → HTTP 409 Conflict. Bei erfolgreichem Write: `version += 1`.

**Idempotenz:** Jeder Write-Request trägt einen `idempotency_key` (UUID v4). Wenn derselbe Key bereits in `mcp_invocations` existiert → gecachtes `output_payload` zurückgeben ohne erneute Ausführung. Fenster: 24h (danach Key ablaufen lassen).

### MCP-Write-Pflichtfelder (Pydantic BaseModel)

```python
from pydantic import BaseModel, Field
from uuid import UUID, uuid4

class WriteRequestMeta(BaseModel):
    request_id: UUID = Field(default_factory=uuid4)
    actor_id: UUID
    actor_role: str
    epic_id: UUID | None = None      # nur bei Epic/Task-scoped Writes
    idempotency_key: UUID = Field(default_factory=uuid4)
    expected_version: int
```

### Beispiel: Optimistic Locking im Service-Layer

```python
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

async def update_with_version_check(db: AsyncSession, entity, expected_version: int, updates: dict) -> None:
    if entity.version != expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Version mismatch: expected {expected_version}, actual {entity.version}. Bitte Entity neu laden.",
        )
    for key, value in updates.items():
        setattr(entity, key, value)
    entity.version += 1
    await db.flush()
```

### Beispiel: Idempotenz-Check

```python
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.models.audit import McpInvocation

async def check_idempotency(db: AsyncSession, idempotency_key: str) -> dict | None:
    """Gibt gecachtes output_payload zurück wenn Key bereits existiert, sonst None."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    result = await db.execute(
        select(McpInvocation).where(
            McpInvocation.idempotency_key == idempotency_key,
            McpInvocation.created_at > cutoff,
        )
    )
    existing = result.scalar_one_or_none()
    return existing.output_payload if existing else None

# In einem Router:
@router.patch("/{id}")
async def update_epic(id: UUID, body: EpicUpdate, db: AsyncSession = Depends(get_db)):
    if cached := await check_idempotency(db, str(body.meta.idempotency_key)):
        return cached  # Idempotenz-Replay
    epic = await get_epic_or_404(db, id)
    await update_with_version_check(db, epic, body.meta.expected_version, body.updates)
    ...
```

### Welche Endpoints brauchen das?
Alle mutierenden Endpoints (`POST` für Creates auf Parent, `PATCH`, `PUT`, `DELETE`):
- `POST /api/projects`, `PATCH /api/projects/{id}`
- `POST /api/epics`, `PATCH /api/epics/{id}`
- `POST /api/tasks`, `PATCH /api/tasks/{id}`, `POST /api/tasks/{id}/approve`, `POST /api/tasks/{id}/reject`
- `POST /api/projects/{id}/members`, `PATCH/DELETE /api/projects/{id}/members/{uid}`

Create-Writes (`POST`) benötigen `expected_version` auf der **Parent-Entität** (z.B. `epic.version` wenn Task erstellt wird).

### HTTP-Antworten
- `409 Conflict` bei Version-Mismatch → Client soll Entity neu laden und erneut versuchen
- `200 OK` + Original-Response-Body bei Idempotenz-Replay (identisches Ergebnis wie Erst-Request)
