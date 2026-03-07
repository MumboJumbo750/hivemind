# Projekt-Repos lokal betreiben

Referenz-Epic: `EPIC-PROJ-AUTO`  
Tracking-Tasks: `TASK-PROJ-001` bis `TASK-PROJ-006`

## Zielbild

Ein lokales Repo wird als Hivemind-Projekt geführt. Anforderungen kommen
entweder direkt über die App oder über projektbezogene Integrationen
(`YouTrack`, `Sentry`) rein. Hivemind speichert dabei immer:

- Projektkontext
- Repo-/Workspace-Kontext
- Intake-Status (`captured`, `materialized`, `triage_pending`)
- Dispatch-/Governance-Entscheidung

## Voraussetzungen

Für den lokalen Betrieb müssen mindestens diese Services laufen:

- `backend`
- `frontend`
- `postgres`
- optional `ollama`

Schnellcheck:

```powershell
podman compose ps
curl http://localhost:8000/health
curl http://localhost:8000/api/mcp/discovery
```

## Neues Repo als Projekt anbinden

1. Projekt in der App anlegen:
   - Name / Slug
   - `repo_host_path`
   - optional `default_branch`, `remote_url`
2. Onboarding prüfen:
   - `POST /api/projects/{project_id}/onboarding/preview`
   - auf `warnings`, `requires_restart` und `files` achten
3. Onboarding anwenden:
   - `POST /api/projects/{project_id}/onboarding/apply`
4. Backend neu starten, falls `requires_restart=true`
5. Runtime verifizieren:
   - `POST /api/projects/{project_id}/onboarding/verify`
   - Zielstatus: `ready`

## YouTrack / Sentry an Projekt koppeln

Settings → `Integrationen`

Empfohlene Mindestkonfiguration:

- `YouTrack`
  - `integration_key`
  - `base_url`
  - `external_project_key`
  - optional `project_selector.aliases`
  - `access_token` für Healthcheck / Outbound
  - `webhook_secret` für Inbound

- `Sentry`
  - `integration_key`
  - optional `base_url`
  - `external_project_key` oder `project_selector.aliases`
  - optional `access_token` für Healthcheck
  - optional `webhook_secret`

Prüfen:

- `POST /api/projects/{project_id}/integrations/{integration_id}/check`
- Status in der Settings-Ansicht kontrollieren

## Smoke-Flows

### 1. Requirement direkt in der App

Soll:

- `POST /api/epic-proposals/draft-requirement`
- liefert `draft_id`, `prompt`, `intake`
- wiederholte identische Anforderungen reusen denselben Draft

Prüfen:

- `intake.materialization == existing_draft` beim zweiten identischen Call

### 2. Sentry-Event

Soll:

- Webhook speichert `project_context` und `_intake`
- `process_inbound()` materialisiert `bug_report`
- Event landet als `routed`, nicht als Endlosschleife in der Auto-Queue

Prüfen:

- `sync_outbox.project_id`
- `sync_outbox.routing_detail.intake_stage == materialized`

### 3. YouTrack-Event

Soll:

- Webhook ordnet Projekt/Integration zu
- Inbound bleibt bei fehlender Direkt-Materialisierung bewusst `triage_pending`
- Triage zeigt Projekt und Grund sichtbar an

Prüfen:

- `sync_outbox.project_id`
- `sync_outbox.routing_state == unrouted`
- `sync_outbox.routing_detail.intake_stage == triage_pending`

### 4. Kontrollierter Agentenstart

Soll:

- nur `triage_pending`-Inbound-Events triggern Auto-Triage
- derselbe Event erzeugt keinen zweiten konkurrierenden Dispatch
- `conductor_dispatches.result.dispatch_context` enthält Projekt-/Repo-Kontext

Prüfen:

- `routing_detail.dispatch_status`
- `routing_detail.dispatch_mode`
- `conductor_dispatches.result.dispatch_context`

## Repo-Wechsel kontrolliert durchführen

Aktuell bleibt der Workspace-Laufzeitpfad global. Deshalb:

1. aktuelles Projekt sauber verifizieren
2. neues Projekt mit neuem Repo onboarden
3. `docker-compose.override.yml` anwenden
4. Backend neu starten
5. `verify` ausführen
6. Integrationsstatus neu prüfen

Nicht empfohlen:

- Repo-Pfad einfach im laufenden Betrieb umbiegen, ohne Verify/Restart

## Troubleshooting

### Workspace / Mount

- Symptom: `verify` liefert `workspace_accessible=false`
- Prüfen: Container-Mount, `docker-compose.override.yml`, Neustart

### Webhook wird angenommen, aber keinem Projekt zugeordnet

- `project_context.matched=false`
- `external_project_key` und `project_selector.aliases` prüfen
- Header-Overrides testen:
  - `x-hivemind-project-id`
  - `x-hivemind-project`
  - `x-hivemind-integration-key`

### Event bleibt dauerhaft in `unrouted`

- beabsichtigt bei `triage_pending`
- `routing_detail.reason` prüfen
- Triage-Dispatch-Status prüfen

### Conductor dispatcht doppelt

- `routing_detail.dispatch_status` prüfen
- offene `conductor_dispatches` mit gleichem Trigger prüfen
- Cooldown und `triage_pending`-Filter kontrollieren

### Requirement erzeugt immer neue Drafts

- Text muss identisch sein
- bestehende Draft-/Proposal-Einträge im Projekt prüfen

## Test-/Verifikationsbefehle

```powershell
podman compose exec backend /app/.venv/bin/pytest tests/test_project_integration_service.py tests/test_intake_service.py tests/test_conductor_project_automation.py -q
podman compose exec backend /app/.venv/bin/pytest tests/integration/test_project_repo_smoke_flows.py -q
podman compose exec backend /app/.venv/bin/alembic upgrade head
```

## Übergabekriterien für lokale Nutzung

Der lokale Flow ist produktiv nutzbar, wenn:

- Projekt-Onboarding auf `ready` steht
- Integrationen im Status `active` oder bewusst `incomplete` sind
- Requirement-Drafts idempotent wiederverwendet werden
- Sentry/YouTrack-Events Projektkontext tragen
- `triage_pending`-Events sichtbar bleiben und nicht reprocessen
- Auto-Dispatches Projekt-/Repo-Kontext im Dispatch-Record tragen
