---
title: "Review-Gate Workflow implementieren"
service_scope: ["backend"]
stack: ["python", "fastapi", "sqlalchemy"]
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

## Skill: Review-Gate Workflow implementieren

### Rolle
Du implementierst den vollständigen Review-Gate-Workflow: `approve_review`, `reject_review`,
`qa_failed`-Handling und die Eskalationslogik bei wiederholtem Fehlschlag.

### Kontext

Das Review-Gate ist der zentrale Qualitätsmechanismus in Hivemind. Kein Task kann
direkt von `in_progress` auf `done` wechseln — der Weg führt immer über `in_review`.

```text
in_progress → in_review → done          (approve_review)
                        → qa_failed     (reject_review)
                            → in_progress  (Worker Re-Entry)
                            → escalated    (bei 3x qa_failed)
```

### Konventionen

- `approve_review` und `reject_review` sind die **einzigen** Wege aus `in_review`
- Nur Epic-Owner oder Admin darf reviewen
- `reject_review` schreibt `review_comment` und inkrementiert `qa_failed_count`
- Worker Re-Entry: Worker setzt `qa_failed → in_progress` via `update_task_state`
- Bei `qa_failed_count >= 3`: System setzt automatisch `escalated` statt `in_progress`
- Eskalation greift beim **Worker-Re-Entry-Versuch**, nicht bei `reject_review`

### approve_review — Implementierung

```python
async def handle_approve_review(args: dict) -> list[TextContent]:
    task_key = args["task_key"]   # Canonical param name (alias: task_id)

    async with get_db() as db:
        task = await TaskService(db).get_by_key(task_key)

        # 1. State-Validierung
        if task.state != "in_review":
            return _err("INVALID_STATE", "Task muss in_review sein", 422)

        # 2. RBAC: Owner oder Admin
        require_permission(actor, "approve_review", epic_id=task.epic_id)

        # 3. State → done
        task.state = "done"
        task.done_at = datetime.utcnow()
        task.version += 1

        # 4. Epic-Auto-Transition prüfen
        #    Wenn ALLE Tasks eines Epics done|cancelled → Epic-State aktualisieren
        await check_epic_auto_transition(db, task.epic_id)

        # 5. EXP-Vergabe (Gamification)
        await award_exp(db, task.assigned_to, "task_done", 50, entity_id=task.id)
        if task.qa_failed_count == 0:
            await award_exp(db, task.assigned_to, "task_done_clean", 20, entity_id=task.id)
        if task.sla_due_at and task.done_at <= task.sla_due_at:
            await award_exp(db, task.assigned_to, "task_done_sla", 10, entity_id=task.id)

        # 6. EXP für Reviewer
        await award_exp(db, actor.id, "review_completed", 15, entity_id=task.id)

        # 7. Notification
        await event_bus.publish(TaskDoneEvent(task_id=task.id, assignee=task.assigned_to))

        # 8. Audit
        await write_audit(db, actor, "approve_review", "task", task.id, ...)

        await db.commit()
        return _ok({"task_key": task.key, "state": "done", "version": task.version})
```

### reject_review — Implementierung

```python
async def handle_reject_review(args: dict) -> list[TextContent]:
    task_key = args["task_key"]   # Canonical param name (alias: task_id)
    comment = args["comment"]  # Pflichtfeld

    async with get_db() as db:
        task = await TaskService(db).get_by_key(task_key)

        # 1. State-Validierung
        if task.state != "in_review":
            return _err("INVALID_STATE", "Task muss in_review sein", 422)

        # 2. State → qa_failed
        task.state = "qa_failed"
        task.review_comment = comment
        task.qa_failed_count += 1
        task.version += 1

        # 3. EXP für Reviewer (auch bei Reject)
        await award_exp(db, actor.id, "review_completed", 15, entity_id=task.id)

        # 4. Audit
        await write_audit(db, actor, "reject_review", "task", task.id, ...)

        await db.commit()
        return _ok({
            "task_key": task.key,
            "state": "qa_failed",
            "qa_failed_count": task.qa_failed_count,
            "version": task.version,
        })
```

### Worker Re-Entry mit Eskalation

```python
# In update_task_state Handler:
if task.state == "qa_failed" and target_state == "in_progress":
    if task.qa_failed_count >= 3:
        # Eskalation statt Re-Entry
        task.state = "escalated"
        task.version += 1
        await event_bus.publish(TaskEscalatedEvent(task_id=task.id, reason="3x qa_failed"))
        return _ok({
            "task_key": task.key,
            "state": "escalated",
            "message": "Task eskaliert nach 3x qa_failed. Admin-Intervention erforderlich.",
        })

    # Normaler Re-Entry
    task.state = "in_progress"
    task.version += 1

    # Guard-Reset: Worker muss alle Guards neu durchlaufen
    await reset_guards_for_task(db, task.id)

    return _ok({"task_key": task.key, "state": "in_progress", "version": task.version})
```

### Epic-Auto-Transition

Wenn `approve_review` den letzten offenen Task abschließt:
```python
async def check_epic_auto_transition(db: AsyncSession, epic_id: UUID) -> None:
    """Prüft ob alle Tasks done/cancelled → setzt Epic auf done."""
    open_tasks = await db.scalar(
        select(func.count(Task.id)).where(
            Task.epic_id == epic_id,
            Task.state.notin_(["done", "cancelled"])
        )
    )
    if open_tasks == 0:
        epic = await db.get(Epic, epic_id)
        epic.state = "done"
        epic.version += 1
```

### Fehler-Typen

| Code | HTTP | Wann |
| --- | --- | --- |
| `INVALID_STATE` | 422 | Task nicht in `in_review` |
| `PERMISSION_DENIED` | 403 | Actor ist weder Owner noch Admin |
| `ESCALATED` | 200 | Task eskaliert statt Re-Entry (Info, kein Fehler) |

### Wichtig
- `reject_review` setzt **immer** `qa_failed`, nie direkt `escalated`
- Eskalation greift erst beim nächsten Worker-Re-Entry-Versuch
- `review_comment` ist Pflichtfeld bei `reject_review`
- Nach `done`: Prompt Station zeigt „Jetzt: Gaertner" (→ Gärtner-Prompt-Flow)

### Verfügbare Tools
- `hivemind/approve_review` — Task von `in_review` auf `done`
- `hivemind/reject_review` — Task von `in_review` auf `qa_failed`
- `hivemind/update_task_state` — Worker Re-Entry (`qa_failed → in_progress`)
