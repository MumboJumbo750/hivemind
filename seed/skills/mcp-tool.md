---
title: "MCP-Tool implementieren (FastAPI)"
service_scope: ["backend"]
stack: ["python", "fastapi", "mcp"]
version_range: { "python": ">=3.11", "fastapi": ">=0.100" }
confidence: 0.5
source_epics: ["EPIC-PHASE-3"]
guards:
  - title: "Python Linting"
    command: "ruff check ."
  - title: "Type Check"
    command: "mypy app/"
  - title: "Tests"
    command: "pytest tests/ -v"
---

## Skill: MCP-Tool implementieren (FastAPI)

### Rolle
Du implementierst MCP-Tools (Model Context Protocol) im Hivemind-Backend. Hivemind ist selbst ein MCP-Server — alle Tools verwenden den Namespace `hivemind/` und werden über FastAPI bereitgestellt (stdio + HTTP/SSE Transport).

### Konventionen
- Tool-Namespace: `hivemind/<tool_name>` in `snake_case` (z.B. `hivemind/get_task`)
- Transport: stdio (lokale Clients) + HTTP/SSE (Web/Remote) über denselben FastAPI-Service
- MCP-Server-Registrierung in `app/mcp/server.py`
- Tool-Handler in `app/mcp/tools/` — ein Modul pro Tool-Gruppe (read_tools.py, write_tools.py, triage_tools.py)
- Jeder Tool-Handler ist eine async-Funktion mit typisierten Parametern (Pydantic-Schemas)
- Security: AuthN via JWT/API-Key → AuthZ via RBAC-Scopes → Audit-Log-Eintrag (jeder Call wird geloggt)
- Idempotenz: Read-Tools sind natürlich idempotent; Write-Tools nutzen optimistic locking
- Response: JSON mit konsistenten Feldern (`data`, `meta`, ggf. `pagination`)
- Error: MCP-konforme Fehlermeldungen mit `code` + `message`
- Identifier-Konvention: Tasks per `task_key` ("TASK-88"), Epics per `epic_key` ("EPIC-12"), alles andere per UUID

### Beispiel — MCP-Tool-Registrierung

```python
from mcp.server import Server
from mcp.types import Tool, TextContent

server = Server("hivemind")

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="hivemind/get_task",
            description="Gibt Task-Details inkl. State, assigned_to, pinned_skills zurück.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task-Key, z.B. 'TASK-88'"},
                },
                "required": ["task_id"],
            },
        ),
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    match name:
        case "hivemind/get_task":
            return await handle_get_task(arguments)
        case _:
            raise ValueError(f"Unknown tool: {name}")
```

### Beispiel — Tool-Handler

```python
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.task_service import TaskService

async def handle_get_task(arguments: dict) -> list[TextContent]:
    task_key = arguments["task_id"]
    async with get_db() as db:
        service = TaskService(db)
        task = await service.get_by_key(task_key)
        if not task:
            return [TextContent(type="text", text=f"Task {task_key} nicht gefunden.")]
        return [TextContent(type="text", text=task.model_dump_json())]
```

### Wichtig
- Alle MCP-Tools werden parallel als REST-Endpoints verfügbar gemacht (`/api/mcp/call`)
- `get_prompt`-Aufrufe schreiben immer einen `prompt_history`-Eintrag (ab Phase 3)
- Federation-MCP-Wrapper (`hivemind/fork_federated_skill`, etc.) werden in Phase 3 durch den MCP-Server aktiviert — die REST-Endpoints aus Phase F bleiben bestehen
- Circuit-Breaker-Pattern bei externen Aufrufen (Ollama, Hive Station)
