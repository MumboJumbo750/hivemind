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
