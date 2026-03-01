---
title: "Decision Request erstellen (Blocker-Management)"
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

## Skill: Decision Request erstellen (Blocker-Management)

### Rolle
Du implementierst das atomare Erstellen von Decision Requests, die einen Task blockieren und
eine Entscheidung durch den Owner/Admin erfordern.

### Kontext

Ein Worker stößt auf einen Blocker und kann nicht weiterarbeiten. Er erstellt einen
Decision Request, der den Task **atomar** von `in_progress` auf `blocked` setzt.

```text
Worker arbeitet an TASK-88
  → Blocker: "Soll OAuth via Google oder GitHub integriert werden?"
  → create_decision_request { task_key: "TASK-88", question: "...", options: ["Google", "GitHub", "Beides"] }
  → Atomare Transaktion:
      (1) decision_request mit state=open erstellt
      (2) Task: in_progress → blocked
  → SLA: sla_due_at = created_at + 72h
```

### Konventionen

- **Atomare Transaktion:** Decision Request und Task-State-Änderung in einer DB-Transaktion
- **Pre-Condition:** Task muss in `in_progress` sein — sonst 409 Conflict
- **SLA:** `sla_due_at` = `created_at + 72h` (konfigurierbar via `HIVEMIND_DECISION_SLA_HOURS`)
- **Phase 5 Limitation:** `resolve_decision_request` existiert erst in Phase 6.
  Workaround: Admin löst manuell via `PATCH /api/tasks/:task_key/state { "state": "in_progress" }`
- Decision Requests haben einen `state` enum: `open | resolved | expired`

### Implementierung

```python
async def handle_create_decision_request(args: dict) -> list[TextContent]:
    task_key = args["task_key"]          # Canonical param name (alias: task_id)
    question = args["question"]          # Freitext: Was ist der Blocker? (alias: blocker)
    options = args.get("options", [])    # Optionale Lösungsvorschläge

    async with get_db() as db:
        task = await TaskService(db).get_by_key(task_key)

        # 1. Pre-Condition: Task muss in_progress sein
        if task.state != "in_progress":
            return _err("INVALID_STATE",
                f"Task {task_key} ist {task.state}, erwartet: in_progress", 409)

        # 2. Atomare Transaktion: Decision Request + Task-Block
        sla_hours = int(os.getenv("HIVEMIND_DECISION_SLA_HOURS", "72"))

        decision_request = DecisionRequest(
            task_id=task.id,
            question=question,
            options=options,           # JSONB Array
            state="open",
            created_by=actor.id,
            sla_due_at=datetime.utcnow() + timedelta(hours=sla_hours),
        )
        db.add(decision_request)

        # Task atomar blockieren
        task.state = "blocked"
        task.version += 1

        # 3. Audit
        await write_audit(db, actor, "create_decision_request", "task", task.id,
            input_snapshot=args,
            output_snapshot={"decision_request_id": str(decision_request.id)})

        # 4. Notification an Epic-Owner
        await event_bus.publish(DecisionRequestEvent(
            task_id=task.id,
            decision_request_id=decision_request.id,
            question=question,
        ))

        await db.commit()
        return _ok({
            "decision_request_id": str(decision_request.id),
            "task_key": task_key,
            "task_state": "blocked",
            "sla_due_at": decision_request.sla_due_at.isoformat(),
            "version": task.version,
        })
```

### Datenmodell

```sql
CREATE TABLE decision_requests (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id     UUID NOT NULL REFERENCES tasks(id),
    question    TEXT NOT NULL,              -- Beschreibung des Blockers
    options     JSONB DEFAULT '[]',         -- Lösungsvorschläge als Array
    state       TEXT NOT NULL DEFAULT 'open',  -- open|resolved|expired
    decision    TEXT,                       -- Gewählte Option (bei resolved)
    rationale   TEXT,                       -- Admin-Begründung (bei resolved)
    created_by  UUID NOT NULL REFERENCES users(id),
    resolved_by UUID REFERENCES users(id),
    sla_due_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);
```

### SLA-Eskalation (Phase 6)

In Phase 6 wird eine SLA-Überwachung ergänzt:
- `sla_due_at` überschritten + `state = open` → Task automatisch `blocked → escalated`
- In Phase 5 existiert nur die passive SLA-Anzeige (Countdown in UI)

### Fehler-Typen

| Code | HTTP | Wann |
| --- | --- | --- |
| `INVALID_STATE` | 409 | Task nicht in `in_progress` |
| `PERMISSION_DENIED` | 403 | Actor hat keine Write-Rechte |
| `ENTITY_NOT_FOUND` | 404 | Task existiert nicht |

### Phase 5 Workaround (resolve)
`resolve_decision_request` kommt erst in Phase 6. Bis dahin:
```
PATCH /api/tasks/:task_key/state { "state": "in_progress", "actor_role": "admin" }
```
Admin setzt Task manuell von `blocked` zurück auf `in_progress`.

### Verfügbare Tools
- `hivemind/create_decision_request` — Decision Request erstellen + Task blockieren
- `hivemind/get_task` — Task-Details laden (zeigt `blocked`-State + offene Decision Requests)
