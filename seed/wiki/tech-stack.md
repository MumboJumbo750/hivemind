---
slug: "tech-stack"
title: "Tech Stack — Entscheidungen und Begründungen"
tags: ["tech-stack", "backend", "frontend", "entscheidungen"]
linked_epics: ["EPIC-PHASE-1A", "EPIC-PHASE-1B"]
---

# Tech Stack — Entscheidungen und Begründungen

## Backend

| Technologie | Warum |
| --- | --- |
| **FastAPI** | Async-first, OpenAPI-Auto-Gen, Python-Ökosystem für AI |
| **SQLAlchemy 2** | Async Engine, Type Hints, deklarative Models |
| **Alembic** | Migration-Standard für SQLAlchemy, Auto-Generate |
| **asyncpg** | Schnellster PostgreSQL-Driver für Python async |
| **PostgreSQL 16** | JSONB, pgvector, Row-Level-Security, PITR-Backup |
| **pgvector** | Embedding-basierte Similarity-Suche für Skills, Wiki, Routing |

## Frontend

| Technologie | Warum |
| --- | --- |
| **Vue 3** | Composition API, gutes TypeScript-Support |
| **Vite** | Schnellster Build-Tool, HMR |
| **TypeScript** | Type Safety, bessere DX |
| **Reka UI** | Headless Primitives, volle Kontrolle über Styling |
| **CSS Variables** | Design Tokens als CSS Custom Properties, Theme-Switch ohne JS |

## Infrastruktur

| Technologie | Warum |
| --- | --- |
| **Docker Compose** | Einheitliche Dev-Umgebung, reproduzierbar |
| **Ollama** | Self-Hosted LLM + Embeddings, keine API-Key-Pflicht |
| **MCP 1.0 (SSE/JSON-RPC 2.0 + REST + stdio)** | Standard-Protokoll für AI-Tool-Integration — externe Clients verbinden via `/api/mcp/sse` |

## Bewusst NICHT gewählt

| Alternative | Warum nicht |
| --- | --- |
| Kubernetes | Overkill für Solo/Small-Team, Docker Compose reicht |
| Redis | PostgreSQL reicht für Queue + Cache in unserem Scale |
| MongoDB | Relationales Modell mit JSONB ist flexibler + konsistenter |
| React/Next.js | Vue 3 passt besser zum Team-Skill |
