# REST API — Frontend-Backend-Vertrag

← [Index](../../masterplan.md) | [Übersicht](./overview.md)

Das Frontend kommuniziert mit dem Backend über eine **REST API** (JSON über HTTP). Die MCP-Tools (→ [mcp-toolset.md](./mcp-toolset.md)) sind für AI-Clients bestimmt; die REST API ist der Vertrag zwischen Vue-3-Frontend und FastAPI-Backend.

> **Typensicherheit:** Alle Request/Response-Modelle sind Pydantic-basiert. Der Build-Schritt exportiert `openapi.json` und `@hey-api/openapi-ts` generiert den typisierten Frontend-Client (→ [overview.md — API-Vertrag](./overview.md#api-vertrag--typensicherheit-golden-middle)).

---

## Authentifizierung & Session-Management

### Login-Flow

```text
1. User gibt username + password ein (Login-View)
2. POST /api/auth/login  { "username": "...", "password": "..." }
   → Backend prüft password_hash (argon2)
   → Gibt JWT Access-Token + Refresh-Token zurück
3. Access-Token wird im Memory (Pinia Store) gespeichert — nicht im LocalStorage
4. Refresh-Token wird als HttpOnly Secure Cookie gesetzt (kein JS-Zugriff)
5. Alle API-Requests senden Access-Token im Authorization: Bearer Header
```

### Token-Lifecycle

| Token | Speicherort | Lebenszeit | Erneuerung |
| --- | --- | --- | --- |
| **Access-Token** (JWT) | In-Memory (Pinia `useAuthStore`) | 15 Minuten | Automatisch via Refresh |
| **Refresh-Token** | HttpOnly Secure Cookie (`hivemind_refresh`) | 7 Tage | POST `/api/auth/refresh` |

**Access-Token Claims:**

```json
{
  "sub": "<user-uuid>",
  "role": "developer|admin|service|kartograph",
  "project_memberships": [
    { "project_id": "<uuid>", "role": "admin" },
    { "project_id": "<uuid>", "role": "developer" }
  ],
  "iat": 1709000000,
  "exp": 1709000900
}
```

### Auth-Endpoints

```text
POST   /api/auth/login      { "username": "...", "password": "..." }
                             → 200 { "access_token": "...", "user": {...} }
                             → 401 { "detail": "Invalid credentials" }

POST   /api/auth/refresh     (Cookie: hivemind_refresh=<token>)
                             → 200 { "access_token": "..." }
                             → 401 + Cookie löschen (Refresh-Token abgelaufen)

POST   /api/auth/logout      (Cookie: hivemind_refresh=<token>)
                             → 204 (Cookie wird serverseitig invalidiert)

POST   /api/auth/stream-token (Authorization: Bearer <access_token>)
                             → 200 { "stream_token": "<opaque>" }
                             → Kurzlebig (30s), single-use, nur für SSE-Handshake
```

### Solo-Modus — Vereinfachte Auth

Im Solo-Modus (`hivemind_mode = 'solo'`) ist Login optional:

| Szenario | Verhalten |
| --- | --- |
| Kein Password gesetzt (`password_hash = NULL`) | Login-Screen wird übersprungen; Auto-Login mit dem einzigen User |
| Password gesetzt | Login wie im Team-Modus |

> **Migrationspfad:** Beim Wechsel Solo → Team wird der erste User aufgefordert, ein Password zu setzen falls noch keines existiert.

### Service-Account-Auth (API-Key)

Service-Accounts (Rolle `service`) authentifizieren sich nicht per Login, sondern per statischem API-Key:

```text
Header: X-API-Key: <key>
Backend prüft: users WHERE api_key_hash = hash(<key>) AND role = 'service'
```

`api_key_hash` wird auf der `users`-Tabelle gespeichert (nur für `role = 'service'`).

---

## REST Endpoint-Übersicht

Alle Endpoints unter `/api/`. Jeder Request erfordert ein gültiges Access-Token im `Authorization: Bearer` Header (außer Auth-Endpoints und `/health`).

### Projects

```text
GET    /api/projects                          → Liste aller Projekte (gefiltert nach User-Membership)
POST   /api/projects                          → Neues Projekt anlegen
GET    /api/projects/:id                      → Projekt-Detail
PATCH  /api/projects/:id                      → Projekt bearbeiten
GET    /api/projects/:id/members              → Mitglieder-Liste
POST   /api/projects/:id/members              → Mitglied hinzufügen
PATCH  /api/projects/:id/members/:user_id     → Rolle ändern
DELETE /api/projects/:id/members/:user_id     → Mitglied entfernen
GET    /api/projects/:id/export               → Projekt-Export (JSON/CSV/Markdown)
```

### Epics & Tasks

```text
GET    /api/projects/:id/epics                → Epics mit Filter (state, owner, limit, offset)
POST   /api/projects/:id/epics                → Epic anlegen (state='incoming')
GET    /api/epics/:epic_key                   → Epic-Detail (z.B. EPIC-12)
PATCH  /api/epics/:epic_key                   → Epic bearbeiten (Owner, SLA, Priority, DoD)
GET    /api/epics/:epic_key/tasks             → Tasks des Epics mit Filter
POST   /api/epics/:epic_key/tasks             → Task anlegen
GET    /api/tasks/:task_key                   → Task-Detail (z.B. TASK-88)
PATCH  /api/tasks/:task_key                   → Task bearbeiten
PATCH  /api/tasks/:task_key/state             → State-Transition (mit Validierung)
POST   /api/tasks/:task_key/review            → Review: approve oder reject
GET    /api/epics/:epic_key/decisions         → Decision Records des Epics
GET    /api/epics/:epic_key/restructure-proposals → Restructure-Proposals
```

### Skills & Guards

```text
GET    /api/skills                            → Skills mit Filter (lifecycle, scope, project_id, federated)
GET    /api/skills/:id                        → Skill-Detail mit Composition-Chain
GET    /api/skills/:id/versions               → Immutable Versionshistorie
POST   /api/skills/:id/change-proposals       → Skill-Change-Proposal einreichen
GET    /api/guards                            → Guards mit Filter (scope, lifecycle, project_id)
GET    /api/guards/:id                        → Guard-Detail
GET    /api/tasks/:task_key/guards            → Alle Guards für einen Task (global+project+skill+task)
GET    /api/projects/:id/skills/export        → Skill-Export (JSON)
```

### Wiki

```text
GET    /api/wiki/articles                     → Artikel-Liste mit Suche (query, tags, limit, offset)
GET    /api/wiki/articles/:id                 → Artikel-Detail
POST   /api/wiki/articles                     → Artikel anlegen (kartograph + admin)
PATCH  /api/wiki/articles/:id                 → Artikel bearbeiten (kartograph + admin)
GET    /api/wiki/categories                   → Kategorie-Baum
GET    /api/projects/:id/wiki/export          → Wiki-Export (.zip Markdown)
```

### Triage

```text
GET    /api/triage                            → Triage-Items mit Filter (state: unrouted|escalated|dead|all)
GET    /api/triage/proposals                  → Offene Proposals (skill, guard, change, restructure)
POST   /api/triage/:id/route                  → Event einem Epic zuweisen
POST   /api/triage/:id/ignore                 → Event ignorieren
POST   /api/triage/dead-letters/:id/requeue   → Dead Letter requeuen
```

### Prompt Station

```text
GET    /api/prompt-queue                      → Aktuelle Queue mit Priorisierung
GET    /api/prompt-queue/active               → Aktiver Prompt (oberster Queue-Eintrag)
GET    /api/prompts/:id                       → Generierter Prompt (kompakt)
GET    /api/prompts/:id/assembled             → Vollständig assemblierter Prompt-Text
GET    /api/prompt-history                    → Prompt-Verlauf (limit, offset)
```

### Notifications

```text
GET    /api/notifications                     → Ungelesene Notifications (projektübergreifend)
PATCH  /api/notifications/:id/read            → Als gelesen markieren
POST   /api/notifications/read-all            → Alle als gelesen markieren
```

### Settings & Audit

```text
GET    /api/settings                          → Alle App-Settings (Key-Value)
PATCH  /api/settings/:key                     → Setting ändern (admin only)
GET    /api/audit                             → Audit-Log mit Filter (actor, tool, from, to, limit, offset)
GET    /api/audit/export                      → Audit-Export (CSV)
GET    /api/users/me                          → Eigenes Profil (inkl. EXP, Level, Achievements)
PATCH  /api/users/me                          → Profil bearbeiten
GET    /api/users/me/achievements             → Eigene Achievements/Badges
```

### Federation

```text
GET    /api/federation/peers                  → Verbundene Peers mit Status
POST   /api/federation/peers                  → Peer hinzufügen
DELETE /api/federation/peers/:node_id         → Peer entfernen (inkl. Cleanup)
POST   /api/federation/peers/:node_id/block   → Peer blockieren
POST   /api/federation/peers/:node_id/ping    → Manueller Ping
GET    /api/federation/identity               → Eigene Node-Identität (Name, URL, Public Key)
GET    /api/federation/shared-epics           → Shared Epics über Peer-Grenzen
GET    /api/federation/guild-skills           → Federated Skills aller Peers
```

### Nexus Grid

```text
GET    /api/projects/:id/code-graph           → Code-Nodes + Edges für Cytoscape.js
                                                Query-Params: area (Optional Pfad-Filter),
                                                max_depth, include_fog (Boolean)
GET    /api/projects/:id/code-graph/heatmap   → Bug-Heatmap-Daten (Knoten-Farbe nach Bug-Dichte)
GET    /api/code-nodes/:id                    → Code-Node-Detail (Docs, Skills, Bugs, Tasks)
```

### Health

```text
GET    /health                                → System-Health (kein Auth nötig)
                                                → 200 { "status": "ok", "db": "ok", "mcp": "ok" }
```

---

## Response-Format (Konvention)

### Erfolg

```json
{
  "data": { ... },
  "meta": {
    "total": 42,
    "limit": 50,
    "offset": 0
  }
}
```

Listen-Endpoints geben `data` als Array + `meta` mit Paginierung. Detail-Endpoints geben `data` als Object ohne `meta`.

### Fehler

```json
{
  "detail": "Beschreibung des Fehlers",
  "error_code": "GUARD_BLOCK",
  "context": {
    "guards_pending": ["uuid1", "uuid2"]
  }
}
```

Standardisierte `error_code`-Werte:

| Code | HTTP | Beschreibung |
| --- | --- | --- |
| `INVALID_CREDENTIALS` | 401 | Login fehlgeschlagen |
| `TOKEN_EXPIRED` | 401 | Access-Token abgelaufen |
| `FORBIDDEN` | 403 | Keine Berechtigung für diese Aktion |
| `NOT_FOUND` | 404 | Ressource nicht gefunden |
| `VERSION_CONFLICT` | 409 | Optimistic Locking — `expected_version` stimmt nicht |
| `GUARD_BLOCK` | 422 | Guards nicht alle passed/skipped — in_review blockiert |
| `VALIDATION_ERROR` | 422 | Pflichtfelder fehlen oder ungültig |
| `STATE_TRANSITION_INVALID` | 422 | Zustandsübergang nicht erlaubt |
| `RATE_LIMITED` | 429 | Rate-Limit überschritten |
| `INTERNAL_ERROR` | 500 | Unerwarteter Serverfehler |

---

## SSE Event-Schema (Server-Sent Events)

Alle SSE-Streams unter `/events/`. Subscriptions erfordern Authentifizierung — da SSE keine Custom-Header unterstützt, wird ein **kurzlebiges Stream-Token** verwendet statt des regulären JWT:

```text
1. Client ruft POST /api/auth/stream-token auf (mit regulärem Bearer-Token)
   → Backend generiert einmaliges Stream-Token (Lebenszeit: 30 Sekunden, single-use)
   → Response: { "stream_token": "<opaque-token>" }
2. Client öffnet SSE-Verbindung: /events/tasks?token=<stream_token>&project_id=<uuid>
3. Backend löst stream_token auf (validiert, markiert als verbraucht, extrahiert User-Claims)
4. Stream bleibt offen bis Disconnect (kein erneutes Token nötig nach Handshake)
```

> **Security-Hinweis:** Das reguläre JWT wird **nicht** als Query-Parameter gesendet — Query-Strings werden in Proxy-Logs, Browser-History und Monitoring sichtbar. Das Stream-Token ist einmalig nutzbar, kurzlebig (30s) und nicht für andere API-Calls gültig. Falls ein Stream-Token abgegriffen wird, ist das Zeitfenster für Missbrauch minimal.

### Kanäle

| Kanal | URL | Events |
| --- | --- | --- |
| Notifications | `/events/notifications?token=<stream_token>` | Neue Notifications, SLA-Alerts |
| Tasks | `/events/tasks?project_id=<uuid>&token=<stream_token>` | State-Transitions, Guard-Updates |
| Triage | `/events/triage?token=<stream_token>` | Neue Unrouted-Items, Proposals |

### Event-Format

Jedes Event folgt dem SSE-Standard mit `event`-Typ und `data`-JSON:

```text
event: task_state_changed
data: {"task_key":"TASK-88","old_state":"in_progress","new_state":"in_review","actor_id":"uuid","timestamp":"2026-03-10T14:32:00Z"}

event: notification
data: {"id":"uuid","type":"sla_warning","title":"EPIC-12 läuft in 4h ab","priority":"critical","target_view":"command-deck","target_id":"EPIC-12","created_at":"2026-03-10T14:30:00Z"}

event: guard_result_reported
data: {"task_key":"TASK-88","guard_id":"uuid","status":"passed","result":"All 42 tests passed","actor_id":"uuid","timestamp":"2026-03-10T14:31:00Z"}
```

### Event-Typen (kanonische Liste)

**Kanal: `/events/tasks`**

| Event-Typ | Payload | Auslöser |
| --- | --- | --- |
| `task_state_changed` | `task_key`, `old_state`, `new_state`, `actor_id`, `timestamp` | Jede State-Transition |
| `task_assigned` | `task_key`, `assigned_to`, `assigned_node_id` (optional), `actor_id` | `assign_task` |
| `guard_result_reported` | `task_key`, `guard_id`, `status`, `result`, `actor_id` | `report_guard_result` |
| `task_result_submitted` | `task_key`, `has_artifacts`, `actor_id` | `submit_result` |
| `epic_state_changed` | `epic_key`, `old_state`, `new_state`, `actor_id` | Epic-State-Transition |
| `context_boundary_set` | `task_key`, `skill_count`, `token_budget_used` | `set_context_boundary` |

**Kanal: `/events/notifications`**

| Event-Typ | Payload | Auslöser |
| --- | --- | --- |
| `notification` | `id`, `type`, `title`, `priority`, `target_view`, `target_id`, `created_at` | Jede neue Notification (aus kanonischer Liste in [views.md](../ui/views.md)) |
| `sla_tick` | `epic_key`, `remaining_hours`, `severity` (warning/breach) | SLA-Cron bei < 4h |

**Kanal: `/events/triage`**

| Event-Typ | Payload | Auslöser |
| --- | --- | --- |
| `unrouted_event` | `outbox_id`, `source_system`, `summary`, `suggested_epics[]` | Neuer ungerouteter Webhook-Event |
| `proposal_submitted` | `proposal_id`, `type` (skill/guard/change/restructure), `title`, `proposed_by` | Neue Proposal eingereicht |
| `dead_letter` | `id`, `original_outbox_id`, `error`, `attempts` | Sync-Fehler in DLQ verschoben |

**Heartbeat (alle Kanäle):**

```text
: heartbeat
```

Intervall: 15 Sekunden (konfigurierbar via `HIVEMIND_SSE_HEARTBEAT_INTERVAL`). Kein `event:`-Feld — reiner SSE-Kommentar.

---

## Projekt-Scoping

Alle projekt-bezogenen Endpoints filtern automatisch nach den Projekt-Memberships des JWT-Subjects:

- `GET /api/projects` → nur Projekte in denen der User Mitglied ist
- `GET /api/projects/:id/epics` → 403 wenn kein Projekt-Mitglied
- **Wiki** ist projektunabhängig — kein Projekt-Filter
- **Notifications** sind projektübergreifend — kein Projekt-Filter

---

## Versionierung

Die API ist initial unversioniert (`/api/...`). Bei Breaking Changes wird `/api/v2/` eingeführt; `/api/` bleibt Alias auf die aktuelle stabile Version. Innerhalb einer Major-Version sind nur additive Änderungen erlaubt (neue Felder, neue Endpoints).
