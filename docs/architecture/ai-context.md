# AI Context & Runtime Environment

← [Architektur-Übersicht](./overview.md) | [Index](../../masterplan.md)

**Ziel:** Sicherstellen, dass AI-Agents (Claude, Cursor, Copilot, GPT-basiert) immer den korrekten Laufzeit-Kontext haben — unabhängig davon, welches AI-System gerade arbeitet.

---

## Das Problem

AI-Agents scheitern selten an Code-Logik — sie scheitern an fehlendem **Laufzeit-Kontext**:

- "Führe ich `alembic upgrade head` auf dem Host oder im Container aus?"
- "Wie heißt der Container? Wie reach ich MCP?"
- "Welche Ports sind exposed?"

Dieser Kontext lebt bisher in Entwicklerköpfen. Das führt zu Fehlern, Rückfragen und abgebrochenen AI-Sessions.

---

## Lösung: AGENTS.md als universelle Wahrheitsquelle

### Datei-Hierarchie

```
projekt-root/
  AGENTS.md                          ← universell, AI-agnostisch (EINZIGE WAHRHEIT)
  CLAUDE.md                          ← @see AGENTS.md + Claude-spezifisch
  .cursorrules                       ← @see AGENTS.md + Cursor-spezifisch
  .github/copilot-instructions.md    ← @see AGENTS.md + Copilot-spezifisch
```

**Prinzip: Eine Wahrheit, viele Konsumenten.** Updates nur in `AGENTS.md` — alle AI-Config-Files sind dünne Wrapper.

### AGENTS.md Pflicht-Abschnitte

| Abschnitt | Inhalt |
|-----------|--------|
| Runtime Environment | Container-Runtime, Service-Topologie-Tabelle (Service / Port / Technologie) |
| ⚠️ Wo Befehle laufen | Explizit: Host vs. Container — mit Gegenbeispielen |
| Dev-Befehle Referenz | Copy-paste-ready, vollständige Befehle |
| MCP-Server | Erreichbarkeit, Voraussetzungen, Health-Check |
| Projektstruktur | Verzeichnisbaum mit Kommentaren |
| Umgebungsvariablen | Tabelle: Variable / Default / Beschreibung |
| Codebase-Konventionen | Projektspezifische Regeln für AI-Agents |

---

## Monorepo-Support

In Monorepos wird AGENTS.md hierarchisch aufgebaut — analog zu CLAUDE.md in Claude Code:

```
monorepo/
  AGENTS.md              ← globaler Kontext: Gesamt-Topologie, Cross-Service-Konventionen
  CLAUDE.md              ← @see root AGENTS.md
  packages/
    backend/
      AGENTS.md          ← backend-spezifisch: alembic, pytest, Container-Befehle
    frontend/
      AGENTS.md          ← frontend-spezifisch: npm/pnpm, Vite, Hot-Reload
    shared/
      AGENTS.md          ← shared-lib: Build-Reihenfolge, Publish-Flow
```

### Hierarchie-Regeln

- **Root AGENTS.md:** Gesamt-Topologie, Cross-Package Build-Order, docker-compose-Services, globale Env-Vars
- **Package AGENTS.md:** Service-spezifische Befehle, lokaler Dev-Server, package-spezifische Konventionen
- **Laden:** Claude Code lädt Root + nächstes Verzeichnis automatisch → vollständiger Kontext ohne Duplikation

### Build-Order (Monorepo-spezifisch)

Root AGENTS.md enthält die Build-Reihenfolge aus `depends_on` (package.json / docker-compose):

```markdown
## Build-Reihenfolge
1. `packages/shared` → `pnpm build`
2. `packages/backend` → `podman compose exec backend alembic upgrade head`
3. `packages/frontend` → automatisch via Vite (kein Build-Step nötig)
```

---

## Skill-Typ: `runtime`

Neben `implementation` und `system` gibt es einen dritten Skill-Typ:

```yaml
skill_type: "runtime"   # Laufzeitumgebung, Container-Befehle, Environment-Kontext
```

| Typ | Beschreibung | Beispiele |
|-----|--------------|-----------|
| `domain` | Code-Muster, API-Patterns | `fastapi-endpoint.md`, `alembic-migration.md` |
| `runtime` | Container-Befehle, Laufzeit-Topologie | `podman-exec.md`, `runtime-environment.md` |
| `system` | Prompt-Templates, System-Level | `prompt-template-worker.md` |

Runtime-Skills werden als `pinned_skill` an alle Backend-Tasks gehängt, die Container-Befehle benötigen.

---

## Rollen-Erweiterungen

### Kartograph: Environment Discovery (Priorität 0)

Der Kartograph ist der Scout — er kartiert das **gesamte Territorium**, nicht nur den Code.

**Trigger:** AGENTS.md fehlt oder ist älter als `docker-compose.yml`

**Algorithmus:**
```
1. docker-compose.yml / podman-compose.yml → Services, Ports, Volumes, Profiles
2. Makefile / package.json scripts → Dev-Befehle
3. .env.example → Umgebungsvariablen
4. alembic.ini / prisma/schema.prisma → Migration-Tools
5. Container-Runtime erkennen: podman in PATH? → podman compose; sonst docker compose
6. AGENTS.md erstellen/aktualisieren
7. Runtime-Skills in seed/skills/ anlegen
```

Environment Discovery hat **höchste Priorität** — fehlendes AGENTS.md blockiert alle anderen AI-Agents.

### Gärtner: Runtime-Skill-Maintenance

Der Gärtner pflegt Runtime-Skills aktiv:

**Staleness-Triggers:**
- `docker-compose.yml` geändert → `podman-exec.md` und `AGENTS.md` prüfen
- Neuer Service in Compose → Service-Tabelle in AGENTS.md ergänzen
- Port-Änderung → Port-Tabelle aktualisieren

**Aktion bei Staleness:** Konkreten Update-Patch vorschlagen (diff-Format), kein stilles Ignorieren.

### Architekt: AGENTS.md Precondition

Der Architekt prüft vor jeder Epic-Dekomposition:

```
AGENTS.md existiert?
  JA  → normale Dekomposition
  NEIN → TASK-ENV-001 als Stufe-0-Task einfügen
         (blockiert alle Backend-Tasks, Frontend kann parallel starten)
```

Vorlage: `seed/tasks/env-bootstrap/TASK-ENV-001.json`

---

## Environment Bootstrap Epic

Für neue Projekte ohne diese Infrastruktur: **EPIC-ENV-BOOTSTRAP** instanziieren.

```
seed/epics/env-bootstrap.json      ← Epic-Definition (Template)
seed/tasks/env-bootstrap/
  TASK-ENV-001.json    ← Basisinfrastruktur: AGENTS.md + CLAUDE.md + Runtime-Skills
  TASK-ENV-002.json    ← Kartograph-Erweiterung: Environment Discovery
  TASK-ENV-003.json    ← Gärtner-Erweiterung: Runtime-Skill-Maintenance
  TASK-ENV-004.json    ← Architekt-Erweiterung: Precondition-Check
  TASK-ENV-005.json    ← Monorepo-Pattern + AI-Config-Files Validation
```

### Dependency-Reihenfolge

```
Stufe 0 (keine Deps):
  TASK-ENV-001  Basisinfrastruktur

Stufe 1 (nach 001):
  TASK-ENV-002  Kartograph
  TASK-ENV-003  Gärtner
  TASK-ENV-004  Architekt

Stufe 2 (nach 002+003+004):
  TASK-ENV-005  Monorepo + Validation
```

---

## Validierung: Qualitätskriterien für AGENTS.md

- [ ] Alle Befehle sind copy-paste-ready (keine `<placeholder>`)
- [ ] "Wo laufen Befehle" ist explizit mit Gegenbeispielen
- [ ] MCP-Health-Check dokumentiert
- [ ] Port-Tabelle vollständig
- [ ] Kein AI-Agent hat "wo führe ich den Befehl aus?" gefragt — Smoke-Test

---

## Abhängigkeiten

- Keine Phasen-Abhängigkeit — kann parallel zu Phase 1 gestartet werden
- Voraussetzung für alle Phasen mit Backend-Tasks

## Öffnet

→ Reibungslose AI-Agent-Ausführung in allen Phasen
