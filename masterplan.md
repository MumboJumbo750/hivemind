# Project Hivemind — Index

> **Ein hybrides Entwickler-Hivemind mit Progressive Disclosure.**
> Startet als manuelles BYOAI-System ("Wizard of Oz") und skaliert ohne Architekturbruch auf autonome MCP-Agenten.
> Hivemind ist selbst ein MCP-Server: der Chat liest und schreibt Kontext direkt.

---

## Kernprinzipien (Kurzfassung)

1. **Progressive Disclosure** — Kontext nur task-genau laden, kein Context-Bloat
2. **BYOAI → Autonomy** — Heute manuell, morgen autonom. Gleiche Endpoints, gleicher Datenvertrag
3. **Prompt Station** — System sagt wann welcher Agent dran ist + liefert den Prompt
4. **Keine autonome AI-Ausführung in Phase 1–7** — AI wird manuell genutzt (Prompts im AI-Client kopieren/einfügen), keine autonomen Agenten-Writes. **Hinweis:** Ab Phase 3 übernimmt der Bibliothekar das Context-Assembly automatisch (pgvector-Similarity, kein manueller Wizard-of-Oz-Prompt mehr) — nur die AI-Ausführung bleibt manuell.
5. **Review-Gate immer aktiv** — Auch im Solo-Modus kein direktes `done`
6. **Sci-Fi Game HUD** — Modern, dunkel, gamelike — Commander eines Agenten-Schwarms
7. **Sovereign Nodes** — Jeder Entwickler ist sein eigener Host; Federation verbindet Peers im VPN

---

## Architektur

| Dokument | Inhalt |
| --- | --- |
| [Übersicht & Stack](docs/architecture/overview.md) | Leitprinzipien, Tech Stack, Trust Boundary, Solo/Team-Modus |
| [REST API](docs/architecture/rest-api.md) | Frontend-Backend-Vertrag, Auth-Flow, SSE-Event-Schema, Endpoint-Übersicht |
| [Datenmodell](docs/architecture/data-model.md) | Vollständiges SQL-Schema aller Tabellen |
| [State Machines](docs/architecture/state-machine.md) | Task-States, Skill-Lifecycle, Concurrency, Eskalations-Flow |
| [MCP Tool-Set](docs/architecture/mcp-toolset.md) | Alle MCP-Tools, Transports, Sicherheitsregeln |
| [RBAC](docs/architecture/rbac.md) | Rollen, Berechtigungsmatrix, Audit-Retention |
| [Observability](docs/architecture/observability.md) | Log-Levels, strukturiertes JSON-Logging, Prometheus-Metrics, OTEL-Tracing, Health-Check |
| [Disaster Recovery](docs/architecture/disaster-recovery.md) | Backup-Strategie, PITR, Wiederherstellungs-Prozeduren, RTO/RPO |

---

## Agenten

| Dokument | Inhalt |
| --- | --- |
| [Übersicht](docs/agents/overview.md) | Alle Agenten im Vergleich |
| [Kartograph](docs/agents/kartograph.md) | Fog-of-War Explorer, Repo-Analyse, Wiki-Autor |
| [Stratege](docs/agents/stratege.md) | Plan→Epics, Dependency-Mapping, Roadmap-Planung |
| [Architekt](docs/agents/architekt.md) | Epic-Dekomposition, Tasks, Context Boundaries |
| [Worker](docs/agents/worker.md) | Task-Ausführung, Guard-Prüfung, Ergebnislieferung |
| [Gaertner](docs/agents/gaertner.md) | Skill-Destillation, Decision Records, Doc-Updates |
| [Triage](docs/agents/triage.md) | Event-Routing, Proposals, Dead Letters, Eskalationen |
| [Bibliothekar](docs/agents/bibliothekar.md) | Context Assembly — Phase 1–2: Prompt, Phase 3+: Service |
| [Prompt Pipeline](docs/agents/prompt-pipeline.md) | Prompt-Typen, Generierung, Templates als Skills |

---

## Features

| Dokument | Inhalt |
| --- | --- |
| [Skills](docs/features/skills.md) | Format, Lifecycle, Versionierung, Task-Pinning, Guard-Verbindung |
| [Agent Skills](docs/features/agent-skills.md) | System-Skills der Agenten, Claude-Kompatibilität, Fach-Skill-Katalog |
| [Guards](docs/features/guards.md) | Executable Checks, Scopes (global/project/skill/task), Kartograph-Discovery |
| [Wiki](docs/features/wiki.md) | Projektübergreifende Wissensbasis, Datenmodell |
| [Memory Ledger](docs/features/memory-ledger.md) | Agent-Gedächtnis, Infinite Context, Progressive Summarization |
| [Nexus Grid](docs/features/nexus-grid.md) | Code-Graph, Fog of War, Bug-Heatmap |
| [Sync & DLQ](docs/features/sync.md) | Outbox Pattern, Retry, Dead Letter Queue, pgvector-Routing |
| [Federation](docs/features/federation.md) | Sovereign Nodes, Shared Epics, Peer-Protokoll, Skill/Wiki-Sharing |
| [Epic Restructure](docs/features/epic-restructure.md) | Kartograph-Proposals: Split, Merge, Task-Move — State Machine, API, Constraints |
| [Gamification](docs/features/gamification.md) | EXP-Tabelle, Badges, Level-System, Datenmodell, Anti-Spam |
| [Hive Station](docs/features/hive-station.md) | Federation Control Plane — Peer Registry, Presence, Relay (eigenständiger Service) |
| [Autonomy Loop](docs/features/autonomy-loop.md) | Conductor-Orchestrator, Reviewer-Skill, Governance-Levels, Autonomie-Spektrum |
| [Glossar](docs/glossary.md) | Zentrale Definition aller Hivemind-Domänenbegriffe |

---

## UI

| Dokument | Inhalt |
| --- | --- |
| [Konzept & Design](docs/ui/concept.md) | Sci-Fi Design-System, Layout, Gamification, Progressive Reveal, Markdown-Strategie |
| [Design Tokens](docs/ui/design-tokens.md) | Verbindliches Token-Schema, Naming-Contract, Theme-Vertrag |
| [Prompt Station](docs/ui/prompt-station.md) | Kern-Interaktion: Agent-Queue, Prompts, Volltext-Modal |
| [Views](docs/ui/views.md) | Command Deck, Triage, Skill Lab, Wiki, Notification Tray, Settings |
| [Feature-Matrix](docs/ui/feature-matrix.md) | Alle Funktionen → UI-Element → Phase |
| [Komponentarchitektur](docs/ui/components.md) | 4-Schichten-Modell, Layer 2/3 Reuse-Matrix, View-Verzeichnisstruktur |

---

## Phasen

| Dokument | Inhalt | Status |
| --- | --- | --- |
| [Übersicht](docs/phases/overview.md) | 8-Phasen-Tabelle, KPIs, Definition of Ready | — |
| [Phase 1](docs/phases/phase-1.md) | Datenfundament, State Machine, Docker Setup | **Nächste Phase** |
| [Phase 2](docs/phases/phase-2.md) | Identity & RBAC, Command Deck, Review | — |
| [Phase F](docs/phases/phase-f.md) | Federation: Sovereign Nodes, Shared Map, Skill-Loadouts | — |
| [Phase 3](docs/phases/phase-3.md) | MCP Read-Tools, Bibliothekar-Prompt, Ollama | — |
| [Phase 4](docs/phases/phase-4.md) | Planer-Writes (Architekt), Skill Lab | — |
| [Phase 5](docs/phases/phase-5.md) | Worker & Gaertner Writes, Wiki, Nexus Grid 2D | — |
| [Phase 6](docs/phases/phase-6.md) | Eskalation, Decision Requests, SLA-Automation | — |
| [Phase 7](docs/phases/phase-7.md) | Integration Hardening, DLQ, Bug Heatmap | — |
| [Phase 8](docs/phases/phase-8.md) | Volle Autonomie, Conductor, Reviewer, Governance-Levels, 3D Nexus Grid | — |

---

## Seed-Strategie — Dogfooding

> Hivemind bootstrapped sich selbst: Das Projekt wird dateibasiert im `seed/`-Ordner als sein eigener erster Anwendungsfall modelliert — bevor die Datenbank existiert.

| Dokument | Inhalt |
| --- | --- |
| [Seed-Strategie](docs/seed-strategy.md) | Dogfooding-Konzept, Ordnerstruktur, Datei-Formate, Import-Prozess |

**Agenten-Rollen im Seed-Prozess:**

| Agent | Aufgabe | Output |
| --- | --- | --- |
| Kartograph | Masterplan → Wiki-Artikel, Epic-Docs | `seed/wiki/`, `seed/docs/` |
| Gärtner | Architektur-Docs → wiederverwendbare Skills | `seed/skills/` |
| Architekt | Phasen → Epics → Tasks + Subtasks mit DoD | `seed/epics/`, `seed/tasks/` |
| Bibliothekar | Konsistenz-Review, Verknüpfungen | Referenzen in allen Dateien |

**Nutzen:** Klare Arbeitspakete ab Tag 1, Seed-Daten für DB-Import in Phase 1a, Showcase-Projekt für neue User, Validierung des Phasenplans durch Dekomposition.

---

## Aktueller Stand

- **Masterplan:** vollständig — aufgeteilt in 37 thematische Dokumente
- **Alle offenen Fragen:** beantwortet
- **Gap-Analyse:** durchgeführt — 77 Findings identifiziert und behoben (52 aus früheren Analysen + 25 aus vierter Analyse: 4 neue Docs, 7 bestehende Docs aktualisiert, Widersprüche aufgelöst)
- **Seed-Strategie:** definiert — Phasen werden als Epics/Tasks im `seed/`-Ordner modelliert (→ [Seed-Strategie](docs/seed-strategy.md))
- **Nächster Schritt:** Seed-Daten erstellen (Kartograph → Gärtner → Architekt), dann [Phase 1](docs/phases/phase-1.md) umsetzen

---

## Tech Stack Kurzreferenz

```
Backend:    FastAPI + SQLAlchemy 2 + Alembic + asyncpg
DB:         PostgreSQL 16 + pgvector
Embeddings: Ollama nomic-embed-text (ab Phase 3)
Frontend:   Vue 3 + Vite + TypeScript + Reka UI + Design Tokens (CSS Variables)
Runtime:    Docker Compose
MCP:        stdio (lokal) + HTTP/SSE (team/remote)
```
