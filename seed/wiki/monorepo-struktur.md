---
slug: monorepo-struktur
title: "Monorepo-Struktur — Ein Repo, alles drin"
tags: [architektur, monorepo, kartograph, code-struktur]
linked_epics: [EPIC-PHASE-1A, EPIC-PHASE-1B]
---

# Monorepo-Struktur — Ein Repo, alles drin

Hivemind ist als **Monorepo** organisiert: Backend, Frontend, Seed-Daten, Dokumentation und Infrastructure-as-Code leben in einem einzigen Git-Repository.

## Warum Monorepo?

1. **Atomare Änderungen** — Backend-API + Frontend-UI + Seed-Daten in einem Commit
2. **Einfaches Onboarding** — Ein `git clone`, ein `podman compose up`
3. **Konsistente Versionierung** — Kein Dependency-Hell zwischen Repos
4. **Kartograph-Freundlich** — Ein Repo-Bootstrap kartiert die gesamte Systemlandschaft

## Verzeichnisstruktur

```
hivemind/
├── backend/           Python 3.11, FastAPI, SQLAlchemy, MCP-Server
│   ├── app/
│   │   ├── models/    Vollständiges DB-Schema (alle Phasen)
│   │   ├── services/  Business Logic Layer
│   │   ├── routers/   HTTP-Endpoints (thin wrapper)
│   │   ├── mcp/       MCP-Server + Tool-Module
│   │   └── schemas/   Pydantic Request/Response Models
│   ├── alembic/       Datenbank-Migrationen
│   ├── tests/         pytest Tests
│   └── scripts/       CLI-Tools (seed_import, etc.)
├── frontend/          Vue 3, Vite, TypeScript
│   └── src/
│       ├── views/     Router-Views (CommandDeck, PromptStation, etc.)
│       ├── components/ UI-Bausteine (layout, ui, domain)
│       └── composables/ Reactive Composables
├── seed/              Hivemind als eigener Anwendungsfall
│   ├── epics/         Phase-Epics (JSON)
│   ├── tasks/         Tasks pro Epic (JSON)
│   ├── wiki/          Wiki-Artikel (Markdown)
│   ├── skills/        Skills (Markdown)
│   ├── docs/          Epic-Docs (Markdown)
│   ├── decisions/     Decision Records (JSON)
│   └── code_nodes/    Kartograph Code-Landkarte (JSON)
├── docs/              Projektdokumentation
└── docker-compose.yml Podman Compose Stack
```

## Container-Architektur

Jedes Verzeichnis wird als Volume in den passenden Container gemountet (Hot-Reload):
- `./backend → /app` (backend-Container)
- `./frontend → /app` (frontend-Container)
- `./seed → /seed:ro` (alle Container, read-only)

## Implikationen für den Kartographen

Der Kartograph kartiert das **gesamte Monorepo** in einem Code-Graphen. `code_nodes`-Einträge referenzieren Pfade relativ zum Repo-Root. Die `node_type`-Klassifikation (model, service, router, view, component, etc.) ermöglicht typisierte Filterung im Nexus Grid.
