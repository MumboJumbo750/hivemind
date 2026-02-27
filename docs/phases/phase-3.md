# Phase 3 — MCP Read-Tools & Bibliothekar-Prompt

← [Phasen-Übersicht](./overview.md) | [Index](../../masterplan.md)

**Ziel:** Erste echte MCP-Integration. AI-Client kann Hivemind-Daten lesen. Bibliothekar als generierter Prompt. Ollama für Embeddings.

**AI-Integration:** Ollama `nomic-embed-text` für Embeddings. Bibliothekar als manueller Prompt (Wizard of Oz).

> **Falls Phase F bereits abgeschlossen:** Die Federation-REST-Endpoints existieren bereits. Phase 3 aktiviert die MCP-Tool-Wrapper (`hivemind/fork_federated_skill`, `hivemind/start_discovery_session`, `hivemind/end_discovery_session`) und registriert die Federation-Read-Tools (`hivemind/list_peers`) im MCP-Server.

---

## Deliverables

### Backend
- [ ] MCP-Server via FastAPI (stdio + HTTP/SSE Transport)
- [ ] Read-Tools implementiert:
  - `hivemind/get_epic`
  - `hivemind/get_task`
  - `hivemind/get_skills` (Bibliothekar-gefiltert, Phase 1-2: alle aktiven Skills)
  - `hivemind/get_skill_versions`
  - `hivemind/get_guards` (liefert alle Guards für einen Task, global+project+skill+task)
  - `hivemind/get_doc`
  - `hivemind/get_triage`
  - `hivemind/get_audit_log`
  - `hivemind/get_wiki_article`
  - `hivemind/search_wiki`
  - `hivemind/get_prompt` (Prompt-Generator-Endpunkt)
- [ ] Prompt-Generator: generiert Bibliothekar-Prompt, Worker-Prompt, Kartograph-Prompt etc.
  - **`prompt_history` Write-Zeitpunkt:** Jeder `get_prompt`-Call schreibt ab Phase 3 einen Eintrag in `prompt_history` (agent_type, prompt_type, prompt_text, token_count, generated_by). Das Backend-Schema existiert seit Phase 1. Die UI-Ansicht (kollabierbare History in der Prompt Station) wird erst in Phase 4 implementiert — aber das Backend schreibt schon ab Phase 3.
- [ ] Prompt-Templates als Skills (globale, lifecycle-gemanagte Skills)
- [ ] Ollama-Container in Docker Compose (nur Phase 3+)
- [ ] Embedding-Service-Abstraktion (Provider-Switch ohne fachliche Datenmigration; mit Embedding-Spalten-ALTER + Recompute)
- [ ] Embeddings für Epics berechnen (Basis für Routing in Phase 7)
- [ ] Webhook-Ingest: YouTrack + Sentry Events empfangen und als `direction='inbound'` in `sync_outbox` schreiben
- [ ] Triage: `[UNROUTED]`-Items für `inbound`-Events erzeugen wenn kein Routing möglich (Phase 1-2: alle Events unrouted)
- [ ] Triage-Write-Tools: `hivemind/route_event` (routing_state → routed) und `hivemind/ignore_event` (routing_state → ignored) — manuelle Zuweisung aus Triage Station

### Frontend
- [ ] Triage Station (erster Stand): Unrouted Events anzeigen, manuelle Zuweisung
- [ ] Token Radar in Prompt Station (Progress-Ring Animation)
- [ ] Prompt Station: MCP-Verbindungsstatus live (WebSocket oder Polling)
- [ ] Prompt Station Queue zeigt "Warum jetzt?"-Badges (`ESCALATED`, `DECISION OFFEN`, `SLA <4h`, `FOLLOW-UP`)
- [ ] Kartograph-Bootstrap-Flow: "Neues Projekt → Kartograph starten" UI

### Docker Compose Erweiterung

```yaml
# Phase 3: Ollama hinzufügen
ollama:
  image: ollama/ollama
  ports:
    - "11434:11434"
  volumes:
    - ollama_data:/root/.ollama
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:11434/api/tags"]
    interval: 30s
    timeout: 10s
    retries: 5
    start_period: 60s

# Init-Container: lädt nomic-embed-text beim ersten Start
ollama-init:
  image: curlimages/curl:latest
  depends_on:
    ollama:
      condition: service_healthy
  restart: "no"
  entrypoint: >
    sh -c "curl -s http://ollama:11434/api/pull
    -d '{\"name\": \"nomic-embed-text\"}' --max-time 600"
```

> **Fallback bei Ollama-Fehler:** Wenn Ollama nicht erreichbar ist oder `nomic-embed-text` nicht geladen werden konnte, loggt das Backend eine Warnung und arbeitet ohne Embeddings weiter. Semantische Suche und pgvector-Routing sind dann deaktiviert — alle anderen Features bleiben funktional. Embedding-Berechnung wird automatisch nachgeholt sobald Ollama wieder erreichbar ist.
>
> **Known Limit — Single Ollama Instance:** Bei paralleler Nutzung durch mehrere Team-Mitglieder (Team-Modus) oder beim Kartograph-Bootstrap großer Repos (> 1000 Dateien) kann die sequenzielle Embedding-Berechnung zum Flaschenhals werden. Mitigation: `HIVEMIND_EMBEDDING_BATCH_SIZE` (Default: 50) erhöhen und Bootstrap außerhalb der Kernarbeitszeit durchführen. Horizontal Scaling wird ab Phase 8 evaluiert (→ [architecture/overview.md — Bekannte Skalierungsgrenzen](../architecture/overview.md#bekannte-skalierungsgrenzen)).

---

## Bibliothekar als Prompt (Phase 1-2 Modus)

Der Prompt-Generator (`hivemind/get_prompt { "type": "bibliothekar", "task_id": "TASK-88" }`) gibt zurück:

```
## Rolle: Bibliothekar

Dein Auftrag: Kontext für TASK-88 assemblieren.

Verfügbare aktive Skills:
- [uuid-1] FastAPI Endpoint erstellen — backend, python
- [uuid-2] Datenbankmigrationen — backend, alembic

Verfügbare Docs für EPIC-12:
- [doc-1] EPIC-12 Architektur

Aufgabe von TASK-88: [task.description]

Wähle 1-3 relevante Skills. Erkläre warum.
Baue danach den Worker-Prompt mit diesen Inhalten.
```

---

## Acceptance Criteria

- [ ] AI-Client (z.B. Claude Desktop) kann sich mit Hivemind MCP verbinden
- [ ] `hivemind/get_epic` gibt korrektes Epic zurück
- [ ] `hivemind/get_task` gibt Task mit State zurück
- [ ] `hivemind/get_skills` gibt gefilterte Skills zurück (alle aktiven in Phase 1-2)
- [ ] `hivemind/get_prompt { "type": "bibliothekar", "task_id": "TASK-1" }` gibt korrekt generierten Prompt zurück
- [ ] Ollama läuft und `nomic-embed-text` ist verfügbar
- [ ] Webhook-Endpoint empfängt YouTrack/Sentry Events und schreibt `direction='inbound'` in `sync_outbox`
- [ ] Triage Station zeigt `[UNROUTED]`-Items aus `sync_outbox` für `direction='inbound'`
- [ ] `hivemind/route_event` setzt `routing_state → routed` und weist Event dem Epic zu
- [ ] `hivemind/ignore_event` setzt `routing_state → ignored`
- [ ] Token Radar zeigt 0/8000 Tokens animiert in Prompt Station
- [ ] MCP-Verbindungsstatus in System Bar korrekt (● verbunden / ◌ getrennt)
- [ ] Prompt Queue zeigt pro Eintrag einen nachvollziehbaren Priorisierungsgrund ("Warum jetzt?")

---

## Abhängigkeiten

- Phase 2 abgeschlossen (RBAC, Auth)

## Öffnet folgende Phase

→ [Phase 4: Planer-Writes](./phase-4.md)
