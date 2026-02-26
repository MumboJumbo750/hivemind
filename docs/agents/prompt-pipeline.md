# Prompt Pipeline

← [Agenten-Übersicht](./overview.md) | [Index](../../masterplan.md)

Hivemind ist nicht nur Datenspeicher — es ist eine **Prompt-Fabrik**. Für jede Rolle und jeden Workflow-Schritt generiert das System einen strukturierten Prompt. Der User fügt ihn in seinen AI-Client ein. Das ist die User-Pipeline im BYOAI-Modus.

---

## Ablauf

```text
Hivemind                    User                    AI-Client
   |                          |                          |
   |-- generiert Prompt ────→ |                          |
   |                          |-- fügt Prompt ein ─────→ |
   |                          |                          |-- ruft MCP-Tools auf
   |←─── MCP-Calls ───────────────────────────────────── |
   |-- generiert Follow-up → |                          |
   |                          |-- nächste Session ─────→ |
```

Ab Phase 8: AI-Client konsumiert Prompts direkt — kein manueller Schritt mehr.

---

## Prompt-Typen

| Typ | Auslöser | Inhalt |
| --- | --- | --- |
| **Initial-Kartograph** | Neues Projekt / neue Repo | Rolle, Ziel, verfügbare Tools, Startpunkte, Repo-Pfad |
| **Follow-up-Kartograph** | Kartograph-Session war unvollständig | Noch nicht kartierte Bereiche, offene Fragen |
| **Architektur-Prompt** | Epic geht auf `scoped` | Epic-Kontext, DoD-Rahmen, Zerlegungsauftrag |
| **Bibliothekar-Prompt** | Task soll bearbeitet werden (Phase 1–2) | Alle aktiven Skills + Task-Beschreibung |
| **Worker-Prompt** | Task geht auf `ready` | Task + Skills + Docs + DoD |
| **Gaertner-Prompt** | Task geht auf `done` | Abgeschlossener Task, Auftrag: Skills/Docs ableiten |
| **Triage-Prompt** | `[UNROUTED]`-Item vorhanden | Unklares Event, Routing-Optionen, Entscheidungsauftrag |

---

## Beispiel: Worker-Prompt

```
## Rolle: Worker

Du arbeitest an TASK-88 im Rahmen von EPIC-12.

### Dein Auftrag
[task.description]

### Definition of Done
[task.definition_of_done]

### Verfügbare Hivemind-Tools
- hivemind/get_task               — Task-Details laden
- hivemind/get_guards             — Guards für diesen Task laden
- hivemind/report_guard_result    — Guard-Ergebnis melden (passed|failed|skipped)
- hivemind/submit_result          — Ergebnis + Artefakte speichern
- hivemind/update_task_state      — Status setzen (→ in_review nur wenn alle Guards passed)
- hivemind/create_decision_request — eskalieren wenn blockiert

### Kontext (vom Bibliotekar, [630/8000] Tokens)
[Skill: FastAPI Endpoint erstellen — 420 Tokens]
[Doc: EPIC-12 Architektur — 210 Tokens]

### Einschränkungen
- Nur die oben gelisteten Tools sind erlaubt
- Kein Write außerhalb von TASK-88 und EPIC-12
- Setze Status direkt auf in_review, nie auf done
```

---

## Beispiel: Review-Prompt

Der Review-Prompt dient in **Phase 1–7 als strukturierte Checkliste** für den menschlichen Reviewer. Ab **Phase 8** kann er auch für AI-assistiertes Review genutzt werden (AI prüft vor, Owner bestätigt final).

```
## Rolle: Reviewer

Du reviewst TASK-88 im Rahmen von EPIC-12.

### Task-Beschreibung
[task.description]

### Eingereichte Ergebnisse
[task.result — vom Worker via submit_result]

### Artefakte
[task.artifacts — Liste der eingereichten Artefakte]

### Definition of Done — Checkliste
☐ Unit tests >= 80% Coverage       (required: true)
☐ API-Dokumentation aktualisiert   (required: false)

### Guard-Status
✓ ruff check .               passed (0 errors)
✓ pytest --cov-fail-under=80  passed (coverage: 87%)
✗ ./tests/integration/auth.sh FAILED — Connection refused

### Dein Auftrag
1. Prüfe ob alle DoD-Kriterien erfüllt sind
2. Prüfe ob die Guard-Ergebnisse akzeptabel sind
3. Entscheide: GENEHMIGEN (→ done) oder ABLEHNEN (→ qa_failed)
4. Bei Ablehnung: Begründung und konkrete Nachbesserungspunkte angeben

### Verfügbare Aktionen
- [✓ GENEHMIGEN] → Task → done, Gaertner-Prompt wird generiert
- [✗ ABLEHNEN]   → Task → qa_failed (persistenter State; Worker liest Kommentar, setzt dann aktiv zurück auf in_progress)
```

> **Phase 1–7:** Der Review-Prompt wird im Review Panel als vorformatierte Checkliste angezeigt. Der Owner entscheidet manuell — kein AI-Client nötig.
> **Phase 8:** Der Review-Prompt kann an die AI-API gesendet werden für ein automatisches Pre-Review. Die finale Entscheidung (approve/reject) bleibt **immer** beim menschlichen Owner — auch im Auto-Modus.

---

## Prompt-Generierung im Backend

- Prompts werden **serverseitig** generiert, nicht clientseitig zusammengebaut
- Jeder Prompt-Typ hat ein versioniertes Template im Backend
- Templates sind selbst **Skills** (global, lifecycle-managed) — können also verbessert werden
- MCP-Endpunkt: `hivemind/get_prompt { "type": "worker", "task_id": "TASK-88" }`

### Zwei Darstellungsformen

| Modus | Parameter | Inhalt | Einsatz |
| --- | --- | --- | --- |
| **Kompakt** (default) | `assembled: false` | Referenzen kollabiert: `[Skill: FastAPI Endpoint — 420 Tokens]` | Prompt Station — übersichtliche Darstellung, Kopieren |
| **Volltext** | `assembled: true` | Alle Skills/Docs inline expandiert | Volltext-Modal — vollständiger lesbarer Prompt-Text |

Die kompakte Form ist für den User leichter zu überfliegen. Die Volltext-Form ist identisch mit dem, was tatsächlich an den AI-Client gesendet wird — beide Formen teilen dieselbe Token-Zählung.

---

## Prompt Station

→ Wie Prompts im UI angezeigt und verwaltet werden: [Prompt Station](../ui/prompt-station.md)
