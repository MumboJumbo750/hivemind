# Phase 1 — Datenfundament

← [Phasen-Übersicht](./overview.md) | [Index](../../masterplan.md)

**Ziel:** Lauffähige Infrastruktur mit vollständigem Datenschema und funktionierender Prompt Station inkl. Inline-Review. Kein AI, kein MCP, kein Auth. Aber das Fundament auf dem alles aufbaut.

**AI-Integration:** Keine. Alles läuft manuell über Chat.

> **Scope-Entscheidung:** Phase 1 ist in zwei sequenzielle Sub-Phasen aufgeteilt, um Scope Creep zu vermeiden. Phase 1a liefert das technische Fundament (Backend + DB). Phase 1b baut darauf auf und liefert die erste nutzbare UI. Beide Sub-Phasen müssen abgeschlossen sein bevor Phase 2 beginnt.

---

## Phase 1a — Datenfundament (Backend)

**Fokus:** Docker Compose, vollständiges DB-Schema, State Machine, API-Skeleton.

### Deliverables Phase 1a

#### Backend

- [ ] Docker Compose Stack (PostgreSQL 16 + pgvector, FastAPI, Vue 3)
- [ ] Vollständiges Datenbankschema via Alembic-Migration (alle Tabellen aus Phase 1–8)
- [ ] FastAPI-Skeleton mit Health-Endpoint
- [ ] Grundlegende CRUD-Endpunkte (ohne Auth) für Projekte, Epics, Tasks
- [ ] Task-State-Machine als Backend-Logik (State-Validierung, erlaubte Transitionen)
- [ ] Epic Auto-Transition: `scoped → in_progress` atomar in `update_task_state`; `in_progress → done` atomar in `approve_review` und `cancel_task` (siehe [State Machine](../architecture/state-machine.md#epic-auto-transition--backend-implementierung))
- [ ] Outbox-Tabelle und DLQ-Tabelle (noch kein Consumer)
- [ ] Audit-Tabelle `mcp_invocations` (noch kein Audit-Writer)

### Acceptance Criteria Phase 1a

- [ ] `docker compose up` startet alle Services ohne Fehler
- [ ] `GET /health` antwortet mit `{"status": "ok"}`
- [ ] Alembic-Migration läuft durch ohne Fehler
- [ ] Alle Tabellen existieren in der Datenbank
- [ ] Task-State-Transition `incoming → scoped` funktioniert via API
- [ ] Direktes `done` ohne `in_review` wird blockiert — Transition `in_review → done` funktioniert, aber `in_progress → done` wird abgelehnt (Review-Gate)

---

## Phase 1b — Design & Prompt Station (Frontend)

**Fokus:** Design System, Layout Shell, Prompt Station mit Inline-Review und Inline-Scoping.

**Voraussetzung:** Phase 1a abgeschlossen (Backend + DB läuft).

### Deliverables Phase 1b

#### Frontend

- [ ] Vue 3 + Vite + TypeScript + Reka UI Scaffold
- [ ] `@hey-api/openapi-ts` Setup für die statische TypeScript-Client-Generierung aus der FastAPI `openapi.json`
- [ ] Token-basiertes Design System gemäß [UI Token-Schema](../ui/design-tokens.md) (keine Hardcoded-Styles in Components)
- [ ] Theme Engine mit mindestens 3 Themes (`space-neon` als Default, plus 2 Alternativen) gemäß Theme-Vertrag im [UI Token-Schema](../ui/design-tokens.md)
- [ ] Accessibility-Baseline im Design System: sichtbarer Focus-Ring (`--focus-ring-color`), `prefers-reduced-motion` respektiert
- [ ] Layout-Shell (System Bar, Nav Sidebar, Main Canvas, Context Panel, Status Bar)
- [ ] Prompt Station Skeleton (leerer State: "Kein Projekt aktiv")
- [ ] **Prompt Station: Inline-Review Mini-Formular** (Phase 1 ohne Command Deck):
  - Wenn Task `in_review` → Prompt Station zeigt eingebettetes Review-Panel
  - DoD-Checkliste (read-only, manuelle Abhakung)
  - Kommentar-Feld (optional)
  - Buttons: `[✗ ABLEHNEN → qa_failed]` und `[✓ GENEHMIGEN → done]`
  - Ruft `hivemind/approve_review` bzw. `hivemind/reject_review` auf (ohne Auth in Phase 1)
  - Ab Phase 2 delegiert die Prompt Station an den Command Deck (vollständiges Review Panel dort)
- [ ] **Prompt Station: Inline-Scoping Mini-Formular** (Phase 1 ohne Command Deck):
  - Wenn Epic `incoming` → Prompt Station zeigt eingebettetes Scoping-Formular
  - Felder: Priorität (`low / medium / high / critical`), SLA-Deadline (optional), DoD-Kurztext
  - Button: `[EPIC SCOPEN → scoped ▶]`
  - Ab Phase 2 delegiert die Prompt Station an den Command Deck (Scoping-Modal dort)
- [ ] Projekt-Anlegen-Dialog (minimal): Name, Slug, Beschreibung — erreichbar aus Prompt Station und System Bar
- [ ] Settings-Seite (Solo/Team-Toggle, MCP-Transport-Auswahl, Theme-Auswahl — noch ohne Backend-Anbindung)
- [ ] Routing (Vue Router — alle Views als Platzhalter angelegt)

### Technische Details

#### Docker Compose

> **Hinweis:** Ein initiales `docker-compose.yml` existiert bereits im Repo-Root als Scaffold. Phase 1 erweitert und finalisiert es mit den unten spezifizierten Services + Health-Checks + Volume-Mounts.

```yaml
services:
  postgres:   pgvector/pgvector:pg16
  backend:    FastAPI + Uvicorn (--reload)
  frontend:   Vue 3 + Vite (--host)
  # Ollama: NICHT in Phase 1 — kommt in Phase 3
```

#### Datenbankschema

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
- `level_thresholds`, `badge_definitions`, `user_achievements` (Gamification-Skeleton — befüllt ab Phase G)
- `prompt_history` (Schema ab Phase 1; befüllt ab Phase 3)

→ Vollständiges Schema: [data-model.md](../architecture/data-model.md)

#### State Machine Validierung (Backend)

Erlaubte Transitionen werden als Backend-Logik implementiert — kein Datenbank-Check, sondern Application-Level:

```python
# Admin kann jeden nicht-terminalen State auf cancelled setzen
ADMIN_CANCELLABLE = {"incoming", "scoped", "ready", "in_progress", "blocked", "escalated"}

ALLOWED_TRANSITIONS = {
    "incoming":    ["scoped", "cancelled"],
    "scoped":      ["ready", "cancelled"],
    "ready":       ["in_progress", "cancelled"],
    "in_progress": ["in_review", "blocked", "cancelled"],
    "in_review":   ["done", "qa_failed"],    # kein cancelled aus in_review — Owner muss entscheiden
    "qa_failed":   ["in_progress", "escalated"],  # escalated nur als System-Intercept bei qa_failed_count >= 3
    "blocked":     ["in_progress", "escalated", "cancelled"],  # escalated nur als System-Intercept bei Decision-SLA > 72h
    "escalated":   ["in_progress", "cancelled"],
    # "done" und "cancelled" sind Terminalstates — keine weiteren Transitionen
}

# Eskalations-Logik (System-Pfade, nicht vom User direkt aufrufbar):
# (a) qa_failed → escalated:  wenn qa_failed_count >= 3 und Worker versucht in_progress → System intercepted
# (b) blocked  → escalated:  wenn Decision-Request-SLA > 72h ohne Auflösung → System-Automatik

# qa_failed_count Logik:
# Bei jeder Transition in_review → qa_failed (via reject_review): tasks.qa_failed_count += 1
# Wenn qa_failed_count >= 3 und Worker versucht qa_failed → in_progress:
#   System intercepted → setzt escalated statt in_progress
```

#### Verzeichnisstruktur

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

## Acceptance Criteria Phase 1b

- [ ] API-Client (`src/api/client/`) kann über das Skript aus dem Backend-Core korrekt und typsicher generiert werden
- [ ] Frontend lädt auf `localhost:5173` ohne Fehler
- [ ] Reka UI ist eingebunden und Basis-Primitive (Dialog, Dropdown, Tabs) sind im Layout genutzt
- [ ] Design System entspricht [UI-Konzept](../ui/concept.md) und [UI Token-Schema](../ui/design-tokens.md) (token-basiert, keine Hardcoded-Styles)
- [ ] Theme-Switch in Settings funktioniert clientseitig (`space-neon` initial aktiv) und erfüllt den Theme-Vertrag aus dem [UI Token-Schema](../ui/design-tokens.md)
- [ ] Keyboard-Fokus ist auf interaktiven Controls sichtbar; reduzierte Motion wird bei `prefers-reduced-motion` angewendet
- [ ] Prompt Station zeigt leeren State: "Kein Projekt aktiv"
- [ ] Projekt-Anlegen-Dialog funktioniert: Projekt wird erstellt und ist in System Bar wählbar
- [ ] **Inline-Review:** Wenn ein Task `in_review` geht, erscheint das Mini-Formular in der Prompt Station mit DoD-Checkliste + Approve/Reject-Buttons
- [ ] **Inline-Scoping:** Wenn ein Epic `incoming` ist, erscheint das Scoping-Formular in der Prompt Station mit Priorität-Auswahl (low/medium/high/critical) + optionalem Deadline-Feld
- [ ] `hivemind/approve_review` über Inline-Formular setzt Task auf `done`
- [ ] `hivemind/reject_review` über Inline-Formular setzt Task auf `qa_failed`

---

## Abhängigkeiten

- Keine — Phase 1 ist das Fundament

## Öffnet folgende Phase

→ [Phase 2: Identity & RBAC](./phase-2.md)
