---
epic_ref: "EPIC-PHASE-1A"
title: "Phase 1a — Architektur-Kontext"
---

# Phase 1a — Architektur-Kontext

## Überblick

Phase 1a legt das technische Fundament: Docker-Infrastruktur, vollständiges DB-Schema und die erste funktionierende API mit State Machine.

## Architektur-Entscheidungen

### Vollständiges Schema ab Phase 1
Alle Tabellen (auch für Phase 2–8) werden sofort angelegt. Vorteile:
- Keine Breaking Migrations zwischen Phasen
- Federation-Felder (`origin_node_id`, `federation_scope`) ab Tag 1 in der FK-Kette
- Jede Phase aktiviert nur Features, keine Schema-Changes

### pgvector vorinstalliert
`pgvector/pgvector:pg16` statt `postgres:16` — Extension ab Phase 3 nutzbar, kein Container-Wechsel nötig.

### State Machine im Backend
Alle State-Transitions werden server-seitig validiert. Kein Client kann ungültige Transitionen durchführen. Review-Gate ist fundamental: kein `done` ohne `in_review`.

## Task-Abhängigkeiten

```
001-docker-compose
  └→ 002-fastapi-skeleton
       └→ 003-alembic-setup
            ├→ 004-schema-federation
            │    └→ 005-schema-core
            │         ├→ 006-schema-epics-tasks
            │         │    ├→ 007-schema-skills-wiki
            │         │    │    └→ 008-schema-remaining → 014-seed-import
            │         │    └→ 009-state-machine
            │         └→ 010-crud-projects
            │              └→ 011-crud-epics
            │                   └→ 012-crud-tasks (benötigt 009 + 011)
            └→ 013-backup-cron
```

## Relevante Skills
- `docker-service` — Docker Compose Konfiguration
- `fastapi-endpoint` — Endpoint-Erstellung
- `alembic-migration` — Schema-Migrationen
- `pydantic-model` — Request/Response Schemas
- `state-machine-transition` — State-Validierung
- `api-test` — Endpoint-Tests
