# Audit-Report: Workflows, Dispatching & Agents

**Datum:** 2026-03-08
**Scope:** Conductor, Agentic Dispatch, Prompt Pipeline, Agent Integration, Frontend-Backend Konsistenz

---

## Executive Summary

Die Codebase ist insgesamt **produktionsreif** mit sauberer Architektur (State Machine → TaskService → Conductor → Agentic Dispatch → MCP Tools). Keine TODO/FIXME/HACK-Kommentare im gesamten Code. Alle Imports werden genutzt, kein Dead Code gefunden.

Dennoch gibt es **6 Kategorien** mit insgesamt **18 konkreten Findings**, die in 4 Epics organisiert werden.

---

## Kategorie A: Fehlende Frontend-UIs (Backend-APIs vorhanden)

### A-1: Learning Artifacts Dashboard fehlt
- **Schwere:** Mittel
- **Ist:** `GET /api/learning/artifacts` + `/stats` vollständig implementiert (12 Filter-Parameter, Paginierung)
- **Soll:** Dedizierte View für Learning Artifacts mit Filterung, Statistiken, Confidence-Anzeige
- **Dateien:** `backend/app/routers/learning.py`, `backend/app/services/learning_artifacts.py`
- **Impact:** Gaertner-Ergebnisse sind nur via API sichtbar, kein Operator-Überblick

### A-2: Dispatch Policies CRUD UI fehlt
- **Schwere:** Mittel
- **Ist:** `GET/PUT/DELETE /api/dispatch/policies/{role}` + Status-Endpoint vollständig
- **Soll:** Settings-Unterseite für Dispatch-Policy-Konfiguration (RPM, Token-Budget, Cooldown, Parallelismus pro Agent-Rolle)
- **Dateien:** `backend/app/routers/dispatch_policies.py` (176 LOC)
- **Impact:** Operator muss API direkt ansprechen für Policy-Änderungen

### A-3: Agent Thread Session View fehlt
- **Schwere:** Niedrig
- **Ist:** `AgentThreadSession` Model mit Thread-Policies (stateless/attempt/epic/project)
- **Soll:** Debug-/Monitoring-View für laufende Agent-Sessions mit Thread-Context
- **Dateien:** `backend/app/models/agent_thread_session.py`, `backend/app/services/agent_threading.py`
- **Impact:** Kein Einblick in Agent-Kontext-Kontinuität während Epic Runs

### A-4: Governance Audit View fehlt
- **Schwere:** Niedrig
- **Ist:** Governance-Levels konfigurierbar (manual/assisted/auto), Recommendations in DB gespeichert
- **Soll:** Audit-Trail-View für Governance-Entscheidungen (wer hat was autorisiert, welche Recommendations wurden überschrieben)
- **Dateien:** `backend/app/services/conductor.py:968-975` (Governance Outcome)
- **Impact:** Kein Audit-Überblick für Governance-Compliance

---

## Kategorie B: Agentic Dispatch Robustness

### B-1: Silent Exception Swallowing in _parse_text_tool_calls
- **Schwere:** Mittel
- **Ist:** `agentic_dispatch.py:202-203` — bare `except: pass` schluckt alle Parsing-Fehler
- **Soll:** Debug-Level Logging vor dem `pass`, damit fehlerhafte Tool-Calls nachvollziehbar sind
- **Dateien:** `backend/app/services/agentic_dispatch.py:186-204`
- **Impact:** Debugging bei kaputten Provider-Responses (z.B. GitHub Copilot Proxy) ist blind

### B-2: Kein Circuit Breaker für AI Provider
- **Schwere:** Mittel
- **Ist:** Exponential Backoff (1s→2s→4s, max 3 Attempts) bei 429/503, aber kein Circuit Breaker
- **Soll:** Nach N konsekutiven Failures pro Provider temporär auf Fallback-Provider oder BYOAI wechseln
- **Dateien:** `backend/app/services/ai_provider.py:222-264`
- **Impact:** Dauerhaft fehlender Provider blockiert alle Dispatches bis Cooldown abläuft

### B-3: Prompt-Truncation ohne Notification
- **Schwere:** Niedrig
- **Ist:** `MAX_PROMPT_CHARS=60_000` — Prompt wird stumm abgeschnitten (`agentic_dispatch.py:347-352`)
- **Soll:** Warnung im System-Prompt einbauen: "Kontext wurde gekürzt, nutze MCP-Tools für Details"
- **Impact:** Agent arbeitet mit unvollständigem Kontext ohne es zu wissen

### B-4: Text-Tool-Call Parser ohne Schema-Validierung
- **Schwere:** Niedrig
- **Ist:** `_parse_text_tool_calls` extrahiert Name + Arguments, validiert aber nicht gegen Tool-Schema
- **Soll:** Optional: Tool-Name gegen registrierte Tools prüfen, unbekannte Tools loggen
- **Dateien:** `backend/app/services/agentic_dispatch.py:186-204`
- **Impact:** Halluzinierte Tool-Names werden an MCP-Handler weitergereicht und scheitern dort

---

## Kategorie C: Conductor & Orchestration Gaps

### C-1: merge_subtasks Prompt Type fehlt
- **Schwere:** Mittel
- **Ist:** Conductor referenziert konzeptionell Subtask-Merging, aber kein Prompt-Type `merge_subtasks` in `prompt_generator.py`
- **Soll:** Prompt-Type implementieren oder explizit aus dem Design entfernen
- **Dateien:** `backend/app/services/prompt_generator.py`
- **Impact:** Subtask-Ergebnisse können nicht automatisch zu Task-Result zusammengeführt werden

### C-2: skip_conductor in Epic Run Scheduler umgeht Governance
- **Schwere:** Mittel
- **Ist:** `epic_run_scheduler.py:216,264` — `skip_conductor=True` bei Batch-Dispatches, um Double-Dispatch zu vermeiden
- **Soll:** Governance-Check separat vom Dispatch-Hook durchführen, sodass Batch-Dispatches trotzdem governance-geprüft sind
- **Dateien:** `backend/app/services/epic_run_scheduler.py:197-230`, `backend/app/services/task_service.py`
- **Impact:** Tasks in Epic Runs laufen ohne Governance-Gate (assisted/auto Unterscheidung verloren)

### C-3: Kein Retry-Mechanismus für transiente Fehler im Local Dispatch
- **Schwere:** Niedrig
- **Ist:** Local-Mode Fehler → sofortiger Fallback auf BYOAI (`conductor.py:925-954`)
- **Soll:** 1x Retry mit kurzem Backoff bei transienten Fehlern (Timeout, Connection Reset), dann erst Fallback
- **Dateien:** `backend/app/services/conductor.py:851-1016`
- **Impact:** Einmalige Netzwerkfehler führen direkt zu manuellem Modus

### C-4: Governance assisted→auto Auto-Transition unvollständig
- **Schwere:** Niedrig
- **Ist:** Governance-Recommendations werden gespeichert, aber Auto-Transition von assisted zu auto bei konsistent guten Ergebnissen nicht implementiert
- **Soll:** Optional: Confidence-basierte Auto-Promotion (z.B. 10 konsekutive approves mit confidence >0.9 → auto)
- **Dateien:** `backend/app/services/conductor.py:697, 968-975`
- **Impact:** Governance-Level bleibt statisch, kein adaptives Vertrauen

---

## Kategorie D: Integration & E2E Testing

### D-1: IDE Dispatch Flow ungetestet
- **Schwere:** Mittel
- **Ist:** Endpoints existieren (`/conductor/dispatches/pending`, `/acknowledge`, `/running`, `/complete`), Timeout-Job implementiert (`conductor_ide_timeout.py`)
- **Soll:** E2E-Test mit VSCode Extension: Dispatch → Acknowledge → Running → Complete/Timeout
- **Dateien:** `backend/app/routers/conductor.py`, `backend/app/services/conductor_ide_timeout.py`
- **Impact:** IDE-Modus untested — Timeout-Behavior und Fallback unklar

### D-2: Worker Endpoint Pool nicht E2E validiert
- **Schwere:** Niedrig
- **Ist:** Pool-Strategien (round_robin, weighted, least_busy) im AI-Provider implementiert
- **Soll:** Integration-Test mit 2+ Ollama-Endpoints, Failover-Szenario, Load-Balancing-Verifikation
- **Dateien:** `backend/app/services/ai_provider.py` (Pool-Logic)
- **Impact:** Multi-Endpoint-Setup in Produktion ungetestet

---

## Kategorie E: Prompt Pipeline Konsistenz

### E-1: Minification Divergenz zwischen History und AI
- **Schwere:** Niedrig
- **Ist:** Prompt History speichert Original-Text, AI bekommt minifizierten Text (QMD)
- **Soll:** Entweder beides speichern (original + minified) oder Token-Count auf minified Basis berechnen
- **Dateien:** `backend/app/services/prompt_generator.py`
- **Impact:** Token-Verbrauch in History weicht von tatsächlichem AI-Verbrauch ab (10-20%)

---

## Kategorie F: Federation Schema

### F-1: Skills ohne assigned_node_id
- **Schwere:** Info
- **Ist:** `tasks.assigned_node_id` und `epics.assigned_node_id` existieren, `skills` hat nur `origin_node_id`
- **Soll:** Prüfen ob Skill-Delegation (Peer schreibt Skill im Auftrag eines anderen Nodes) geplant ist — falls ja, Feld ergänzen
- **Dateien:** `backend/app/models/skill.py`
- **Impact:** Kein funktionaler Bug, aber potenziell fehlende Federation-Capability

---

## Zusammenfassung nach Schwere

| Schwere | Anzahl | Findings |
|---------|--------|----------|
| Mittel  | 7      | A-1, A-2, B-1, B-2, C-1, C-2, D-1 |
| Niedrig | 9      | A-3, A-4, B-3, B-4, C-3, C-4, D-2, E-1, F-1 |
| Info    | 1      | F-1 |

---

## Empfohlene Epics

1. **EPIC-AUDIT-UI** — Fehlende Operator-UIs nachrüsten (A-1, A-2, A-3, A-4)
2. **EPIC-AUDIT-DISPATCH** — Agentic Dispatch Hardening (B-1, B-2, B-3, B-4)
3. **EPIC-AUDIT-CONDUCTOR** — Conductor Orchestration Fixes (C-1, C-2, C-3, C-4)
4. **EPIC-AUDIT-E2E** — Integration Tests & Konsistenz (D-1, D-2, E-1, F-1)
