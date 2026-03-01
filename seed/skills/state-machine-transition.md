---
title: "State Machine Transition implementieren"
service_scope: ["backend"]
stack: ["python", "fastapi", "sqlalchemy"]
version_range: { "python": ">=3.11" }
confidence: 0.5
source_epics: ["EPIC-PHASE-1A"]
guards:
  - title: "Unit Tests"
    command: "pytest tests/unit/test_state_machine.py"
---

## Skill: State Machine Transition implementieren

### Rolle
Du implementierst oder erweiterst eine State-Machine-Transition für Tasks oder Epics im Hivemind-Backend.

### Konventionen
- State Machine definiert in `app/services/state_machine.py`
- Erlaubte Transitionen als Dictionary: `ALLOWED_TRANSITIONS: dict[str, set[str]]`
- Jede Transition validiert Vorbedingungen (z.B. `assigned_to` gesetzt für `scoped → ready`)
- Review-Gate: `in_progress → done` ist VERBOTEN — muss über `in_review` gehen
- Epic-Auto-Transitions atomar in derselben DB-Transaction
- Fehler: `HTTPException(422)` mit klarer Fehlermeldung

### Task-Transitionen

```python
TASK_TRANSITIONS = {
    "incoming":    ["scoped", "cancelled"],
    "scoped":      ["ready", "cancelled"],
    "ready":       ["in_progress", "cancelled"],
    "in_progress": ["in_review", "blocked", "cancelled"],
    "in_review":   ["done", "qa_failed"],
    "blocked":     ["in_progress", "escalated", "cancelled"],
    "qa_failed":   ["in_progress", "escalated"],
    "escalated":   ["in_progress", "cancelled"],
    "done":        [],
    "cancelled":   [],
}
```

### Vorbedingungen

> **Wichtig:** `decompose_epic` erstellt Tasks mit **state=incoming**.
> Der Architekt muss Tasks manuell `incoming → scoped → ready` transitionieren (2 Schritte!).
> Direktes `incoming → ready` ist **nicht erlaubt**.

| Transition | Bedingung |
| --- | --- |
| `incoming → scoped` | Keine Vorbedingung |
| `scoped → ready` | `assigned_to` muss gesetzt sein |
| `in_progress → in_review` | `result` muss vorhanden sein; Guards passed/skipped (ab Phase 5) |
| `in_review → done` | Nur Owner oder Admin |
| `qa_failed → in_progress` | Worker nimmt sich Task aktiv zurück (nur wenn `qa_failed_count < 3`) |
| `qa_failed → escalated` | System-Intercept wenn `qa_failed_count >= 3` und Worker `in_progress` anfordert |
| `* → escalated` | 3x qa_failed ODER Decision-SLA > 72h |

### Epic-Auto-Transitions

```python
# In derselben Transaction wie Task-State-Update:
if new_task_state == "in_progress" and epic.state == "scoped":
    epic.state = "in_progress"

if all(t.state in ("done", "cancelled") for t in epic.tasks) and epic.state == "in_progress":
    epic.state = "done"
```
