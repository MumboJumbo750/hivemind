# Architektur & Leitprinzipien

← [Index](../../masterplan.md)

## Leitprinzipien

1. **Progressive Disclosure** — Kontext nur task-genau laden, kein Context-Bloat.
2. **BYOAI → Autonomy** — Heute manuell, morgen autonom. Gleiche Endpoints, gleicher Datenvertrag.
3. **Strict Standardization** — EPIC/TASK/BUG mappen stabil auf externe Systeme.
4. **Zero-Loss Memory** — Flüssiges Wissen wird über den Gärtner-Flow dauerhaft gespeichert.
5. **Epic Ownership** — Jedes Epic hat genau einen menschlichen Owner als fachliche Instanz.
6. **Global Skills mit Gate** — Lesbar für alle, aktivierbar nur über Merge-Prozess.
7. **Security by Default** — Kein Write ohne AuthN, AuthZ, Scope und Audit.
8. **Deterministische Workflows** — Eindeutige Statusmaschine, Idempotenz, Konfliktregeln.
9. **Sovereign Nodes** — Jeder Entwickler betreibt seine eigene vollständige Instanz. Federation ist architektonisch nativ (Schema ab Phase 1, kein Nachbau), aber operativ opt-in — Aktivierung über `HIVEMIND_FEDERATION_ENABLED`.

---

## Stack

| Layer | Technologie |
| --- | --- |
| Frontend | Vue 3 + Vite + TypeScript + Reka UI + Design Tokens (CSS Variables, Theme Engine) |
| Backend | FastAPI (Bibliothekar + Router + MCP-Server im selben Service) |
| Datenbank | PostgreSQL 16 + pgvector |
| Embeddings | Ollama `nomic-embed-text` (ab Phase 3) — kein API-Key nötig |
| Laufzeit | Docker Compose |
| Integrationen | YouTrack (Webhook/API), Sentry (Webhook/API), GitLab (MCP Consumer) |

> **Skalierungsstrategie:** In Phase 1–7 laufen alle Komponenten (MCP-Server, Webhook-Ingest, Prompt-Generator, Bibliothekar) im selben FastAPI-Prozess. Ab Phase 8 (hohe Last / Team-Setup) können Backend-Aufgaben in separate Prozesse ausgelagert werden: **(1)** Outbox-Consumer als eigener Worker-Prozess, **(2)** SLA-Cron als eigenständiger Scheduler, **(3)** Embedding-Berechnung als Background-Job-Queue. Die Trennung erfordert keinen Architekturbruch — alle Prozesse teilen dieselbe DB und nutzen die Outbox-Tabelle als Koordinationspunkt.
>
> **Bottleneck-Hinweis (Phase 3+):** Im Team-Modus mit 5+ Usern können gleichzeitige Embedding-Berechnungen (Kartograph-Bootstrap), Prompt-Generierung und MCP-Calls den Single-Process belasten. Alle async Background-Tasks laufen über `asyncio.create_task` im selben Event-Loop. **Empfehlung ab Phase 3:** Embedding-Queue mit konfigurierbarem Parallelisierungsgrad (`HIVEMIND_EMBEDDING_CONCURRENCY`, Default: 2) und Monitoring der Event-Loop-Latenz. Bei nachgewiesenem Bottleneck vor Phase 8: Embedding-Worker als separaten Prozess evaluieren (Docker Compose Service, selbe DB).

---

## API-Vertrag & Typensicherheit (Golden Middle)

Hivemind nutzt den "Goldenen Mittelweg": Das Backend läuft in Python/FastAPI (für optimalen Zugang zum KI-Ökosystem und LLM-Tools), während das Frontend in Vue3/TypeScript entwickelt wird.

Um 100%ige Typensicherheit vom Datenbank-Modell bis in die Vue-Components zu garantieren, *ohne* Typen doppelt pflegen zu müssen, setzen wir auf **automatische API-Client-Generierung**:

1. **Backend (Pydantic):** Alle Requests und Responses sind als Pydantic-Modelle in FastAPI strikt typisiert.
2. **OpenAPI-Export:** Ein Build-Skript exportiert die `openapi.json` statisch aus dem FastAPI-Kern (ohne dass der Server laufen muss).
3. **Frontend-Generierung:** Das Tool `@hey-api/openapi-ts` liest die Struktur und generiert im Frontend-Workspace automatisch einen typisierten API-Client (`src/api/client/`).

**Regel:** Wenn sich das Backend-Model ändert, bricht der TypeScript-Compiler im Frontend sofort den Build ab.

---

## Trust Boundary

```text
[AI-Client / Chat]          [Hivemind Backend]          [Datenbank]
       |                           |                          |
  MCP-Calls ──────────────→  Validierung                     |
  (als unsicher betrachten)   AuthN + AuthZ                  |
                               Idempotenz-Check              |
                               Optimistic Lock ──────────→  Commit
                               Audit-Eintrag
```

- Chat-Ausgaben und externe Payloads gelten als **potentiell unsicher**
- Nur die Hivemind-Middleware darf Writes final validieren und committen
- Kein direkter DB-Zugriff von außen

---

## Solo vs. Team Modus

Konfiguration: in der Datenbank (`app_settings`-Tabelle, Key `hivemind_mode`). Kein Neustart erforderlich.

**Laufzeit-Switch:** Der Modus ist zur Laufzeit umschaltbar über die Settings-Seite (Admin-Recht im Team-Modus erforderlich). Das Backend liest den Modus per Request aus dem DB-Cache — kein Service-Neustart, kein Deployment.

> `HIVEMIND_MODE=solo|team` als Env-Var dient nur als **Bootstrap-Default** beim allerersten Start. Danach ist der DB-Wert maßgeblich und die Env-Var wird ignoriert.

| Feature | Solo | Team |
| --- | --- | --- |
| RBAC-Enforcement | Deaktiviert | Aktiv |
| Review-Gate | Self-Review erzwungen (kein direktes `done`) | Owner/Admin-Review Pflicht (Implementierer darf identisch sein) |
| Skill-Merge-Gate | Kein Admin nötig — `submit_skill_proposal` setzt direkt `active` | Admin-Pflicht |
| Actor-Pflichtfelder | Automatisch mit System-User befüllt | Explizit Pflicht |
| Triage-Station | Vereinfacht (kein Owner-Missing) | Vollständig |
| Decision-Request-SLA | Kein Timeout | 24h/48h aktiv |

**Migrationspfad Solo → Team:** Keine Datenmigration nötig. Die Datenstruktur ist identisch — nur die Policy-Enforcement-Schicht ändert sich. Bestehende Tasks und Epics bleiben unverändert.

---

## Federation Modus

Neben Solo und Team gibt es einen dritten Betriebsmodus: **Federation**. Federation ist orthogonal zu `hivemind_mode` (solo|team) und wird separat über `HIVEMIND_FEDERATION_ENABLED` aktiviert.

> **Abgrenzung:** `hivemind_mode` (solo|team) steuert RBAC-Enforcement und Actor-Modell. Federation steuert Peer-Kommunikation und Datenverteilung. Beide sind unabhängig kombinierbar: Solo+Federation (Einzel-Node synct mit Peers ohne RBAC), Team+Federation (geteilte Instanz mit RBAC synct mit Peers).

| Modus | Beschreibung | Typischer Einsatz |
| --- | --- | --- |
| **Solo** | Einzelner Nutzer, RBAC deaktiviert | Persönliche Projekte |
| **Team** | Geteilte zentrale Instanz, RBAC aktiv | Team mit einem gemeinsamen Server |
| **Federation** | Jeder Node ist souverän; Peers teilen Skills/Wiki/Epics | Team im selben VPN — jeder hat eigenen Host |

---

## Multi-Projekt-Kontextwechsel

Der System Bar ermöglicht das Umschalten zwischen Projekten. Beim Wechsel gelten folgende Regeln:

| Bereich | Verhalten bei Projekt-Wechsel |
| --- | --- |
| **Prompt Queue** | Queue wird nach neuem Projekt gefiltert. Alte Queue-Einträge des vorherigen Projekts verschwinden aus der Ansicht, bleiben aber im Backend bestehen. Cross-Projekt-Queue-Items (SLA-Warnungen, Eskalationen) bleiben sichtbar wenn `HIVEMIND_CROSS_PROJECT_ALERTS=true` (Default: true). |
| **Notifications** | Notifications sind **projektübergreifend** — kein Filter beim Wechsel. Das Notification Tray zeigt immer alle ungelesenen Notifications aller Projekte. |
| **Nexus Grid** | Grid wird zurückgesetzt auf das neue Projekt. Der letzte Viewport-State (Zoom, Position) wird pro Projekt im LocalStorage gespeichert und beim Rückkehr wiederhergestellt. |
| **Command Deck** | Zeigt Epics/Tasks des neuen Projekts. |
| **Arsenal / Skill Lab** | Zeigt projekt-spezifische + globale Skills. |
| **Wiki** | Wiki ist projektunabhängig — kein Wechsel nötig. |
| **Settings** | Tab PROJEKT wechselt auf das neue Projekt (Mitglieder, Rollen). |
| **LocalStorage Key** | `hivemind:last_project_id:<user_id>` — wird beim Reload automatisch wiederhergestellt. |

> **Technisch:** Der Frontend-Store (`useProjectStore`) hält die aktive `project_id`. Alle API-Calls die projekt-scoped sind, senden diese als Query-Parameter oder Path-Segment. SSE-Subscriptions werden beim Wechsel ge-unsubscribed und neu-subscribed.

---

## Solo-Modus: Task-Assignment

Im Solo-Modus (`hivemind_mode = 'solo'`) gibt es nur einen User. Task-Assignment wird automatisiert:

| Szenario | Verhalten |
| --- | --- |
| `assign_task` aufgerufen (Architekt-Agent) | `assigned_to` wird automatisch auf den Solo-User gesetzt, unabhängig vom übergebenen `user_id`-Parameter. Das Backend erkennt Solo-Modus und substituiert. |
| `assign_task` nicht aufgerufen | Beim Versuch `scoped → ready` prüft das Backend: `assigned_to` nicht gesetzt? → Automatisch mit Solo-User befüllen (kein 422). |
| Epic-Owner | Automatisch der Solo-User. `owner_id` und `backup_owner_id` werden auf den Solo-User gesetzt. |
| Decision Request SLA | Deaktiviert im Solo-Modus (kein Timeout, da Solo-User gleichzeitig Owner und Worker ist). |

> **Regel:** Im Solo-Modus wird `assign_task` nicht übersprungen — es wird mit dem Solo-User aufgerufen. Der Workflow bleibt identisch, nur das Ziel ist implizit. Das ermöglicht einen nahtlosen Übergang zu Team-Modus ohne Code-Änderung.

Federation ist architektonisch nativ — das Schema (`nodes`, `node_identity`, `origin_node_id`, `federation_scope`) wird in Phase 1 angelegt, nicht nachträglich aufgepfropft. Operativ ist Federation opt-in: ohne `HIVEMIND_FEDERATION_ENABLED=true` bleiben alle Federation-Endpoints inaktiv und die Node arbeitet rein lokal. Jeder Entwickler betreibt seine eigene vollständige Hivemind-Instanz (eigene DB, eigenes Docker Compose). Nodes kennen sich über eine `peers.yaml` Peer-Liste (VPN-IPs) und können:

- **Skills & Wiki-Artikel** mit `federation_scope = 'federated'` an alle bekannten Peers pushen
- **Epics teilen** — Sub-Tasks eines Epics können einem anderen Node zugewiesen werden und werden dort abgearbeitet
- **Task-State-Updates** empfangen — der Origin-Node sieht Fortschritt über alle Peer-Nodes hinweg

Federation läuft in drei Topologien ohne Datenmodell- oder API-Bruch:

| Topologie | Beschreibung | Typischer Einsatz |
| --- | --- | --- |
| **Direct Mesh** | Direkte Node-zu-Node Verbindungen über `peers.yaml` | Kleines Team im selben VPN |
| **Hub-Assisted Mesh** | Optionaler Hive Station Server für Discovery + Presence, Datenverkehr weiter direkt | Teams mit häufig wechselnden Nodes |
| **Hub Relay (optional)** | Hive Station zusätzlich als Store-and-Forward Relay bei Verbindungsproblemen | Instabile Netze oder zeitweise Offline-Peers |

Der optionale Hive Station Server ist ein **Control Plane** Dienst, keine Data-Authority. Origin-Authority (`origin_node_id`) und End-to-End Signaturen bleiben unverändert auf Node-Ebene.

**Origin-Authority:** Jede Entität (Epic, Skill, Wiki-Artikel) hat einen `origin_node_id`. Nur der Origin-Node kann diese Entität editieren. Peers empfangen Read-only-Kopien und können Change-Proposals zurückschicken.

**Transport:** HTTP/REST zwischen Nodes (FastAPI `POST /federation/*` Endpoints). Alle Nachrichten werden mit Ed25519 signiert; Empfänger verifizieren die Signatur gegen den bekannten Public Key des Senders.

**Offline-Toleranz:** Nicht erreichbare Peers werden in der `sync_outbox` als `peer_outbound`-Einträge gepuffert und mit derselben Retry-Logik wie externe Syncs zugestellt.

→ Vollständige Spec: [federation.md](../features/federation.md)

---

## Multi-Projekt

- 1 Instanz = 1 Team mit beliebig vielen Projekten
- Skills können global (projekt-übergreifend, `project_id = NULL`) oder projektspezifisch sein
- `project_id` auf Epics, Tasks und projektspezifischen Skills
- Kartograph hat lesenden Zugriff auf alle Projekte (→ [Kartograph](../agents/kartograph.md))

**Nexus Grid — Global View (Monorepo-Support):**

`code_edges` können projekt-übergreifend sein — `source_id` und `target_id` dürfen in verschiedenen Projekten liegen. `project_id` auf `code_edges` bezeichnet das Quell-Projekt (für Queries). Das ermöglicht:

- Monorepo mit geteilten UI-Controls: `frontend/src/Button.tsx` → `ui-controls/src/ui/Button.vue`
- Microservice-Abhängigkeiten: `service-a/client.py` → `service-b/api.py`
- Im Nexus Grid: Projekt-Filter-Dropdown (`Alle` | `backend` | `frontend` | ...) mit gestrichelten Cross-Project Kanten

→ Details: [Nexus Grid — Multi-Projekt-Ansicht](../features/nexus-grid.md#multi-projekt-ansicht)

---

## Realtime-Updates

Frontend und Backend kommunizieren Echtzeitdaten via **Server-Sent Events (SSE)**:

| Kanal | Events | Konsument |
| --- | --- | --- |
| `/events/notifications` | Neue Notifications, SLA-Alerts | Notification Tray |
| `/events/tasks` | State-Transitions, Guard-Updates | Command Deck, Prompt Station |
| `/events/triage` | Neue `[UNROUTED]`-Items, Proposals | Triage Station |

SSE wurde gewählt weil: (1) bereits für MCP HTTP-Transport verwendet, (2) simpler als WebSocket für unidirektionale Server→Client-Push, (3) automatische Reconnection durch Browser. Polling-Fallback: 30 Sekunden für Clients die SSE nicht unterstützen.

### SSE-Verbindungsmanagement & Event-Catch-Up

| Parameter | Wert | Konfigurierbar |
| --- | --- | --- |
| **Heartbeat-Intervall** | 15 Sekunden (`:heartbeat` Comment-Event, mit `id`-Sequenz) | `HIVEMIND_SSE_HEARTBEAT_INTERVAL` |
| **Client Timeout-Detection** | 45 Sekunden ohne Event (inkl. Heartbeat) → Verbindung als tot betrachten | Frontend-Konstante `SSE_DEAD_TIMEOUT_MS` |
| **Reconnection-Delay** | Exponential Backoff: 1s → 2s → 4s → 8s → max 30s | Frontend: `SSE_RECONNECT_BASE_MS`, `SSE_RECONNECT_MAX_MS` |
| **Fallback auf Polling** | Nach 3 fehlgeschlagenen SSE-Reconnects → Polling alle 30s | `HIVEMIND_POLL_FALLBACK_INTERVAL` |
| **Rückkehr zu SSE** | Polling prüft Server-Health; bei Erfolg → SSE-Reconnect-Versuch | Automatisch |

**Event-Sequencing & Last-Event-ID Catch-Up:**

SSE-Events werden mit einer aufsteigenden `id`-Sequenz pro Kanal versehen. Dies ermöglicht Catch-Up nach Verbindungsunterbrechungen:

```text
id: 4217
event: task_state_changed
data: {"task_key":"TASK-88","old_state":"in_progress","new_state":"in_review",...}
```

- Client sendet `Last-Event-ID` Header beim Reconnect (Browser-nativ bei SSE)
- Backend liefert alle Events seit dieser ID nach (aus einem Ring-Buffer der letzten 1000 Events pro Kanal)
- Falls `Last-Event-ID` nicht mehr im Buffer (zu viele Events verpasst): Server sendet `event: full_sync` — Client lädt State komplett neu via REST
- Ring-Buffer-Größe konfigurierbar: `HIVEMIND_SSE_BUFFER_SIZE` (Default: 1000)

**Polling-Fallback-Endpoint (explizit):**

```text
GET /api/events/poll?channel=tasks&since=<last_event_id>&project_id=<uuid>
→ 200 { "events": [...], "last_id": 4220 }
→ Aktiviert nach 3 fehlgeschlagenen SSE-Reconnects
→ Polling-Intervall: 30 Sekunden (HIVEMIND_POLL_FALLBACK_INTERVAL)
```

**Frontend-Ablauf:**
1. SSE-Stream öffnen → Events empfangen
2. Heartbeat innerhalb von 45s nicht empfangen → SSE-Stream schließen
3. Reconnect mit Exponential Backoff versuchen (max 3 Versuche)
4. Nach 3 Fehlversuchen → Polling-Fallback aktivieren, Status-Badge auf ◌ (getrennt)
5. Polling prüft `/health` + letzte Events → bei Erfolg SSE erneut versuchen
6. SSE wiederhergestellt → Polling deaktivieren, Status-Badge auf ● (verbunden)

---

## Error States & UI-Fehlerbehandlung

Das Frontend behandelt Fehler nach einer einheitlichen Strategie. Alle Error-States sind visuell definiert und benötigen keine spezifischen Mockups pro View — sie nutzen eine gemeinsame `ErrorBoundary`-Komponente.

### HTTP-Fehler

| HTTP Status | UI-Verhalten | Benutzeraktion |
| --- | --- | --- |
| 401 Unauthorized | Redirect zum Login; Session-Token erneuern | Erneut anmelden |
| 403 Forbidden | Inline-Fehlerbanner: "Keine Berechtigung für diese Aktion" + betroffene Permission | — (informativ) |
| 409 Conflict | Toast: "Daten wurden zwischenzeitlich geändert — bitte neu laden" + Auto-Reload des betroffenen Elements | [NEU LADEN] Button |
| 422 Unprocessable | Inline-Validation-Fehler am betroffenen Formularfeld oder Guard-Status; bei Guard-Block: Liste offener Guards anzeigen | Eingabe korrigieren |
| 429 Too Many Requests | Toast: "Anfrage-Limit erreicht — bitte warten" + Retry-After Header beachten | Automatisches Retry nach Header-Wert |
| 500 Internal Server Error | Fullscreen-Error-Banner mit Retry-Button; Fehler-ID aus Response anzeigen | [ERNEUT VERSUCHEN] |
| Netzwerk-Timeout (kein Response) | Nach 30s: Toast "Verbindung zum Server verloren" + MCP-Badge auf ◌ | Automatischer Retry |

### MCP-Verbindungsabbruch

| Situation | UI-Verhalten |
| --- | --- |
| MCP-Endpoint nicht erreichbar | Status-Badge ● → ◌; Prompt Station zeigt "MCP nicht verbunden — Prompts können nicht generiert werden" |
| MCP-Response-Timeout (> 60s) | Spinner stoppt → Toast: "MCP-Operation Timeout — prüfe den AI-Client" |
| MCP wiederhergestellt | Status-Badge ◌ → ●; Toast: "MCP-Verbindung wiederhergestellt" |

### Backend-Container-Crash

| Situation | UI-Verhalten |
| --- | --- |
| SSE-Stream bricht ab + Health-Check schlägt fehl | Fullscreen-Overlay: "Backend nicht erreichbar" mit pulsierendem Reconnect-Indikator |
| Backend wieder erreichbar | Overlay verschwindet; alle Views laden neu; Toast: "Verbindung wiederhergestellt" |

### Reconnection-Strategie (zusammengefasst)

```text
SSE-Disconnect → Exponential Backoff (1s/2s/4s/8s/30s max) × 3 Versuche
  ├─ Erfolg → SSE restored, alle Subscriptions erneuern
  └─ 3× Fehlgeschlagen → Polling-Fallback (30s)
       ├─ /health OK → SSE erneut versuchen
       └─ /health Fail → Overlay "Backend nicht erreichbar"
```

---

## Data Export & Backup

Hivemind läuft als souveräne, selbst-gehostete Instanz. Export und Backup sind Pflicht-Features.

### Backup-Strategie

| Komponente | Methode | Zyklus | Konfig |
| --- | --- | --- | --- |
| **PostgreSQL** | `pg_dump --format=custom` via Cron-Job im Docker-Container | Täglich 02:00 UTC (Default) | `HIVEMIND_BACKUP_CRON`, `HIVEMIND_BACKUP_DIR` |
| **Uploads / Attachments** | Dateisystem-Snapshot des `volumes/uploads`-Verzeichnisses | Zusammen mit DB-Backup | Selbes Backup-Dir |
| **Ed25519 Keys** | Exportiert via `hivemind export-keys` CLI-Befehl; **nicht** im regulären Backup enthalten (Separation of Secrets) | Manuell bei Setup + nach Key-Rotation | Passwort-geschützter Export |
| **Retention** | Letzte N Backups behalten, ältere löschen | Default: 7 tägliche + 4 wöchentliche | `HIVEMIND_BACKUP_RETENTION_DAILY`, `_WEEKLY` |

### Daten-Export (User-facing)

| Export | Format | Verfügbar ab | MCP-Tool / Endpoint |
| --- | --- | --- | --- |
| **Projektzusammenfassung** | Markdown (.md) | Phase 1 | `GET /api/projects/:id/export` |
| **Epics + Tasks** | JSON oder CSV | Phase 2 | `GET /api/projects/:id/export?format=json&scope=epics` |
| **Wiki** | Markdown-Archiv (.zip) | Phase 5 | `GET /api/projects/:id/wiki/export` |
| **Skills** | JSON (inkl. Versionshistorie) | Phase 4 | `GET /api/projects/:id/skills/export` |
| **Vollständig (alle Daten)** | `pg_dump`-kompatibles SQL oder JSON | Phase 6 | `hivemind export-full` CLI |
| **Audit-Log** | CSV | Phase 6 | `GET /api/audit/export?from=&to=` |

### Restore

```bash
# Vollständiges Restore aus Backup
hivemind restore --backup /backups/hivemind-2025-01-15.dump

# Nur Datenbank (ohne Uploads)
hivemind restore --backup /backups/hivemind-2025-01-15.dump --db-only

# Dry-Run (validate ohne zu schreiben)
hivemind restore --backup /backups/hivemind-2025-01-15.dump --dry-run
```

> **Phase F (Federation):** Restore setzt `origin_node_id` korrekt. Peers werden nach Restore via `/federation/ping` re-announced. Peers mit zwischenzeitlichen Änderungen erhalten ein Full-Sync.

---

## Rate-Limiting & Throttling

Alle API-Endpoints sind rate-limited. Die Limits gelten pro Actor (identifiziert via JWT `actor_id`).

| Endpoint-Kategorie | Limit | Zeitfenster | HTTP bei Überschreitung |
| --- | --- | --- | --- |
| **Read-Tools** (`get_*`, `list_*`, `search_*`) | 120 Requests | 60 Sekunden | 429 + `Retry-After` Header |
| **Write-Tools** (`create_*`, `update_*`, `submit_*`, `propose_*`) | 30 Requests | 60 Sekunden | 429 + `Retry-After` Header |
| **Admin-Writes** (`merge_*`, `reject_*`, `resolve_*`, `cancel_*`) | 20 Requests | 60 Sekunden | 429 |
| **Webhook-Ingest** (`/webhooks/*`) | 60 Requests | 60 Sekunden | 429 (pro Source-IP) |
| **Federation-Endpoints** (`/federation/*`) | 60 Requests | 60 Sekunden | 429 (pro Peer-Node-ID) |
| **Health-Check** (`/health`) | Kein Limit | — | — |
| **SSE-Streams** (`/events/*`) | 5 gleichzeitige Verbindungen | pro User | 429 bei 6. Verbindung |

**Phase 8 (Autonomy) Erweiterung:**
- AI-Provider-Calls (Claude/OpenAI API) werden via separatem Token-Bucket limitiert: max `HIVEMIND_AI_RPM` Requests/Minute (Default: 10) um Provider-Rate-Limits nicht zu triggern.
- Federation Peer-to-Peer: Zusätzliches per-Peer Throttling via `HIVEMIND_FEDERATION_PEER_RPM` (Default: 30/min) gegen Abuse durch kompromittierte Peers.

**Implementation:** Middleware-basiert im FastAPI-Service. Phase 1–7: **In-Memory Token Bucket** (Python `dict` mit TTL-basiertem Cleanup, ausreichend für Single-Instance — kein Redis im Stack). Rate-Limit-State geht bei Prozess-Neustart verloren (akzeptabel). Ab Phase 8 bei Multi-Worker Setup: Redis-basierter Distributed Rate Limiter evaluieren.

> **DDoS-Schutz:** Rate-Limiting ist die erste Verteidigung. Zusätzlich: Federation-Endpoints akzeptieren nur signierte Requests (Ed25519); Webhook-Endpoints validieren HMAC-Signatures. Nicht-authentifizierte Endpoints (nur `/health`) sind unkritisch.

---

## Cron-Job & Scheduled Tasks — Infrastruktur

Hivemind nutzt mehrere periodische Hintergrund-Jobs. Die Infrastruktur ist bewusst einfach und wächst mit den Phasen:

### Phase 1–7: In-Process APScheduler

Alle Cron-Jobs laufen **im FastAPI-Prozess** via [APScheduler](https://apscheduler.readthedocs.io/) (`AsyncIOScheduler`). Kein separater Worker-Prozess, kein Celery, kein Redis.

```python
# Beispiel: Job-Registrierung beim App-Start
scheduler = AsyncIOScheduler()
scheduler.add_job(sla_check_cron, "interval", minutes=60, id="sla_check")
scheduler.add_job(outbox_consumer, "interval", seconds=30, id="outbox_consumer")
scheduler.add_job(federation_ping, "interval", seconds=60, id="federation_ping")
scheduler.start()
```

### Registrierte Jobs

| Job-ID | Intervall | Ab Phase | Beschreibung | Konfig Env-Var |
| --- | --- | --- | --- | --- |
| `sla_check` | 60 min | 2 | SLA-Warnungen prüfen (Epics + Tasks nahe Deadline) | `HIVEMIND_SLA_CRON_INTERVAL` (Sekunden, default: 3600) |
| `outbox_consumer` | 30 sec | 2 | Sync-Outbox Pending-Einträge verarbeiten | `HIVEMIND_OUTBOX_POLL_INTERVAL_SECONDS` (default: 30) |
| `federation_ping` | 60 sec | F | Heartbeat an alle Peers | `HIVEMIND_FEDERATION_PING_INTERVAL` (default: 60) |
| `dlq_cleanup` | 24 h | 2 | Dead-Letter-Queue alte Einträge archivieren | — |
| `backup_db` | 24 h | 1 | `pg_dump` (via Docker exec oder subprocess) | `HIVEMIND_BACKUP_CRON` (Cron-Expression) |
| `idempotency_cleanup` | 1 h | 2 | Abgelaufene Idempotency-Keys löschen (TTL-basiert) | — |
| `peer_status_check` | 5 min | F | Offline-Peers erkennen, Triage-Items erzeugen | `HIVEMIND_FEDERATION_OFFLINE_THRESHOLD` |
| `embedding_queue` | 10 sec | 3 | Ausstehende Embedding-Berechnungen via Ollama | `HIVEMIND_EMBEDDING_BATCH_SIZE` (default: 10) |

### Phase 8: Prozess-Separation & Leader Election

Ab Phase 8 (Multi-Worker-Setup) müssen Cron-Jobs dedupliziert werden damit z.B. der SLA-Check nicht von 3 Workers gleichzeitig ausgeführt wird:

```text
Strategie: PostgreSQL Advisory Lock als Leader Election

1. Jeder Worker versucht beim Job-Start: SELECT pg_try_advisory_lock(:job_id_hash)
2. Nur ein Worker erhält das Lock → führt den Job aus
3. Lock wird nach Job-Abschluss freigegeben (oder nach Timeout)
4. Kein Redis, kein ZooKeeper — PostgreSQL reicht
```

> **Bewusste Entscheidung:** APScheduler statt Celery/Dramatiq weil kein Message-Broker benötigt wird (Phase 1–7 = Single-Process). Der Wechsel zu einem externen Scheduler ist für Phase 8 evaluierbar, aber mit Advisory Locks + APScheduler ist Multi-Worker bereits abgedeckt.

---

## Bekannte Skalierungsgrenzen

| Bereich | Limit | Mitigation | Phase |
| --- | --- | --- | --- |
| Token-Budget (Default 8000) | Knapp bei Skill Composition (3 Ebenen ~600 Tokens/Skill) | `HIVEMIND_TOKEN_BUDGET_PROVIDER_OVERRIDE` mit Provider-spezifischen Werten einführen | 3+ |
| Ollama Single Instance | Flaschenhals bei Team-Modus mit parallelen Nutzern | Connection-Pool-Konfiguration + Horizontal Scaling evaluieren | 8 |
| SLA-Cron stündlich | 4h-Warnung kann bis zu 1h zu spät kommen | Cron-Intervall auf 15 Minuten reduzieren (`HIVEMIND_SLA_CRON_INTERVAL`) | 6 |
| `skill_versions` append-only | Lineares Wachstum ohne Retention | Retention-Policy evaluieren (z.B. nur letzte 20 Versionen behalten, ältere archivieren) | 8 |
