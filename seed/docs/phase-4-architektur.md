---
epic_ref: "EPIC-PHASE-4"
title: "Phase 4 — Architektur-Kontext"
---

# Phase 4 — Planer-Writes (Stratege & Architekt)

## Überblick

Phase 4 ermöglicht das aktive Planen über MCP: Der Stratege erstellt Epic-Proposals, der Architekt zerlegt Epics in Tasks mit Context Boundaries. Außerdem wird das Skill Lab vollständig implementiert.

## Architektur-Entscheidungen

### Epic-Proposal-Workflow
Stratege schlägt Epics vor (`proposed` State), Triage/Admin akzeptiert oder lehnt ab. Akzeptierte Proposals werden zu Epics im `incoming`-State. Abhängige Proposals erhalten Warnungen bei Ablehnungen.

### Context Boundaries
Der Architekt setzt pro Task eine Context Boundary — definiert welche Epics, Skills und Docs der Bibliothekar in den Kontext aufnehmen darf. Verhindert Context-Bloat und fokussiert AI-Arbeit.

### Skill Lab & Lifecycle
Skills durchlaufen: `draft → pending_merge → active` (oder `rejected`). Merge durch Admin. Diff-Ansicht für Proposals. Federated Skills (aus Phase F) werden hier ins Arsenal integriert.

## Backend-Deliverables

### Planer-Write-Tools
- `hivemind-propose_epic` — Epic-Proposal (Stratege)
- `hivemind-accept_epic_proposal` / `reject_epic_proposal` — Triage/Admin
- `hivemind-create_epic` — Direktes Erstellen (Developer/Admin)
- `hivemind-decompose_epic` — Epic → Tasks/Subtasks (Architekt)
- `hivemind-create_task` / `create_subtask`
- `hivemind-link_skill` — Skill mit Task verknüpfen
- `hivemind-set_context_boundary` — Context Boundary setzen
- `hivemind-assign_task` — Task zuweisen

### Prompt-Generatoren
- `stratege` (project_id als Pflicht-Parameter)
- `architekt` (epic_id als Pflicht-Parameter)

### Skill-Management
- `hivemind-submit_skill_proposal` (draft → pending_merge)
- `hivemind-merge_skill` / `reject_skill` (Admin)
- Skill-Lab-Backend mit CRUD + Lifecycle-Transitions

## Frontend-Deliverables
- Skill Lab (komplett): Browse, Detail, Diff-Ansicht, Merge/Reject
- Command Deck Erweiterung: Architekt-Prompt-Button, Task-Dialog
- Audit-Log-Ansicht in Settings
- Prompt-History-View (kollabierbare History)

## Relevante Skills
- `mcp-write-tool` — MCP-Write-Tool-Pattern
- `epic-proposal` — Epic-Proposal-Workflow
- `state-machine-transition` — State-Machine-Transitions
- `skill-lifecycle` — Skill-Lifecycle-Management
- `pydantic-model` — Pydantic-Schema-Pattern
- `vue-component` — Vue 3 Component-Pattern
