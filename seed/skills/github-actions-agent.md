---
title: "GitHub Actions Agent: Guards & Agenten in CI-Pipelines"
service_scope: ["backend"]
stack: ["python", "fastapi", "httpx", "github-actions"]
version_range: { "python": ">=3.11", "fastapi": ">=0.100" }
confidence: 0.5
source_epics: ["EPIC-PHASE-8"]
guards:
  - title: "Python Linting"
    command: "ruff check ."
  - title: "Type Check"
    command: "mypy app/"
  - title: "Tests"
    command: "pytest tests/ -v"
---

## Skill: GitHub Actions Agent

### Rolle
Du implementierst die Brücke zwischen Hivemind-Conductor und GitHub Actions. Der Conductor kann Guards und Agent-Dispatches als GitHub Actions Workflows ausführen — im nativen Repo-Kontext mit richtigen Runtimes und Dependencies. Die Action connected zurück zum Hivemind MCP Server und reportet Ergebnisse.

### Kontext
Warum guards nicht nur im Backend-Container, sondern auch in CI?
- Container hat nicht alle Language-Runtimes (Node, Go, Rust, etc.)
- CI hat den Repo-Checkout (Code + Dependencies + Build-Artefakte)
- CI kann komplexe Testsuites ausführen (Integration Tests, E2E)
- GitHub Actions hat Free-Tier-Compute (2000 min/Monat bei Free, unlimited bei Pro)
- Status Checks in PRs sichtbar — direktes Feedback im GitHub-Flow

### Architektur

```
Hivemind Conductor
  │
  ├─ dispatch_agent("worker", task_key="TASK-88")
  │    ↓
  │  Option A: AI-Provider-Service (wie bisher)
  │    → Prompt an Claude/GPT/Ollama senden
  │
  ├─ dispatch_guards("TASK-88")
  │    ↓
  │  Option B: GitHub Actions Dispatch
  │    → POST /repos/{owner}/{repo}/actions/workflows/{workflow}/dispatches
  │    → Input: { task_key, guard_commands, hivemind_url }
  │    → Action führt Guards im Repo-Kontext aus
  │    → Action reportet via: POST {hivemind_url}/api/mcp/call
  │       → hivemind/report_guard_result { task_key, guard_id, status, result }
  │
  └─ dispatch_agent_in_ci("worker", task_key="TASK-88")
       ↓
     Option C: Agent als GitHub Action
       → Workflow startet AI-Agent im CI-Runner
       → Agent hat Repo-Checkout + Hivemind MCP-Zugang
       → Agent schreibt Code, erstellt PR, reportet Result
```

### GitHub Actions Workflow (Template)

```yaml
# .github/workflows/hivemind-agent.yml
name: Hivemind Agent Dispatch

on:
  workflow_dispatch:
    inputs:
      task_key:
        description: 'Hivemind Task Key'
        required: true
      agent_role:
        description: 'Agent role (worker, kartograph, gaertner)'
        required: true
      hivemind_url:
        description: 'Hivemind MCP Server URL'
        required: true
      prompt:
        description: 'Agent prompt (base64-encoded)'
        required: false

jobs:
  agent:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Environment
        run: |
          # Language-spezifisches Setup (aus Repository .tool-versions oder Dockerfile)
          # Python, Node, Go, etc.
          pip install httpx  # Für MCP-Calls zurück an Hivemind

      - name: Run Hivemind Agent
        env:
          HIVEMIND_URL: ${{ inputs.hivemind_url }}
          HIVEMIND_TASK_KEY: ${{ inputs.task_key }}
          HIVEMIND_AGENT_ROLE: ${{ inputs.agent_role }}
          HIVEMIND_API_TOKEN: ${{ secrets.HIVEMIND_API_TOKEN }}
        run: |
          python .github/scripts/hivemind_agent_runner.py

      - name: Report Results
        if: always()
        env:
          HIVEMIND_URL: ${{ inputs.hivemind_url }}
          HIVEMIND_API_TOKEN: ${{ secrets.HIVEMIND_API_TOKEN }}
        run: |
          python .github/scripts/hivemind_report.py
```

### Guard-Execution in GitHub Actions

```yaml
# .github/workflows/hivemind-guards.yml
name: Hivemind Guard Execution

on:
  workflow_dispatch:
    inputs:
      task_key:
        required: true
      guards:
        description: 'JSON array of guards [{id, title, command}]'
        required: true
      hivemind_url:
        required: true

jobs:
  guards:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup
        run: |
          pip install -r requirements.txt 2>/dev/null || true
          npm install 2>/dev/null || true

      - name: Execute Guards
        env:
          GUARDS: ${{ inputs.guards }}
          HIVEMIND_URL: ${{ inputs.hivemind_url }}
          TASK_KEY: ${{ inputs.task_key }}
          HIVEMIND_API_TOKEN: ${{ secrets.HIVEMIND_API_TOKEN }}
        run: |
          python - <<'EOF'
          import json, os, subprocess, httpx

          guards = json.loads(os.environ["GUARDS"])
          url = os.environ["HIVEMIND_URL"]
          task_key = os.environ["TASK_KEY"]
          token = os.environ["HIVEMIND_API_TOKEN"]
          client = httpx.Client(headers={"Authorization": f"Bearer {token}"})

          for guard in guards:
              try:
                  result = subprocess.run(
                      guard["command"], shell=True,
                      capture_output=True, text=True, timeout=300
                  )
                  status = "passed" if result.returncode == 0 else "failed"
                  output = result.stdout + result.stderr
              except subprocess.TimeoutExpired:
                  status = "failed"
                  output = "Guard timed out after 300s"

              # Report zurück an Hivemind
              client.post(f"{url}/api/mcp/call", json={
                  "name": "hivemind/report_guard_result",
                  "arguments": {
                      "task_key": task_key,
                      "guard_id": guard["id"],
                      "status": status,
                      "result": output[:5000],  # Truncate
                  }
              })
          EOF
```

### Backend: Dispatch-Service

```python
import base64
import httpx

class GitHubActionsDispatcher:
    """Triggert GitHub Actions Workflows als Alternative zu lokaler Ausführung."""

    def __init__(self, github_token: str, github_url: str = "https://api.github.com"):
        self.client = httpx.AsyncClient(
            base_url=github_url,
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    async def dispatch_guards(
        self, repo: str, task_key: str, guards: list[dict], hivemind_url: str
    ):
        """Triggert Guard-Execution als GitHub Actions Workflow."""
        await self.client.post(
            f"/repos/{repo}/actions/workflows/hivemind-guards.yml/dispatches",
            json={
                "ref": "main",
                "inputs": {
                    "task_key": task_key,
                    "guards": json.dumps(guards),
                    "hivemind_url": hivemind_url,
                },
            },
        )

    async def dispatch_agent(
        self, repo: str, task_key: str, agent_role: str,
        prompt: str, hivemind_url: str
    ):
        """Triggert Agent-Execution als GitHub Actions Workflow."""
        await self.client.post(
            f"/repos/{repo}/actions/workflows/hivemind-agent.yml/dispatches",
            json={
                "ref": "main",
                "inputs": {
                    "task_key": task_key,
                    "agent_role": agent_role,
                    "hivemind_url": hivemind_url,
                    "prompt": base64.b64encode(prompt.encode()).decode(),
                },
            },
        )

    async def get_workflow_status(self, repo: str, run_id: int) -> dict:
        """Prüft Status eines laufenden Workflow-Runs."""
        resp = await self.client.get(f"/repos/{repo}/actions/runs/{run_id}")
        resp.raise_for_status()
        return resp.json()
```

### Integration in Conductor

```python
# In conductor.py:
async def _dispatch(self, agent_role: str, prompt_type: str, **kwargs):
    config = await self._get_config(agent_role)

    # Prüfe ob CI-Dispatch konfiguriert ist
    if config and config.execution_mode == "github_actions":
        repo = await self._get_project_repo(kwargs.get("task_key"))
        prompt = await self.prompt_gen.generate(prompt_type, **kwargs)
        await self.github_dispatcher.dispatch_agent(
            repo=repo,
            task_key=kwargs["task_key"],
            agent_role=agent_role,
            prompt=prompt,
            hivemind_url=settings.external_url,
        )
        return

    # Standard: AI-Provider-Service
    # ...
```

### Commit-Status-Checks

```python
async def create_commit_status(self, repo: str, sha: str, task_key: str, state: str):
    """Erstellt GitHub Commit Status Check für Hivemind-Task."""
    github_state = {"in_progress": "pending", "done": "success", "qa_failed": "failure"}.get(state, "pending")
    await self.client.post(
        f"/repos/{repo}/statuses/{sha}",
        json={
            "state": github_state,
            "target_url": f"{settings.external_url}/tasks/{task_key}",
            "description": f"Hivemind: {task_key} ({state})",
            "context": "hivemind/task-status",
        },
    )
```

### Konfiguration

Neue Felder in `ai_provider_configs`:
```python
execution_mode: Mapped[str] = mapped_column(
    String(20), default="api"
)  # "api" (Standard AI-Provider) | "github_actions" (CI-Dispatch)
github_repo: Mapped[str | None] = mapped_column(String(200))  # "owner/repo"
github_workflow: Mapped[str | None] = mapped_column(String(200))  # Workflow-Dateiname
```

### Env-Variablen

| Variable | Default | Beschreibung |
| --- | --- | --- |
| `HIVEMIND_GITHUB_TOKEN` | — | GitHub PAT (shared) |
| `HIVEMIND_EXTERNAL_URL` | — | Öffentliche URL des Hivemind-Servers (für Callback) |

### Sicherheit
- Hivemind MCP-URL muss von GitHub Actions erreichbar sein (Public URL oder VPN)
- `HIVEMIND_API_TOKEN` als GitHub Actions Secret konfigurieren
- Workflow-Dispatch braucht `actions:write` Scope im PAT
- Guard-Commands werden im Repo-Kontext ausgeführt → selbe Sicherheit wie CI
- Prompt wird Base64-encoded übertragen (Workflow-Inputs sind Strings)

### Wichtige Regeln
- GitHub Actions Dispatch ist **optional** — Standard bleibt AI-Provider-Service
- `execution_mode: "github_actions"` in `ai_provider_configs` aktiviert CI-Dispatch
- Ergebnisse kommen **asynchron** zurück (Action → MCP-Call → Hivemind)
- Conductor muss mit asynchronem Callback umgehen können (Status: `dispatched_to_ci`)
- Guard-Execution in CI ist natürlicher als im Backend-Container (richtige Runtimes)
