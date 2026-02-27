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
9. **Sovereign Nodes** — Jeder Entwickler betreibt seine eigene vollständige Instanz. Federation ist opt-in, nicht Pflicht.

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

Neben Solo und Team gibt es einen dritten Betriebsmodus: **Federation**. Alle drei Modi sind kompatibel und können kombiniert werden.

| Modus | Beschreibung | Typischer Einsatz |
| --- | --- | --- |
| **Solo** | Einzelner Nutzer, RBAC deaktiviert | Persönliche Projekte |
| **Team** | Geteilte zentrale Instanz, RBAC aktiv | Team mit einem gemeinsamen Server |
| **Federation** | Jeder Node ist souverän; Peers teilen Skills/Wiki/Epics | Team im selben VPN — jeder hat eigenen Host |

Federation ist kein optionales Feature — es ist die Grundlage des kollaborativen Spielerlebnisses. Jeder Entwickler betreibt seine eigene vollständige Hivemind-Instanz (eigene DB, eigenes Docker Compose). Nodes kennen sich über eine `peers.yaml` Peer-Liste (VPN-IPs) und können:

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

---

## Bekannte Skalierungsgrenzen

| Bereich | Limit | Mitigation | Phase |
| --- | --- | --- | --- |
| Token-Budget (Default 8000) | Knapp bei Skill Composition (3 Ebenen ~600 Tokens/Skill) | `HIVEMIND_TOKEN_BUDGET_PROVIDER_OVERRIDE` mit Provider-spezifischen Werten einführen | 3+ |
| Ollama Single Instance | Flaschenhals bei Team-Modus mit parallelen Nutzern | Connection-Pool-Konfiguration + Horizontal Scaling evaluieren | 8 |
| SLA-Cron stündlich | 4h-Warnung kann bis zu 1h zu spät kommen | Cron-Intervall auf 15 Minuten reduzieren (`HIVEMIND_SLA_CRON_INTERVAL`) | 6 |
| `skill_versions` append-only | Lineares Wachstum ohne Retention | Retention-Policy evaluieren (z.B. nur letzte 20 Versionen behalten, ältere archivieren) | 8 |
