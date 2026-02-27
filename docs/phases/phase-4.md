# Phase 4 — Planer-Writes (Stratege & Architekt)

← [Phasen-Übersicht](./overview.md) | [Index](../../masterplan.md)

**Ziel:** Stratege kann über MCP Epic-Proposals erstellen; Architekt kann Epics zerlegen, Tasks anlegen, Context Boundaries setzen.

**AI-Integration:** Strategie-Prompt und Architektur-Prompt werden manuell in AI-Client eingefügt; AI ruft Planer-Write-Tools auf.

---

## Deliverables

### Backend

- [ ] Planer-Write-Tools implementiert:
  - `hivemind/create_epic` — Epic direkt erstellen mit state='incoming' (developer in eigenen Projekten, admin überall)
  - `hivemind/propose_epic` — Epic-Proposal erstellen (Stratege)
  - `hivemind/update_epic_proposal` — Proposal nachbessern (Stratege)
  - `hivemind/accept_epic_proposal` — Proposal akzeptieren → Epic (incoming) (Triage/Admin)
  - `hivemind/reject_epic_proposal` — Proposal ablehnen mit Begründung (Triage/Admin)
  - `hivemind/decompose_epic` — Epic → Tasks/Subtasks
  - `hivemind/create_task` — einzelnen Task anlegen
  - `hivemind/create_subtask` — Subtask mit Parent
  - `hivemind/link_skill` — Skill mit Task verknüpfen
  - `hivemind/set_context_boundary` — Context Boundary für Task setzen
  - `hivemind/assign_task` — Task einem User zuweisen (löst `task_assigned`-Notification aus)
- [ ] Strategie-Prompt-Generator (`hivemind/get_prompt { "type": "stratege", "project_id": "uuid" }`) — für Stratege ist `project_id` der Pflicht-Parameter
- [ ] Architektur-Prompt-Generator (`hivemind/get_prompt { "type": "architekt", "epic_id": "uuid" }`) — für Architekt ist `epic_id` der Pflicht-Parameter statt `task_id`
- [ ] `epic_proposals`-Tabelle + CRUD-Endpoints
- [ ] Triage Station: `[EPIC PROPOSAL]`-Kategorie mit Accept/Reject-UI
- [ ] Skill Lab Backend: Skills CRUD, Lifecycle-Transitions
- [ ] Proposer-Submit-Tool: `hivemind/submit_skill_proposal` (`draft → pending_merge`)
- [ ] Admin-Write-Tools (Subset): `hivemind/merge_skill`, `hivemind/reject_skill`
- [ ] Audit-Log-Viewer-Endpoint: `GET /api/audit` mit Filterung

### Frontend

- [ ] Skill Lab (vollständig):
  - Skills browsen mit Lifecycle-Filter
  - Skill-Detail mit Markdown-Renderer
  - Skill-Proposal einsehen (Diff-Ansicht)
  - Admin: Merge / Reject Buttons
  - Confidence Bar Animation
- [ ] Command Deck Erweiterung:
  - Architekt-Prompt-Button auf scopedEpics: "Architekt starten ▶"
  - Task-Erstellungs-Dialog (für manuell erstellte Tasks)
  - Context Boundary anzeigen (read-only, gesetzt vom Architekt via MCP)
- [ ] Audit-Log-Ansicht in Settings (Tabelle mit MCP-Invocations)

---

## Acceptance Criteria

- [ ] `hivemind/propose_epic` erstellt Epic-Proposal mit korrektem State (`proposed`)
- [ ] `hivemind/accept_epic_proposal` erstellt Epic (state: `incoming`) und setzt `resulting_epic_id`
- [ ] `hivemind/reject_epic_proposal` setzt `state = rejected` und sendet Notification an Proposer
- [ ] Abhängige Proposals (`depends_on`) erhalten Warnung wenn referenziertes Proposal abgelehnt wird
- [ ] `hivemind/decompose_epic` erstellt Tasks in korrekter Reihenfolge
- [ ] Subtasks sind korrekt mit Parent verknüpft
- [ ] `hivemind/set_context_boundary` wird in `context_boundaries` gespeichert
- [ ] `hivemind/link_skill` pinnt Skill-Version auf Task
- [ ] Skill-Lifecycle-Transition `draft → pending_merge` via `hivemind/submit_skill_proposal`
- [ ] `hivemind/merge_skill` setzt `lifecycle = active`
- [ ] `hivemind/reject_skill` setzt `lifecycle = rejected` und liefert Begründung an Proposer
- [ ] Skill Lab zeigt alle Skills mit korrekten Lifecycle-Badges (inkl. `rejected`)
- [ ] Diff-Ansicht für Skill-Proposals funktioniert
- [ ] Audit-Log-Ansicht zeigt letzte 50 MCP-Invocations

---

## Abhängigkeiten

- Phase 3 abgeschlossen (MCP Read-Tools, Prompt-Generator)

## Öffnet folgende Phase

→ [Phase 5: Worker & Gaertner](./phase-5.md)
