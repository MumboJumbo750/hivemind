---
epic_ref: "EPIC-PHASE-5"
title: "Phase 5 — Architektur-Kontext"
---

# Phase 5 — Worker & Gaertner Writes, Wiki, Nexus Grid 2D

## Überblick

Phase 5 liefert den vollständigen Worker-Flow (Task bearbeiten → Review → done), die Gaertner-Wissenskonsolidierung, Kartograph-Write-Tools, Wiki-UI, Nexus Grid 2D und Gamification-Aktivierung.

**Abhängigkeit:** Phase 4 abgeschlossen (Planer-Writes, Skill Lab).

## Architektur-Entscheidungen

### Scope-Split-Empfehlung (5a / 5b)

| Sub-Phase | Inhalt | Blocker für Phase 6? |
| --- | --- | --- |
| **5a** | Worker-Write-Tools (`submit_result`, `update_task_state`, `report_guard_result`, `create_decision_request`), Review-Write-Tools, Guard-Provenance im Review | Ja — Phase 6 (Eskalation) setzt Worker-Writes voraus |
| **5b** | Gaertner-Writes, Kartograph-Writes, Wiki, Nexus Grid 2D, Gamification-Aktivierung | Nein — kann nach Phase 6 nachgeholt werden |

### Decision Request Gap

`hivemind-resolve_decision_request` wird erst in Phase 6 implementiert. In Phase 5 kann ein `blocked` Task nur durch Admin-Direkt-Intervention wieder freigegeben werden: `PATCH /api/tasks/:task_key/state { "state": "in_progress", "actor_role": "admin" }`.

## Backend-Deliverables

### Worker-Write-Tools
- `hivemind-submit_result` — Ergebnis + Artefakte an Task (State bleibt `in_progress`)
- `hivemind-update_task_state` — State-Transitions; `→ in_review` prüft Guards + Result
- `hivemind-create_decision_request` — Blocker eskalieren (atomar: erstellt Decision Request + setzt Task `blocked`)
- `hivemind-report_guard_result` — Guard-Ergebnis melden (passed|failed|skipped)

### Gaertner-Write-Tools
- `hivemind-propose_skill` — neuen Skill vorschlagen
- `hivemind-propose_skill_change` — bestehenden Skill ändern
- `hivemind-submit_skill_proposal` — Skill-Proposal einreichen (`draft → pending_merge`)
- `hivemind-create_decision_record` — Entscheidung dokumentieren
- `hivemind-update_doc` — Epic-Doc aktualisieren

### Kartograph-Write-Tools
- `hivemind-create_wiki_article`
- `hivemind-update_wiki_article`
- `hivemind-create_epic_doc`
- `hivemind-link_wiki_to_epic`
- `hivemind-propose_epic_restructure`
- `hivemind-propose_guard` / `propose_guard_change` / `submit_guard_proposal`

### Review-Write-Tools
- `hivemind-approve_review` — Task `in_review → done` (Review-Gate bestanden)
- `hivemind-reject_review` — Task `in_review → qa_failed` + Kommentar

### Admin-Write-Tools (Erweiterung)
- `hivemind-merge_guard` / `reject_guard`
- `hivemind-accept_skill_change` / `reject_skill_change`
- `hivemind-accept_guard_change` / `reject_guard_change`
- `hivemind-accept_epic_restructure` / `reject_epic_restructure`
- `hivemind-cancel_task`

### Weitere Backend-Aufgaben
- Prompt-Generatoren: Worker-Prompt, Gaertner-Prompt, Initial-Kartograph-Prompt
- `code_nodes` schreiben: Kartograph Wiki-Artikel → `explored_at` setzen
- Wiki-Such-Backend: Volltextsuche + Tag-Filterung (pgvector ab Phase 3 verfügbar)
- qa_failed-Flow: Worker kann `qa_failed → in_progress` aktiv zurücksetzen
- Notification-Types: `guard_proposal`, `restructure_proposal`
- Gamification: EXP-Trigger, Badge-Check, Level-Up, Status Bar, Achievements-Endpoint

## Frontend-Deliverables

### Wiki View
- Artikel-Reader mit Markdown-Renderer
- Suchleiste + Tag-Filter
- "Mit Epic verknüpfen"-Dialog
- Versions-History

### Nexus Grid 2D
- Force-directed Graph (Cytoscape.js)
- Fog-of-War-Overlay (unerkundete Nodes = dunkel)
- Click → Detail-Panel
- Kartierte Nodes hervorheben (● statt ░)

### Gaertner-Prompt-Flow
- Task `done` → Prompt Station zeigt "Jetzt: Gaertner"

### Review Panel Erweiterung
- Guard-Provenance (`source`, `checked_at`)
- Warnhinweis bei `self-reported` + unklarer Ausgabe

## Acceptance Criteria (Auswahl)
- `submit_result` speichert Ergebnis (State bleibt `in_progress`)
- `update_task_state { state: "in_review" }` prüft Guards + Result
- `update_task_state` blockiert direkte `in_progress → done` (Review-Gate)
- `create_decision_request` erstellt Decision Request + setzt Task atomar `blocked`
- `approve_review` → Task `done`; `reject_review` → Task `qa_failed` + `qa_failed_count++`
- `qa_failed_count >= 3` → Worker re-entry Trigger → `escalated`
- `propose_skill` erstellt Skill mit `lifecycle = draft`
- `create_wiki_article` erstellt Artikel + setzt `code_nodes.explored_at`
- Nexus Grid 2D zeigt kartierte vs. unerkundete Nodes
- Wiki-Suche funktioniert
- Gaertner-Prompt erscheint bei Task `done`
- Guard-Provenance im Review Panel sichtbar

## Relevante Skills
- `mcp-write-tool` — MCP-Write-Tool-Pattern
- `state-machine-transition` — State-Machine-Transitions
- `vue-component` — Vue 3 Component-Pattern
- `prompt-generator` — Prompt-Generierung
- `api-test` — API-Test-Pattern
- `pydantic-model` — Pydantic-Schema-Pattern
- `fastapi-endpoint` — FastAPI-Endpoint-Pattern
- `skill-lifecycle` — Skill-Lifecycle-Management
- `rbac-middleware` — RBAC-Enforcement
- `sse-event-stream` — SSE-Event-Streaming
