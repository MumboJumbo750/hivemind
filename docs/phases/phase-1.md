# Phase 1 — Datenfundament

← [Phasen-Übersicht](./overview.md) | [Index](../../masterplan.md)

**Ziel:** Lauffähige Infrastruktur mit vollständigem Datenschema. Kein AI, kein MCP, kein Auth. Aber das Fundament auf dem alles aufbaut.

**AI-Integration:** Keine. Alles läuft manuell über Chat.

---

## Deliverables

### Backend

- [ ] Docker Compose Stack (PostgreSQL 16 + pgvector, FastAPI, Vue 3)
- [ ] Vollständiges Datenbankschema via Alembic-Migration (alle Tabellen aus Phase 1–8)
- [ ] FastAPI-Skeleton mit Health-Endpoint
- [ ] Grundlegende CRUD-Endpunkte (ohne Auth) für Projekte, Epics, Tasks
- [ ] Task-State-Machine als Backend-Logik (State-Validierung, erlaubte Transitionen)
- [ ] Epic Auto-Transition: `scoped → in_progress` atomar in `update_task_state`; `in_progress → done` atomar in `approve_review` und `cancel_task` (siehe [State Machine](../architecture/state-machine.md#epic-auto-transition--backend-implementierung))
- [ ] Outbox-Tabelle und DLQ-Tabelle (noch kein Consumer)
- [ ] Audit-Tabelle `mcp_invocations` (noch kein Audit-Writer)

### Frontend

- [ ] Vue 3 + Vite + TypeScript + Reka UI Scaffold
- [ ] `@hey-api/openapi-ts` Setup für die statische TypeScript-Client-Generierung aus der FastAPI `openapi.json`.
- [ ] Token-basiertes Design System gemaess [UI Token-Schema](../ui/design-tokens.md) (keine Hardcoded-Styles in Components)
- [ ] Theme Engine mit mindestens 3 Themes (`space-neon` als Default, plus 2 Alternativen) gemaess Theme-Vertrag im [UI Token-Schema](../ui/design-tokens.md)
- [ ] Accessibility-Baseline im Design System: sichtbarer Focus-Ring (`--focus-ring-color`), `prefers-reduced-motion` respektiert
- [ ] Layout-Shell (System Bar, Nav Sidebar, Main Canvas, Context Panel, Status Bar)
- [ ] Prompt Station Skeleton (leerer State: "Kein Projekt aktiv")
- [ ] Projekt-Anlegen-Dialog (minimal): Name, Slug, Beschreibung — erreichbar aus Prompt Station und System Bar, damit der Kartograph-Bootstrap nicht auf Phase 2 warten muss
- [ ] Settings-Seite (Solo/Team-Toggle, MCP-Transport-Auswahl, Theme-Auswahl — noch ohne Backend-Anbindung)
- [ ] Routing (Vue Router — alle Views als Platzhalter angelegt)

---

## Technische Details

### Docker Compose

```yaml
services:
  postgres:   pgvector/pgvector:pg16
  backend:    FastAPI + Uvicorn (--reload)
  frontend:   Vue 3 + Vite (--host)
  # Ollama: NICHT in Phase 1 — kommt in Phase 3
```

### Datenbankschema

Alle Tabellen werden in Phase 1 erstellt — auch die die erst in späteren Phasen befüllt werden:

- `nodes`, `node_identity` (Federation — Peer-Registry + eigene Identität, wird beim Start auto-generiert)
- `users`, `app_settings` (Solo/Team-Konfiguration)
- `projects`, `project_members`
- `epics` (inkl. `origin_node_id`), `tasks` (inkl. `assigned_node_id`) — mit State Machine Columns + `qa_failed_count` + `result` + `artifacts` + `review_comment`
- `skills` (inkl. `origin_node_id`, `federation_scope`), `skill_versions`, `skill_parents` (Composition)
- `docs`, `context_boundaries`
- `wiki_articles` (inkl. `origin_node_id`, `federation_scope`), `wiki_versions`
- `code_nodes` (inkl. `origin_node_id`, `federation_scope='federated'` default, `exploring_node_id`), `code_edges` (inkl. `origin_node_id`), `node_bug_reports`, `epic_node_links`, `task_node_links`
- `mcp_invocations`, `sync_outbox` (mit `dedup_key` + `target_node_id`), `sync_dead_letter`
- `decision_requests`, `decision_records`
- `guards`, `task_guards`
- `notifications`
- `epic_restructure_proposals`

→ Vollständiges Schema: [data-model.md](../architecture/data-model.md)

### State Machine Validierung (Backend)

Erlaubte Transitionen werden als Backend-Logik implementiert — kein Datenbank-Check, sondern Application-Level:

```python
# Admin kann jeden nicht-terminalen State auf cancelled setzen
ADMIN_CANCELLABLE = {"incoming", "scoped", "ready", "in_progress", "blocked", "escalated"}

ALLOWED_TRANSITIONS = {
    "incoming":    ["scoped", "cancelled"],
    "scoped":      ["ready", "cancelled"],
    "ready":       ["in_progress", "cancelled"],
    "in_progress": ["in_review", "blocked", "escalated", "cancelled"],
    "in_review":   ["done", "qa_failed"],    # kein cancelled aus in_review — Owner muss entscheiden
    "qa_failed":   ["in_progress"],
    "blocked":     ["in_progress", "cancelled"],
    "escalated":   ["in_progress", "cancelled"],
    # "done" und "cancelled" sind Terminalstates — keine weiteren Transitionen
}

# qa_failed_count Logik:
# Bei jeder Transition in_review → qa_failed (via reject_review): tasks.qa_failed_count += 1
# Wenn qa_failed_count >= 3 und Worker versucht qa_failed → in_progress:
#   System intercepted → setzt escalated statt in_progress
```

### Verzeichnisstruktur

```text
hivemind/
├── masterplan.md
├── docs/                      ← diese Dokumentation
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/
│   │   └── versions/
│   │       └── 001_initial_schema.py
│   ├── scripts/
│   │   └── export_openapi.py    ← exported openapi.json statically
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── database.py
│       ├── models/
│       ├── routers/
│       └── services/
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── openapi-ts.config.ts     ← hey-api generator config
    ├── vite.config.ts
    └── src/
        ├── main.ts
        ├── App.vue
        |-- design/
        |   |-- tokens.css
        |   `-- themes/
        |       |-- space-neon.css
        |       |-- industrial-amber.css
        |       `-- operator-mono.css
        ├── router/
        ├── api/
        │   └── client/          ← auto-generated by openapi-ts
        ├── components/
        │   ├── layout/
        │   └── ui/
        └── views/
            ├── PromptStation.vue
            └── Settings.vue
```

---

## Acceptance Criteria

- [ ] `docker compose up` startet alle Services ohne Fehler
- [ ] `GET /health` antwortet mit `{"status": "ok"}`
- [ ] Alembic-Migration läuft durch ohne Fehler
- [ ] Alle Tabellen existieren in der Datenbank
- [ ] Task-State-Transition `incoming → scoped` funktioniert via API
- [ ] API-Client (`src/api/client/`) kann über das Skript aus dem Backend-Core korrekt und typsicher generiert werden.
- [ ] Direktes `done` ohne `in_review` wird blockiert — Transition `in_review → done` funktioniert, aber `in_progress → done` wird abgelehnt (Review-Gate)
- [ ] Frontend lädt auf `localhost:5173` ohne Fehler
- [ ] Reka UI ist eingebunden und Basis-Primitive (Dialog, Dropdown, Tabs) sind im Layout genutzt
- [ ] Design System entspricht [UI-Konzept](../ui/concept.md) und [UI Token-Schema](../ui/design-tokens.md) (token-basiert, keine Hardcoded-Styles)
- [ ] Theme-Switch in Settings funktioniert clientseitig (`space-neon` initial aktiv) und erfuellt den Theme-Vertrag aus dem [UI Token-Schema](../ui/design-tokens.md)
- [ ] Keyboard-Fokus ist auf interaktiven Controls sichtbar; reduzierte Motion wird bei `prefers-reduced-motion` angewendet
- [ ] Prompt Station zeigt leeren State: "Kein Projekt aktiv"
- [ ] Projekt-Anlegen-Dialog funktioniert: Projekt wird erstellt und ist in System Bar wählbar

---

## Abhängigkeiten

- Keine — Phase 1 ist das Fundament

## Öffnet folgende Phase

→ [Phase 2: Identity & RBAC](./phase-2.md)
