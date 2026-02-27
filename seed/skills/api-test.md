---
title: "API Endpoint testen"
service_scope: ["backend"]
stack: ["python", "pytest", "httpx"]
version_range: { "python": ">=3.11", "pytest": ">=7.0" }
confidence: 0.5
source_epics: ["EPIC-PHASE-1A"]
guards:
  - title: "Tests"
    command: "pytest tests/ -v"
---

## Skill: API Endpoint testen

### Rolle
Du schreibst Tests für FastAPI-Endpoints im Hivemind-Backend.

### Konventionen
- Tests in `tests/` — Struktur spiegelt `app/` (z.B. `tests/routers/test_tasks.py`)
- `httpx.AsyncClient` mit `ASGITransport` für Async-Tests
- Fixtures in `tests/conftest.py`: `client`, `db_session`, `test_user`
- Jeder Test ist isoliert (DB-Rollback nach jedem Test)
- Naming: `test_{action}_{entity}_{condition}` z.B. `test_create_task_success`
- Assertions auf: Status-Code, Response-Body, DB-State

### Beispiel

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest.mark.anyio
async def test_create_task_success(client: AsyncClient, seed_epic):
    response = await client.post("/api/tasks/", json={
        "title": "Test Task",
        "epic_id": str(seed_epic.id),
        "priority": "medium",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Task"
    assert data["state"] == "incoming"

@pytest.mark.anyio
async def test_create_task_missing_title(client: AsyncClient, seed_epic):
    response = await client.post("/api/tasks/", json={
        "epic_id": str(seed_epic.id),
    })
    assert response.status_code == 422

@pytest.mark.anyio
async def test_task_state_transition_review_gate(client: AsyncClient, seed_task_in_progress):
    """Review-Gate: in_progress → done ist verboten."""
    response = await client.patch(
        f"/api/tasks/{seed_task_in_progress.id}/state",
        json={"state": "done"}
    )
    assert response.status_code == 422
    assert "review" in response.json()["detail"].lower()
```

### Wichtig
- Review-Gate immer testen: `in_progress → done` muss 422 zurückgeben
- State-Machine-Transitionen sowohl valid als auch invalid testen
- Idempotenz-Tests: gleicher `idempotency_key` → gleiche Response (ab Phase 2)
