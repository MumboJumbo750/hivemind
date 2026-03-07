---
title: "Runtime Environment — AGENTS.md Pattern"
service_scope: ["*"]
stack: ["devops", "documentation"]
skill_type: "runtime"
confidence: 0.9
source_epics: ["EPIC-ENV-BOOTSTRAP"]
guards: []
---

## Skill: Runtime Environment — AGENTS.md Pattern

### Rolle

Du erstellst oder aktualisierst `AGENTS.md` — das universelle AI-Kontext-File für ein Projekt.
Dieses File ist AI-agnostisch und wird von allen AI-Agents als Wahrheitsquelle verwendet.

### Warum AGENTS.md?

AI-Agents scheitern häufig nicht an Code-Logik, sondern an fehlendem Laufzeit-Kontext:
- "Wo führe ich `alembic upgrade head` aus?" (Host vs. Container)
- "Wie ist der MCP-Server erreichbar?"
- "Was heißen die Container?"

`AGENTS.md` löst das **einmalig für alle AI-Systeme** — Claude, Cursor, Copilot, GPT-basierte Tools.

### Datei-Hierarchie (auch für Monorepos)

```
projekt-root/
  AGENTS.md              ← globaler Kontext (immer vorhanden)
  CLAUDE.md              ← @see AGENTS.md + Claude-spezifisch
  .cursorrules           ← @see AGENTS.md + Cursor-spezifisch
  .github/
    copilot-instructions.md  ← @see AGENTS.md + Copilot-spezifisch
  packages/              ← Monorepo: pro Package ein AGENTS.md
    backend/
      AGENTS.md          ← backend-spezifischer Kontext (überschreibt/erweitert root)
    frontend/
      AGENTS.md          ← frontend-spezifischer Kontext
```

**Monorepo-Regel:** Claude Code lädt hierarchisch — Root + nächstes Verzeichnis. Das gleiche gilt für AGENTS.md.

### AGENTS.md Mindest-Inhalt

Für jedes Projekt müssen diese Abschnitte vorhanden sein:

```markdown
# {Projektname} — AI Agent Context

## Runtime Environment
### Container-Runtime
[Welches Tool: docker/podman/docker-compose/k8s]
[Start/Stop Befehle]

### Service-Topologie
[Tabelle: Service | Rolle | Host-Port | Technologie]

## ⚠️ Wo Befehle ausgeführt werden
[Was auf Host, was im Container — mit Beispielen]

## Dev-Befehle Referenz
[Alle häufigen Befehle — copy-paste-ready]

## MCP-Server (falls vorhanden)
[Wie erreichbar, Voraussetzungen]

## Projektstruktur
[Verzeichnisbaum mit Kommentaren]

## Umgebungsvariablen
[Tabelle: Variable | Default | Beschreibung]

## Codebase-Konventionen
[Projektspezifische Regeln die AI-Agents kennen müssen]
```

### Kartograph-Aufgabe: Environment Discovery

Der Kartograph soll beim Erkunden einer Codebase automatisch `AGENTS.md` erzeugen/aktualisieren:

```
1. docker-compose.yml / podman-compose.yml gefunden?
   → Services extrahieren (Namen, Ports, Images)
   → Volume-Mounts analysieren (was ist wo gemountet?)
   → "Wo laufen Befehle?" ableiten

2. Makefile / package.json scripts / Taskfile gefunden?
   → Dev-Befehle extrahieren und dokumentieren

3. .env.example gefunden?
   → Umgebungsvariablen dokumentieren

4. alembic.ini / prisma/schema.prisma / etc. gefunden?
   → Migration-Commands dokumentieren

5. AGENTS.md erstellen/aktualisieren
```

### Gärtner-Aufgabe: Staleness-Detection

Der Gärtner soll Runtime-Skills aktuell halten:

```
Trigger: docker-compose.yml wurde geändert
  → Prüfe: Sind Service-Namen in AGENTS.md + podman-exec.md noch korrekt?
  → Schlage Skill-Update vor

Trigger: Neuer Service hinzugefügt
  → Ergänze Service-Topologie-Tabelle in AGENTS.md
  → Erstelle/erweitere Runtime-Skill

Trigger: Port-Mapping geändert
  → Aktualisiere Port-Tabelle in AGENTS.md

Trigger: Manueller Agent-Run / Prompt Station Workflow geändert
  → Aktualisiere `AGENTS.md`, Runtime-Skills und Prompt-Doku gemeinsam
  → Dokumentiere explizit: ausgewählter Agent, serverseitig generierter Prompt, Container-/Workspace-Kontext
```

### AI-spezifische Config-Files (Thin Wrapper)

Diese Files sollen **dünn** bleiben — nur Referenz auf AGENTS.md + AI-spezifische Felder:

**CLAUDE.md:**
```markdown
# {Projekt} — Claude Code Context
> Vollständiger Laufzeit-Kontext: → [AGENTS.md](AGENTS.md)
> Hier nur Claude-spezifische Ergänzungen.

## [Claude-spezifische Regeln]
```

**.cursorrules:**
```markdown
# {Projekt} — Cursor Context
Vollständiger Laufzeit-Kontext: siehe AGENTS.md im Projektroot.

[Cursor-spezifische Regeln]
```

### Qualitätskriterien für AGENTS.md

- [ ] Alle Befehle sind **copy-paste-ready** (vollständige Befehle, keine Platzhalter)
- [ ] "Wo läuft was" ist **explizit** dokumentiert (nicht implizit aus Struktur ableitbar)
- [ ] MCP-Verbindung erklärt (falls vorhanden)
- [ ] Port-Tabelle vollständig
- [ ] Mindestens eine "häufige Fehler"-Sektion

### Wichtig

- `AGENTS.md` gehört ins Repository (kein `.gitignore`)
- Wird vor JEDEM AI-Task gelesen — kurz und präzise halten
- Redundanz zu `README.md` ist gewollt — AGENTS.md ist für AI optimiert, README für Menschen
