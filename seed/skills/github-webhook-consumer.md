in der app später sind ---
title: "GitHub Webhook Consumer: Issues, PRs, Actions, Projects"
service_scope: ["backend"]
stack: ["python", "fastapi", "pydantic", "httpx"]
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

## Skill: GitHub Webhook Consumer

### Rolle
Du implementierst den GitHub-Webhook-Ingest — parallel zum bestehenden GitLab-Consumer. GitHub-Events (Issues, Pull Requests, Check Runs, Push, Projects V2) werden empfangen, validiert und als `direction='inbound'` in die `sync_outbox` geschrieben. Selbes Outbox-Pattern wie YouTrack/Sentry/GitLab.

### Kontext
GitHub nutzt HMAC-SHA256 Signatur-Validierung (Header: `X-Hub-Signature-256`). Events werden über einen generischen Webhook-Ingest-Router empfangen. Das Event-Mapping übersetzt GitHub-Events in Hivemind-Aktionen.

### Konventionen
- Router: `app/routers/webhooks.py` (erweitert bestehenden Router)
- Endpoint: `POST /api/webhooks/ingest/<token>` (generisch für alle Quellen)
- Alternativ: `POST /api/webhooks/github` (dediziert für GitHub)
- Handler: `app/services/github_webhook_handler.py`
- Secret: `HIVEMIND_GITHUB_WEBHOOK_SECRET` Env-Var (HMAC-SHA256)
- Auth (API-Calls zurück an GitHub): `HIVEMIND_GITHUB_TOKEN` (PAT) oder GitHub App Installation Token
- GitHub-URL: `HIVEMIND_GITHUB_URL` (Default: `https://api.github.com`, für GitHub Enterprise: custom)

### Event-Mapping

| GitHub Event | Action | Hivemind-Ziel | event_type |
| --- | --- | --- | --- |
| `issues` | `opened`, `reopened` | Triage `[UNROUTED]` | `github_issue_opened` |
| `issues` | `closed` | Status-Sync (optional) | `github_issue_closed` |
| `pull_request` | `opened` | Task-Artefakt-Link | `github_pr_opened` |
| `pull_request` | `merged`, `closed` | Task-Completion-Trigger | `github_pr_merged` |
| `check_run` | `completed` (conclusion: `failure`) | Triage `[UNROUTED]` (Bug-Kandidat) | `github_check_failed` |
| `check_suite` | `completed` (conclusion: `failure`) | CI-Status-Sync | `github_ci_failed` |
| `push` | — | Kartograph-Trigger | `github_push` |
| `workflow_run` | `completed` | CI-Status-Sync | `github_workflow_completed` |
| `projects_v2_item` | `edited`, `created` | GitHub Projects Sync | `github_project_item_changed` |
| `release` | `published` | Informational (Wiki/Notification) | `github_release` |

### Implementierung

```python
import hashlib
import hmac

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

@router.post("/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str = Header(None, alias="X-Hub-Signature-256"),
    x_github_event: str = Header(None, alias="X-GitHub-Event"),
    x_github_delivery: str = Header(None, alias="X-GitHub-Delivery"),
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()

    # 1. HMAC-SHA256 Signatur validieren
    if settings.github_webhook_secret:
        expected = hmac.new(
            settings.github_webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(f"sha256={expected}", x_hub_signature_256 or ""):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")

    payload = await request.json()
    action = payload.get("action", "")

    # 2. Idempotenz (X-GitHub-Delivery ist unique per Event)
    dedup_key = f"github:{x_github_delivery}"
    existing = await check_idempotency(db, dedup_key)
    if existing:
        return {"status": "duplicate", "id": str(existing.id)}

    # 3. Event normalisieren + in sync_outbox schreiben
    normalized = normalize_github_event(x_github_event, action, payload)
    if not normalized:
        return {"status": "ignored", "reason": f"Unhandled event: {x_github_event}.{action}"}

    entry = SyncOutbox(
        direction="inbound",
        system="github",
        entity_type=normalized["entity_type"],
        entity_id=normalized["entity_id"],
        event_type=normalized["event_type"],
        routing_state="unrouted",
        payload=normalized,
        dedup_key=dedup_key,
    )
    db.add(entry)
    await db.commit()

    return {"status": "accepted", "id": str(entry.id)}
```

### Payload-Normalisierung

```python
def normalize_github_event(event: str, action: str, raw: dict) -> dict | None:
    """GitHub-Webhook-Payload → internes Hivemind-Format."""

    match (event, action):
        case ("issues", "opened" | "reopened"):
            issue = raw["issue"]
            return {
                "source": "github",
                "event_type": "github_issue_opened",
                "entity_type": "issue",
                "entity_id": f"github:issue:{issue['number']}",
                "title": issue["title"],
                "body": issue.get("body", ""),
                "url": issue["html_url"],
                "author": issue["user"]["login"],
                "labels": [l["name"] for l in issue.get("labels", [])],
                "repo": raw["repository"]["full_name"],
                "created_at": issue["created_at"],
            }

        case ("pull_request", "opened" | "merged" | "closed"):
            pr = raw["pull_request"]
            return {
                "source": "github",
                "event_type": f"github_pr_{action}",
                "entity_type": "pull_request",
                "entity_id": f"github:pr:{pr['number']}",
                "title": pr["title"],
                "body": pr.get("body", ""),
                "url": pr["html_url"],
                "author": pr["user"]["login"],
                "base_branch": pr["base"]["ref"],
                "head_branch": pr["head"]["ref"],
                "merged": pr.get("merged", False),
                "repo": raw["repository"]["full_name"],
            }

        case ("check_run", "completed") if raw["check_run"]["conclusion"] == "failure":
            check = raw["check_run"]
            return {
                "source": "github",
                "event_type": "github_check_failed",
                "entity_type": "check_run",
                "entity_id": f"github:check:{check['id']}",
                "name": check["name"],
                "conclusion": check["conclusion"],
                "url": check["html_url"],
                "head_sha": check["head_sha"],
                "repo": raw["repository"]["full_name"],
            }

        case ("push", _):
            return {
                "source": "github",
                "event_type": "github_push",
                "entity_type": "push",
                "entity_id": f"github:push:{raw['after'][:12]}",
                "ref": raw["ref"],
                "commits": [{"sha": c["id"][:12], "message": c["message"]} for c in raw.get("commits", [])[:10]],
                "pusher": raw["pusher"]["name"],
                "repo": raw["repository"]["full_name"],
            }

        case ("projects_v2_item", _):
            item = raw.get("projects_v2_item", {})
            return {
                "source": "github",
                "event_type": "github_project_item_changed",
                "entity_type": "project_item",
                "entity_id": f"github:project_item:{item.get('id', 'unknown')}",
                "action": action,
                "project_id": item.get("project_node_id"),
                "content_type": item.get("content_type"),
                "content_id": item.get("content_node_id"),
            }

        case _:
            return None  # Unhandled event → ignore
```

### MCP-Tool-Wrapper (Read-only, für Agenten-Kontext)

```text
hivemind/get_github_pr        { "repo": "owner/repo", "number": 42 }
                                — PR-Details inkl. Diff-Stats, Review-Status, Checks
hivemind/get_github_issue      { "repo": "owner/repo", "number": 123 }
                                — Issue-Details inkl. Labels, Assignees, Kommentare
hivemind/get_github_workflow   { "repo": "owner/repo", "run_id": 456 }
                                — Workflow-Run-Details inkl. Jobs, Steps, Logs-URL
hivemind/search_github_issues  { "repo": "owner/repo", "query": "bug label:critical" }
                                — Issue-Suche via GitHub Search API
```

### GitHub App vs. PAT

| Aspekt | Personal Access Token (PAT) | GitHub App |
| --- | --- | --- |
| Setup | Einfach (1 Token) | Komplex (App registrieren, Install) |
| Rate-Limit | 5000 req/h (user-bound) | 5000 req/h (installation-bound) |
| Granularität | Fine-grained Scopes | Permissions per Repo |
| Empfehlung | Phase 8 Initial | Später für Multi-Repo |

**Phase-8-Empfehlung:** PAT für den Einstieg (einfacher Setup), Migration zu GitHub App bei Multi-Repo-Bedarf.

### Env-Variablen

| Variable | Default | Beschreibung |
| --- | --- | --- |
| `HIVEMIND_GITHUB_TOKEN` | — | GitHub PAT (Fine-Grained) |
| `HIVEMIND_GITHUB_URL` | `https://api.github.com` | API-URL (für Enterprise: custom) |
| `HIVEMIND_GITHUB_WEBHOOK_SECRET` | — | HMAC-SHA256 Webhook Secret |

### Wichtige Regeln
- Selbes Outbox-Pattern wie alle anderen Ingests (YouTrack, Sentry, GitLab)
- `X-GitHub-Delivery` Header als Idempotenz-Key (ist unique pro Event)
- Events die nicht im Mapping sind werden ignoriert (200 OK, `status: "ignored"`)
- Rate-Limiting: GitHub API hat 5000 req/h — bei MCP-Tool-Calls beachten
- Raw-Payload aufbewahren für DLQ-Debugging
