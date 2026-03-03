# Hivemind VS Code Extension

## Auto-Execute (TASK-IDE-006)

Die Extension empfängt `conductor:dispatch` Events über SSE (`/api/events/tasks`) und delegiert sie an Copilot:

- `chat` (GUI): öffnet Copilot Chat über `workbench.action.chat.open`
- `cli` (headless/terminal): startet `gh copilot` mit einem task-spezifischen Taskfile

## Governance

Settings:

- `hivemind.governanceLevel`: `manual` | `semi-auto` | `full-auto`
- `hivemind.governanceSource`: `extension` | `backend` | `merged`

Logik:

- `manual`: immer Bestätigung
- `semi-auto`: Auto nur für `worker`, `kartograph`, `gaertner`
- `full-auto`: Auto für alle Rollen
- `merged`: kombiniert lokale Governance mit `/api/settings/governance` (striktere Stufe gewinnt)

## Progress + Completion

Während einer Ausführung meldet die Extension Progress an:

- `POST /api/conductor/dispatches/{id}/progress`

Zusätzlich pollt sie `/api/audit` und erkennt MCP-Aktivität:

- Tool-Calls (`hivemind/*`) werden als Progress gemeldet
- `hivemind/submit_result` oder `hivemind/update_task_state` (Completion-State) markieren den Dispatch als `completed`

Finale Statusmeldung:

- `POST /api/conductor/dispatches/{id}/complete` mit `completed|failed|cancelled|timed_out`

## Copilot CLI (Headless)

Setze:

- `hivemind.executionTarget = "cli"`
- optional `hivemind.copilotCliCommandTemplate`

Default-Template:

```bash
gh copilot run --input-file "{taskfile}"
```

Platzhalter:

- `{taskfile}`: generiertes Taskfile (`.hivemind/dispatches/{dispatch_id}.md`)
- `{task_key}`: Dispatch-Trigger (z. B. `TASK-HEALTH-001`)
- `{agent_role}`: Agent-Rolle (z. B. `worker`)

Beispiel:

```bash
gh copilot run --input-file "{taskfile}" --model gpt-5
```
