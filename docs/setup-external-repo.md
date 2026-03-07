# Hivemind in einem externen Repository einrichten

> Ergänzende Betriebsdoku für projektbezogene Repo-/Intake-Automation:
> `docs/project-repo-automation.md`

Diese Anleitung erklärt, wie der Hivemind-MCP-Server für ein **fremdes Repository** konfiguriert wird,
sodass Analyzer und Filesystem-Tools auf dieses Repo zugreifen können.

## Voraussetzungen

- Hivemind-Repo lokal geklont (z. B. nach `~/projects/hivemind`)
- Podman oder Docker installiert
- Python ≥ 3.11 (nur für das Init-Script auf dem Host, optional)

---

## Schnellstart: `hivemind init`

Das Init-Script generiert alle benötigten Konfigurationsdateien automatisch:

```bash
# Vom hivemind-Root aus:
python scripts/hivemind_init.py --workspace /absolute/path/to/your/repo
```

> Für projektbezogenes Onboarding über die Web-App ist `remote_url` auf Windows praktisch Pflicht,
> wenn der Host-Pfad aus dem Container nicht direkt lesbar ist. `verify` kann den Runtime-Workspace
> dann über das Git-Remote eindeutig dem Projekt zuordnen.
>
> `preview` und `verify` übernehmen außerdem automatisch `remote_url`, `default_branch` und den
> erkannten Stack in den Projekt-Datensatz, sobald das Repo im Container eindeutig zugeordnet werden kann.

Das Script erstellt:

| Datei | Ablageort | Zweck |
|---|---|---|
| `docker-compose.override.yml` | Hivemind-Root | Workspace-Mount in den backend-Container |
| `.vscode/mcp.json` | Ziel-Workspace | Copilot Agent Mode — MCP-Server-Eintrag |
| `.cursor/mcp.json` | Ziel-Workspace | Cursor IDE — MCP-Server-Eintrag |
| `.hivemind/config.yml` | Ziel-Workspace | Workspace-Einstellungen (optional committen) |

### Optionen

```text
--workspace, -w       Absoluter Pfad zum externen Repo (Pflicht)
--container-path      Container-interner Pfad (default: /workspace)
--port, -p            MCP-Server-Port (default: 8000)
--deny-patterns       Kommagetrennte Ignore-Muster (default: .git/objects,.env,...)
--output-dir          Hivemind-Root für docker-compose.override.yml (default: CWD)
--vscode-only         Nur IDE-Konfigdateien, kein docker-compose.override.yml
--dry-run             Vorschau ohne Dateien zu schreiben
```

### Beispiel

```bash
python scripts/hivemind_init.py \
  --workspace /home/user/projects/myapp \
  --port 8000 \
  --deny-patterns ".git/objects,.env,.env.local,node_modules,.venv"
```

---

## Manuelle Einrichtung

Falls das Init-Script nicht verwendet werden soll:

### 1. docker-compose.override.yml anlegen

Im Hivemind-Root eine Datei `docker-compose.override.yml` mit folgendem Inhalt:

```yaml
services:
  backend:
    volumes:
      - /absolute/path/to/your/repo:/workspace:ro
    environment:
      HIVEMIND_WORKSPACE_ROOT: "/workspace"
```

> **Hinweis:** `/workspace` als Container-Pfad ist der Standard. Der Wert von
> `HIVEMIND_WORKSPACE_ROOT` steuert, wo Analyzer und Filesystem-Tools suchen.

### 2. Stack neu starten

```bash
make down && make up
```

### 3. IDE konfigurieren

**VS Code / Copilot** — `.vscode/mcp.json` im Ziel-Repo anlegen:

```json
{
  "servers": {
    "hivemind": {
      "type": "sse",
      "url": "http://localhost:8000/api/mcp/sse"
    }
  }
}
```

**Cursor** — `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "hivemind": {
      "type": "sse",
      "url": "http://localhost:8000/api/mcp/sse"
    }
  }
}
```

**Claude Desktop** (Windows `~/AppData/Roaming/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "hivemind": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:8000/api/mcp/sse"]
    }
  }
}
```

---

## Konfiguration: HIVEMIND_WORKSPACE_ROOT

Der Container-Pfad zum Workspace ist über die Umgebungsvariable `HIVEMIND_WORKSPACE_ROOT` konfigurierbar:

```env
# .env im Hivemind-Root
HIVEMIND_WORKSPACE_ROOT=/workspace
```

Standard: `/workspace`

Der Analyzer (`hivemind-run_analyzer`) verwendet diesen Pfad als Default für `root_path`,
falls kein expliziter Wert übergeben wird.

---

## Konfiguration: Workspace Deny-Patterns

Pfade und Dateimuster, die von Filesystem-Tools ignoriert werden sollen, werden über
`HIVEMIND_FS_DENY_LIST` konfiguriert (kommagetrennte Muster):

```env
# .env im Hivemind-Root
HIVEMIND_FS_DENY_LIST=".git/objects,.env,.env.local,.env.production,.venv,node_modules"
```

Alternativ in `.hivemind/config.yml` des Ziel-Repos:

```yaml
hivemind:
  workspace:
    deny_patterns: ".git/objects,.env,.env.local,.venv,node_modules"
```

> **Hinweis:** `.hivemind/config.yml` wird aktuell als Dokumentation genutzt.
> Die aktive Konfiguration erfolgt per Umgebungsvariable im Hivemind-Stack.

---

## Verification

Nach dem Setup prüfen:

```bash
# Health-Check
curl http://localhost:8000/health

# Discovery-Endpoint — zeigt workspace.root und deny_patterns
curl http://localhost:8000/api/mcp/discovery | python -m json.tool

# Analyzer auf dem externen Repo ausführen
curl -X POST http://localhost:8000/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{"tool": "hivemind-run_analyzer", "arguments": {"analyzer_name": "all"}}'
```

---

## Mehrere Workspaces

Hivemind unterstützt genau einen Workspace gleichzeitig (der in `HIVEMIND_WORKSPACE_ROOT`
konfigurierte Pfad). Um zwischen Repos zu wechseln:

1. `docker-compose.override.yml` anpassen (neuen Host-Pfad eintragen)
2. `make restart-be` (Backend neu starten, kein Rebuild nötig)

---

## Gitignore respektieren

Das Init-Script setzt `deny_patterns` mit Standard-Einträgen. Weitere Muster können
aus der `.gitignore` des Ziel-Repos abgeleitet und in `HIVEMIND_FS_DENY_LIST` eingetragen werden:

```bash
# Muster aus .gitignore extrahieren und in .env eintragen
grep -v '^#' /path/to/your/repo/.gitignore | grep -v '^$' | tr '\n' ',' | sed 's/,$//'
```

---

## Troubleshooting

| Problem | Lösung |
|---|---|
| Analyzer findet keine Dateien | `HIVEMIND_WORKSPACE_ROOT` korrekt gesetzt? Volume-Mount korrekt? |
| `scripts.analyzers` nicht gefunden | Volume-Mount prüfen: `podman compose exec backend ls /workspace/scripts/` |
| Copilot zeigt keine Hivemind-Tools | Backend läuft? `.vscode/mcp.json` korrekt? VS Code neu starten |
| `run_analyzer` gibt leere Ergebnisse zurück | `root_path` explizit übergeben: `{"root_path": "/workspace"}` |
| `fs_read` liefert `access_denied` | Pfad in Deny-List? `HIVEMIND_FS_DENY_LIST` prüfen |
| `fs_write` in Read-Only-Mount | Volume-Mount ohne `:ro`-Flag einbinden |

---

## Workspace-FS Tools — Übersicht

Nach erfolgreicher Einrichtung stehen im Agent-Mode folgende Filesystem-Tools zur Verfügung:

| Tool | Beispiel-Prompt | Beschreibung |
|------|-----------------|--------------|
| `hivemind-fs_read` | "Lies src/main.py" | Datei lesen (optional Zeilenbereich) |
| `hivemind-fs_write` | "Schreib eine README" | Datei erstellen/überschreiben (atomisch) |
| `hivemind-fs_list` | "Zeig mir die Verzeichnisstruktur" | Verzeichnis auflisten |
| `hivemind-fs_search` | "Suche alle TODOs" | Grep/Regex über Workspace |
| `hivemind-fs_stat` | "Wie groß ist config.yaml?" | Datei-Metadaten |
| `hivemind-run_analyzer` | "Mach einen Health-Check" | Repo-Analyse → JSON-Report |

Alle Tools sind auf `HIVEMIND_WORKSPACE_ROOT` eingesperrt (kein Path-Traversal möglich).

**Vollständige technische Dokumentation:** [`docs/features/workspace-fs.md`](features/workspace-fs.md)
