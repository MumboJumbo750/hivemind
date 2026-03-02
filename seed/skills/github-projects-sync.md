---
title: "GitHub Projects V2 Sync: Bidirektionale Projekt-Synchronisation"
service_scope: ["backend"]
stack: ["python", "fastapi", "httpx", "graphql"]
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

## Skill: GitHub Projects V2 Sync

### Rolle
Du implementierst die bidirektionale Synchronisation zwischen Hivemind Epics/Tasks und GitHub Projects V2. Hivemind ist Source of Truth für Task-State. Änderungen fließen über Webhooks (GitHub→Hivemind) und Outbox (Hivemind→GitHub).

### Kontext
GitHub Projects V2 ist ein flexibles Projekt-Management-Board mit Custom Fields. Es nutzt **ausschließlich GraphQL** (kein REST). Die Sync ermöglicht:
- Hivemind-Tasks als Karten im GitHub Project sichtbar
- Status-Änderungen in Hivemind → automatisch im GitHub Board reflektiert
- Manuelle Board-Änderungen in GitHub → als Events in Hivemind ingestiert
- Team-Mitglieder die kein Hivemind nutzen können den Fortschritt im GitHub Board verfolgen

### Konventionen
- Service: `app/services/github_projects_sync.py`
- GraphQL-Client: `app/services/github_graphql.py` (wiederverwendbar)
- Sync-Richtung Hivemind→GitHub: via `sync_outbox` (`direction='outbound'`, `system='github'`)
- Sync-Richtung GitHub→Hivemind: via Webhooks (`projects_v2_item.*` Events)
- Konflikt-Regel: Hivemind gewinnt bei State-Konflikten (selbe Regel wie YouTrack)
- Konfiguration: per Project in `project_integrations` Tabelle

### Field-Mapping

| Hivemind | GitHub Project Field | Typ | Sync-Richtung |
| --- | --- | --- | --- |
| `task.state` | Status (Single Select) | Enum | Bidirektional (Hivemind wins) |
| `task.priority` | Priority (Single Select) | Enum | Hivemind → GitHub |
| `task.assigned_to` | Assignees | User | Hivemind → GitHub |
| `task.title` | Item Title | Text | Bidirektional |
| `epic.title` | Project Title | Text | Hivemind → GitHub |
| `task.key` | Hivemind Key (Custom Text) | Text | Hivemind → GitHub (read-only) |

### State-Mapping

```python
# Hivemind Task States → GitHub Project Status Field Options
STATE_MAPPING = {
    "incoming": "Backlog",
    "scoped": "Todo",
    "ready": "Todo",
    "in_progress": "In Progress",
    "in_review": "In Review",
    "qa_failed": "In Progress",  # Zurück in Arbeit
    "done": "Done",
    "blocked": "Blocked",
    "cancelled": "Done",  # Oder eigenes Feld
}

# Reverse Mapping (GitHub → Hivemind) — nur für Triage-Ingest
REVERSE_STATE_MAPPING = {
    "Backlog": None,     # Kein Hivemind-State-Change — nur informational
    "Todo": None,        # Kein automatischer State-Change
    "In Progress": None, # State-Changes nur über Hivemind MCP-Tools
    "Done": None,        # Nie automatisch done setzen — Review-Gate!
}
# WICHTIG: GitHub Board-Änderungen erzeugen KEINE automatischen State-Changes in Hivemind.
# Sie werden als [UNROUTED] Events ingestiert → Triage entscheidet.
# Dies schützt das Review-Gate.
```

### GraphQL-Client

```python
import httpx

class GitHubGraphQL:
    """GraphQL-Client für GitHub Projects V2 API."""

    def __init__(self, token: str, url: str = "https://api.github.com/graphql"):
        self.client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        self.url = url

    async def query(self, query: str, variables: dict = None) -> dict:
        resp = await self.client.post(self.url, json={
            "query": query,
            "variables": variables or {},
        })
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            raise GitHubGraphQLError(data["errors"])
        return data["data"]

    async def get_project(self, project_id: str) -> dict:
        return await self.query("""
            query($id: ID!) {
                node(id: $id) {
                    ... on ProjectV2 {
                        id
                        title
                        fields(first: 20) {
                            nodes {
                                ... on ProjectV2SingleSelectField {
                                    id name
                                    options { id name }
                                }
                                ... on ProjectV2Field {
                                    id name
                                }
                            }
                        }
                    }
                }
            }
        """, {"id": project_id})

    async def add_item(self, project_id: str, content_id: str) -> str:
        """Fügt Issue/PR als Item zum Project hinzu. Gibt Item-ID zurück."""
        result = await self.query("""
            mutation($project: ID!, $content: ID!) {
                addProjectV2ItemById(input: {projectId: $project, contentId: $content}) {
                    item { id }
                }
            }
        """, {"project": project_id, "content": content_id})
        return result["addProjectV2ItemById"]["item"]["id"]

    async def update_item_field(
        self, project_id: str, item_id: str, field_id: str, value: str
    ):
        """Aktualisiert ein Feld eines Project Items."""
        await self.query("""
            mutation($project: ID!, $item: ID!, $field: ID!, $value: ProjectV2FieldValue!) {
                updateProjectV2ItemFieldValue(input: {
                    projectId: $project
                    itemId: $item
                    fieldId: $field
                    value: $value
                }) { projectV2Item { id } }
            }
        """, {
            "project": project_id,
            "item": item_id,
            "field": field_id,
            "value": {"singleSelectOptionId": value},
        })
```

### Outbound-Sync (Hivemind → GitHub)

```python
class GitHubProjectsSync:
    """Bidirektionale Sync zwischen Hivemind und GitHub Projects V2."""

    async def on_task_state_changed(self, task_key: str, new_state: str):
        """Task-State-Change → GitHub Project Item Status aktualisieren."""
        integration = await self._get_integration(task_key)
        if not integration or not integration.github_project_id:
            return

        github_status = STATE_MAPPING.get(new_state)
        if not github_status:
            return

        # In sync_outbox schreiben (Outbox-Pattern)
        entry = SyncOutbox(
            direction="outbound",
            system="github",
            entity_type="task_state",
            entity_id=task_key,
            payload={
                "project_id": integration.github_project_id,
                "item_id": integration.github_item_id,
                "field_id": integration.status_field_id,
                "value": github_status,
            },
            dedup_key=f"github:task_state:{task_key}:{new_state}",
        )

    async def sync_new_task(self, task):
        """Neuer Task → GitHub Issue erstellen + zum Project hinzufügen."""
        # 1. GitHub Issue erstellen
        issue = await self.github_api.create_issue(
            repo=integration.github_repo,
            title=f"[{task.key}] {task.title}",
            body=self._format_task_body(task),
            labels=["hivemind"],
        )

        # 2. Issue zum Project hinzufügen
        item_id = await self.graphql.add_item(
            project_id=integration.github_project_id,
            content_id=issue["node_id"],
        )

        # 3. Mapping speichern
        await self._save_mapping(task.key, issue["number"], item_id)
```

### Inbound-Sync (GitHub → Hivemind)

```python
# Im github_webhook_handler.py:
case ("projects_v2_item", "edited"):
    # GitHub Board-Änderung → als Event ingestieren
    # NICHT automatisch Hivemind-State ändern (Review-Gate!)
    return {
        "source": "github",
        "event_type": "github_project_item_changed",
        "entity_type": "project_item",
        "entity_id": f"github:project_item:{item['id']}",
        "changes": raw.get("changes", {}),
        "action": action,
    }
    # → Landet in Triage als [UNROUTED]
    # → Triage/Admin entscheidet ob State-Change in Hivemind
```

### Konfiguration (per Project)

```python
class ProjectIntegration(Base):
    __tablename__ = "project_integrations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"))
    integration_type: Mapped[str] = mapped_column(String(50))  # "github_projects"
    github_repo: Mapped[str] = mapped_column(String(200))  # "owner/repo"
    github_project_id: Mapped[str] = mapped_column(String(100))  # GraphQL Node ID
    status_field_id: Mapped[str | None] = mapped_column(String(100))
    priority_field_id: Mapped[str | None] = mapped_column(String(100))
    sync_enabled: Mapped[bool] = mapped_column(default=True)
    sync_direction: Mapped[str] = mapped_column(default="bidirectional")  # bidirectional, hivemind_to_github, github_to_hivemind
    created_at: Mapped[datetime] = mapped_column(default=func.now())
```

### Setup-Flow

1. Admin erstellt GitHub Project V2 (oder verknüpft bestehendes)
2. Admin konfiguriert Integration in Hivemind Settings (Repo, Project-ID, Field-Mapping)
3. Initial-Sync: bestehende Tasks → GitHub Project Items
4. Laufend: Outbox-Consumer synct State-Changes, Webhooks synct Board-Änderungen

### Wichtige Regeln
- **GitHub Board-Änderungen erzeugen NIE automatische State-Changes in Hivemind** (Review-Gate-Schutz)
- Hivemind ist Source of Truth für Task-State — GitHub Board ist eine Spiegel-Ansicht
- Projects V2 API ist **nur GraphQL** — kein REST-Fallback
- Rate-Limit: GitHub GraphQL hat 5000 Points/h — Batch-Operationen beachten
- GitHub-seitige Änderungen werden als `[UNROUTED]` ingestiert → Triage entscheidet
- Conflict Resolution: Bei gleichzeitiger Änderung gewinnt Hivemind (Outbox überschreibt)
