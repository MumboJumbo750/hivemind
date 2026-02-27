---
title: "Pydantic v2 Model definieren"
service_scope: ["backend"]
stack: ["python", "pydantic"]
version_range: { "python": ">=3.11", "pydantic": ">=2.0" }
confidence: 0.5
source_epics: ["EPIC-PHASE-1A"]
guards:
  - title: "Type Check"
    command: "mypy app/"
---

## Skill: Pydantic v2 Model definieren

### Rolle
Du definierst Pydantic v2 Schemas für Request/Response-Validierung im Hivemind-Backend.

### Konventionen
- Schemas liegen in `app/schemas/` — ein Modul pro Domain-Entity
- Naming: `{Entity}Create`, `{Entity}Update`, `{Entity}Response`, `{Entity}List`
- `model_config = ConfigDict(from_attributes=True)` für ORM-Kompatibilität
- UUIDs als `uuid.UUID` typisieren
- Datetimes als `datetime` mit Timezone-Awareness
- Optional-Felder explizit: `field: str | None = None`
- Enums als `Literal[...]` statt Python Enum (kompatibel mit JSON-Schema)

### Beispiel

```python
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    epic_id: UUID
    priority: Literal["low", "medium", "high", "critical"] = "medium"

class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None
    state: Literal["incoming", "scoped", "ready", "in_progress", "in_review", "done", "blocked", "qa_failed", "escalated", "cancelled"]
    priority: Literal["low", "medium", "high", "critical"]
    epic_id: UUID
    assigned_to: UUID | None
    created_at: datetime
    updated_at: datetime

class TaskList(BaseModel):
    items: list[TaskResponse]
    total: int
```
