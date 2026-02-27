# Phasen-Übersicht

← [Index](../../masterplan.md)

8 Phasen von "Datenfundament" bis "Volle Autonomie". UI-Entwicklung läuft **parallel** zu Backend-Phasen.

---

## Übersicht

| Phase | Backend | UI | AI-Integration |
| --- | --- | --- | --- |
| [Phase 1a](./phase-1.md#phase-1a--datenfundament-backend) | Datenfundament, State Machine, Docker Compose | — | Keins — alles manuell |
| [Phase 1b](./phase-1.md#phase-1b--design--prompt-station-frontend) | — | Design System, Prompt Station + Inline-Review/Scoping | Keins — alles manuell |
| [Phase 2](./phase-2.md) | Identity & RBAC | Command Deck, Login, Notifications | Keins — alles manuell |
| [Phase F](./phase-f.md) | Federation Protocol, Peer Discovery, Epic-Sharing, Kartograph-Sync | Peer-Overview, Shared Map, Skill-Loadout | Keins — alles manuell |
| [Phase 3](./phase-3.md) | MCP Read-Tools + Bibliothekar-Prompt | Triage Station, Token Radar | Ollama Container (Embeddings) |
| [Phase 4](./phase-4.md) | Planer-Writes (Architekt) | Skill Lab, Audit-Log | — |
| [Phase 5](./phase-5.md) | Worker & Gaertner Writes | Wiki, Nexus Grid 2D | — |
| [Phase 6](./phase-6.md) | Triage & Eskalation | Decision Requests, SLA-UI | — |
| [Phase 7](./phase-7.md) | Externe Integration Hardening | Dead Letter, Bug Heatmap, Sync-Status | — |
| [Phase 8](./phase-8.md) | Volle Autonomie | 3D Nexus Grid, Auto-Modus | API-Keys, GitLab MCP Consumer |

> **Phase F ist strategischer Core** — Federation ist das Zielbild für kollaboratives Arbeiten. Operativ kann ein Team mit Shared Instance (Phase 2) starten und Federation später aktivieren; beide Betriebsarten bleiben kompatibel.

### Phase-F-Sequenzierung

```text
Lineare Pflichtsequenz:   Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6 → Phase 7 → Phase 8

Phase F (optional):       Kann nach Phase 2 eingeschoben werden — vor, nach oder parallel zu Phase 3.
                          Voraussetzung: Phase 2 abgeschlossen (Identity & RBAC aktiv).
                          Hinweis: Der Mercenary Loadout Screen (Phase F Erweiterung) mit Federated Skills
                                   setzt Phase 4 (Arsenal) voraus. Falls Phase F vor Phase 4 aktiviert wird,
                                   ist der Loadout auf lokale Skills beschränkt oder noch nicht verfügbar.
                                   Basis-Loadout (nur lokale Skills) ist ab Phase 4 unabhängig von Phase F
                                   verfügbar.

Empfohlene Reihenfolge für Teams:   Phase 1 → Phase 2 → Phase F → Phase 3 → ...
Solo-Entwickler (kein Peer):         Phase F überspringen oder nach Phase 5 nachholen.
```

**Kompatibilitätsgarantie:** Das Schema (inkl. `nodes`, `node_identity`, `origin_node_id`, `federation_scope`) wird bereits in Phase 1 angelegt. Phase F aktiviert darauf aufbauend das Federation-Protokoll — kein Migrations-Bruch.

**MCP-Tool-Abgrenzung:** Phase F implementiert Federation als REST-API-Endpoints (`/federation/*`). Das Frontend nutzt diese Endpoints direkt (UI-Buttons, Settings). Die MCP-Tool-Wrapper (`hivemind/fork_federated_skill`, `hivemind/start_discovery_session`, `hivemind/end_discovery_session`) werden erst verfügbar wenn Phase 3 den MCP-Server bereitstellt. Vor Phase 3 sind alle Federation-Aktionen ausschließlich über die UI erreichbar.

---

## Definition of Ready für Phase 8 (Autonomous Mode)

Autonomous Mode wird erst aktiviert wenn alle Kriterien erfüllt sind:

1. RBAC und Audit für alle Writes produktiv (Phase 2)
2. Idempotenz und optimistic locking für alle mutierenden Domain-Writes aktiv (Phase 2)
3. Review-Gate verhindert direkte `done`-Transitions (Phase 2)
4. Eskalations-SLA mit Backup-Owner und Admin-Fallback verifiziert (Phase 6)
5. KPI-Baselines über mindestens 2 Wochen stabil gemessen (Phase 7)

---

## KPIs (ab Phase 3 messen)

| KPI | Zielwert |
| --- | --- |
| Routing-Precision bei Auto-Owner-Zuweisung | >= 85% |
| Median Zeit bis `scoped` nach Epic-Ingest | <= 4h |
| Anteil Tasks ohne Reopen nach `done` | >= 80% |
| Decision Requests innerhalb SLA gelöst | >= 95% |
| Skill-Proposals mit Entscheidung in 72h | >= 90% |
| Unauthorized Write Attempts | 0 toleriert |

---

## Migrations-Strategie (Alembic)

Schema-Änderungen zwischen Phasen werden über Alembic verwaltet. Da alle Tabellen in Phase 1 angelegt werden (viele Spalten initial leer), sind spätere Phasen primär **Feature-Aktivierung** und **Index-Erweiterung** — keine destruktiven Schema-Changes.

### Konventionen

| Regel | Beschreibung |
| --- | --- |
| **Ein Migration-Ordner pro Phase** | `alembic/versions/phase_<N>/` — ermöglicht klare Zuordnung |
| **Forward-only in Produktion** | Rollback-Migrations (`downgrade`) existieren für Dev/Test, werden aber in Produktion nicht ausgeführt. Stattdessen: Backup → Forward-Fix |
| **Additive Changes bevorzugt** | Neue Spalten mit `DEFAULT`, neue Tabellen, neue Indexes. Bestehende Spalten werden nicht umbenannt oder gelöscht (Kompatibilität) |
| **Daten-Migration separat** | Schema-Migrations und Daten-Migrations (Backfills, Re-Embeddings) sind getrennte Alembic-Schritte — Daten-Migration ist re-runnable |
| **Phase-Gate-Check** | Jede Migration prüft `app_settings.current_phase` — eine Phase-5-Migration wird nicht ausgeführt wenn `current_phase < 5` |

### Typische Migrations pro Phase

| Phase | Schema-Änderungen | Daten-Migration |
| --- | --- | --- |
| 1 | Alle Tabellen anlegen, Basis-Indexes | Bootstrap: `app_settings`, `level_thresholds`, `badge_definitions` |
| 2 | — (Schema existiert) | Ggf. erster Admin-User anlegen |
| 3 | Embedding-Spalten (`vector(768)`) + HNSW-Indexes | Initial-Embedding-Berechnung für bestehende Skills/Wiki |
| 4 | — | — |
| 5 | — | — |
| 6 | — | SLA-Cron-Job aktivieren |
| 7 | Ggf. `sync_outbox` Partitioning evaluieren | DLQ-Backfill |
| 8 | Ggf. `ai_provider`-Config in `app_settings` | — |

```bash
# Phase-Upgrade durchführen
hivemind upgrade --to-phase 3

# Intern: prüft current_phase, führt Alembic-Migrations aus, aktualisiert current_phase
# Warnung bei fehlenden Voraussetzungen (z.B. "Phase 2 RBAC nicht abgeschlossen")
```

### CLI-Spezifikation (`hivemind` Management-Tool)

Das `hivemind`-CLI ist ein **Click/Typer-basiertes Python-Tool** das als Entry-Point im Backend-Package installiert wird (`pyproject.toml`). Es verbindet sich direkt mit der PostgreSQL-Datenbank (kein laufender Server nötig für Admin-Operationen).

```bash
# Phase-Management
hivemind upgrade --to-phase <N>      # Alembic-Migrations + current_phase aktualisieren
hivemind status                       # Aktuelle Phase, DB-Health, Pending-Migrations anzeigen

# Backup & Restore
hivemind backup                       # Manuelles pg_dump (zusätzlich zum Cron)
hivemind restore --backup <path>      # Vollständiges Restore aus Backup
hivemind restore --backup <path> --db-only   # Nur DB (ohne Uploads)
hivemind restore --backup <path> --dry-run   # Validierung ohne Write

# Embedding-Management
hivemind reembed --all                # Alle Embeddings neu berechnen (Provider-Wechsel)
hivemind reembed --entity skills      # Nur Skills re-embedden

# Federation Key-Management
hivemind federation rotate-key        # Ed25519-Keypair rotieren
hivemind federation revoke-key --peer <id>  # Peer-Key widerrufen
hivemind federation show-key          # Eigenen Public Key anzeigen
hivemind federation export-key --encrypted  # Key-Backup

# Export
hivemind export-full                  # Vollständiger Daten-Export (pg_dump + Uploads)
hivemind export-keys                  # Ed25519-Keys exportieren (passwortgeschützt)
```

**Implementierung:** `click` oder `typer` (evaluieren in Phase 1). Verbindung zur DB via `DATABASE_URL` Env-Var (selbe Config wie Backend). Kein eigener API-Server — direkter DB-Zugriff für Admin-Operationen.

---

## Testing-Strategie

### Test-Pyramide

| Ebene | Tool | Scope | Mindestabdeckung |
| --- | --- | --- | --- |
| **Unit-Tests** | `pytest` (Backend), `vitest` (Frontend) | Einzelne Funktionen, Pydantic-Modelle, Composables | 80% Line Coverage |
| **Integration-Tests** | `pytest` + `httpx` (TestClient) + testcontainers-postgres | API-Endpoints, MCP-Tools, DB-Queries | Alle MCP-Tools + alle REST-Endpoints |
| **E2E-Tests** | `Playwright` | Kritische User-Flows (Login → Scoping → Worker → Review → Done) | 5 Kernflows |
| **Contract-Tests** | OpenAPI-Diff (`oasdiff`) | Frontend-Client vs. Backend-Schema — Breaking Changes erkennen | CI-Pflicht |

### CI-Pipeline (pro PR)

```text
1. Lint:      ruff check + eslint
2. Type:      mypy (Backend) + vue-tsc (Frontend)
3. Unit:      pytest --cov + vitest --coverage
4. Schema:    openapi.json export → oasdiff gegen main
5. Integ:     pytest tests/integration/ (mit testcontainers-postgres)
6. Build:     vite build (Frontend) — Lighthouse >= 80
7. E2E:       Playwright (nur auf main-Branch, nicht auf jedem PR)
```

### Test-Fixtures

- **DB-Fixtures:** `conftest.py` mit Factory-Funktionen für alle Entitäten (User, Project, Epic, Task, Skill, Guard)
- **MCP-Fixtures:** Mock-MCP-Client der Tool-Calls simuliert
- **SSE-Fixtures:** Test-Utility die SSE-Events collected und assertbar macht

---

## Token-Counting-Methodik

Hivemind zählt Tokens für das Prompt-Assembly (Budget-Anzeige im Token Radar) und für Skill-Gewichte im Loadout.

| Aspekt | Spezifikation |
| --- | --- |
| **Tokenizer** | `tiktoken` mit dem Encoding `cl100k_base` (kompatibel mit GPT-4, Claude, die meisten LLMs) |
| **Berechnung** | **Serverseitig** beim Prompt-Assembly (`get_prompt`). Der Token-Count wird im Response mitgegeben |
| **Caching** | Skill-Token-Counts werden beim Merge/Version-Update einmalig berechnet und in `skill_versions.token_count` gespeichert |
| **Frontend** | Zeigt nur den vom Backend gelieferten Wert an — keine Client-seitige Zählung |
| **Budget-Quelle** | Präzedenz: (1) `context_boundaries.max_token_budget` (Task-spezifisch) → (2) `HIVEMIND_TOKEN_BUDGET_PROVIDER_OVERRIDE` Env-Var (JSON: `{"claude": 100000, "gpt4": 128000}`, Phase 8) → (3) `app_settings.token_budget_default` (Default: 8000). Siehe [bibliothekar.md — Token-Budget](../agents/bibliothekar.md#token-budget) |
| **Überschreitung** | Soft-Limit: Warnung im Loadout wenn > 90%. Hard-Limit: Prompt-Assembly schneidet niedrig-priorisierte Context-Blöcke ab (Docs vor Skills, ältere Docs zuerst) |

---

## Embedding-Pipeline

Ab Phase 3 (Ollama) werden Embeddings für semantische Suche und pgvector-basiertes Routing generiert.

### Was wird embedded?

| Entität | Embedded-Feld | Trigger | Tabelle / Spalte |
| --- | --- | --- | --- |
| **Skills** (active) | `content` (Skill-Volltext) | On-Write: bei `merge_skill`, `accept_skill_change` | `skills.embedding` |
| **Wiki-Artikel** | `content` (Artikel-Volltext) | On-Write: bei `create_wiki_article`, `update_wiki_article` | `wiki_articles.embedding` |
| **Code-Nodes** | `summary` (Kartograph-generiert) | On-Write: bei Kartograph-Discovery | `code_nodes.embedding` |
| **Sync-Outbox** (unrouted Events) | `payload` (externer Event-Text) | On-Ingest: beim Webhook-Empfang | `sync_outbox.embedding` |

### Embedding-Ablauf

```text
1. Write-Trigger (z.B. merge_skill)
2. Backend schreibt Entität in DB (ohne Embedding)
3. Background-Task: Embedding-Request an Ollama (nomic-embed-text)
4. Ollama liefert vector(768)
5. Backend aktualisiert Embedding-Spalte
6. HNSW-Index wird automatisch aktualisiert (pgvector)
```

### Freshness & Re-Embedding

| Szenario | Verhalten |
| --- | --- |
| Skill-Version-Update | Neues Embedding für die neue Version; alte Version behält ihr Embedding |
| Wiki-Artikel-Update | Neues Embedding für die neue Version |
| Provider-Wechsel (Ollama → OpenAI) | Batch-Re-Embedding aller Entitäten (async Background-Job, `hivemind reembed --all`) |
| Embedding-Spalte NULL | Entität wird bei semantischer Suche ignoriert; erscheint nur bei ILIKE-Suche |

### Dimensionswechsel als Breaking Migration

Wenn der neue Embedding-Provider eine andere Vektordimension verwendet (z.B. `nomic-embed-text` 768d → OpenAI `text-embedding-3-small` 1536d), ist ein **Schema-Änderung** nötig:

```sql
-- Dimensionswechsel erfordert:
ALTER TABLE skills ALTER COLUMN embedding TYPE vector(1536);
ALTER TABLE wiki_articles ALTER COLUMN embedding TYPE vector(1536);
ALTER TABLE code_nodes ALTER COLUMN embedding TYPE vector(1536);
ALTER TABLE sync_outbox ALTER COLUMN embedding TYPE vector(1536);
-- HNSW-Indexes werden automatisch invalidiert und müssen rebuilt werden
REINDEX INDEX idx_skills_embedding;
-- etc.
```

| Metrik | Geschätzter Aufwand |
| --- | --- |
| ALTER TABLE pro Tabelle | < 1 Sekunde (Metadaten-Änderung, keine Daten-Rewrite) |
| REINDEX pro HNSW-Index | ~2–5 Sekunden pro 1000 Einträge |
| Re-Embedding via Ollama | ~10–20 Sekunden pro 1000 Einträge (abhängig von GPU) |
| Re-Embedding via OpenAI API | ~5–10 Sekunden pro 1000 Einträge (Netzwerk-abhängig) |
| **Gesamtdauer (1000 Entitäten)** | **~15–30 Sekunden** |
| **Gesamtdauer (10.000 Entitäten)** | **~3–5 Minuten** |

> **Klassifikation:** Ein Dimensionswechsel ist eine **Breaking Migration** — während des Re-Embeddings ist die semantische Suche degradiert (Entitäten mit NULL-Embedding werden ignoriert). Der Wechsel sollte in einem Wartungsfenster erfolgen. `hivemind reembed --all` ist idempotent und re-runnable.

### Konfiguration

| Env-Variable | Default | Beschreibung |
| --- | --- | --- |
| `HIVEMIND_EMBEDDING_PROVIDER` | `ollama` | `ollama` oder `openai` |
| `HIVEMIND_EMBEDDING_MODEL` | `nomic-embed-text` | Modell-Name beim Provider |
| `HIVEMIND_OLLAMA_URL` | `http://ollama:11434` | Ollama-Endpunkt (Docker-Service) |
| `HIVEMIND_OPENAI_EMBEDDING_KEY` | — | API-Key für OpenAI Embeddings (optional) |
| `HIVEMIND_EMBEDDING_BATCH_SIZE` | `50` | Batch-Größe für Re-Embedding-Jobs |
