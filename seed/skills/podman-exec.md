---
title: "Podman Exec — Hivemind Container-Befehle"
service_scope: ["backend", "database", "devops"]
stack: ["podman", "docker-compose"]
skill_type: "runtime"
confidence: 0.95
source_epics: ["EPIC-ENV-BOOTSTRAP"]
guards: []
---

## Skill: Podman Exec — Hivemind Container-Befehle

### Rolle

Du führst Befehle im Hivemind-Stack aus. Der Stack läuft in **Podman Compose**.
**Backend-Befehle laufen IMMER im Container** — der Host hat kein Python-Virtualenv.

> Vollständiger Laufzeit-Kontext → [AGENTS.md](../../AGENTS.md)

### Makefile (bevorzugt)

Das Projekt hat ein `Makefile` das Container-Kontext kapselt. `make`-Targets bevorzugen:

```bash
make up                # Stack starten
make test              # Alle Tests (installiert Test-Deps automatisch)
make test-integration  # Nur Integration-Tests
make migrate           # alembic upgrade head
make shell-be          # bash im Backend-Container
make logs              # Backend-Logs live
make rebuild-be        # Backend-Image neu bauen (nur bei Dockerfile-Änderungen!)
make help              # Alle Targets anzeigen
```

### Container-Services

| Service | Verwendung |
| ------- | ---------- |
| `backend` | FastAPI, alembic, pytest, python |
| `postgres` | psql, pg_dump |
| `frontend` | (Hot-Reload via Volume, kein exec nötig) |
| `ollama` | Embeddings (Phase 3+, `--profile ai`) |

### Rebuild vs. Restart vs. Nichts

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

**Warum reicht Restart für `requirements.txt`?** Das Image enthält `dep-check.sh` als Entrypoint — es vergleicht den MD5-Hash und führt automatisch `pip install` aus, wenn sich die Datei geändert hat.

### Stack-Verwaltung (direkt)

```bash
podman compose up -d                      # ohne Ollama
podman compose --profile ai up -d         # mit Ollama (Phase 3+)
podman compose down
podman compose ps
podman compose logs -f backend
podman compose restart backend
```

### Datenbank-Migrationen (Venv-Pfad beachten!)

```bash
# Venv-Pfad im Container: /app/.venv/bin/
podman compose exec backend /app/.venv/bin/alembic upgrade head
podman compose exec backend /app/.venv/bin/alembic downgrade -1

# Roundtrip-Test
podman compose exec backend /app/.venv/bin/alembic downgrade -1 && \
  podman compose exec backend /app/.venv/bin/alembic upgrade head

# Neue Migration generieren
podman compose exec backend /app/.venv/bin/alembic revision --autogenerate -m "beschreibung"
```

### Tests ausführen

```bash
# Test-Deps zuerst installieren (einmalig, oder nach requirements-dev.txt Änderung):
podman compose exec backend /app/.venv/bin/pip install -q -r /app/requirements-dev.txt

# Tests
podman compose exec backend /app/.venv/bin/pytest tests/ -v
podman compose exec backend /app/.venv/bin/pytest tests/unit/ -v
podman compose exec backend /app/.venv/bin/pytest tests/integration/ -v
podman compose exec backend /app/.venv/bin/pytest tests/ -k "test_outbox" -v
podman compose exec backend /app/.venv/bin/pytest --tb=short -q
```

### Seed-Daten importieren

```bash
podman compose exec backend /app/.venv/bin/python -m app.cli seed
```

### Datenbank direkt (psql)

```bash
podman compose exec postgres psql -U hivemind hivemind
# Im psql: \dt (Tabellen), \d tablename (Schema), \q (beenden)
```

### MCP-Tools vom Host aufrufen (ohne MCP-Client)

Wenn kein MCP-Client (VS Code, Cursor, Claude Desktop) verfügbar ist, können MCP-Tools über den **Convenience-REST-Endpoint** aufgerufen werden:

```bash
# ✅ RICHTIG — Alle MCP-Tools über EINEN Endpoint:
curl -X POST http://localhost:8000/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{"tool": "hivemind/submit_result", "arguments": {"task_key": "TASK-88", "result": "..."}}'

# ✅ Alternativ via mcp_call.py Helper (im Container!):
podman compose exec backend /app/.venv/bin/python /workspace/scripts/mcp_call.py \
  "hivemind/get_task" '{"task_key": "TASK-88"}'
```

```bash
# ❌ FALSCH — Diese Endpoints existieren NICHT:
curl http://localhost:8000/api/mcp/submit_result      # 404!
curl http://localhost:8000/api/mcp/update_task_state   # 404!

# ❌ FALSCH — Python existiert NICHT auf dem Windows-Host:
python scripts/mcp_call.py "hivemind/get_task" ...     # scheitert!
```

**Merke:**
- Es gibt **keine** individuellen REST-Endpoints pro MCP-Tool
- **Alle** Tools laufen über `POST /api/mcp/call` mit Body `{"tool": "hivemind/TOOLNAME", "arguments": {...}}`
- Python-Scripts müssen via `podman compose exec backend` ausgeführt werden — der Host hat kein Python
- Alternativ: `curl` / `Invoke-WebRequest` direkt vom Host — kein Python nötig

### PowerShell-Besonderheiten

```powershell
# ✅ RICHTIG — JSON in einfachen Anführungszeichen, keine Backticks:
Invoke-WebRequest -Uri "http://localhost:8000/api/mcp/call" `
  -Method POST -ContentType "application/json" `
  -Body '{"tool": "hivemind/submit_result", "arguments": {"task_key": "TASK-88", "result": "Ergebnis ohne Backticks"}}'

# ❌ FALSCH — Backticks (`) in Strings werden als Escape-Zeichen interpretiert:
$body = @"
{"result": "Code mit `backticks` bricht PowerShell"}
"@
# → Parse-Error! ` wird als Unicode-Escape interpretiert
```

**Regeln für PowerShell:**
- Backticks (`` ` ``) in Here-Strings (`@"..."@`) werden als Escape-Sequenzen interpretiert
- Markdown-Ergebnisse mit Code-Backticks müssen escaped oder vermieden werden
- Sicherer: JSON aus Datei lesen statt inline: `$body = Get-Content payload.json -Raw`
- Alternativ: Backticks durch `'` (Apostroph) oder `(Backtick)` ersetzen

### Häufige Fehler

| Fehler | Ursache | Fix |
| ------ | ------- | --- |
| `command not found: alembic` | Befehl auf dem Host | `make migrate` oder vollständiger Venv-Pfad |
| `command not found: pytest` | Test-Deps nicht installiert | `make test-install` |
| `python: not found` / MS Store Stub | Python nicht auf Host-PATH | `podman compose exec backend /app/.venv/bin/python` |
| `404 Not Found` bei MCP-Tool | Falscher Endpoint | `POST /api/mcp/call` mit `{"tool": "..."}` |
| `connection refused` (MCP) | Backend läuft nicht | `make up` |
| `Can't locate revision` | Migrations-Konflikt | `podman compose exec backend /app/.venv/bin/alembic heads` |
| Port 8000 belegt | Anderer Prozess | `podman compose ps` + `make down` |
| PowerShell Parse-Error in JSON | Backticks in Strings | JSON in Datei auslagern oder einfache Anführungszeichen nutzen |

### Wichtig

- Venv-Pfad im Container: `/app/.venv/bin/` — immer vollständigen Pfad verwenden
- `./backend` ist als Volume gemountet → Code-Änderungen live (Hot-Reload), kein Neustart nötig
- `./seed` ist als `/seed:ro` gemountet → read-only
- Test-Deps (`pytest`, `testcontainers`, `respx`) sind in `requirements-dev.txt`, **nicht** im Production-Image
