# Agenten — Übersicht

← [Index](../../masterplan.md)

Hivemind kennt **7 Rollen/Agenten** (6 ab Phase 1, Reviewer ab Phase 8). In Phase 1–7 sind alle manuell — der User fügt den generierten Prompt in seinen AI-Client ein. Ab Phase 8 können sie automatisiert werden — koordiniert durch den **Conductor** (Backend-Orchestrator) und gesteuert durch **Governance-Levels** (manual/assisted/auto).

---

## Vergleichsmatrix

| | Kartograph | Stratege | Architekt | Worker | Gaertner | Triage | Reviewer ¹ |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Sichtweite** | Fog of War, max. Berechtigung | Breit (alle Hivemind-Daten, kein Code) | Ein Epic (gesetzt) | Context Boundary (fix) | Abgeschlossene Tasks | Unrouted Events | Ein Task (in_review) |
| **Kontextfilter** | Deaktiviert | Deaktiviert (braucht Gesamtbild) | Setzt ihn | Strikt begrenzt | Abgeschlossene Tasks | Keine Boundary | Task + Guards + Skills |
| **Output** | Wiki, Docs, Restructure-Proposals | Epic-Proposals, Roadmap, Dependencies | Tasks, Subtasks, Boundaries | Task-Ergebnisse + Artefakte | Skill-Proposals, Doc-Updates, Decision Records | Epic-Zuweisung | Review-Empfehlung |
| **Timing** | Initial + nach Epic-Abschluss | Vor Architekt; nach Plan-Import/Kartograph | Nach Stratege/Scoping | Während Sprint | Nach Task-done | Bei eingehenden Events | Nach Worker submit (in_review) |
| **Prompt-Typ** | Initial-Kartograph, Follow-up | Strategie-Prompt | Architektur-Prompt | Worker-Prompt | Gaertner-Prompt | Triage-Prompt | Reviewer-Prompt |
| **Schreibrechte** | Wiki, Epic-Docs, Restructure-Proposals | Epic-Proposals, Wiki (Roadmap) | Tasks, Subtasks, Context Boundaries | submit_result, Statuswechsel, Decision Request | Skill-Proposals, Doc-Updates, Decision Records | — | submit_review_recommendation |

> ¹ Reviewer ist erst ab Phase 8 verfügbar und wird nur dispatcht wenn `governance.review ≠ 'manual'`.

---

## Detaildokumente

- [Kartograph](./kartograph.md) — Fog-of-War Explorer, Repo-Analyse, Wiki-Autor
- [Stratege](./stratege.md) — Plan→Epics, Dependency-Mapping, Roadmap-Planung
- [Architekt](./architekt.md) — Epic-Dekomposition, Context Boundaries, Task-Zuweisung
- [Worker](./worker.md) — Task-Ausführung, Guard-Prüfung, Ergebnislieferung
- [Gaertner](./gaertner.md) — Skill-Destillation, Decision Records, Doc-Updates
- [Triage](./triage.md) — Event-Routing, Proposals, Dead Letters, Eskalationen
- [Reviewer](../features/agent-skills.md#-reviewer-skill-phase-8) — AI-gestütztes Code-Review, Confidence-Scoring *(Phase 8)*
- [Bibliothekar](./bibliothekar.md) — Context Assembly (Phase 1–2: Prompt, Phase 3+: Service)
- [Prompt Pipeline](./prompt-pipeline.md) — Wie Prompts generiert und ausgeliefert werden
- [Autonomy Loop](../features/autonomy-loop.md) — Conductor, Reviewer-Skill, Governance-Levels *(Phase 8)*

---

## Governance

- Agenten handeln immer **im Namen eines Actors** (niemals anonym)
- Kein Agent kann direkt auf `done` setzen — Review-Gate gilt immer
- Skill-Aktivierung nur per Admin-Merge (auch wenn Gaertner den Proposal erstellt)
- Kartograph kann nicht Tasks erstellen oder ausführen — nur lesen + wiki/docs schreiben
- Stratege kann nicht Tasks erstellen oder ausführen — nur Epic-Proposals + Wiki/Roadmap schreiben
- Epic-Proposals des Strategen müssen von Admin/Owner akzeptiert werden (→ Triage Station)
- **Governance-Levels** (Phase 8): Jeder Gate-Point kann auf `manual`, `assisted` oder `auto` konfiguriert werden (→ [autonomy-loop.md](../features/autonomy-loop.md#3-governance-levels))
- **Conductor** (Phase 8): Event-driven Orchestrator dispatcht Agenten automatisch auf State-Transitions (→ [autonomy-loop.md](../features/autonomy-loop.md#1-conductor--event-driven-orchestrator))
