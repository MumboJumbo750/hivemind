# Seed-Strategie — Hivemind bootstrapped sich selbst

← [Index](../masterplan.md)

> **Kernidee:** Das Hivemind-Projekt wird sein eigener erster Anwendungsfall. Wir simulieren das System dateibasiert in einem `seed/`-Ordner — bevor die Datenbank existiert. Bei Phase 1 wird der `seed/`-Ordner als initialer DB-Import genutzt: jeder Nutzer sieht sofort ein echtes Projekt und lernt dabei wie Hivemind funktioniert.

---

## Warum?

1. **Dogfooding** — Wir testen die Agent-Workflows (Kartograph, Architekt, Gärtner, Bibliothekar) konzeptionell bevor Code geschrieben wird
2. **Seed-Daten** — Das Ergebnis wird zum initialen DB-Import; kein leeres System beim ersten Start
3. **Onboarding** — Neue User sehen ein komplett durchgeplantes Projekt und verstehen Epics, Tasks, Skills, Wiki sofort
4. **Validierung** — Die Dekomposition der Phasen in Tasks deckt Lücken und Widersprüche im Plan auf
5. **Living Documentation** — Die Seed-Daten sind gleichzeitig die aktuellste Projektdokumentation

---

## Agenten-Rollen bei der Seed-Erstellung

| Agent | Aufgabe im Seed-Prozess | Output im `seed/`-Ordner |
| --- | --- | --- |
| **Kartograph** | Analysiert den Masterplan und die Docs; erstellt Wiki-Artikel die das System erklären | `seed/wiki/*.md` |
| **Gärtner** | Destilliert wiederverwendbare Skills aus den Architektur-Docs und Konventionen | `seed/skills/*.md` |
| **Bibliothekar** | Organisiert den Kontext; verknüpft Wiki, Skills und Docs mit Epics/Tasks | Referenzen in den JSON-Dateien |
| **Architekt** | Zerlegt jede Phase (= Epic) in konkrete Tasks und Subtasks mit DoD und Verweisen | `seed/epics/*.json`, `seed/tasks/**/*.json` |

---

## Ordnerstruktur

```
seed/
├── README.md                           # Diese Datei erklärt das Seed-Konzept
├── project.json                        # HiveMind als Projekt-Entity
│
├── epics/                              # Phasen → Epics (1 JSON pro Epic)
│   ├── phase-1a.json                   # Datenfundament Backend
│   ├── phase-1b.json                   # Design & Prompt Station
│   ├── phase-2.json                    # Identity & RBAC
│   ├── phase-f.json                    # Federation
│   ├── phase-3.json                    # MCP Read-Tools
│   ├── phase-4.json                    # Planer-Writes
│   ├── phase-5.json                    # Worker & Gaertner Writes
│   ├── phase-6.json                    # Eskalation & SLA
│   ├── phase-7.json                    # Integration Hardening
│   └── phase-8.json                    # Volle Autonomie
│
├── tasks/                              # Architekt-Output: Tasks pro Epic
│   ├── phase-1a/                       # Tasks für Phase 1a
│   │   ├── 001-docker-compose.json
│   │   ├── 002-db-schema.json
│   │   └── ...
│   ├── phase-1b/
│   │   ├── 001-vue-scaffold.json
│   │   └── ...
│   └── ...
│
├── wiki/                               # Kartograph-Output: Wiki-Artikel
│   ├── system-architektur.md           # Gesamtarchitektur-Überblick
│   ├── agent-konzept.md                # Wie die Agenten zusammenarbeiten
│   ├── progressive-disclosure.md       # Kernprinzip erklärt
│   ├── byoai-workflow.md               # BYOAI-Ansatz für User
│   ├── state-machine-guide.md          # Task- und Epic-Lifecycle
│   ├── federation-konzept.md           # Sovereign Nodes Überblick
│   ├── tech-stack.md                   # Stack-Entscheidungen und Begründungen
│   ├── glossar.md                      # System-Glossar als Wiki-Artikel
│   ├── nexus-grid.md                   # Die Code-Landkarte
│   ├── eskalation-und-sla.md           # Automatische Deadlines
│   ├── mcp-integration.md             # Wie Agents kommunizieren
│   ├── autonomie-loop.md              # Von BYOAI zur Autonomie
│   ├── sync-und-integration.md        # Externe Systeme anbinden
│   ├── gamification.md                # EXP, Badges & Levels
│   ├── monorepo-struktur.md           # Ein Repo, alles drin
│   └── skill-system.md               # Wiederverwendbare Instruktionen
│
├── skills/                             # Gärtner-Output: Skills mit Frontmatter
│   ├── fastapi-endpoint.md             # FastAPI Endpoint erstellen
│   ├── alembic-migration.md            # Datenbank-Migration schreiben
│   ├── vue-component.md                # Vue 3 Component erstellen
│   ├── pydantic-model.md               # Pydantic v2 Model definieren
│   ├── state-machine-transition.md     # State-Transition implementieren
│   ├── docker-service.md               # Docker Compose Service konfigurieren
│   ├── api-test.md                     # API-Endpoint-Test schreiben
│   └── design-token.md                 # Design Token anlegen/verwenden
│
├── docs/                               # Epic-Docs (Kartograph + Gärtner)
│   ├── phase-1a-architektur.md         # Architektur-Kontext für Phase 1a
│   ├── phase-1b-ui-konzept.md          # UI-Kontext für Phase 1b
│   ├── phase-2-architektur.md          # Identity & RBAC Kontext
│   ├── phase-3-architektur.md          # MCP & Embeddings Kontext
│   ├── phase-4-architektur.md          # Planer-Writes Kontext
│   ├── phase-5-architektur.md          # Worker/Gaertner Kontext
│   ├── phase-6-architektur.md          # Eskalation & Triage Kontext
│   ├── phase-7-technischer-kontext-und-vorarbeiten.md
│   ├── phase-8-architektur.md          # Volle Autonomie Kontext
│   └── phase-f-architektur.md          # Federation Kontext
│
├── decisions/                          # Decision Records (JSON)
│   ├── dr-001.json
│   ├── dr-002.json
│   └── dr-003.json
│
└── code_nodes/                         # Kartograph Code-Landkarte
    └── hivemind-code-map.json          # Code Nodes + Edges des Monorepos
```

---

## Datei-Formate

### project.json

```json
{
  "name": "Hivemind",
  "slug": "hivemind",
  "description": "Ein hybrides Entwickler-Hivemind mit Progressive Disclosure. Startet als BYOAI-System und skaliert auf autonome MCP-Agenten.",
  "created_by": "admin"
}
```

### Epic (z.B. `epics/phase-1a.json`)

Orientiert sich am DB-Schema (`epics`-Tabelle), aber als flat JSON:

```json
{
  "external_id": "EPIC-PHASE-1A",
  "title": "Phase 1a — Datenfundament Backend",
  "description": "Docker Compose Stack, vollständiges DB-Schema, State Machine, API-Skeleton.",
  "state": "scoped",
  "priority": "critical",
  "sla_deadline": null,
  "definition_of_done": "docker compose up startet fehlerfrei, alle Tabellen existieren, State Machine validiert Transitions.",
  "tags": ["backend", "infrastructure", "phase-1"],
  "depends_on": [],
  "source_doc": "docs/phases/phase-1.md#phase-1a"
}
```

### Task (z.B. `tasks/phase-1a/001-docker-compose.json`)

Orientiert sich am DB-Schema (`tasks`-Tabelle):

```json
{
  "external_id": "TASK-1A-001",
  "epic_ref": "EPIC-PHASE-1A",
  "title": "Docker Compose Stack aufsetzen",
  "description": "PostgreSQL 16 + pgvector, FastAPI + Uvicorn, Vue 3 + Vite als Docker Compose Services konfigurieren. Health-Checks, Volume-Mounts, Netzwerk.",
  "state": "incoming",
  "priority": "critical",
  "definition_of_done": {
    "criteria": [
      "docker compose up startet alle 3 Services ohne Fehler",
      "PostgreSQL mit pgvector-Extension erreichbar",
      "FastAPI Health-Endpoint antwortet",
      "Vue Dev-Server erreichbar auf Port 5173",
      "Hot-Reload funktioniert für Backend und Frontend"
    ]
  },
  "tags": ["docker", "infrastructure"],
  "subtasks": [],
  "pinned_skills": ["docker-service"],
  "linked_wiki": ["system-architektur", "tech-stack"],
  "source_doc": "docs/phases/phase-1.md",
  "estimated_complexity": "medium"
}
```

### Wiki-Artikel (Markdown mit YAML-Frontmatter)

```markdown
---
slug: "system-architektur"
title: "Systemarchitektur — Hivemind Überblick"
tags: ["architektur", "backend", "frontend", "überblick"]
linked_epics: ["EPIC-PHASE-1A", "EPIC-PHASE-1B"]
---

# Systemarchitektur — Hivemind Überblick

Hivemind ist ein hybrides Entwicklungssystem ...
```

### Skill (Markdown mit Hivemind-Frontmatter)

Identisch zum Skill-Format in [skills.md](./features/skills.md):

```markdown
---
title: "FastAPI Endpoint erstellen"
service_scope: ["backend"]
stack: ["python", "fastapi"]
version_range: { "python": ">=3.11", "fastapi": ">=0.100" }
confidence: 0.5
source_epics: ["EPIC-PHASE-1A"]
guards:
  - title: "Python Linting"
    command: "ruff check ."
  - title: "Unit Tests"
    command: "pytest tests/unit/"
---

## Skill: FastAPI Endpoint erstellen

### Rolle
Du erstellst einen neuen FastAPI-Endpoint ...
```

---

## DB-Import (Phase 1a)

Der Seed-Import wird als **Alembic Data-Migration** oder als **CLI-Command** implementiert:

```bash
# Option A: CLI-Command
hivemind seed import --path ./seed/

# Option B: Alembic Data-Migration (empfohlen für Erstsetup)
# In der initialen Migration: seed/ Ordner lesen und DB befüllen
```

### Import-Reihenfolge

1. `project.json` → `projects`-Tabelle
2. `epics/*.json` → `epics`-Tabelle (mit Projekt-FK)
3. `skills/*.md` → `skills`-Tabelle (Frontmatter parsen, Body als Content)
4. `wiki/*.md` → `wiki_articles`-Tabelle (Frontmatter parsen, Body als Content)
5. `docs/*.md` → `docs`-Tabelle (mit Epic-FK)
6. `tasks/**/*.json` → `tasks`-Tabelle (mit Epic-FK, Skill-Refs auflösen)
7. `decisions/*.json` → `decision_records`-Tabelle (mit Epic-FK)
8. `code_nodes/*.json` → `code_nodes` + `code_edges` (Kartograph-Landkarte)

### Idempotenz

Der Import nutzt `external_id` bzw. `slug` als Deduplizierungsschlüssel — mehrfaches Ausführen überschreibt nicht, sondern skippt existierende Einträge (oder aktualisiert bei explizitem `--update`-Flag).

---

## Arbeitsprozess

### Schritt 1: Kartograph-Pass (Wiki + Docs)

Wir durchlaufen den gesamten Masterplan und die 37 Docs mit der Kartograph-Perspektive:
- Systemverständnis in Wiki-Artikel gießen
- Jeder Wiki-Artikel = ein abgeschlossener Wissensbereich
- Epic-Docs als Kontext-Zusammenfassung pro Phase

### Schritt 2: Gärtner-Pass (Skills)

Aus den Architektur-Docs und Konventionen destillieren wir wiederverwendbare Skills:
- Jeder Skill = eine konkrete Handlungsanweisung für einen AI-Agenten
- Guards wo sinnvoll (Linting, Tests)
- `service_scope` und `stack` korrekt setzen

### Schritt 3: Architekt-Pass (Epics → Tasks)

Jede Phase wird als Epic modelliert und in Tasks zerlegt:
- Tasks mit klarer DoD
- Subtasks für komplexe Tasks
- Verweise auf relevante Skills und Wiki-Artikel
- Abhängigkeiten zwischen Tasks markieren

### Schritt 4: Bibliothekar-Review (Konsistenz)

Abschließende Konsistenzprüfung:
- Alle Skill-Referenzen in Tasks zeigen auf existierende Skills
- Alle Wiki-Referenzen sind gültig
- Alle Epic-Referenzen in Docs stimmen
- Keine verwaisten Dateien

---

## Nutzen für die Umsetzung

| Vorteil | Beschreibung |
| --- | --- |
| **Klare Arbeitspakete** | Jede Phase hat atomare Tasks — kein "irgendwo anfangen" |
| **Kontext sofort greifbar** | Skills und Wiki sagen dem AI-Client genau wie gearbeitet wird |
| **Paralleles Arbeiten** | Tasks sind unabhängig genug für mehrere Entwickler |
| **Fortschritt messbar** | Task-States (incoming → done) zeigen den Projektstand |
| **Selbstdokumentierend** | Das Projekt dokumentiert sich über seine eigenen Mechanismen |
| **Showcase** | Jeder neue User versteht sofort was Hivemind kann |

---

## Zusammenhang mit dem Phasenplan

```
  docs/phases/       ──── Kartograph ────→   seed/wiki/
       │                                     seed/docs/
       │
       ├──────────── Gärtner ─────────→   seed/skills/
       │
       └──────────── Architekt ───────→   seed/epics/
                                          seed/tasks/
                                              │
                                              ▼
                                    Phase 1a: Alembic Import
                                              │
                                              ▼
                                    DB befüllt → UI zeigt Projekt
```
