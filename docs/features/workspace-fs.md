# Workspace-FS — MCP Filesystem Tools

> **Implementiert in:** `backend/app/mcp/tools/fs_tools.py`
> **Task-Serie:** TASK-WFS-001 bis TASK-WFS-006
> **API-Endpoint:** `POST /api/mcp/call` mit `{"tool": "hivemind-fs_*", ...}`

---

## Überblick

Die Workspace-FS-Tools ermöglichen KI-Agents (Copilot, Claude, Cursor) direkten, gesicherten Zugriff auf das Dateisystem eines externen Repositories. Der MCP-Server läuft im `backend`-Container und greift via Volume-Mount auf das Ziel-Repository zu.

```
AI-Agent (IDE)
    │
    │  POST /api/mcp/call
    │  {"tool": "hivemind-fs_read", "arguments": {"path": "src/main.py"}}
    ▼
┌─────────────────────────────────────────────────────────┐
│  FastAPI / MCP-Router  (backend-Container :8000)        │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │  fs_tools.py — Sicherheitsschicht                │  │
│  │                                                  │  │
│  │  1. _sandbox(path)  ← Path-Traversal-Schutz     │  │
│  │  2. _is_denied(rel) ← Deny-List-Check           │  │
│  │  3. _check_rate_limit() ← Rate-Limiter          │  │
│  │  4. Handler (fs_read / fs_write / ...)           │  │
│  └────────────────────┬─────────────────────────────┘  │
│                       │                                 │
│           HIVEMIND_WORKSPACE_ROOT = /workspace          │
└───────────────────────┼─────────────────────────────────┘
                        │  Volume-Mount
                        │  ./your-repo → /workspace
                        ▼
              ┌──────────────────┐
              │  Host-Filesystem │
              │  /your-repo/     │
              │    src/          │
              │    tests/        │
              │    ...           │
              └──────────────────┘
```

---

## Verfügbare Tools

| Tool | Beschreibung | Pflichtfelder |
|------|--------------|---------------|
| `hivemind-fs_read` | Datei lesen (optionaler Zeilenbereich) | `path` |
| `hivemind-fs_write` | Datei schreiben/erstellen (atomisch) | `path`, `content` |
| `hivemind-fs_list` | Verzeichnis auflisten (rekursiv optional) | — |
| `hivemind-fs_search` | Grep/Regex-Suche über Workspace | `pattern` |
| `hivemind-fs_stat` | Metadaten abfragen (Größe, mtime, Typ) | `path` |
| `hivemind-run_analyzer` | Repo Health Scan → JSON-Report | — |

---

## Sicherheitsarchitektur

### 1. Path-Sandboxing

Alle Pfade werden auf den `HIVEMIND_WORKSPACE_ROOT` eingesperrt. Relative Pfade werden von dort aufgelöst, absolute Pfade müssen innerhalb des Roots liegen. Symlinks werden vollständig aufgelöst (`Path.resolve()`) und danach validiert — dadurch werden auch mehrstufige Symlink-Chains geblockt.

```
Eingabe: "../../etc/passwd"
→ resolve() → /etc/passwd
→ relative_to(/workspace) → ValueError → access_denied
```

### 2. Deny-List

Konfigurierbar via `HIVEMIND_FS_DENY_LIST` (Komma-separierte fnmatch-Patterns):

```bash
HIVEMIND_FS_DENY_LIST=".git/objects,.env,.env.local,.env.*,*.pem,*.key,secrets/*"
```

Die Deny-List wird in **allen** Tools angewendet (`fs_read`, `fs_write`, `fs_list`, `fs_stat`, `fs_search`).

### 3. Rate-Limiting

In-Memory Rate-Limiter pro Tool und Sliding Window (60 Sekunden). Konfigurierbar via `HIVEMIND_FS_RATE_LIMIT` (Aufrufe/Minute).

### 4. Atomisches Schreiben (fs_write)

`fs_write` nutzt `tempfile.NamedTemporaryFile` + `os.replace()` — kein partial-write sichtbar:

```
write → tmp_XXX.tmp (same directory) → os.replace(tmp, target)
```

### 5. Symlink-Traversal-Schutz

`fs_list` und `fs_search` lösen jede Datei via `resolve()` auf und prüfen die relative Position zum Workspace-Root. Symlinks, die auf externe Pfade zeigen, werden still übersprungen.

---

## Konfigurationsreferenz

| Variable | Default | Beschreibung |
|----------|---------|--------------|
| `HIVEMIND_WORKSPACE_ROOT` | `/workspace` | Sandbox-Root im Container |
| `HIVEMIND_FS_DENY_LIST` | `.git/objects,.env,...` | Komma-sep. Deny-Patterns (fnmatch) |
| `HIVEMIND_FS_RATE_LIMIT` | `120` | Max. Aufrufe/Minute pro Tool |

---

## Nutzung — Beispielaufrufe

### fs_read

```bash
curl -X POST http://localhost:8000/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{"tool": "hivemind-fs_read", "arguments": {"path": "src/main.py", "start_line": 1, "end_line": 30}}'
```

Response:
```json
{
  "result": [{
    "type": "text",
    "text": "{\"data\": {\"path\": \"src/main.py\", \"content\": \"...\", \"total_lines\": 120, \"encoding\": \"utf-8\"}}"
  }]
}
```

### fs_write

```bash
curl -X POST http://localhost:8000/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{"tool": "hivemind-fs_write", "arguments": {"path": "docs/notes.md", "content": "# Notes\n"}}'
```

### fs_search

```bash
curl -X POST http://localhost:8000/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{"tool": "hivemind-fs_search", "arguments": {"pattern": "TODO", "glob": "**/*.py", "context_lines": 2}}'
```

### run_analyzer

```bash
curl -X POST http://localhost:8000/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{"tool": "hivemind-run_analyzer", "arguments": {"min_severity": "warning"}}'
```

---

## Fehlerformat

Alle Tools verwenden ein einheitliches Fehlerformat:

```json
{
  "error": {
    "code": "access_denied",
    "message": "Path '../../etc/passwd' escapes workspace root '/workspace'. Access denied."
  }
}
```

| Code | Bedeutung |
|------|-----------|
| `access_denied` | Path-Traversal oder Deny-List verletzt |
| `not_found` | Datei/Verzeichnis existiert nicht |
| `not_a_file` | Pfad ist ein Verzeichnis, Datei erwartet |
| `not_a_directory` | Pfad ist eine Datei, Verzeichnis erwartet |
| `read_error` | OS-Lesefehler |
| `write_error` | OS-Schreibfehler |
| `rate_limit_exceeded` | Rate-Limit überschritten |
| `invalid_pattern` | Ungültiges Regex-Pattern in fs_search |

---

## Teststrategie

| Schicht | Datei | Abdeckung |
|---------|-------|-----------|
| Unit | `tests/test_fs_tools.py` | Handler direkt, gemockter Workspace-Root |
| Integration | `tests/integration/test_fs_tools_integration.py` | HTTP-Stack (ASGI), realer Dateisystem-I/O |

Die Integration-Tests rufen `POST /api/mcp/call` über den ASGI-Test-Client auf und verifizieren, dass Dateien physisch erstellt werden (Test auf "Host-sichtbare" Änderungen im Volume-Mount-Szenario).

---

## Verwandte Dokumentation

- [External-Repo-Setup-Guide](../setup-external-repo.md)
- [run_analyzer / Health Scanner](../../scripts/analyzers/README.md)
- [AGENTS.md — Workspace-FS Abschnitt](../../AGENTS.md#workspace-fs-tools)
