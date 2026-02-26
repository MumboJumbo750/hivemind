# Agenten — Übersicht

← [Index](../../masterplan.md)

Hivemind kennt 5 Rollen/Agenten. In Phase 1–7 sind alle manuell — der User fügt den generierten Prompt in seinen AI-Client ein. Ab Phase 8 können sie automatisiert werden.

---

## Vergleichsmatrix

| | Kartograph | Architekt | Worker | Gaertner | Triage |
| --- | --- | --- | --- | --- | --- |
| **Sichtweite** | Fog of War, max. Berechtigung | Ein Epic (gesetzt) | Context Boundary (fix) | Abgeschlossene Tasks | Unrouted Events |
| **Kontextfilter** | Deaktiviert | Setzt ihn | Strikt begrenzt | Abgeschlossene Tasks | Keine Boundary |
| **Output** | Wiki, Docs, Restructure-Proposals | Tasks, Subtasks, Boundaries | Task-Ergebnisse + Artefakte | Skill-Proposals, Doc-Updates, Decision Records | Epic-Zuweisung |
| **Timing** | Initial + nach Epic-Abschluss | Nach Kartograph | Während Sprint | Nach Task-done | Bei eingehenden Events |
| **Prompt-Typ** | Initial-Kartograph, Follow-up | Architektur-Prompt | Worker-Prompt | Gaertner-Prompt | Triage-Prompt |
| **Schreibrechte** | Wiki, Epic-Docs, Restructure-Proposals | Tasks, Subtasks, Context Boundaries | submit_result, Statuswechsel, Decision Request | Skill-Proposals, Doc-Updates, Decision Records | — |

---

## Detaildokumente

- [Kartograph](./kartograph.md) — Fog-of-War Explorer, Repo-Analyse, Wiki-Autor
- [Architekt](./architekt.md) — Epic-Dekomposition, Context Boundaries, Task-Zuweisung
- [Worker](./worker.md) — Task-Ausführung, Guard-Prüfung, Ergebnislieferung
- [Gaertner](./gaertner.md) — Skill-Destillation, Decision Records, Doc-Updates
- [Triage](./triage.md) — Event-Routing, Proposals, Dead Letters, Eskalationen
- [Bibliothekar](./bibliothekar.md) — Context Assembly (Phase 1–2: Prompt, Phase 3+: Service)
- [Prompt Pipeline](./prompt-pipeline.md) — Wie Prompts generiert und ausgeliefert werden

---

## Governance

- Agenten handeln immer **im Namen eines Actors** (niemals anonym)
- Kein Agent kann direkt auf `done` setzen — Review-Gate gilt immer
- Skill-Aktivierung nur per Admin-Merge (auch wenn Gaertner den Proposal erstellt)
- Kartograph kann nicht Tasks erstellen oder ausführen — nur lesen + wiki/docs schreiben
