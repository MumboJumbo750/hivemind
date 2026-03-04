# Worker — Task-Ausführung & Ergebnislieferung

← [Agenten-Übersicht](./overview.md) | [Index](../../masterplan.md)

Der Worker ist der **ausführende Agent**. Er erhält einen fertig kontextualisierten Task mit Skills, Docs und Guards und liefert das Ergebnis gemäß Definition of Done.

> Analogie: Ein Spezialist der den Einsatzbefehl (Task) vom Architekten erhält, die Ausrüstung (Skills/Docs) vom Bibliothekar bekommt und nach erledigter Arbeit ein Protokoll (Result + Artefakte) abliefert.

---

## Kernaufgaben

1. **Task-Ausführung** — Implementiert die Aufgabe gemäß Description und Definition of Done
2. **Guard-Prüfung** — Führt alle Guards aus und meldet Ergebnisse
3. **Ergebnis-Einreichung** — Speichert Result und Artefakte via `submit_result`
4. **Review-Anforderung** — Setzt Task auf `in_review` (nur wenn alle Guards bestanden)
5. **Eskalation bei Blockade** — Erstellt Decision Requests wenn blockiert

---

## RBAC

Der Worker arbeitet als `developer` oder `admin`:

| Permission | Beschreibung |
| --- | --- |
| `execute_tasks` | Tasks bearbeiten (submit_result, update_task_state, report_guard_result) |
| `read_own_epic` | Eigene Epics und Tasks lesen |
| `read_assigned_task` | Implizit: Task + Epic + Context Boundary lesen wenn via `assigned_to` zugeteilt (auch ohne `project_member`) |
| `read_any_skill` | Alle aktiven Skills sehen |
| `read_any_doc` | Docs im Epic lesen |

> Wie Architekt und Gaertner ist "Worker" keine eigene RBAC-Rolle, sondern eine **Workflow-Funktion**. Die Rechte kommen aus der `developer`- oder `admin`-Rolle.

---

## Typischer Workflow

```text
1. Task ist auf `ready` (Architekt hat Context Boundary + DoD gesetzt)
   → Prompt Station zeigt: "Jetzt: Worker"

2. User fügt Worker-Prompt in AI-Client ein
   → AI liest Task via hivemind/get_task
   → AI liest Guards via hivemind/get_guards

3. AI führt Task aus (Code schreiben, Tests, etc.)

4. AI prüft Guards und meldet Ergebnisse:
   hivemind/report_guard_result {
     "task_id": "TASK-88", "guard_id": "uuid",
     "status": "passed", "result": "All 42 tests passed"
   }

5. AI reicht Ergebnis ein:
   hivemind/submit_result {
     "task_id": "TASK-88",
     "result": "Auth-Endpoint implementiert...",
     "artifacts": [{"type": "file", "path": "src/auth/endpoint.py"}]
   }

6. AI setzt Status auf in_review:
   hivemind/update_task_state { "task_id": "TASK-88", "state": "in_review" }
   → Backend prüft: Guards vollständig? Result vorhanden?
   → Notification an Owner: review_requested

7. Owner reviewed im Review Panel → done oder qa_failed
```

---

## Blockade & Decision Request

Wenn der Worker nicht weiterkommt:

```text
Worker stellt fest: Blocker (z.B. unklare API-Spezifikation)
  → hivemind/create_decision_request {
      "task_id": "TASK-88",
      "blocker": "API-Format unklar: JSON oder XML?",
      "options": [
        {"id": "A", "description": "JSON + OpenAPI", "tradeoffs": "Standard, einfacher"},
        {"id": "B", "description": "XML + XSD", "tradeoffs": "Legacy-kompatibel"}
      ]
    }
  → Task-State: in_progress → blocked
  → SLA-Timer startet (24h → Owner, 48h → Backup, 72h → Admin)
  → Owner löst auf: resolve_decision_request → Task automatisch blocked → in_progress
```

---

## Guard-Sequenz (verpflichtend vor in_review)

> **Phase-abhängiges Verhalten:** Die kanonische Guard-Enforcement-Timeline steht in [guards.md](../features/guards.md#kanonische-guard-enforcement-timeline). Phase 2–4: Guards sind **informativ** (kein Blocker für `in_review`). Ab Phase 5: Guards sind **blockierend** (422 bei offenen Guards).

```text
1. hivemind/get_guards { "task_id": "TASK-88" }
   → Alle Guards laden (global + project + skill + task)

2. Jeden Guard ausführen und Ergebnis melden:
   hivemind/report_guard_result { ..., "status": "passed|failed|skipped", "result": "..." }
   → skipped nur bei Guards mit skippable = true, mit Begründung

3. hivemind/submit_result { "task_id": "TASK-88", "result": "...", "artifacts": [...] }

4. hivemind/update_task_state { "task_id": "TASK-88", "state": "in_review" }
   → Phase 2–4: 422 nur wenn Result fehlt (Guards nicht geprüft)
   → Ab Phase 5: 422 wenn Guards offen oder Result fehlt
```

---

## qa_failed-Loop

```text
Owner rejected TASK-88 (1. Mal):
  → qa_failed, review_comment gesetzt
  → Worker liest Kommentar
  → Worker: update_task_state { "state": "in_progress" }
  → Guards werden auf pending zurückgesetzt
  → Worker behebt Probleme, wiederholt Guard-Sequenz + submit_result

Owner rejected TASK-88 (3. Mal):
  → qa_failed, qa_failed_count = 3
  → Worker versucht: update_task_state { "state": "in_progress" }
  → System intercepted: qa_failed_count >= 3 → Task auf escalated
  → Admin muss resolve_escalation aufrufen
```

> **Guard-Reset:** Bei jeder Transition `qa_failed → in_progress` werden alle `task_guards`-Einträge auf `status = 'pending'` zurückgesetzt. Der Worker muss alle Guards erneut bestehen.

---

## ⚠️ Operative Hinweise für Worker-Agents

### MCP-Tool-Aufrufe

Alle MCP-Tools laufen über **einen** Endpoint. Es gibt **keine** individuellen REST-Endpoints pro Tool:

```bash
# ✅ RICHTIG:
curl -X POST http://localhost:8000/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{"tool": "hivemind/submit_result", "arguments": {"task_key": "TASK-88", "result": "..."}}'

# ❌ FALSCH (404!):
curl http://localhost:8000/api/mcp/submit_result
curl http://localhost:8000/api/mcp/update_task_state
```

### Host-Einschränkungen

- **Kein Python auf dem Windows-Host!** `python scripts/mcp_call.py ...` schlägt fehl (nur Microsoft Store Stub).
- Scripts müssen via Container ausgeführt werden:
  ```bash
  podman compose exec backend /app/.venv/bin/python /workspace/scripts/mcp_call.py \
    "hivemind/get_task" '{"task_key": "TASK-88"}'
  ```
- Alternativ: `curl` oder PowerShell `Invoke-WebRequest` direkt vom Host.

### PowerShell-Besonderheiten

- Backticks (`` ` ``) in Here-Strings (`@"..."@`) werden als Escape-Sequenzen interpretiert
- Markdown mit Code-Backticks in JSON-Bodys führt zu **Parse-Errors**
- **Lösung:** JSON in Datei auslagern und mit `Get-Content payload.json -Raw` einlesen

---

## MCP-Tools

```text
-- Lesen
hivemind/get_task           { "id": "TASK-88" }
hivemind/get_guards         { "task_id": "TASK-88" }

-- Schreiben
hivemind/report_guard_result     { "task_id": "TASK-88", "guard_id": "uuid",
                                   "status": "passed|failed|skipped",
                                   "result": "output text" }
hivemind/submit_result           { "task_id": "TASK-88", "result": "...", "artifacts": [...] }
hivemind/update_task_state       { "task_id": "TASK-88", "state": "in_review" }
hivemind/create_decision_request { "task_id": "TASK-88", "blocker": "...", "options": [...] }
```

---

## Context Boundary

Der Worker sieht nur was der Architekt via Context Boundary erlaubt hat:

- **Mit Boundary:** Nur erlaubte Skills + Docs, bis `max_token_budget`
- **Ohne Boundary:** Bibliothekar wählt per Similarity (aber trotzdem Token-Budget-begrenzt)
- **Wiki:** Immer verfügbar (ignoriert Context Boundary)
- **Kartograph-Ausnahme:** Gilt nicht für Worker — Worker hat standardmäßig aktiven Kontextfilter

---

## Solo-Modus

Im Solo-Modus ist der Entwickler selbst der Worker. Der Worker-Prompt strukturiert die Arbeit und erzwingt Guard-Prüfung + Result-Einreichung bevor ein Review stattfindet — auch bei Self-Review.

---

## Abgrenzung

| | Worker | Architekt | Gaertner | Kartograph |
| --- | --- | --- | --- | --- |
| Timing | Während Task-Bearbeitung | Vor Task-Start | Nach Task-Abschluss | Initial + iterativ |
| Input | Ready Task + Context | Gescoptes Epic | Abgeschlossener Task | Unbekanntes Repo |
| Output | Result + Artefakte | Tasks, Boundaries | Skills, Decision Records | Wiki, Epic-Docs |
| Fokus | Ausführen & Liefern | Planen & Zerlegen | Konservieren & Destillieren | Entdecken & Kartieren |
