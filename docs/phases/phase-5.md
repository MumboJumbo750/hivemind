# Phase 5 — Worker & Gaertner Writes

← [Phasen-Übersicht](./overview.md) | [Index](../../masterplan.md)

**Ziel:** Vollständiger Worker-Flow und Gaertner-Wissenskonsolidierung. Nexus Grid 2D. Wiki.

**AI-Integration:** Worker- und Gaertner-Prompts werden manuell ausgeführt. Review-Gate aktiv.

---

## Deliverables

### Backend

- [ ] Worker-Write-Tools:
  - `hivemind/submit_result` — Ergebnis + Artefakte an Task schreiben (State bleibt `in_progress`)
  - `hivemind/update_task_state` — State-Transitions; `→ in_review` prüft Guards + Result
  - `hivemind/create_decision_request` — Blocker eskalieren (atomar: erstellt offenen Decision Request + setzt Task `in_progress → blocked`)
  - `hivemind/report_guard_result` — Guard-Ergebnis melden (passed|failed|skipped)
- [ ] Gaertner-Write-Tools:
  - `hivemind/propose_skill` — neuen Skill vorschlagen
  - `hivemind/propose_skill_change` — bestehenden Skill ändern
  - `hivemind/submit_skill_proposal` — Skill-Proposal zur Admin-Review einreichen (`draft → pending_merge`)
  - `hivemind/create_decision_record` — Entscheidung dokumentieren
  - `hivemind/update_doc` — Epic-Doc aktualisieren
- [ ] Kartograph-Write-Tools:
  - `hivemind/create_wiki_article`
  - `hivemind/update_wiki_article`
  - `hivemind/create_epic_doc`
  - `hivemind/link_wiki_to_epic`
  - `hivemind/propose_epic_restructure`
  - `hivemind/propose_guard` — Guard vorschlagen (Kartograph entdeckt aus Repo)
  - `hivemind/propose_guard_change` — Guard-Änderung vorschlagen
  - `hivemind/submit_guard_proposal` — Guard-Proposal zur Admin-Review einreichen (`draft → pending_merge`)
- [ ] Review-Write-Tools (Owner/Admin):
  - `hivemind/approve_review` — Task von `in_review` auf `done` setzen (Review-Gate bestanden)
  - `hivemind/reject_review` — Task von `in_review` auf `qa_failed` setzen + Kommentar; `qa_failed_count >= 3` → automatisch `escalated`
- [ ] Admin-Write-Tools (Erweiterung):
  - `hivemind/merge_guard` — Guard-Proposal aktivieren (`lifecycle → active`)
  - `hivemind/reject_guard` — Guard-Proposal ablehnen (`lifecycle → rejected`)
  - `hivemind/accept_skill_change` — Skill-Change-Proposal annehmen (`state → accepted`)
  - `hivemind/reject_skill_change` — Skill-Change-Proposal ablehnen (`state → rejected`)
  - `hivemind/accept_guard_change` — Guard-Change-Proposal annehmen (`state → accepted`)
  - `hivemind/reject_guard_change` — Guard-Change-Proposal ablehnen (`state → rejected`)
  - `hivemind/accept_epic_restructure` — Restructure-Proposal annehmen (`state → accepted`)
  - `hivemind/reject_epic_restructure` — Restructure-Proposal ablehnen (`state → rejected`)
  - `hivemind/cancel_task` — Task abbrechen (alle non-terminalen States)
- [ ] Prompt-Generatoren: Worker-Prompt, Gaertner-Prompt, Initial-Kartograph-Prompt
- [ ] `code_nodes` schreiben: wenn Kartograph Wiki-Artikel erstellt → `explored_at` setzen
- [ ] Wiki-Such-Backend: Volltextsuche + Tag-Filterung (pgvector ab Phase 3 verfügbar)
- [ ] qa_failed-Flow: `reject_review` setzt Task auf `qa_failed` (persistenter State); Worker setzt via `update_task_state { "state": "in_progress" }` aktiv zurück nach Review-Kommentar-Lesen
- [ ] **Gamification aktivieren** (→ [Phase 1 Gamification-Spezifikation](./phase-1.md#gamification-spezifikation)):
  - EXP-Trigger in `approve_review` (+100 EXP, +50 First-Try-Bonus), `merge_skill` (+75), `create_wiki_article` (+50), `merge_guard` (+50), `create_decision_record` (+25)
  - Badge-Check nach jedem EXP-Event (gegen `badge_definitions`)
  - Level-Up-Check (gegen `level_thresholds`)
  - Status Bar zeigt `[EXP: ████████░░░░ Lvl. 5 Commander]`
  - `GET /api/users/me/achievements` Endpoint aktiv

### Frontend

- [ ] Wiki View:
  - Artikel-Reader mit Markdown-Renderer
  - Suchleiste + Tag-Filter
  - "Mit Epic verknüpfen"-Dialog
  - Versions-History anzeigen
- [ ] Nexus Grid 2D (erster Stand):
  - Force-directed Graph (Cytoscape.js — verbindlich, siehe [nexus-grid.md](../features/nexus-grid.md#bibliothek-entscheidung-cytoscapejs))
  - Fog-of-War-Overlay (unerkundete Nodes = dunkel/semi-transparent)
  - Click auf Node → Detail-Panel (verlinkter Docs, Skills, Tasks)
  - Kartierte Nodes hervorheben (● statt ░)
- [ ] Gaertner-Prompt-Flow:
  - Wenn Task auf `done` → Prompt Station zeigt "Jetzt: Gaertner"
  - Gaertner-Prompt mit abgeschlossenem Task als Kontext
- [ ] Review Panel zeigt Guard-Provenance:
  - `source` pro Guard (`self-reported` | `system-executed`)
  - `checked_at` pro Guard
  - Warnhinweis bei `self-reported` und leerer/unklarer Guard-Ausgabe

---

## Acceptance Criteria

- [ ] `hivemind/submit_result` speichert Ergebnis + Artefakte (State bleibt `in_progress`)
- [ ] `hivemind/update_task_state { state: "in_review" }` prüft Guards + Result, setzt erst dann State auf `in_review`
- [ ] `update_task_state → in_review` schlägt mit 422 fehl wenn Guards offen oder Result fehlt
- [ ] `hivemind/update_task_state` blockiert direkte `in_progress -> done` (Review-Gate)
- [ ] `hivemind/create_decision_request` erstellt Decision Request mit `state = open` und setzt Task atomar `in_progress -> blocked`
- [ ] `hivemind/approve_review` setzt Task auf `done` (nur aus `in_review`); Notification `task_done` ausgelöst
- [ ] `hivemind/reject_review` setzt Task auf `qa_failed` + schreibt `review_comment`; `qa_failed_count` wird inkrementiert
- [ ] `qa_failed_count >= 3` → Worker-Versuch `in_progress` zu setzen wird abgefangen → Task auf `escalated` (Worker re-entry Trigger)
- [ ] Worker kann `qa_failed → in_progress` via `update_task_state { "state": "in_progress" }` setzen (erst nach Review-Kommentar lesen)
- [ ] `hivemind/propose_skill` erstellt Skill mit `lifecycle = draft`
- [ ] `hivemind/submit_skill_proposal` setzt `lifecycle = pending_merge`
- [ ] `hivemind/create_wiki_article` erstellt Artikel + setzt `code_nodes.explored_at`
- [ ] Nexus Grid 2D zeigt kartierte Nodes als ● und unerkundete als ░
- [ ] Wiki-Suche findet Artikel per Volltextsuche
- [ ] Gaertner-Prompt erscheint in Prompt Station wenn Task auf `done` geht
- [ ] Review Panel zeigt Guard-Provenance (`source`, `checked_at`) fuer alle Guard-Ergebnisse
- [ ] `self-reported` Guards mit leerer/unklarer Ausgabe werden im Review visuell als Warnung markiert

---

## Abhängigkeiten

- Phase 4 abgeschlossen (Planer-Writes, Skill Lab)

## Öffnet folgende Phase

→ [Phase 6: Eskalation & Triage](./phase-6.md)
