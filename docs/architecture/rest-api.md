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

## Security Policy — Auth-Abgrenzung

Vier Auth-Pfade koexistieren. Die Middleware entscheidet anhand von Endpoint-Pfad und Header:

| Auth-Pfad | Scope | Header / Mechanismus | Wer |
| --- | --- | --- | --- |
| **Bearer JWT** | Alle `/api/*`-Endpoints (außer Auth + `/health`) | `Authorization: Bearer <token>` | Menschliche User (developer, admin, kartograph) |
| **API-Key** | Alle `/api/*`-Endpoints (außer Auth + `/health`) | `X-API-Key: <key>` | Service-Accounts (`role = 'service'`). Kein Login-Flow, kein Refresh-Token. |
| **Solo Auto-Login** | Alle `/api/*`-Endpoints | Kein Header nötig; Backend erkennt Solo-Modus + `password_hash IS NULL` → impliziter System-User | Solo-Modus ohne Passwort. **Hard-Block bei Federation:** Wenn `HIVEMIND_FEDERATION_ENABLED=true` und `hivemind_mode='solo'` **und** kein Passwort gesetzt, **verweigert das Backend den Start** mit Fehler: `"FATAL: Solo+Federation ohne Passwort ist nicht erlaubt. Entweder Passwort setzen (hivemind set-password) oder Federation deaktivieren."` **Begründung:** Im Solo-Modus ohne Passwort sind alle `/api/*`-Endpoints ohne Header nutzbar. Sobald die Instanz nicht strikt lokal bleibt (Federation = Netzwerk-Erreichbarkeit), ist das ein Sicherheitsrisiko. Federation-Endpoints (`/federation/*`) haben zwar eigene Ed25519-Signaturprüfung, aber die `/api/*`-Endpoints wären ungeschützt. |
| **Ed25519-Signatur** | Alle `/federation/*`-Endpoints | `X-Hivemind-Signature` Header (Ed25519 über Body-Hash) | Peer-Nodes. Kein JWT/API-Key nötig. Unbekannte oder ungültige Signatur → HTTP 401. |

**Reihenfolge der Middleware-Prüfung (pro Request):**

```text
1. Pfad beginnt mit /federation/* → Ed25519-Signaturprüfung (kein JWT/API-Key nötig)
2. Pfad ist /health oder /api/auth/* → kein Auth nötig
3. Header X-API-Key vorhanden → API-Key-Auth (service-Rolle)
4. Header Authorization: Bearer vorhanden → JWT-Auth
5. Solo-Modus + password_hash IS NULL → Auto-Login mit System-User
6. Nichts davon → HTTP 401
```

> **Regel:** Bearer und API-Key schließen sich gegenseitig aus — ein Request hat entweder `Authorization: Bearer` oder `X-API-Key`, nie beides. Bei beiden Headern gleichzeitig → HTTP 400.

---

## REST Endpoint-Übersicht

Alle Endpoints unter `/api/`. Jeder Request erfordert ein gültiges Access-Token im `Authorization: Bearer` Header (außer Auth-Endpoints, `/health` und `/federation/*` — siehe Security Policy oben).

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
POST   /api/epics/:epic_key/docs              → Epic-Doc anlegen (admin, ab Phase 3)
GET    /api/tasks/:task_key                   → Task-Detail (z.B. TASK-88)
PATCH  /api/tasks/:task_key                   → Task bearbeiten
PATCH  /api/tasks/:task_key/state             → State-Transition (mit Validierung)
POST   /api/tasks/:task_key/review            → Review: approve oder reject
GET    /api/epics/:epic_key/decisions         → Decision Records des Epics
GET    /api/epics/:epic_key/restructure-proposals → Restructure-Proposals
```

### Epic Restructure

```text
GET    /api/epic-restructure                  → Alle Proposals mit Filter (state: proposed|accepted|applied|rejected)
POST   /api/epic-restructure                  → Neuen Proposal erstellen (kartograph + admin)
                                                Body: { "restructure_type": "split|merge|task_move",
                                                        "payload": { ... }, "rationale": "...",
                                                        "code_node_refs": ["uuid"] }
GET    /api/epic-restructure/:key             → Einzelner Proposal + Diff-Preview (im accepted-State)
POST   /api/epic-restructure/:key/accept      → Proposal akzeptieren (admin, → accepted)
POST   /api/epic-restructure/:key/reject      → Proposal ablehnen (admin, → rejected)
                                                Body: { "reason": "..." }
POST   /api/epic-restructure/:key/apply       → Restructure ausführen (admin, → applied)
                                                → 200 bei Erfolg (neue Epic-Keys + verschobene Tasks im Response)
                                                → 422 wenn blockierende Tasks vorhanden (blocking_tasks-Liste)
                                                → Vollständiger Apply-Flow: docs/features/epic-restructure.md
```

### Skills & Guards

```text
GET    /api/skills                            → Skills mit Filter (lifecycle, scope, project_id, federated)
GET    /api/skills/:id                        → Skill-Detail mit Composition-Chain
GET    /api/skills/:id/versions               → Immutable Versionshistorie
POST   /api/skills/:id/change-proposals       → Skill-Change-Proposal einreichen
POST   /api/skills/:id/fork                   → Federierten Skill lokal forken (Phase F+)
                                                Body: { "node_id": "<origin-peer-uuid>" }
                                                → 201 { "skill_id": "<uuid>", "lifecycle": "draft", "extends": "<origin-id>" }
                                                → Intern: erstellt lokalen Draft mit extends-Link auf Origin-Skill
                                                → Selber Service wie MCP-Tool hivemind/fork_federated_skill
GET    /api/guards                            → Guards mit Filter (scope, lifecycle, project_id)
GET    /api/guards/:id                        → Guard-Detail
POST   /api/guards                            → Guard anlegen (admin, ab Phase 3)
PATCH  /api/guards/:id                        → Guard bearbeiten (admin, ab Phase 3)
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

### Globale Suche (Spotlight)

Die Spotlight-Suche (Ctrl+K) nutzt einen übergreifenden Such-Endpoint. Die Ergebnisse sind RBAC-gefiltert und nach Entitätstyp gruppiert.

```text
GET    /api/search                            → Übergreifende Suche
                                                Query-Params:
                                                  q (Pflicht): Suchbegriff (mind. 2 Zeichen)
                                                  types (Optional): Komma-separiert: tasks,epics,skills,guards,wiki,code_nodes
                                                         Default: alle verfügbaren Typen der aktuellen Phase
                                                  project_id (Optional): Auf ein Projekt beschränken
                                                  limit (Optional): Max. Ergebnisse pro Typ (Default: 5, Max: 20)
                                                → Response: { data: { tasks: [...], epics: [...], skills: [...], ... } }
                                                → Suchmethode:
                                                  Phase 2–3: ILIKE-Suche auf title/name-Feldern (Fuzzy via trigram)
                                                  Ab Phase 3: Hybrid — ILIKE + pgvector-Similarity (bestes Ergebnis gewinnt)
                                                → RBAC: Developer sieht nur Entitäten aus eigenen Projekten/Epics;
                                                  Admin/Kartograph sieht alles; context_boundary_filter wird angewendet
                                                → Phasen-Rollout: Phase 2 (Tasks+Epics), Phase 4 (+Skills+Guards),
                                                  Phase 5 (+Wiki+Code-Nodes)
```

### Triage

```text
GET    /api/triage                            → Triage-Items mit Filter (state: unrouted|escalated|dead|quarantined|all)
GET    /api/triage/proposals                  → Offene Proposals (skill, guard, change, restructure)
POST   /api/triage/:id/route                  → Event einem Epic zuweisen
POST   /api/triage/:id/ignore                 → Event ignorieren
POST   /api/triage/dead-letters/:id/requeue   → Dead Letter requeuen
POST   /api/triage/dead-letters/:id/discard   → Dead Letter verwerfen (endgültig, Audit-Trail bleibt)
POST   /api/triage/quarantined/:id/approve    → Quarantined-Eintrag freigeben (→ state: pending, wird normal verarbeitet)
POST   /api/triage/quarantined/:id/discard    → Quarantined-Eintrag verwerfen (→ state: cancelled, Audit-Trail bleibt)
                                                Body (optional): { "reason": "..." }
POST   /api/triage/bugs/:id/assign            → Bug manuell einem Epic zuweisen (ab Phase 7, admin)
                                                Body: { "epic_id": "<uuid>" }
                                                → Intern: hivemind/assign_bug; setzt routing_state=routed
```

### Prompt Station

```text
GET    /api/prompt-station/status              → Aktueller Prompt-Station-State (idle|agent_required|waiting_for_mcp|
                                                completed|human_action_required|api_key_mode) + Actions-Array
                                                → Berechnet aus Task/Epic/Decision-Request-Daten (→ prompt-station.md)
GET    /api/prompt-queue                      → Aktuelle Queue mit Priorisierung
GET    /api/prompt-queue/active               → Aktiver Prompt (oberster Queue-Eintrag)
GET    /api/prompts/:id                       → Generierter Prompt (kompakt)
GET    /api/prompts/:id/assembled             → Vollständig assemblierter Prompt-Text
POST   /api/prompts/:id/override              → Angepassten Prompt-Text speichern (ab Phase 2)
                                                Body: { "override_text": "..." }
                                                → 200 { "prompt_id": "...", "override_active": true }
                                                → Override ersetzt den assemblierten Text für diesen Queue-Eintrag.
                                                  Beim nächsten Laden ohne Override wird der Text neu assembliert.
                                                  Scoped auf den jeweiligen Queue-Eintrag; in prompt_history.override_text gespeichert.
GET    /api/prompt-history                    → Prompt-Verlauf (limit, offset)
```

### Webhooks

```text
GET    /api/webhooks                          → Liste konfigurierter Webhook-Quellen (YouTrack, Sentry, etc.)
POST   /api/webhooks                          → Neue Webhook-Quelle anlegen (admin)
                                                Body: { "source": "youtrack|sentry|custom", "name": "...",
                                                        "enabled": true, "event_types": ["issue.*"] }
                                                → 201 { "id": "...", "endpoint_url": "/webhooks/ingest/<token>", "auth_token": "..." }
GET    /api/webhooks/:id                      → Webhook-Detail inkl. letztem Event-Timestamp
PATCH  /api/webhooks/:id                      → Webhook bearbeiten (enabled toggle, event_types)
DELETE /api/webhooks/:id                      → Webhook entfernen (admin)
GET    /api/webhooks/:id/events               → Letzte 50 empfangene Events (limit, offset)
```

> **Ingest-Endpoint:** `POST /webhooks/ingest/<token>` (kein `/api/`-Prefix) ist der öffentliche Endpunkt für eingehende Webhooks. Keine Auth außer Token-Verifikation. Schreibt `direction='inbound'` in `sync_outbox`.

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

### Governance & Conductor (Phase 8)

```text
GET    /api/settings/governance               → Governance-Levels (7 Entscheidungstypen × 3 Stufen)
                                                → { "review": { "level": "assisted", "confidence_threshold": 0.85, "grace_minutes": 15 }, ... }
PATCH  /api/settings/governance               → Governance-Levels ändern (admin only)
                                                → Body: { "<typ>": { "level": "manual|assisted|auto", ...Optionen } }
GET    /api/tasks/:task_key/review-recommendation
                                              → AI-Review-Empfehlung für einen Task (falls vorhanden)
                                                → { "recommendation": "approve", "confidence": 0.92, "summary": "...", "checklist": [...], "concerns": [] }
POST   /api/tasks/:task_key/review-recommendation/accept
                                              → Owner bestätigt AI-Empfehlung (nur bei assisted)
                                                → triggert approve_review oder reject_review je nach recommendation
POST   /api/tasks/:task_key/review-recommendation/override
                                              → Owner überschreibt AI-Empfehlung (bei assisted oder auto-Grace-Period)
                                                → Body: { "action": "approve|reject", "comment": "..." }
GET    /api/conductor/dispatches              → Letzte Conductor-Dispatches (admin, limit, offset)
                                                → [{ "trigger_event": "task.state.in_review", "agent_role": "reviewer", "status": "completed", ... }]
GET    /api/conductor/status                  → Conductor-Health (enabled, active_dispatches, cooldown_status)
```

> **Governance-Sicherheit:** `PATCH /api/settings/governance` erfordert `admin`-Rolle. Ungültige Level-Kombinationen (z.B. `auto` ohne `confidence_threshold`) werden serverseitig validiert und mit HTTP 422 abgelehnt.

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
POST   /api/federation/emergency-revoke       → Notfall-Revocation: setzt nodes.public_key eines Peers sofort auf NULL
                                                Body: { "node_id": "<uuid>", "reason": "..." }
                                                → 200 { "node_id": "...", "revoked_at": "..." }
                                                → Keine Grace-Period — alle weiteren Nachrichten dieses Peers: HTTP 401
                                                → Erzeugt Audit-Eintrag. Admin-Only.
                                                → Muss auf JEDEM Peer-Node einzeln ausgeführt werden (kein Broadcast)
                                                → Verwendung: Key-Kompromittierung (→ federation.md#key-kompromittierung--notfallprozedur)
```

### Nexus Grid

```text
GET    /api/projects/:id/code-graph           → Code-Nodes + Edges für Cytoscape.js
                                                Query-Params: area (Optional Pfad-Filter),
                                                max_depth, include_fog (Boolean)
GET    /api/projects/:id/code-graph/heatmap   → Bug-Heatmap-Daten (Knoten-Farbe nach Bug-Dichte)
GET    /api/code-nodes/:id                    → Code-Node-Detail (Docs, Skills, Bugs, Tasks)
POST   /api/code-nodes                        → Code-Node anlegen (kartograph + admin, ab Phase 3)
PATCH  /api/code-nodes/:id                    → Code-Node bearbeiten (kartograph + admin, ab Phase 3)
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

### Polling-Fallback-Endpoint

Wird nach 3 fehlgeschlagenen SSE-Reconnects aktiviert (→ [architecture/overview.md — SSE-Fallback](overview.md#realtime-sse--polling-fallback)):

```text
GET /api/events/poll?channel=tasks&since=<last_event_id>&project_id=<uuid>
→ 200 { "events": [...], "last_id": 4220 }
→ Auth: Bearer JWT (reguläre Auth, kein Stream-Token)
→ Polling-Intervall: 30 Sekunden (HIVEMIND_POLL_FALLBACK_INTERVAL)
```

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

**Kanal: `/events/conductor`** *(Phase 8)*

| Event-Typ | Payload | Auslöser |
| --- | --- | --- |
| `agent_dispatched` | `dispatch_id`, `agent_role`, `prompt_type`, `trigger_event`, `provider` | Conductor dispatcht einen Agent |
| `agent_completed` | `dispatch_id`, `agent_role`, `duration_ms`, `result_status` | Agent-Dispatch abgeschlossen |
| `review_recommendation` | `task_key`, `recommendation`, `confidence`, `summary` | Reviewer gibt Empfehlung ab |
| `auto_action_pending` | `task_key`, `action`, `grace_until`, `confidence` | Auto-Aktion wartet auf Grace Period |
| `auto_action_executed` | `task_key`, `action`, `was_vetoed` | Auto-Aktion durchgeführt oder vetoed |

**Heartbeat (alle Kanäle):**

```text
: heartbeat
```

Intervall: 15 Sekunden (konfigurierbar via `HIVEMIND_SSE_HEARTBEAT_INTERVAL`). Kein `event:`-Feld — reiner SSE-Kommentar.

### SSE Reconnect & Ring-Buffer

Wenn eine SSE-Verbindung unterbrochen wird, sendet der Browser automatisch einen Reconnect-Request mit dem Header `Last-Event-ID: <id>` des zuletzt empfangenen Events. Das Backend liefert dann alle verpassten Events nach:

```text
Ablauf:
1. Client trennt die Verbindung (Netzwerk-Fehler, Tab wechsel)
2. Browser reconnectet: GET /events/tasks?token=<new_stream_token>
   Header: Last-Event-ID: 1172
3. Backend sucht im Ring-Buffer alle Events mit id > 1172
4. Liefert alle verpassten Events sequenziell, dann weiter im Live-Stream

Ring-Buffer:
  Größe:  1000 Events pro SSE-Kanal (konfigurierbar via HIVEMIND_SSE_RING_BUFFER_SIZE)
  TTL:    Kein Zeit-Limit — nur größenbasierte Rotation (älteste raus wenn voll)
  Typ:    In-Memory (pro Backend-Prozess) — bei Multi-Prozess-Deployment: Redis-Backed
```

**Ring-Buffer-Overflow:** Wenn der Client länger offline war als der Ring-Buffer speichert (> 1000 Events seit Last-Event-ID), kann das Backend die Lücke nicht füllen. In diesem Fall:

```text
event: full_sync
data: {"reason": "ring_buffer_overflow", "last_known_id": 1172, "current_id": 2380}
```

**Client-Verhalten bei `full_sync`:**

1. Frontend verwirft den lokalen UI-State (Tasks-Liste, Epic-Liste)
2. Führt vollständigen REST-Reload durch:
   - `GET /api/projects/:id/epics` (alle Epics)
   - `GET /api/projects/:id/tasks?state=in_progress,in_review,blocked,escalated` (offene Tasks)
   - `GET /api/prompt-station/status` (Queue-State)
3. Nach erfolgreichem Reload: SSE-Stream normal weiterführen
4. Badge in der UI: "Neu synchronisiert" (1 Sekunde sichtbar)

> **Stream-Token bei Reconnect:** Da das Stream-Token single-use und 30s gültig ist, muss der Client vor jedem Reconnect-Versuch ein neues Stream-Token anfordern (`POST /api/auth/stream-token`). Das Browser-SSE-API übernimmt den Reconnect automatisch — der Client muss das Token-Refresh in den `EventSource`-Wrapper implementieren (kein nativer Browser-Support für Token-Refresh bei SSE).

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
