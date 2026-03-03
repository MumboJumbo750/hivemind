---
slug: mcp-integration
title: "MCP-Integration — Wie Agents kommunizieren"
tags: [mcp, tools, agenten, api, phase-3]
linked_epics: [EPIC-PHASE-3, EPIC-PHASE-4, EPIC-PHASE-5, EPIC-PHASE-8]
---

# MCP-Integration — Wie Agents kommunizieren

MCP (Model Context Protocol) ist die Brücke zwischen AI-Agents und dem Hivemind-System. Alle Agent-Aktionen laufen über MCP-Tools im `hivemind/`-Namespace.

## Architektur

Der MCP-Server ist Teil der FastAPI-App und läuft im Backend-Container auf Port 8000. Transport: SSE/JSON-RPC 2.0 + Convenience-REST + stdio.

## Tool-Kategorien

### Read-Tools (Phase 3)
`get_epic`, `get_task`, `get_skills`, `get_doc`, `get_triage`, `get_audit_log`, `get_wiki_article`, `search_wiki`, `get_prompt`

### Planer-Write-Tools (Phase 4)
`propose_epic`, `decompose_epic`, `create_task`, `set_context_boundary`, `assign_task`, `link_skill`

### Worker/Gaertner/Kartograph-Write-Tools (Phase 5)
`submit_result`, `update_task_state`, `propose_skill`, `create_wiki_article`, `propose_epic_restructure`

### Eskalations-Tools (Phase 6)
`resolve_decision_request`, `resolve_escalation`

### DLQ-Tools (Phase 7)
`requeue_dead_letter`, `discard_dead_letter`

### Autonomie-Tools (Phase 8)
`submit_review_recommendation`, GitHub-/GitLab-Proxy-Tools

## MCP Bridge / Gateway (Phase 8)

Ab Phase 8 wird Hivemind zum **Meta-MCP**: gleichzeitig MCP-Server (für Agents) und MCP-Client (zu externen MCP-Servern wie GitHub MCP, GitLab MCP). Namespace-Isolation: `hivemind/*` (lokal), `github/*` (proxied), `gitlab/*` (proxied).

## Audit

Jeder MCP-Call wird in `mcp_invocations` protokolliert: Tool-Name, Input, Output, Actor, Timestamp. Die Retention-Policy nullifiziert Payloads nach `AUDIT_RETENTION_DAYS` (Default: 90).
