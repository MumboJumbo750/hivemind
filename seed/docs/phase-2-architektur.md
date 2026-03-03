---
epic_ref: "EPIC-PHASE-2"
title: "Phase 2 — Architektur-Kontext"
---

# Phase 2 — Identity & RBAC

## Überblick

Phase 2 liefert das vollständige Actor-Modell, JWT-Authentifizierung, rollenbasierte Zugriffskontrolle (RBAC), Optimistic Locking, Audit-Writing und den Solo/Team-Modus-Switch.

## Architektur-Entscheidungen

### JWT Bearer + HttpOnly Refresh Cookie
Entschieden für stateless JWT-Tokens statt Session-basierter Auth. Access-Token kurzlebig (15 Min), Refresh-Cookie (HttpOnly, Secure) für Token-Rotation. Backend ist Single Source of Truth für Rollen — Client-Claims werden gegen Token validiert.

### Actor-Modell
Vier Rollen: `developer`, `admin`, `service`, `kartograph`. Jede Rolle hat definierte Permissions. Scope-Validierung: Zugriff nur bei `project_member` oder `assigned_to`.

### Optimistic Locking
Alle mutierenden Write-Endpoints erfordern `expected_version`. Bei Version-Mismatch → HTTP 409. Verhindert verlorene Updates bei paralleler Bearbeitung.

### Solo/Team-Modus
`HIVEMIND_MODE=solo` als Bootstrap-Default, danach DB-gesteuert (`app_settings`-Tabelle). Solo: RBAC deaktiviert, System-User automatic. Team: volle Rollenprüfung. Review-Gate bleibt in beiden Modi aktiv.

### Node-Bootstrap
Beim ersten Start wird automatisch eine Node-Identity generiert: UUID + Ed25519-Keypair. Der eigene Node wird in die `nodes`-Tabelle eingetragen — Basis für die spätere Federation (Phase F).

## Task-Abhängigkeiten

```
001-jwt-auth
  └→ 002-actor-model-rbac
       ├→ 003-optimistic-locking
       ├→ 004-audit-writer
       │    └→ 008-audit-retention-cron
       ├→ 005-solo-team-switch
       ├→ 006-node-bootstrap
       └→ 007-frontend-login
            ├→ 009-command-deck
            ├→ 010-epic-scoping-modal
            ├→ 011-task-review-panel
            ├→ 012-spotlight-search
            └→ 013-notification-tray
```

## Relevante Skills
- `jwt-auth` — JWT-Authentifizierung
- `rbac-middleware` — RBAC-Enforcement-Middleware
- `optimistic-locking` — Versionsbasiertes Locking
- `fastapi-endpoint` — Endpoint-Erstellung
- `vue-component` — Vue 3 Component-Pattern
- `api-test` — Endpoint-Tests
- `ed25519-signing` — Ed25519-Keypair-Generierung
