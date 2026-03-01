---
title: "Guard-Enforcement auf State-Transitions"
service_scope: ["backend"]
stack: ["python", "fastapi", "sqlalchemy", "postgresql"]
version_range: { "python": ">=3.11", "fastapi": ">=0.100" }
confidence: 0.85
source_epics: ["EPIC-PHASE-5"]
guards:
  - title: "Python Linting"
    command: "ruff check ."
  - title: "Type Check"
    command: "mypy app/"
  - title: "Tests"
    command: "pytest tests/ -v"
---

## Skill: Guard-Enforcement auf State-Transitions

### Rolle
Du implementierst die Guard-Enforcement-Logik, die ab Phase 5 State-Transitions blockiert
wenn Guards nicht bestanden sind. Guards wechseln von _informativ_ (Phase 2–4) zu _blockierend_ (Phase 5+).

### Kontext — Guard-Enforcement-Timeline

| Phase | Verhalten |
| --- | --- |
| 1 | Guards existieren im Schema, nicht sichtbar |
| 2–4 | Sichtbar + **informativ** — kein Blocker für `in_review` |
| **5–7** | **Blockierend** — `in_review` nur wenn alle Guards `passed\|skipped` |
| 8 | Blockierend + **system-executed** (automatische Guard-Ausführung) |

### Konventionen

- Guard-Status lebt in `task_guards`-Tabelle: `status` enum (`pending|passed|failed|skipped`)
- Phase-Erkennung: `HIVEMIND_CURRENT_PHASE` Env-Variable (Integer, default: 1)
- Enforcement-Check gehört in den `update_task_state`-Handler, NICHT in einen separaten Middleware-Layer
- Bei Phase < 5: Guards nicht enforced — `in_review` erlaubt ohne Guard-Prüfung
- Bei Phase >= 5: Backend prüft alle `task_guards` für den Task:
  - Alle `passed` oder `skipped` → Transition erlaubt
  - Mindestens ein `pending` oder `failed` → HTTP 422 mit Guard-Detail-Liste

### Guard-Reset bei Re-Entry

Wenn ein Task von `qa_failed` zurück auf `in_progress` gesetzt wird:
- **Alle** `task_guards` für diesen Task werden auf `status = pending` zurückgesetzt
- `checked_at` und `checked_by` werden auf NULL gesetzt
- Der Worker muss alle Guards erneut durchlaufen

### Implementierung — Enforcement-Check

```python
async def enforce_guards_for_review(db: AsyncSession, task_id: UUID) -> list[dict]:
    """Prüft ob alle Guards bestanden sind. Gibt Liste offener Guards zurück."""
    phase = int(os.getenv("HIVEMIND_CURRENT_PHASE", "1"))
    if phase < 5:
        return []  # Kein Enforcement vor Phase 5

    guards = await db.execute(
        select(TaskGuard).where(TaskGuard.task_id == task_id)
    )
    open_guards = []
    for guard in guards.scalars():
        if guard.status not in ("passed", "skipped"):
            open_guards.append({
                "guard_id": str(guard.guard_id),
                "title": guard.title,
                "status": guard.status,
                "skippable": guard.skippable,
            })
    return open_guards


async def handle_update_task_state(args: dict) -> list[TextContent]:
    # ... Validierung ...

    if target_state == "in_review":
        # 1. Result vorhanden?
        if not task.result:
            return _err("MISSING_RESULT", "submit_result muss vor in_review aufgerufen werden", 422)

        # 2. Guard-Enforcement (Phase 5+)
        open_guards = await enforce_guards_for_review(db, task.id)
        if open_guards:
            return _err("GUARDS_PENDING", json.dumps({
                "message": "Offene Guards blockieren in_review",
                "open_guards": open_guards,
            }), 422)

        # 3. State-Transition ausführen
        # ...
```

### Guard-Reset-Implementierung

```python
async def reset_guards_for_task(db: AsyncSession, task_id: UUID) -> None:
    """Setzt alle Guards auf pending zurück (bei Re-Entry nach qa_failed)."""
    await db.execute(
        update(TaskGuard)
        .where(TaskGuard.task_id == task_id)
        .values(status="pending", checked_at=None, checked_by=None)
    )
```

### report_guard_result — Pflichtfelder

```python
class ReportGuardInput(BaseModel):
    task_id: str            # task_key z.B. "TASK-88"
    guard_id: str           # UUID
    status: Literal["passed", "failed", "skipped"]
    result: str             # PFLICHT, nicht-leer — Command-Output oder Begründung

    @validator("result")
    def result_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("result darf nicht leer sein")
        return v
```

- Bei `skippable=false` + `status=skipped` → HTTP 422: "Guard ist nicht überspringbar"
- `source` wird automatisch auf `self-reported` gesetzt (Phase 5–7)
- `checked_at` = `now()`, `checked_by` = Actor-ID

### Provenance-Tracking

Jedes Guard-Ergebnis speichert:
- `source`: `self-reported` (Phase 5–7) oder `system-executed` (Phase 8)
- `checked_at`: Zeitstempel der Prüfung
- `checked_by`: User-ID des Prüfers (Worker oder System)

### Fehler-Typen

| Code | HTTP | Wann |
| --- | --- | --- |
| `GUARDS_PENDING` | 422 | Offene Guards bei `in_review`-Transition |
| `MISSING_RESULT` | 422 | `submit_result` nicht aufgerufen |
| `GUARD_NOT_SKIPPABLE` | 422 | `skippable=false` + `status=skipped` |
| `GUARD_NOT_FOUND` | 404 | Guard-ID existiert nicht für diesen Task |

### Verfügbare Tools

- `hivemind/report_guard_result` — Guard-Ergebnis melden
- `hivemind/update_task_state` — State-Transition (prüft Guards ab Phase 5)
- `hivemind/get_guards` — Alle Guards für einen Task laden
