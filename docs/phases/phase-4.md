# Phase 4 — Planer-Writes (Architekt)

← [Phasen-Übersicht](./overview.md) | [Index](../../masterplan.md)

**Ziel:** Architekt kann über MCP Epics zerlegen, Tasks anlegen, Context Boundaries setzen.

**AI-Integration:** Architekt-Prompt wird manuell in AI-Client eingefügt; AI ruft Planer-Write-Tools auf.

---

## Deliverables

### Backend

- [ ] Planer-Write-Tools implementiert:
  - `hivemind/decompose_epic` — Epic → Tasks/Subtasks
  - `hivemind/create_task` — einzelnen Task anlegen
  - `hivemind/create_subtask` — Subtask mit Parent
  - `hivemind/link_skill` — Skill mit Task verknüpfen
  - `hivemind/set_context_boundary` — Context Boundary für Task setzen
  - `hivemind/assign_task` — Task einem User zuweisen (löst `task_assigned`-Notification aus)
- [ ] Architektur-Prompt-Generator (`hivemind/get_prompt { "type": "architekt", "epic_id": "uuid" }`) — für Architekt ist `epic_id` der Pflicht-Parameter statt `task_id`
- [ ] Skill Lab Backend: Skills CRUD, Lifecycle-Transitions
- [ ] Proposer-Submit-Tool: `hivemind/submit_skill_proposal` (`draft → pending_merge`)
- [ ] Admin-Write-Tools (Subset): `hivemind/merge_skill`, `hivemind/reject_skill`
- [ ] Audit-Log-Viewer-Endpoint: `GET /admin/audit` mit Filterung

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
