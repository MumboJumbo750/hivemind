---
epic_ref: "EPIC-PHASE-3"
title: "Phase 3 — Architektur-Kontext"
---

# Phase 3 — MCP Read-Tools & Bibliothekar-Prompt

## Überblick

Phase 3 bringt die erste echte MCP-Integration: Der AI-Client kann Hivemind-Daten lesen, der Bibliothekar assembliert Kontext als generierter Prompt, und Ollama liefert Embeddings für semantische Suche.

## Architektur-Entscheidungen

### MCP 1.0 Standard
FastAPI-basierter MCP-Server mit SSE/JSON-RPC 2.0 + Convenience-REST + stdio-Transport. Namespace: `hivemind/` für alle lokalen Tools.

### Embedding-Provider-Abstraktion
Ollama mit `nomic-embed-text` als Default. Provider-Switch möglich ohne Datenmigration — Embedding-Spalten werden per ALTER TABLE angepasst + Recompute bei Provider-Wechsel.

### Circuit-Breaker für Embeddings
Exponentieller Backoff bei Ollama-Ausfällen: 60s → 120s → 240s → max 600s. Feature-Degradation (embedding=NULL) statt harter Fehler. Reset nach 10 Min stabiler CLOSED-Phase.

### Prompt-History ab Phase 3
Jeder `get_prompt`-Call schreibt in `prompt_history`. Max 500 Einträge pro Task (FIFO). Retention-Cron (180 Tage) läuft täglich.

### REST-CRUD für Phase-5-MCP-Write-Entitäten
Wiki-Artikel, Guards, Code-Nodes und Epic-Docs erhalten REST-Endpoints als technische Grundlage. MCP-Tool-Wrapper folgen in Phase 5.

## Backend-Deliverables

### MCP Read-Tools
- `hivemind/get_epic`, `hivemind/get_task`, `hivemind/get_skills`
- `hivemind/get_skill_versions`, `hivemind/get_guards`, `hivemind/get_doc`
- `hivemind/get_triage`, `hivemind/get_audit_log`
- `hivemind/get_wiki_article`, `hivemind/search_wiki`
- `hivemind/get_prompt` (Prompt-Generator-Endpunkt)

### SSE-Infrastruktur
- Kanäle: `/events/notifications`, `/events/tasks`, `/events/triage`
- Stream-Token-Handshake, Heartbeat (15s), kanonische Event-Typen

### Webhook-Ingest
- YouTrack + Sentry Events empfangen → `sync_outbox` (direction=inbound)
- Triage erzeugt `[UNROUTED]`-Items für nicht-zuordnbare Events

## Frontend-Deliverables
- Triage Station (erster Stand)
- Token Radar in Prompt Station
- MCP-Verbindungsstatus
- Kartograph-Bootstrap-Flow (mit manueller Dateneingabe bis Phase 5)

## Relevante Skills
- `mcp-tool` — MCP-Tool-Pattern
- `ollama-embedding` — Embedding-Integration
- `sse-event-stream` — SSE-Streaming
- `webhook-ingest` — Webhook-Verarbeitung
- `triage-routing` — Triage/Routing-Logik
- `fastapi-endpoint` — Endpoint-Erstellung
- `prompt-generator` — Prompt-Generierung
