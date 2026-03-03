---
title: "MCP-Write-Tool implementieren (FastAPI)"
service_scope: ["backend"]
stack: ["python", "fastapi", "mcp", "sqlalchemy"]
version_range: { "python": ">=3.11", "fastapi": ">=0.100" }
confidence: 0.8
source_epics: ["EPIC-PHASE-3", "EPIC-PHASE-4"]
guards:
  - title: "Python Linting"
    command: "ruff check ."
  - title: "Type Check"
    command: "mypy app/"
  - title: "Tests"
    command: "pytest tests/ -v"
---

## Skill: MCP-Write-Tool implementieren (FastAPI)

### Rolle
Du implementierst MCP-Write-Tools im Hivemind-Backend. Write-Tools sind zustandsverändernde Operationen (CREATE, UPDATE, STATE-TRANSITION) die besondere Anforderungen an Idempotenz, Optimistic Locking, RBAC und Audit-Logging stellen.

### Konventionen
- Tool-Namespace: `hivemind/<tool_name>` — Write-Tools enden semantisch auf `create_*`, `update_*`, `propose_*`, `accept_*`, `reject_*`, `link_*`, `assign_*`
- Handler in `app/mcp/tools/write_tools.py` (planer: propose/decompose), `skill_write_tools.py` (skill lifecycle)
- Jeder Write-Call **muss** einen Audit-Log-Eintrag schreiben (tool_name, actor_id, input_snapshot, output_snapshot, timestamp)
- **Optimistic Locking:** alle mutierbaren Entitäten haben ein `version`-Feld (INT). PATCH/UPDATE prüft: `WHERE id = :id AND version = :expected_version`. Bei Mismatch → 409 Conflict mit `{"code": "VERSION_CONFLICT", "message": "..."}`
- **RBAC-Enforcement:** Permission-Check via `require_permission(actor, "<permission>")` **vor** jeder DB-Mutation. Fehlende Permission → 403 mit MCP-konformem Error-Body
- **Notifications:** State-Transitions die andere Nutzer betreffen (z.B. `task_assigned`, `skill_proposal_rejected`) triggern Notification via `event_bus.publish(NotificationEvent(...))`
- **Idempotenz-Keys:** Für kritische Create-Operations (epic_proposal, task) optional `idempotency_key` im Input-Schema akzeptieren — bei Duplikat das vorhandene Objekt zurückgeben (kein Fehler)
- Response: konsistentes Format `{"data": {...}, "meta": {"version": N}}` — `version` immer mitliefern damit Client Folgecalls korrekt locken kann

### Typische Write-Tool-Struktur

```python
@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    match name:
        case "hivemind/create_task":
            return await handle_create_task(arguments)
        # ...

async def handle_create_task(args: dict) -> list[TextContent]:
    # 1. Validierung (Pydantic)
    body = CreateTaskInput(**args)

    async with get_db() as db:
        actor = await resolve_actor(db, args.get("_actor_id"))

        # 2. RBAC
        require_permission(actor, "write_tasks")

        # 3. Business-Logik via Service
        task = await TaskService(db).create(body, actor)

        # 4. Audit-Log
        await AuditService(db).log(
            actor_id=actor.id,
            action="create_task",
            entity_type="task",
            entity_id=str(task.id),
            input_snapshot=args,
            output_snapshot={"task_key": task.key},
        )

        # 5. Notification (falls relevant)
        if body.assigned_to:
            await event_bus.publish(TaskAssignedEvent(task_id=task.id, ...))

        return [TextContent(type="text", text=json.dumps({"data": task.to_dict(), "meta": {"version": task.version}}))]
```

### Optimistic Locking — Beispiel

```python
async def update_task(db: AsyncSession, task_key: str, update: TaskUpdate, expected_version: int):
    result = await db.execute(
        update(Task)
        .where(Task.key == task_key, Task.version == expected_version)
        .values(**update.model_dump(exclude_unset=True), version=expected_version + 1)
        .returning(Task)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise VersionConflictError(f"Task {task_key} version mismatch — expected {expected_version}")
    return task
```

### ⚠️ Zwei-Schritt-Abschluss (häufiger Fehler!)

`hivemind/submit_result` **speichert nur** Ergebnis + Artifacts — der Task bleibt in `in_progress`.
Der State-Wechsel ist **bewusst getrennt** und muss separat ausgelöst werden:

```
1. hivemind/submit_result     → result/artifacts speichern (State: in_progress → in_progress)
2. hivemind/update_task_state → target_state: "in_review"  (State: in_progress → in_review)
```

Warum getrennt? Damit der Worker das Ergebnis mehrfach überschreiben kann (Idempotenz) bevor
er den Review-Prozess startet. `submit_result` ist idempotent, der State-Wechsel nicht.

### Fehler-Typen

| Code | HTTP | Wann |
| --- | --- | --- |
| `VERSION_CONFLICT` | 409 | Optimistic Lock Mismatch |
| `PERMISSION_DENIED` | 403 | RBAC schlägt fehl |
| `ENTITY_NOT_FOUND` | 404 | Referenzierte Entität nicht vorhanden |
| `INVALID_STATE_TRANSITION` | 422 | Unerlaubter State-Wechsel |
| `DUPLICATE_KEY` | 409 | Idempotency-Key bereits verwendet (mit vorhandenem Objekt im Body) |

### Implementierte Tool-Parameter (exakte Feldnamen!)

| Tool | Required Params | Typ-Hinweise |
|------|----------------|----|
| `hivemind/decompose_epic` | `epic_key`, `tasks[]` | epic_key ist String (z.B. "EPIC-PHASE-5"), NICHT epic_id |
| `hivemind/create_task` | `epic_key`, `title` | Optional: `description`, `definition_of_done` |
| `hivemind/link_skill` | `task_key`, `skill_id` | task_key ist String (z.B. "TASK-6"), NICHT task_id |
| `hivemind/set_context_boundary` | `task_key` | Optional: `allowed_skills[]`, `allowed_docs[]`, `max_token_budget` |
| `hivemind/assign_task` | `task_key`, `user_id` | user_id als UUID-String, NICHT assigned_to |
| `hivemind/update_task_state` | `task_key`, `target_state` | target_state ist String, NICHT state |

> **Achtung Namens-Konvention:** Tools verwenden `task_key` / `epic_key` (den menschenlesbaren Key wie "TASK-6"),
> nicht `task_id` / `epic_id` (die interne UUID). Viele Docs nutzen fälschlicherweise `_id` — die tatsächlichen
> Parameter in `write_tools.py` sind `_key`-basiert.

### Decision Record
`mcp-write-tool` ist eine Spezialisierung von `mcp-tool` für mutierende Operationen. Der Hauptunterschied ist die verpflichtende Kombination aus Optimistic Locking + RBAC + Audit vor jeder Mutation. Read-Tools benötigen nur RBAC + Audit.
