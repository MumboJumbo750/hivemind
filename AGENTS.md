# Hivemind — AI Agent Context

> **Universeller Laufzeit-Kontext für alle AI-Agents.**
> Claude lädt dieses File via `CLAUDE.md`, Cursor via `.cursorrules`, Copilot via `.github/copilot-instructions.md`.
> **Eine Wahrheit — alle AIs.** Änderungen nur hier vornehmen.

---

## Runtime Environment

### Container-Runtime

Dieses Projekt läuft in **Podman Compose** (nicht Docker). Alle Befehle verwenden `podman compose`.

```bash
podman compose up -d                        # Stack starten (ohne Ollama)
podman compose --profile ai up -d           # Stack + Ollama (Phase 3+)
podman compose down                         # Stack stoppen
podman compose ps                           # Service-Status
```

### Service-Topologie

| Compose-Service | Rolle | Host-Port | Technologie |
|-----------------|-------|-----------|-------------|
| `backend` | FastAPI + MCP-Server | **8000** | Python 3.11, uvicorn |
| `postgres` | Datenbank | **5432** | PostgreSQL 16 + pgvector |
| `frontend` | Web-UI | **5173** | Vue 3 + Vite (Hot-Reload) |
| `ollama` | Embeddings | **11434** | Ollama (nur `--profile ai`) |
| `db-backup` | Backup-Cron | — | pg_dump, kein Port |

### Volume-Mounts (Hot-Reload)

```
./backend  → /app        (backend-Container, Hot-Reload aktiv)
./frontend → /app        (frontend-Container, Hot-Reload aktiv)
./seed     → /seed:ro    (alle Container, read-only)
./         → /workspace  (backend-Container, Workspace-Root für Analyzer/Scripts)
```

---

## ⚠️ Kritische Regel: Wo Befehle ausgeführt werden

**Backend-Befehle laufen IMMER im Container — nie auf dem Host.**

Der Host hat kein Python-Virtualenv. `alembic`, `pytest`, `pip` existieren nur im Container.

```bash
# ✅ RICHTIG — im Container ausführen:
podman compose exec backend alembic upgrade head
podman compose exec backend pytest tests/
podman compose exec backend python -m app.cli seed

# ❌ FALSCH — funktioniert nicht auf dem Host:
alembic upgrade head        # kein alembic auf dem Host!
pytest                      # kein Python-Env auf dem Host!
```

---

## Dev-Befehle — Makefile (bevorzugt)

Das Projekt hat ein `Makefile` im Projektroot. Nutze `make`-Targets — sie kapseln Container-Kontext und sind einfacher zu merken.

```bash
make help              # Alle verfügbaren Targets

make up                # Stack starten
make up-ai             # Stack + Ollama (Phase 3+)
make down              # Stack stoppen
make ps                # Service-Status

make test              # Alle Backend-Tests
make test-integration  # Nur Integration-Tests
make test-install      # Test-Deps einmalig im Container installieren

make migrate           # alembic upgrade head
make shell-be          # bash im Backend-Container
make db                # psql-Shell
make logs              # Backend-Logs live

make health            # Repo Health Scan (text)
make health-scan       # Alias für make health
make health-json       # Repo Health Scan → health_report.json
make health-md         # Repo Health Scan → health_report.md
make health-test       # Analyzer-Unit-Tests im Container
```

## ⚠️ Rebuild vs. Restart vs. Nichts

Der häufigste Irrtum: wann brauche ich `rebuild`?

| Änderung | Aktion | Befehl |
| -------- | ------ | ------ |
| Code in `backend/app/` | **Nichts** — Hot-Reload | — |
| Code in `frontend/src/` | **Nichts** — Vite HMR | — |
| `requirements.txt` geändert | **Restart** | `make restart-be` |
| `requirements-dev.txt` geändert | **Test-Install** | `make test-install` |
| `.env` geändert | **Restart** | `make restart-be` |
| `backend/Dockerfile` geändert | **Rebuild** | `make rebuild-be` |
| `frontend/package.json` geändert | **Rebuild** | `make rebuild-fe` |
| Neue System-Deps (`apt-get`) | **Rebuild** | `make rebuild-be` |

**Faustregel:** Rebuild ist selten. `make restart-be` reicht bei Dep-Änderungen (dep-check.sh re-installiert automatisch).

## Dev-Befehle Referenz (direkte podman-Befehle)

### Backend (Python / FastAPI)

```bash
# Venv-Pfad im Container: /app/.venv/bin/
podman compose exec backend /app/.venv/bin/alembic upgrade head
podman compose exec backend /app/.venv/bin/alembic downgrade -1
podman compose exec backend /app/.venv/bin/alembic revision --autogenerate -m "beschreibung"

# Tests (erst make test-install ausführen!)
podman compose exec backend /app/.venv/bin/pytest tests/ -v
podman compose exec backend /app/.venv/bin/pytest tests/integration/ -v
podman compose exec backend /app/.venv/bin/pytest tests/ -k "test_name" -v

# Seed-Daten
podman compose exec backend /app/.venv/bin/python -m app.cli seed
```

### Datenbank

```bash
podman compose exec postgres psql -U hivemind hivemind
podman compose exec postgres pg_dump -U hivemind hivemind
```

### Logs & Diagnose

```bash
podman compose logs -f backend
podman compose logs -f frontend
podman compose restart backend
podman compose restart frontend
```

---

## MCP-Server

Der MCP-Server ist **Teil der FastAPI-App** und läuft im `backend`-Container auf Port 8000.

- **Voraussetzung:** `podman compose up -d backend` muss laufen, bevor MCP-Tools nutzbar sind
- **Health-Check:** `curl http://localhost:8000/health` → `{"status": "ok"}`
- **Claude Code:** Verbindet via HTTP/SSE auf `http://localhost:8000` (Konfiguration in `.claude/settings.json`)

### MCP-Tool Feldnamen (häufige Fehler)

| Falsch | Richtig |
|--------|---------|
| `task_id` | `task_key` |
| `state` | `target_state` |
| `result_text` | `result` |
### MCP-Tool-Aufrufe vom Host (ohne MCP-Client)

**Alle MCP-Tools laufen über EINEN Endpoint:** `POST /api/mcp/call` mit Body `{"tool": "hivemind/TOOLNAME", "arguments": {...}}`.
Es gibt **keine** individuellen REST-Endpoints pro Tool (kein `/api/mcp/submit_result` etc.).

```bash
# ✅ RICHTIG — curl vom Host:
curl -X POST http://localhost:8000/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{"tool": "hivemind/get_task", "arguments": {"task_key": "TASK-88"}}'

# ✅ RICHTIG — mcp_call.py im Container:
podman compose exec backend /app/.venv/bin/python /workspace/scripts/mcp_call.py \
  "hivemind/get_task" '{"task_key": "TASK-88"}'

# ❌ FALSCH — Python auf dem Host (existiert nicht):
python scripts/mcp_call.py "hivemind/get_task" ...    # Kein Python auf dem Host!

# ❌ FALSCH — Individuelle Endpoints (existieren nicht):
curl http://localhost:8000/api/mcp/submit_result       # 404!
```

### PowerShell-Besonderheiten

- Backticks (`` ` ``) in PowerShell Here-Strings (`@"..."@`) werden als **Escape-Sequenzen** interpretiert
- Markdown mit Code-Backticks in JSON-Bodys führt zu Parse-Errors
- **Lösung:** JSON in Datei auslagern und mit `Get-Content payload.json -Raw` einlesen
- Oder: einfache Anführungszeichen für JSON-Strings ohne Variablen-Interpolation

```powershell
# ✅ RICHTIG — Einfache Anführungszeichen:
Invoke-WebRequest -Uri "http://localhost:8000/api/mcp/call" `
  -Method POST -ContentType "application/json" `
  -Body '{"tool": "hivemind/get_task", "arguments": {"task_key": "TASK-88"}}'

# ✅ RICHTIG — JSON aus Datei:
$body = Get-Content payload.json -Raw
Invoke-WebRequest -Uri "http://localhost:8000/api/mcp/call" `
  -Method POST -ContentType "application/json" -Body $body
```
---

## Projektstruktur

```
hivemind/
  AGENTS.md              ← Dieses File (universeller AI-Kontext)
  CLAUDE.md              ← Claude-spezifisch (@see AGENTS.md)
  docker-compose.yml     ← Podman Compose Stack
  backend/               ← FastAPI-App → läuft in `backend`-Container
    app/
      routers/           ← FastAPI Router (HTTP-Endpoints)
      services/          ← Business Logic (scheduler.py, outbox_consumer.py, ...)
      models/            ← SQLAlchemy Models
      mcp/               ← MCP-Server + Tools
    alembic/versions/    ← Datenbank-Migrationen (Nummerierung: 001_..., 010_...)
    tests/               ← pytest Tests (unit/ + integration/)
  frontend/              ← Vue 3 + Vite → läuft in `frontend`-Container
    src/
      components/        ← Vue-Komponenten
      composables/       ← Vue Composables (use*.ts)
      views/             ← Router-Views
  seed/                  ← Seed-Daten (gemounted als /seed:ro)
    skills/              ← Skill-Definitionen (Markdown mit Frontmatter)
    tasks/               ← Task-Definitionen (JSON, nach Phase sortiert)
    epics/               ← Epic-Definitionen (JSON)
```

---

## Umgebungsvariablen

Alle Variablen haben Defaults in `docker-compose.yml`. Overrides via `.env` im Projektroot.

| Variable | Default | Beschreibung |
|----------|---------|-------------|
| `POSTGRES_USER` | `hivemind` | DB-User |
| `POSTGRES_PASSWORD` | `hivemind` | DB-Passwort |
| `HIVEMIND_MODE` | `solo` | `solo` \| `team` |
| `HIVEMIND_ROUTING_THRESHOLD` | `0.85` | pgvector Auto-Routing Schwellwert |
| `HIVEMIND_DLQ_MAX_ATTEMPTS` | `5` | Max Retry vor DLQ |
| `HIVEMIND_OLLAMA_URL` | `http://ollama:11434` | Ollama-Endpoint (Phase 3+) |
| `HIVEMIND_EMBEDDING_MODEL` | `nomic-embed-text` | Embedding-Modell |
| `AUDIT_RETENTION_DAYS` | `90` | Payload-Nullification nach N Tagen |

---

## IDE MCP-Integration

Hivemind läuft als MCP-Server — jede IDE die MCP unterstützt bekommt alle `hivemind/*`-Tools.

### VS Code / Copilot Agent Mode

**Automatisch:** `.vscode/mcp.json` ist im Repo eingecheckt. Copilot Agent Mode erkennt den Server beim Öffnen des Projekts.

```json
// .vscode/mcp.json (bereits vorhanden, kein Setup nötig)
{
  "servers": {
    "hivemind": {
      "type": "sse",
      "url": "http://localhost:8000/api/mcp/sse"
    }
  }
}
```

**Voraussetzung:** Backend muss laufen (`make up`), dann in Copilot Chat → Agent Mode aktivieren.

### Copilot CLI (`gh copilot`)

```json
// ~/.copilot/mcp-config.json
{
  "mcpServers": {
    "hivemind": {
      "type": "sse",
      "url": "http://localhost:8000/api/mcp/sse",
      "tools": ["*"]
    }
  }
}
```

Registrierung: `gh copilot mcp add hivemind --type sse --url http://localhost:8000/api/mcp/sse`

### Claude Desktop

```json
// ~/AppData/Roaming/Claude/claude_desktop_config.json  (Windows)
// ~/Library/Application Support/Claude/claude_desktop_config.json  (macOS)
{
  "mcpServers": {
    "hivemind": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:8000/api/mcp/sse"]
    }
  }
}
```

### Cursor

```json
// .cursor/mcp.json
{
  "mcpServers": {
    "hivemind": {
      "type": "sse",
      "url": "http://localhost:8000/api/mcp/sse"
    }
  }
}
```

### Discovery-Endpoint

`GET /api/mcp/discovery` — liefert Config-Snippets für alle IDE-Clients als JSON.
Nützlich für automatische Einrichtungsskripte.

---

## Codebase-Konventionen (für AI-Agents)

### APScheduler
Jobs **immer** in `backend/app/services/scheduler.py` → `start_scheduler()` registrieren — **nie** in `main.py`.

### SyncOutbox State-Machine
```
state-Werte: NUR 'pending' und 'dead_letter'
— KEIN 'delivered', 'failed', 'dead'!

Erfolg outbound = db.delete(entry)        ← Eintrag LÖSCHEN
DLQ-Promotion  = entry.state = 'dead_letter'
Inbound-Erfolg = routing_state = 'routed' ← Eintrag BLEIBT (Audit-Record)
```

### FK-Referenzen
```
node_bug_reports.node_id → code_nodes.id  (NICHT nodes.id!)
```

### Workspace-FS Tools

Die MCP-Filesystem-Tools (`hivemind/fs_read`, `fs_write`, `fs_list`, `fs_search`, `fs_stat`) laufen im `backend`-Container und greifen via Volume-Mount auf den Workspace zu.

**Implementierung:** `backend/app/mcp/tools/fs_tools.py`
**Vollständige Doku:** `docs/features/workspace-fs.md`
**Externe Repos:** `docs/setup-external-repo.md`

```
HIVEMIND_WORKSPACE_ROOT   = /workspace  (Container-Pfad, default)
HIVEMIND_FS_DENY_LIST     = .git/objects,.env,...  (fnmatch, kommasepariert)
HIVEMIND_FS_RATE_LIMIT    = 120  (Aufrufe/Minute pro Tool)
```

Sicherheitsregeln (müssen bei Changes respektiert werden):
- **Path-Sandboxing**: Alle Pfade werden auf `HIVEMIND_WORKSPACE_ROOT` eingesperrt (`Path.resolve()` + `relative_to()`)
- **Deny-List**: Wird in **allen** Tools geprüft — kein Tool darf Deny-List-Einträge überspringen
- **Symlink-Traversal**: `fs_list` und `fs_search` lösen Symlinks auf und prüfen, ob das Ziel noch im Root liegt
- **Atomisches Schreiben**: `fs_write` nutzt `tempfile` + `os.replace()` — kein partial-write
