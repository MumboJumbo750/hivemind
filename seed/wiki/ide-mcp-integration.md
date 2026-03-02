---
slug: ide-mcp-integration
title: "IDE MCP-Integration — Hivemind in der IDE einrichten"
tags: [mcp, ide, vscode, copilot, cursor, claude-desktop, phase-ide]
linked_epics: [EPIC-IDE-AUTOMATION]
---

# IDE MCP-Integration — Hivemind in der IDE einrichten

Hivemind läuft als MCP-Server (Model Context Protocol). Jede IDE die MCP unterstützt bekommt automatisch alle `hivemind/*`-Tools — keine manuelle Konfiguration der Tool-Definitionen nötig.

**Voraussetzung:** Backend läuft (`make up` → `http://localhost:8000` erreichbar).

## VS Code / Copilot Agent Mode

`.vscode/mcp.json` ist im Repo eingecheckt — **kein Setup nötig**. Copilot Agent Mode erkennt Hivemind automatisch beim Öffnen des Projekts.

Sichtbar unter: Copilot Chat → Agent Mode → MCP-Tools-Symbol.

## Copilot CLI (`gh copilot`)

```bash
gh copilot mcp add hivemind --type sse --url http://localhost:8000/api/mcp/sse
```

Im interaktiven Copilot-CLI-Chat entspricht das dem Slash-Command:

```text
/mcp add hivemind --type sse --url http://localhost:8000/api/mcp/sse
```

Oder manuell in `~/.copilot/mcp-config.json`:

```json
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

## Claude Desktop

**Windows:** `~/AppData/Roaming/Claude/claude_desktop_config.json`
**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

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

Hinweis: `mcp-remote` ist ein Node-Proxy der SSE-Server für Claude Desktop zugänglich macht.

## Cursor

`.cursor/mcp.json` im Projektroot:

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

## Discovery-Endpoint

`GET /api/mcp/discovery` liefert Config-Snippets für alle unterstützten Clients als JSON — nützlich für automatische Setup-Skripte.

```bash
curl http://localhost:8000/api/mcp/discovery
```

## Verfügbare Tools

Nach der Verbindung sind alle `hivemind/*`-Tools verfügbar:

- **Read:** `get_task`, `get_epic`, `get_skills`, `get_wiki_article`, `search_wiki`, `get_prompt`
- **Write (Worker):** `submit_result`, `update_task_state`
- **Write (Planer):** `propose_epic`, `decompose_epic`, `create_task`
- **Write (Gaertner/Kartograph):** `propose_skill`, `create_wiki_article`
- **Admin:** `assign_task`, `resolve_escalation`, `requeue_dead_letter`

Vollständige Tool-Liste: `GET /api/mcp/tools`

## BYOAI-Workflow (ohne Extension)

Solange die VS Code Extension (TASK-IDE-003) noch nicht installiert ist:

1. Prompt Station öffnen → nächsten Dispatch wählen
2. Prompt kopieren → in Copilot Chat (Agent Mode) einfügen
3. Copilot hat über `.vscode/mcp.json` bereits alle Hivemind-Tools
4. Agent führt Tasks aus, ruft `submit_result` auf → State-Transition in Hivemind
