# Epic-Start, Parallel-Worker und Resume-Loop

← [Autonomy Loop](./autonomy-loop.md) | [Agent Skills](./agent-skills.md) | [Index](../../masterplan.md)

Dieses Dokument beschreibt das Zielbild für einen **Epic-Start-Button**, der ein Epic operativ anstößt, ausführbare Tasks erkennt, mehrere Worker kontrolliert parallel dispatcht, Reviews automatisch nachzieht und bei `qa_failed` einen gezielten Resume-Loop startet.

---

## Ziel

Ein Owner oder Operator soll ein Epic nicht mehr Task für Task manuell lostreten müssen. Stattdessen arrangiert Hivemind den Ausführungsfluss:

```text
Epic Start
  → Runnable Tasks bestimmen
  → kontrolliert mehrere Worker dispatchen
  → pro Task Review triggern
  → Folge-Tasks nach Dependencies freischalten
  → bei qa_failed Resume-Paket erzeugen
  → Learnings aus Worker/Reviewer/Gaertner verwerten
```

Wichtig: Das ist **keine freie Schwarm-Autonomie**, sondern orchestrierte Parallelisierung unter Governance, Review und Audit.

---

## Kernprinzipien

### 1. Parallel nur bei echten Unabhängigkeiten

Mehrere Worker dürfen nur gleichzeitig laufen, wenn:

- keine offene Task-Dependency besteht
- keine exklusive Dateikollision zu erwarten ist
- keine gemeinsame kritische Decision offen ist
- der Epic-Zustand die parallele Ausführung erlaubt

Parallelität ist also **graph- und konfliktbewusst**, nicht nur „alle offenen Tasks gleichzeitig“.

### 2. Worker sprechen nicht frei miteinander

Worker-zu-Worker-Chat ist nicht das Zielbild. Freie direkte Kommunikation erzeugt:

- schwer nachvollziehbare Entscheidungen
- versteckte Zustände außerhalb des Audit-Trails
- Prompt-Drift und unnötige Tokenkosten
- Race Conditions in Code und Architektur

Stattdessen kommunizieren Worker **strukturiert über Systemartefakte**:

- Epic-Scratchpad
- Handoff-Notes
- File-Claims
- Decision Requests
- Review-Kommentare
- Resume-Pakete

### 3. Kontext teilen ja — aber kontrolliert

Es gibt drei Kontextebenen:

1. **Task-Kontext**  
   Task, DoD, Guards, Skills, Boundary, relevante Docs

2. **Epic-Koordination**  
   gemeinsames Scratchpad, API-Verträge, offene Annahmen, File-Claims, Task-Status

3. **Resume-/Review-Kontext**  
   letzter Versuch, Review-Kommentar, Guard-Fails, Artefakt-Diff, offene Punkte

Worker erhalten nicht den vollständigen Chat aller anderen Worker, sondern nur den für ihre Aufgabe nötigen, destillierten Systemkontext.

### 4. Stateful Chats nur selektiv

Nicht jede Rolle profitiert von langlebigen Threads.

**Stateful sinnvoll:**

- `stratege`
- `architekt`
- `triage`
- `kartograph`

Diese Rollen arbeiten mit fortlaufendem Planungs- oder Erkundungskontext.

**Eher stateless / attempt-basiert:**

- `worker`
- `reviewer`

Hier ist Reproduzierbarkeit wichtiger als langer Chat-Kontext. Ein neuer Worker-Run soll mit einem klaren Task- und Resume-Paket starten, nicht mit einem unkontrolliert gewachsenen Thread.

**Destillierend statt dauerhaft dialogisch:**

- `gaertner`

Gaertner sollte eher Ergebnisse konsolidieren als lange Threads weiterführen.

---

## Epic-Start-Button

### Operator-Semantik

Der Button `Epic Start` tut fachlich mehr als ein einzelner Dispatch:

1. prüft, ob das Epic startbar ist
2. analysiert Task-Graph und Abhängigkeiten
3. identifiziert `runnable` Tasks
4. reserviert Worker-Slots gemäß Policy
5. dispatcht Worker für ausführbare Tasks
6. überwacht Review- und Resume-Zyklus
7. startet Folge-Tasks nach erfolgreichem Abschluss

### Startvoraussetzungen

Ein Epic ist startbar, wenn:

- Epic in passendem Zustand ist (`scoped` oder definierter Auto-Run-State)
- Tasks konsistent modelliert sind
- Context Boundaries / Skills / DoD ausreichend vorhanden sind
- keine blockierende Decision offen ist
- ein Projekt-Workspace verfügbar ist
- mindestens ein gültiger Dispatch-Modus für Worker vorhanden ist

### Operator-Optionen

Beim Start sollten steuerbare Parameter möglich sein:

- `max_parallel_workers`
- `execution_mode_preference`
- `respect_file_claims = true|false`
- `auto_resume_on_qa_failed = true|false`
- `review_mode_override` nur wenn Governance es erlaubt
- `dry_run` für Ausführbarkeitsanalyse ohne Dispatch

---

## Runnable-Task-Auswahl

### Ziel

Das System braucht einen expliziten `runnable`-Begriff:

Eine Task ist `runnable`, wenn sie:

- im passenden Ausgangszustand steht
- keine offenen Vorgänger hat
- nicht durch File-Claim-Konflikte blockiert ist
- nicht bereits aktiv dispatcht ist
- nicht an offener Entscheidung hängt

### Task-Graph

Der Graph besteht mindestens aus:

- Task-Dependencies
- Parent/Subtask-Beziehungen
- optionalen Architektur-/Boundary-Konflikten
- potentiellen File-Claim-Kollisionen

`Epic Start` soll nicht nur nach State filtern, sondern eine **Planungsansicht auf Ausführbarkeit** erzeugen.

---

## Parallel-Worker-Modell

### Dispatch-Strategie

```text
Epic Start
  → runnable task set = {T1, T2, T3}
  → worker slots = 2
  → dispatch T1 + T2
  → T3 bleibt queued
  → nach done/review von T1 wird Slot frei
  → T3 startet
```

Parallelität ist also slot-basiert und policy-gesteuert.

### Konfliktschutz

Parallele Worker brauchen mindestens:

- **File-Claims**: deklarierter Besitz an Dateien/Teilbäumen
- **Optimistic Conflict Detection**: Warnung bei Überschneidungen
- **Review-Hinweise**: falls zwei Tasks angrenzende Bereiche ändern

### Große Modelle vs. viele Worker

Ein großes Modell kann kleine Epics oft allein erledigen. Für größere Epics ist ein Mix besser:

- **großes Modell** für `stratege`, `architekt`, `triage`, `reviewer`
- **kleinere/schnellere Modelle** für `worker`

Faustregel:

- **kleines, eng zusammenhängendes Epic** → ein starker Worker kann genug sein
- **breites Epic mit mehreren Teilsträngen** → mehrere Worker mit klarer Koordination

Nicht das größte Modell gewinnt, sondern das **beste Orchestrierungsmodell pro Aufgabentyp**.

---

## Review-Kette

### Gewünschter Ablauf

```text
Worker fertig
  → submit_result
  → state: in_review
  → Reviewer dispatch
  → approve => done
  → reject => qa_failed
  → Resume-Paket erzeugen
  → optional erneuter Worker-Dispatch
```

### Resume statt Chat-Wiederverwendung

Bei `qa_failed` soll nicht der gesamte alte Chat stumpf weiterlaufen.

Stattdessen erzeugt das System ein **Resume-Paket**:

- letzter Versuch / Ergebniszusammenfassung
- Review-Kommentar
- Guard-Failures
- betroffene Dateien
- offene DoD-Lücken
- bekannte Fehlannahmen

Damit bleibt der neue Run:

- reproduzierbar
- gezielt
- billiger im Tokenverbrauch
- weniger anfällig für Altlasten aus dem alten Thread

---

## Gemeinsame Artefakte statt freier Kommunikation

### Epic-Scratchpad

Gemeinsamer, strukturierter Koordinationsraum pro Epic:

- Architekturentscheidungen
- API-Verträge
- offene Annahmen
- bekannte Risiken
- wichtige Dateibereiche

### Handoff-Note

Kurzformat zwischen Agenten:

- Quelle
- Zielrolle
- Anlass
- relevante Erkenntnisse
- offene Risiken
- empfohlene nächste Schritte

### File-Claim

Claim auf Datei oder Verzeichnis mit:

- Task
- Worker/Dispatch
- Claim-Typ (`exclusive`, `shared-read`, `shared-edit`)
- TTL / Freigabezeitpunkt

### Resume-Paket

Speziell für `qa_failed` oder Timeouts:

- attempt number
- condensed summary
- rejects / gaps
- changed files
- next best action

---

## Thread-Policy pro Rolle

| Rolle | Empfohlenes Modell | Begründung |
| --- | --- | --- |
| `kartograph` | stateful session | fortlaufende Repo-Erkundung |
| `stratege` | stateful session | Plan-/Roadmap-Kontinuität |
| `architekt` | stateful session pro Epic | konsistente Dekomposition |
| `triage` | stateful session begrenzt | wiederkehrende Muster / Fallhistorie |
| `worker` | stateless per attempt | Reproduzierbarkeit, weniger Drift |
| `reviewer` | stateless per review | neutrale, frische Bewertung |
| `gaertner` | semi-stateful / batchweise | Destillation statt Langdialog |

Thread-Persistenz sollte also **pro Rolle konfigurierbar** sein, nicht global.

### Konkretes Policy-Modell

Empfohlene Werte:

- `stateless`  
  Jeder Lauf startet ohne wiederverwendeten Thread.
- `attempt_stateful`  
  Ein Thread gilt nur fuer einen konkreten Task-Attempt. Ein neuer QA-Reentry startet bewusst einen neuen Thread.
- `epic_stateful`  
  Ein Thread wird ueber mehrere Dispatches innerhalb desselben Epics fortgefuehrt.
- `project_stateful`  
  Ein Thread wird pro Projekt-Rolle wiederverwendet, z. B. fuer laufende Exploration oder Planung.

Aufloesungsreihenfolge:

1. Projekt-Override fuer die Rolle
2. Rollen-Default aus `ai_provider_configs.thread_policy`
3. System-Default pro Rolle

Resume-Konsistenz:

- `worker` und `reviewer` bleiben standardmaessig `attempt_stateful`
- ein `qa_failed`-Reentry bekommt dadurch absichtlich einen frischen Thread-Key
- fachlich stateful Rollen erhalten nur destillierte Session-Hinweise, keinen ungefilterten Alt-Chat

---

## Lernen aus Agenten-Ausgaben

Der Lernertrag lässt sich deutlich steigern, wenn Ergebnisse nicht nur gespeichert, sondern **strukturiert verwertet** werden.

### Relevante Quellen

- Worker-Ergebnisse und Artefakte
- Reviewer-Reject-Gründe
- Resume-Pakete
- Triage-Begründungen
- Architekt-Entscheidungen
- Gaertner-Destillate

### Lernziele

- bessere Prompt-Hinweise für ähnliche Tasks
- Review-Checklisten aus häufigen Reject-Gründen
- Skill-Kandidaten aus wiederkehrenden Fixmustern
- Routing-Hinweise für Triage
- Architektur-Heuristiken für Architekt/Stratege

### Qualitätsregel

Lernen darf nicht aus rohem Chat-Verlauf unkontrolliert in das System kippen. Maßgeblich sind:

- destillierte Zusammenfassungen
- Confidence / Qualität
- Dedupe
- optionaler Review-Gate

### Konkreter Ausführungs-Lern-Loop

Quellen für `execution_learning`:

- `worker_result` aus `submit_result`
- `review_feedback` / `task_review_reject`
- `review_recommendation` mit fehlgeschlagenen Checklist-Punkten
- `resume_package` mit offenen DoD-Lücken oder Guard-Failures

Destillierte Typen:

- `fix_pattern`
- `reject_reason`
- `review_checklist`
- `resume_guidance`
- `skill_candidate`

Rueckkopplung:

1. Prompt-Generator referenziert verwendete Learnings in `prompt_history.context_refs`
2. bei `done` oder `qa_failed` aktualisiert der kanonische Review-Pfad die Erfolgs-/Fehlschlag-Metriken
3. Read-API zeigt pro Learning u. a. `prompt_inclusions`, `success_count` und `qa_failed_count`

Damit bleibt nachvollziehbar, welche Learnings spaeter nur angezeigt wurden und welche tatsaechlich bei erfolgreichen Re-Runs geholfen haben.

---

## Betriebsmodell

### Einstellbar pro Rolle

Folgende Dinge sollten **pro Agent-Rolle** steuerbar sein:

- `stateful_threading`
- `thread_policy`
- `resume_enabled`
- `max_parallel_dispatches`
- `execution_mode`
- `fallback_chain`
- `rpm_limit`
- `token_budget`
- `learning_capture_level`

### Einstellbar pro Epic-Run

Zusätzlich sinnvoll:

- maximale Parallelität
- Dry-Run
- aggressive vs. konservative Scheduling-Strategie
- Auto-Resume aktiv/inaktiv
- projektbezogene `agent_thread_overrides` fuer einzelne Rollen

---

## Runbook

### Operator-Workflow

1. Im Command Deck ein Epic in `scoped` oder `in_progress` öffnen.
2. `Epic Start` beziehungsweise `Run Monitor` öffnen.
3. Zuerst einen Dry-Run mit gewünschter Parallelität, Dispatch-Modus und Resume-Option ausführen.
4. `blockers`, `waiting`, `conflicting` und `slot_plan.dispatch_now` prüfen.
5. Erst bei plausibler Analyse den Live-Run starten.
6. Während des Runs `status`, Worker-Slots, Konflikte, Handoffs, Scratchpads und Resume-Pakete beobachten.

### Wichtige Read-APIs

- `POST /api/epics/{epic_key}/start`
- `GET /api/epics/{epic_key}/runs`
- `GET /api/epic-runs/{run_id}`
- `GET /api/epic-runs/{run_id}/artifacts`
- `GET /api/kpis/execution-learnings`

### Typische Blockerbilder

- `ACTIVE_TASKS_PRESENT`
  Ein Epic läuft bereits teilweise. Entweder vorhandene Tasks sauber abschließen oder bewusst einen Resume-/Reentry-Pfad benutzen.
- `WORKER_MODE_UNAVAILABLE`
  Kein valider Dispatch-Modus. Provider-Konfiguration oder BYOAI/IDE-Modus prüfen.
- `TASKS_MISSING`
  Epic ist noch nicht dekomponiert. Erst Architekt/Task-Erstellung abschließen.
- `WORKSPACE_*`
  Projekt-Onboarding, `repo_host_path` oder `workspace_root` korrigieren.

### Debugging-Hinweise

- Bei unerwartet leerem `dispatch_now` zuerst `slot_plan.occupied_slots`, `queued_runnable` und `conflicting` prüfen.
- Bei QA-Schleifen `resume_package`-Artefakte und `qa_failed_count` gegen `auto_resume_on_qa_failed` abgleichen.
- Bei Parallelitätsproblemen `analysis.scheduler.effective_max_parallel_workers` gegen Run-Wunsch, Projekt-Limits, Rollen-Limits und `HIVEMIND_CONDUCTOR_PARALLEL` prüfen.
- Bei Dateikollisionen die `file_claim`-Artefakte des Runs und die `conflicting[*].reasons[].file_conflicts` vergleichen.
- Bei Review-/Gaertner-Folgen die erzeugten `handoff`, `resume_package` und `scratchpad`-Artefakte im selben Run inspizieren.

### Reproduzierbare Tests

- Backend-Service-Tests: `podman compose exec backend /app/.venv/bin/pytest tests/test_epic_run_service.py tests/test_epic_run_scheduler.py tests/test_epics_router.py -q`
- UI-Typprüfung: `podman compose exec frontend npm run build`

---

## Fazit

Das richtige Zielbild ist weder:

- „ein Worker macht alles“
- noch „alle Worker reden frei miteinander“

sondern:

**kontrolliert parallele Worker, strukturierter geteilter Kontext, automatische Review-Kette, gezielte Resume-Pakete und selektiv stateful Threads nur dort, wo sie wirklich helfen.**

Daraus ergibt sich ein klarer Umsetzungsplan:

1. Epic-Start-Orchestrierung
2. Runnable-Task-Graph
3. Parallel-Worker-Scheduler mit File-Claims
4. Shared Context Artefakte
5. Review- und Resume-Loop
6. Thread-Policy pro Agent-Rolle
7. Lern-Extraktion aus Worker/Reviewer-Ausgaben
8. E2E-Tests und Operator-UI
