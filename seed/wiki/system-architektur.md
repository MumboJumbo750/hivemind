---
slug: "system-architektur"
title: "Systemarchitektur — Hivemind Überblick"
tags: ["architektur", "backend", "frontend", "überblick"]
linked_epics: ["EPIC-PHASE-1A", "EPIC-PHASE-1B", "EPIC-PHASE-2"]
---

# Systemarchitektur — Hivemind Überblick

## Was ist Hivemind?

Hivemind ist ein hybrides Entwicklungssystem das **Progressive Disclosure** als Kernprinzip nutzt. Es startet als manuelles BYOAI-System ("Wizard of Oz") und skaliert ohne Architekturbruch auf autonome MCP-Agenten.

## Stack

| Schicht | Technologie |
| --- | --- |
| Backend | FastAPI + SQLAlchemy 2 + Alembic + asyncpg |
| Datenbank | PostgreSQL 16 + pgvector |
| Embeddings | Ollama nomic-embed-text (ab Phase 3) |
| Frontend | Vue 3 + Vite + TypeScript + Reka UI |
| Runtime | Docker Compose |
| MCP | stdio (lokal) + HTTP/SSE (team/remote) |

## Architektur-Schichten

```
┌─────────────────────────────────────────────────┐
│                   Frontend                       │
│         Vue 3 + Reka UI + Design Tokens          │
├─────────────────────────────────────────────────┤
│              REST API + SSE                      │
│         FastAPI + JWT Auth + RBAC                │
├─────────────────────────────────────────────────┤
│            MCP Server (Phase 3+)                 │
│         stdio + HTTP/SSE Transport               │
├─────────────────────────────────────────────────┤
│         Domain Services + State Machine          │
│        SQLAlchemy 2 + Business Logic             │
├─────────────────────────────────────────────────┤
│              PostgreSQL 16                        │
│         pgvector + Vollständiges Schema          │
└─────────────────────────────────────────────────┘
```

## Trust Boundary

- **Innen:** Backend + DB. Alle Writes gehen durch RBAC + Audit.
- **Außen:** AI-Client, MCP-Tools, Federation-Peers. Signaturprüfung für Federation.
- **Solo-Modus:** RBAC deaktiviert, System-User automatisch.
- **Team-Modus:** RBAC aktiv, explizite Rollen.

## Kernprinzipien

1. **Progressive Disclosure** — Kontext nur task-genau laden
2. **BYOAI → Autonomy** — Gleiche Endpoints, gleicher Datenvertrag
3. **Review-Gate immer aktiv** — Kein direktes `done` ohne Review
4. **Sovereign Nodes** — Jeder Entwickler ist sein eigener Host
