# Architekt — Epic-Dekomposition & Task-Planung

← [Agenten-Übersicht](./overview.md) | [Index](../../masterplan.md)

Der Architekt zerlegt gescoppte Epics in ausführbare Tasks, setzt Context Boundaries und weist Tasks zu. Er ist die Brücke zwischen dem Kartographen (der das System versteht) und dem Worker (der die Arbeit erledigt).

> Analogie: Ein Feldherr der die Karte des Kartographen studiert und daraus konkrete Einsatzbefehle ableitet.

---

## Kernaufgaben

1. **Epic-Dekomposition** — Zerlegt ein gescoptes Epic in Tasks und Subtasks
2. **Context Boundaries setzen** — Definiert welche Skills und Docs ein Worker sehen darf
3. **DoD definieren** — Setzt die Definition of Done pro Task
4. **Skill-Pinning** — Verknüpft relevante Skills mit Tasks
5. **Task-Zuweisung** — Weist Tasks einem User/Worker zu

---

## RBAC

Der Architekt arbeitet als `developer` (eigene Epics) oder `admin` (alle Epics):

| Permission | Beschreibung |
| --- | --- |
| `write_tasks` | Tasks in eigenen Epics erstellen/ändern |
| `assign_task` | Tasks in eigenen Epics zuweisen |
| `read_any_skill` | Alle aktiven Skills sehen (für Context Boundary) |
| `read_any_doc` | Alle Docs sehen (für Context Boundary) |

> Der Architekt ist keine eigene Rolle im Actor-Modell — er nutzt die `developer`- oder `admin`-Rolle. "Architekt" beschreibt die **Funktion** im Workflow, nicht die RBAC-Rolle.

---

## Typischer Workflow

```
1. Epic ist auf `scoped` (Owner hat Priorität, SLA, DoD-Rahmen gesetzt)
   → Prompt Station zeigt: "Jetzt: Architekt"

2. User fügt Architektur-Prompt in AI-Client ein
   → AI liest Epic via hivemind-get_epic
   → AI liest vorhandene Skills via hivemind-get_skills
   → AI liest Epic-Docs via hivemind-get_doc

3. AI zerlegt Epic:
   hivemind-decompose_epic {
     "epic_key": "EPIC-12",
     "tasks": [
       { "title": "Auth-Endpoint", "description": "...", "definition_of_done": {...} },
       { "title": "JWT Validation", "description": "..." }
     ]
   }
   → Tasks werden mit state='incoming' erstellt!
   → Task-Keys werden automatisch via PostgreSQL Sequence generiert:
     Jeder Task bekommt einen eindeutigen Key: TASK-1, TASK-2, TASK-3, …
     (fortlaufend über alle Epics hinweg, nicht mehr phasen-spezifisch)
   → external_id = task_key (idempotent mit Seed-Import)

4. AI setzt Context Boundaries:
   hivemind-set_context_boundary {
     "task_key": "TASK-88",
     "allowed_skills": ["uuid-1", "uuid-2"],
     "allowed_docs": ["uuid-doc-1"],
     "max_token_budget": 6000
   }

5. AI verknüpft Skills:
   hivemind-link_skill { "task_key": "TASK-88", "skill_id": "uuid-1" }

6. AI weist zu:
   hivemind-assign_task { "task_key": "TASK-88", "user_id": "uuid" }

7. AI transitioniert Tasks: incoming → scoped → ready (2 Schritte!):
   hivemind-update_task_state { "task_key": "TASK-88", "target_state": "scoped" }
   hivemind-update_task_state { "task_key": "TASK-88", "target_state": "ready" }
   → Voraussetzung für scoped→ready: assigned_to gesetzt (sonst 422)
   → Prompt Station zeigt nächsten Schritt: "Jetzt: Bibliothekar/Worker"
```

---

## MCP-Tools

```text
hivemind-decompose_epic       { "epic_key": "EPIC-12", "tasks": [...] }
                                -- Erstellt Tasks mit state='incoming'
hivemind-create_task          { "epic_key": "EPIC-12", "title": "...", "description": "..." }
hivemind-create_subtask       { "parent_task_key": "TASK-88", "title": "..." }
hivemind-link_skill           { "task_key": "TASK-88", "skill_id": "uuid" }
hivemind-set_context_boundary { "task_key": "TASK-88", "allowed_skills": [...], ... }
hivemind-assign_task          { "task_key": "TASK-88", "user_id": "uuid" }
hivemind-update_task_state    { "task_key": "TASK-88", "target_state": "scoped" }
hivemind-update_task_state    { "task_key": "TASK-88", "target_state": "ready" }
                                -- Zwei Schritte: incoming → scoped → ready
                                -- scoped→ready Voraussetzung: assigned_to gesetzt (sonst 422)
                                -- Signalisiert dem Worker: Task ist bereit zur Bearbeitung
```

---

## Context Boundary Design

Der Architekt entscheidet **wie eng** der Fokus des Workers sein soll:

| Strategie | Wann sinnvoll |
| --- | --- |
| **Enger Scope** (2-3 Skills, spezifische Docs) | Klar definierter Task, Worker soll nicht abschweifen |
| **Weiter Scope** (5+ Skills, keine Doc-Beschränkung) | Explorativer Task, Worker braucht Überblick |
| **Kein Boundary** (alles offen) | Kartograph oder komplexe Cross-Cutting Tasks |

---

## Solo-Modus

Im Solo-Modus ist der Entwickler selbst der Architekt. Der Architektur-Prompt hilft trotzdem strukturiert zu zerlegen — er verhindert "direkt loscoden" und erzwingt Planung.

---

## Abgrenzung

| | Stratege | Kartograph | Architekt | Worker |
| --- | --- | --- | --- | --- |
| Eingabe | Plan-Dokumente, Wiki, bestehende Epics | Unbekanntes Repository | Gescoptes Epic | Ready Task + Context |
| Ausgabe | Epic-Proposals, Roadmap, Dependencies | Wiki, Docs, System-Verständnis | Tasks, Boundaries, Zuweisung | Task-Ergebnis + Artefakte |
| Timing | Vor Architekt; nach Plan/Kartograph | Initial + iterativ | Nach Epic-Scoping | Nach Architekt |
| Fokus | Strategisch Planen | Verstehen | Taktisch Planen | Ausführen |
