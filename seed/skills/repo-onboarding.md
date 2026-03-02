---
title: "Repo Onboarding — Initiale Analyse & Setup"
service_scope: ["*"]
stack: ["devops", "documentation"]
skill_type: "system"
confidence: 0.9
source_epics: ["EPIC-ENV-BOOTSTRAP"]
guards: []
---

## Skill: Repo Onboarding — Initiale Analyse & Setup

### Wann verwenden

Pinne diesen Skill wenn:

- **Kartograph:** Erstes Erkunden einer unbekannten Codebase (`AGENTS.md` fehlt)
- **Architekt:** Kein `AGENTS.md` vorhanden vor dem ersten Epic-Decompose
- **Worker:** Aufgabe lautet explizit "Projekt aufsetzen" oder "Umgebung dokumentieren"

Worker die Features implementieren brauchen diesen Skill **nicht** — sie lesen `AGENTS.md` direkt.

---

### Phase 1: Orientierung — Was ist das für ein Projekt?

Beantworte diese Fragen zuerst, bevor du irgendetwas erstellst:

```
1. Welche Sprache(n)?      → requirements.txt / package.json / go.mod / Cargo.toml
2. Welches Framework?      → FastAPI / Express / Gin / Axum / Spring
3. Wie wird es gestartet?  → docker-compose.yml / Makefile / package.json scripts
4. Welche Container-Runtime? → docker oder podman?
5. Gibt es Tests?          → pytest.ini / vitest.config / jest.config / *_test.go
6. Gibt es CI?             → .github/workflows / .gitlab-ci.yml / Jenkinsfile
7. Ist es ein Monorepo?    → packages/ / apps/ / services/ Verzeichnisse
```

### Phase 2: Stack-Detection

#### Container-Runtime erkennen

```bash
# Podman vorhanden?
which podman && podman --version   # → "podman compose" verwenden

# Nur Docker?
which docker && docker --version   # → "docker compose" verwenden

# Beide? → Kommentar in AGENTS.md, empfehle Podman
```

Signale in der Codebase:
- CI-Pipeline nutzt `podman` → Podman
- `podman-compose.yml` existiert → Podman
- `.devcontainer/` → Container-Kontext im Editor (Dev Containers)
- Kein Container → direkt auf Host, Venv oder System-Python

#### Sprach-spezifische Patterns

| Signal | Stack | Typische Befehle |
| ------ | ----- | ---------------- |
| `requirements.txt` + `Dockerfile` | Python/FastAPI | `pip install`, `uvicorn`, `alembic` |
| `pyproject.toml` mit `[tool.poetry]` | Python/Poetry | `poetry install`, `poetry run pytest` |
| `package.json` + `Dockerfile` | Node.js | `npm install`, `npm run dev`, `npm test` |
| `pnpm-lock.yaml` | Node.js/pnpm | `pnpm install`, `pnpm run dev` |
| `go.mod` | Go | `go build`, `go test ./...` |
| `Cargo.toml` | Rust | `cargo build`, `cargo test` |
| `pom.xml` | Java/Maven | `mvn package`, `mvn test` |

#### Monorepo-Detection

```
packages/     → npm/pnpm Workspaces oder Nx
apps/         → Turborepo
services/     → Microservices (je eigenes docker-compose?)
libs/         → Shared Libraries
```

Bei Monorepos: eine `AGENTS.md` pro Package/App das von AI-Agents bearbeitet wird.

#### Venv/Runtime-Pfad

| Setup | Venv-Pfad | Befehl-Präfix |
| ----- | --------- | ------------- |
| Python + Docker (Hivemind-Muster) | `/app/.venv/bin/` | `podman compose exec backend /app/.venv/bin/pytest` |
| Python + lokales Venv | `.venv/bin/` | `.venv/bin/pytest` oder `source .venv/bin/activate` |
| Python + Poetry | `.venv/bin/` | `poetry run pytest` |
| Node.js | `node_modules/.bin/` | `npm run test` oder `npx vitest` |

---

### Phase 3: Setup-Reihenfolge

Immer in dieser Reihenfolge — **nicht überspringen**:

```
1. AGENTS.md erstellen (root)
   → Service-Topologie, Ports, Venv-Pfad, "Wo laufen Befehle"

2. CLAUDE.md erstellen (root)
   → @see AGENTS.md + Claude-spezifisch (Sprache, Memory-Pfad)

3. Makefile erstellen / prüfen
   → make up / make test / make migrate / make rebuild-*
   → Falls Makefile fehlt: anlegen mit den häufigsten Befehlen

4. Runtime-Skill erstellen (seed/skills/{runtime-name}.md)
   → skill_type: "runtime"
   → Vollständige Container-Befehls-Referenz

5. Test-Dependencies prüfen
   → Sind Test-Tools im Container verfügbar?
   → Falls nicht: requirements-dev.txt / package.json devDependencies + make test-install

6. AGENTS.md Completeness-Check (→ Phase 4)
```

---

### Phase 4: Completeness-Check

Bevor du fertig bist — beantworte jede Frage mit ✓ oder ✗:

```
AGENTS.md Vollständigkeit:
  ✓/✗  Service-Topologie-Tabelle vollständig (alle Services aus docker-compose.yml)?
  ✓/✗  "Wo laufen Befehle" Sektion mit Gegenbeispielen?
  ✓/✗  Venv-Pfad explizit dokumentiert (z.B. /app/.venv/bin/)?
  ✓/✗  Alle Befehle copy-paste-ready (kein <placeholder>)?
  ✓/✗  Rebuild vs. Restart Entscheidungstabelle?
  ✓/✗  MCP-Verbindung dokumentiert (falls vorhanden)?

Makefile:
  ✓/✗  make up / make down vorhanden?
  ✓/✗  make test vorhanden (läuft im Container)?
  ✓/✗  make migrate oder Äquivalent vorhanden?
  ✓/✗  make rebuild-* vorhanden?
  ✓/✗  make help vorhanden?

Test-Infrastructure:
  ✓/✗  Test-Command läuft im Container ohne manuelle Vorbereitung?
  ✓/✗  Test-Dependencies dokumentiert?

Smoke-Test:
  ✓/✗  make up startet den Stack ohne Fehler?
  ✓/✗  make test läuft durch (mindestens 0 Fehler, 0 Errors)?
```

Alle ✓ → Onboarding abgeschlossen. Jedes ✗ → Aufgabe ergänzen.

---

### Phase 5: Ergebnis dokumentieren

Nach erfolgreichem Onboarding als Task-Result (submit_result):

```markdown
## Repo Onboarding abgeschlossen

**Stack:** {Sprache} / {Framework} / {Container-Runtime}
**Monorepo:** ja/nein

**Erstellt:**
- AGENTS.md (root)
- CLAUDE.md (root)
- seed/skills/{runtime-name}.md
- Makefile (ergänzt/erstellt)

**Completeness-Check:** alle ✓

**Offene Punkte für Folge-Tasks:**
- {Liste was noch fehlt}
```

---

### Wichtig

- Niemals AGENTS.md erstellen ohne die Befehle vorher zu verifizieren — falsche Befehle sind schlimmer als keine
- Bei Unsicherheit über Container-Runtime: `podman compose` versuchen, bei Fehler auf `docker compose` fallen
- Für Monorepos: Root-AGENTS.md zuerst, dann Package-AGENTS.md bei Bedarf
- Das Makefile ist ausführbare Dokumentation — es muss auch für Menschen (nicht nur AI) lesbar sein
