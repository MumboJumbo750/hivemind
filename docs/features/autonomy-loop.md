# Autonomy Loop — Vom BYOAI zur autarken Pipeline

← [Agent Skills](./agent-skills.md) | [Phase 8](../phases/phase-8.md) | [Index](../../masterplan.md)

In Phase 8 können alle 6 Agenten automatisiert via AI-Provider laufen. Aber **automatisierte Agenten ≠ autarkes System**. Ohne zusätzliche Mechanismen bricht der Loop an 5 Human-Gates — das System automatisiert die Arbeit, kann sie aber nicht eigenständig orchestrieren und freigeben.

Dieses Dokument schließt die Lücke: **Conductor**, **Reviewer-Skill** und **Governance-Levels** machen aus automatisierten Agenten einen selbststeuernden Kreislauf.

---

## Das Problem: Wo der Loop bricht

```text
Externer Input (Plan, Code, Event)
  → Kartograph erkundet Repo                       ✓ AI-automatisiert
  → Stratege plant → Epic-Proposals                 ✓ AI-automatisiert
  → ❌ GATE 1: Epic-Proposal akzeptieren            Admin manuell (Triage)
  → ❌ GATE 2: Epic scopen (incoming → scoped)      Owner manuell
  → Architekt zerlegt → Tasks                       ✓ AI-automatisiert
  → Worker führt aus                                ✓ AI-automatisiert
  → ❌ GATE 3: Review-Gate (in_review → done)       Owner manuell
  → Gaertner destilliert                            ✓ AI-automatisiert
  → ❌ GATE 4: Skill-Proposal mergen                Admin manuell
  → ❌ GATE 5: Decision Requests lösen              Owner/Admin manuell
```

**5 Human-Gates**, davon 3 im kritischen Pfad (Gate 1, 2, 3). Ohne diese Gates wartet das System endlos — jeder automatisierte Agent produziert Output der nie weiterverarbeitet wird.

---

## Lösung: Drei neue Konzepte

### Übersicht

| Konzept | Löst | Phase |
| --- | --- | --- |
| **Conductor** | "Wer triggert den nächsten Agenten?" — Event-getriebene Orchestrierung | Phase 8 |
| **Reviewer-Skill** | Gate 3 (Review) — AI-Pre-Review + 1-Click-Confirmation | Phase 8 |
| **Governance-Levels** | Gates 1, 2, 4, 5 — abgestufte Automatisierung pro Entscheidungstyp | Phase 8 |

---

## 1. Conductor — Event-getriebener Orchestrator

### Warum ein Conductor?

In Phase 1–7 ist der Conductor der **Mensch**: die Prompt Station sagt "Jetzt: Worker" → der User kopiert den Prompt. In Phase 8 fehlt dieses Bindeglied. Ohne Conductor generiert das Backend Prompts die niemand abholt.

### Design

Der Conductor ist **kein Agent** (er hat keine AI-Intelligenz), sondern ein **Backend-Service** der auf State-Transitions und Events reagiert und den nächsten Agenten triggert. Er ist das serverseitige Äquivalent der Prompt Station.

```text
Event/State-Transition  →  Conductor entscheidet  →  Agent-Dispatch

Beispiel:
  SSE: task_state_changed { new_state: "done" }
    → Conductor: "Task done → Gaertner braucht Prompt"
    → Lookup ai_provider_configs["gaertner"]
    → Konfiguriert? → Prompt generieren + an AI-Provider senden
    → Nicht konfiguriert? → Prompt Station zeigt Prompt (BYOAI-Fallback)
```

### Dispatch-Regeln (kanonisch)

| Trigger-Event | Bedingung | Dispatched Agent | Prompt-Typ |
| --- | --- | --- | --- |
| Epic `incoming → scoped` | `governance.epic_scoping = 'auto'` | Architekt | `architekt` |
| Epic `incoming` (neu) | `governance.epic_scoping = 'auto'` | Conductor auto-scopes | — (kein Agent, interner Transition) |
| Task `scoped → ready` | — | Worker (nach Bibliothekar-Assembly) | `worker` |
| Task `in_review` | `governance.review = 'assisted'\|'auto'` | Reviewer | `review` |
| Task `done` | — | Gaertner | `gaertner` |
| `[UNROUTED]` Event eingetroffen | — | Triage | `triage` |
| `[EPIC PROPOSAL]` eingereicht | `governance.epic_proposals = 'auto'` | Triage (auto-accept) | `triage` |
| `[SKILL PROPOSAL]` eingereicht | `governance.skill_merge = 'auto'` | Auto-Merge-Check | — |
| Projekt erstellt + Repo vorhanden | — | Kartograph | `kartograph` |
| Kartograph-Session beendet + Plan vorhanden | — | Stratege | `stratege` |
| GitLab `push`-Event (Phase 8) | Kartograph follow-up nötig | Kartograph | `kartograph` |
| `decision_request` erstellt | `governance.decisions = 'assisted'\|'auto'` | Decision-Resolver | — |

### Implementierung

```python
# conductor.py — Event Listener (Teil des Backend-Services, kein eigener Container)

class Conductor:
    """Event-getriebener Orchestrator für Phase 8 Auto-Modus."""

    async def on_task_state_changed(self, event: TaskStateChanged):
        match event.new_state:
            case "ready":
                await self.dispatch_agent("worker", task_id=event.task_key)
            case "in_review":
                await self.dispatch_review(event.task_key)
            case "done":
                await self.dispatch_agent("gaertner", task_id=event.task_key)

    async def on_epic_state_changed(self, event: EpicStateChanged):
        match event.new_state:
            case "scoped":
                await self.dispatch_agent("architekt", epic_id=event.epic_key)

    async def on_unrouted_event(self, event: UnroutedEvent):
        await self.dispatch_agent("triage")

    async def dispatch_agent(self, role: str, **kwargs):
        """Generiert Prompt + sendet an konfigurierten AI-Provider."""
        config = await self.get_provider_config(role)
        if not config or not config.enabled:
            return  # BYOAI-Fallback — Prompt Station zeigt Prompt
        prompt = await self.generate_prompt(role, **kwargs)
        await self.ai_provider_service.send(config, prompt)

    async def dispatch_review(self, task_key: str):
        """Review-Dispatch mit Governance-Level."""
        level = await self.get_governance_level("review")
        match level:
            case "manual":
                pass  # Prompt Station zeigt Review-Prompt an Owner
            case "assisted":
                await self.dispatch_agent("reviewer", task_id=task_key)
                # AI pre-reviewed → Owner bekommt 1-Click-Confirmation
            case "auto":
                await self.dispatch_agent("reviewer", task_id=task_key)
                # AI reviewed → auto-approve wenn confidence > threshold
```

### Dispatch-Parallelität & Backpressure

Nicht alle Dispatches sind gleichwertig. Der Conductor unterscheidet zwischen **unabhängigen** (parallel) und **abhängigen** (sequenziell) Dispatches:

```python
# UNABHÄNGIGE Dispatches: parallel — kein gemeinsamer State, kein Output-Dependency
async def on_multiple_tasks_ready(task_ids: list[str]):
    await asyncio.gather(*[
        self.dispatch_agent("worker", task_id=tid)
        for tid in task_ids
    ])
    # Alle Worker starten gleichzeitig — IO-bound (AI-API-Calls), kein Event-Loop-Block

# ABHÄNGIGE Dispatches: sequenziell — Output A ist Input B
async def on_task_scoped(task_id: str):
    context = await self.dispatch_agent("bibliothekar", task_id=task_id)
    # Bibliothekar MUSS fertig sein bevor Worker startet
    await self.dispatch_agent("worker", task_id=task_id, context=context)

# SERIELL durch Geschäftsregel: Epic-Scoping vor Architekt-Dekomposition
async def on_epic_incoming(epic_id: str):
    await self.auto_scope_epic(epic_id)          # atomic: scoped
    await self.dispatch_agent("architekt", epic_id=epic_id)  # danach
```

**Parallelitäts-Grenze:** `HIVEMIND_CONDUCTOR_PARALLEL = 3` (Default) begrenzt die Gesamtzahl gleichzeitiger Dispatches via `asyncio.Semaphore`. Überschreitung → Queue im Conductor. Nicht: Thread-Blocking, sondern: await auf freien Slot.

**RPM-Limit als primäre Backpressure:**

Der natürliche Throttle-Mechanismus sind die `rpm_limit`-Felder in `ai_provider_configs`:

```text
ai_provider_configs:
  worker:     rpm_limit = 10  (Ollama lokal → 10 Req/Min max)
  kartograph: rpm_limit = 5   (Gemini API → Rate-Limit-freundlich)
  gaertner:   rpm_limit = 10  (Claude → Default)

Conductor-Verhalten bei RPM-Überschreitung:
  → Token Bucket pro Agent-Rolle (nicht pro Dispatch)
  → Bei voller Bucket: await asyncio.sleep(backoff) — KEIN Fehler
  → Backoff: 60s / rpm_limit (z.B. bei 10 RPM: 6s zwischen Requests)
  → Keine externe Queue nötig — asyncio.sleep() hält Event Loop frei
```

**Warum keine externe Message Queue:**

Für Single-Node-Betrieb (Docker Compose, ein Backend-Prozess) ist asyncio ausreichend:

| Bedarf | Unsere Lösung | Externe Queue nötig wenn... |
| --- | --- | --- |
| At-least-once Delivery | `sync_outbox` + Retry (Outbox IS die Queue) | Mehrere Backend-Prozesse |
| Task-Priorität | `asyncio.PriorityQueue` im Conductor | >10k Dispatches/Sekunde |
| Guard-Execution | `asyncio.to_thread()` + `asyncio.Semaphore` | Guards > 5 Min (dann Sidecar) |
| AI-API-Calls | `httpx.AsyncClient` (non-blocking by design) | Nie nötig |

### Conductor-Garantien

| Garantie | Mechanismus |
| --- | --- |
| **Idempotenz** | Jeder Dispatch erzeugt einen `conductor_dispatch`-Eintrag mit `idempotency_key`. Doppelte Events → Noop |
| **Retry** | Fehlgeschlagene AI-Provider-Calls → Exponential Backoff (wie in Phase 8 spezifiziert) |
| **Audit** | Jeder Dispatch wird geloggt: welcher Event → welcher Agent → welcher Provider → Ergebnis |
| **BYOAI-Fallback** | Nicht-konfigurierte Rollen bleiben manuell — Conductor dispatcht nur wo ein Provider konfiguriert ist |
| **Kein Eigenleben** | Conductor reagiert nur auf Events — er initiiert nie selbst eine Aktion ohne Auslöser |
| **Concurrency** | Maximal `HIVEMIND_CONDUCTOR_PARALLEL` gleichzeitige Dispatches (Default: 3). Überlauf → Queue |

### Konfiguration

| Env-Variable | Default | Beschreibung |
| --- | --- | --- |
| `HIVEMIND_CONDUCTOR_ENABLED` | `false` | Conductor aktivieren (Phase 8) |
| `HIVEMIND_CONDUCTOR_PARALLEL` | `3` | Max. gleichzeitige Agent-Dispatches |
| `HIVEMIND_CONDUCTOR_COOLDOWN_SECONDS` | `10` | Mindestzeit zwischen Dispatches für denselben Kontext (Epic/Task) |

---

## 2. Reviewer-Skill — AI-Pre-Review

### Warum?

Das Review-Gate ist **Design-Prinzip #5** ("Review-Gate immer aktiv"). Es wird nie entfernt. Aber in Phase 8 kann ein AI-Reviewer die Vorarbeit leisten — der Owner bestätigt nur noch.

### Governance-abhängiges Verhalten

| Review-Level | Verhalten | Owner-Aufwand |
| --- | --- | --- |
| `manual` (Default) | Kein AI-Review. Owner reviewed vollständig wie bisher | Hoch |
| `assisted` | AI-Reviewer pre-reviewed + gibt Empfehlung. Owner sieht: "AI empfiehlt Approve ✓" + kann 1-Click bestätigen oder überschreiben | Niedrig |
| `auto` | AI-Reviewer reviewed + auto-approved wenn Confidence ≥ Threshold. Owner wird notifiziert + kann innerhalb von `auto_review_grace_period` widersprechen. Bei Widerspruch: Revert auf `in_review` | Minimal (nur bei Widerspruch) |

### Reviewer System-Skill

```markdown
---
title: "hivemind-reviewer"
service_scope: ["system"]
stack: ["hivemind"]
---

# Reviewer — AI-gestütztes Code-Review

## Rolle
Du bist der Reviewer. Du prüfst eingereichte Task-Ergebnisse gegen die
Definition of Done, Guard-Ergebnisse und Skill-Instruktionen.

## Workflow
1. Task-Kontext laden:
   hivemind/get_task { "id": "TASK-88" }
   → result, artifacts, definition_of_done studieren

2. Guard-Ergebnisse prüfen:
   hivemind/get_guards { "task_id": "TASK-88" }
   → Alle Guards passed/skipped? Begründungen bei skipped plausibel?

3. Definition of Done abgleichen:
   → Jedes DoD-Kriterium: Ist es durch Result + Artefakte erfüllt?
   → Fehlende Kriterien explizit benennen

4. Skill-Konformität prüfen:
   hivemind/get_skills { "task_id": "TASK-88" }
   → Folgt die Implementierung den Skill-Instruktionen?
   → Gibt es Abweichungen die begründet sind?

5. Code-Qualität bewerten (falls Artefakte Code enthalten):
   → Lesbarkeit, Fehlerbehandlung, Edge Cases
   → Bekannte Anti-Patterns erkennen

6. Entscheidung treffen:
   Confidence: 0.0–1.0

   Bei Confidence ≥ 0.85:
     hivemind/submit_review_recommendation {
       "task_id": "TASK-88",
       "recommendation": "approve",
       "confidence": 0.92,
       "summary": "DoD erfüllt, alle Guards passed, Code sauber.",
       "checklist": [
         { "criterion": "Unit Tests >= 80%", "status": "passed", "detail": "87% coverage" },
         { "criterion": "API-Docs aktualisiert", "status": "passed", "detail": "OpenAPI spec updated" }
       ]
     }

   Bei Confidence < 0.85:
     hivemind/submit_review_recommendation {
       "task_id": "TASK-88",
       "recommendation": "needs_human_review",
       "confidence": 0.62,
       "summary": "Guard passed aber DoD-Kriterium 'Integration Tests' unklar.",
       "concerns": ["Integration-Test-Coverage nicht verifizierbar aus Artefakten"]
     }

   Bei klarem Fehler:
     hivemind/submit_review_recommendation {
       "task_id": "TASK-88",
       "recommendation": "reject",
       "confidence": 0.95,
       "summary": "Guard 'ruff check' passed, aber hardcoded API-Key in src/config.py:42",
       "concerns": ["Security: hardcoded secret"]
     }

## Einschränkungen
- Nicht: Direkt approve_review oder reject_review aufrufen (das entscheidet der Governance-Level)
- Nicht: Code ausführen oder Tests laufen lassen (das machen Guards)
- Immer: Confidence-Score angeben — bei Unsicherheit lieber needs_human_review
- Immer: Konkrete Zeilen/Dateien referenzieren wenn Probleme gefunden
```

### Review-Governance-Flow

```text
Governance: "manual"
  Task in_review → Prompt Station zeigt Review-Prompt → Owner reviewed manuell

Governance: "assisted"
  Task in_review
    → Conductor dispatcht Reviewer an AI-Provider
    → AI: submit_review_recommendation { recommendation: "approve", confidence: 0.92 }
    → Backend speichert Recommendation
    → Owner sieht im Review-Panel:
      ┌──────────────────────────────────────────────┐
      │  AI-REVIEW ✓  Empfehlung: APPROVE            │
      │  Confidence: 92%                              │
      │  "DoD erfüllt, alle Guards passed."           │
      │                                               │
      │  [✓ APPROVE]  [✗ REJECT]  [DETAILS ▤]       │
      └──────────────────────────────────────────────┘
    → Owner klickt [APPROVE] → approve_review (1 Click statt Deep Review)
    → Owner klickt [REJECT] → reject_review mit eigenem Kommentar

Governance: "auto"
  Task in_review
    → Conductor dispatcht Reviewer
    → AI: submit_review_recommendation { recommendation: "approve", confidence: 0.92 }
    → Confidence ≥ auto_review_threshold (Default: 0.90)?
      → Ja: Backend führt automatisch approve_review aus
        → Owner wird notifiziert: "TASK-88 auto-approved (AI: 92% Confidence)"
        → Grace Period: Owner kann innerhalb von HIVEMIND_AUTO_REVIEW_GRACE_MINUTES
          (Default: 30) widersprechen → revert auf in_review
      → Nein: Fallback auf "assisted" — Owner muss bestätigen
    → AI: recommendation "reject" → IMMER Fallback auf "assisted" (nie auto-reject)
```

### MCP-Tools (Reviewer)

```text
-- Lesen (geteilt)
hivemind/get_task            { "id": "TASK-88" }
hivemind/get_guards          { "task_id": "TASK-88" }
hivemind/get_skills          { "task_id": "TASK-88" }

-- Schreiben (Reviewer-spezifisch)
hivemind/submit_review_recommendation  { "task_id": "TASK-88",
                                         "recommendation": "approve|reject|needs_human_review",
                                         "confidence": 0.92,
                                         "summary": "...",
                                         "checklist": [...],     -- optional
                                         "concerns": [...] }    -- optional bei reject/needs_human_review
                                         -- Speichert Empfehlung in review_recommendations
                                         -- Triggert NICHT approve_review/reject_review direkt
                                         -- Governance-Level entscheidet über nächsten Schritt
                                         -- Erfordert: reviewer-Berechtigung (system-intern, nicht user-aufrufbar)
```

### Konfiguration

| Setting | Default | Beschreibung |
| --- | --- | --- |
| `governance.review` | `manual` | Review-Level: `manual`, `assisted`, `auto` |
| `auto_review_threshold` | `0.90` | Mindest-Confidence für Auto-Approve |
| `HIVEMIND_AUTO_REVIEW_GRACE_MINUTES` | `30` | Grace Period nach Auto-Approve (Owner kann widersprechen) |

---

## 3. Governance-Levels — Abgestufte Automatisierung

### Prinzip

Nicht alle Entscheidungen sind gleich kritisch. Ein Skill-Merge nach 3 erfolgreichen Einsätzen ist weniger riskant als ein neues Epic zu akzeptieren. Governance-Levels erlauben dem Admin, **pro Entscheidungstyp** den Automatisierungsgrad zu wählen.

### Die drei Stufen

| Level | Bedeutung | Mensch-Aufwand |
| --- | --- | --- |
| `manual` | Mensch entscheidet. System unterstützt mit Kontext (wie Phase 1–7) | Voll |
| `assisted` | AI analysiert + empfiehlt. Mensch bestätigt mit 1-Click | Niedrig |
| `auto` | AI entscheidet + führt aus. Mensch wird notifiziert + kann widersprechen | Minimal |

### Governance-Matrix

| Entscheidungstyp | `manual` | `assisted` | `auto` | Default | Risiko |
| --- | --- | --- | --- | --- | --- |
| **Review** (Gate 3) | Owner reviewed komplett | AI pre-reviewed, Owner 1-Click | AI auto-approved (Grace Period) | `manual` | Mittel |
| **Epic-Proposals** (Gate 1) | Admin reviewed in Triage | AI bewertet Proposal-Qualität, Admin 1-Click | AI auto-accepts wenn Score ≥ Threshold | `manual` | Hoch |
| **Epic-Scoping** (Gate 2) | Owner scopt manuell | Architekt schlägt Scope vor, Owner bestätigt | Auto-Scope basierend auf Kartograph-Daten | `manual` | Mittel |
| **Skill-Merge** (Gate 4) | Admin reviewed Proposal | AI prüft Qualität + Duplikate, Admin 1-Click | Auto-Merge nach N erfolgreichen Einsätzen | `manual` | Niedrig |
| **Guard-Merge** | Admin reviewed | AI prüft Allowlist-Kompatibilität | Auto-Merge (Guards sind deterministisch) | `manual` | Niedrig |
| **Decision Requests** (Gate 5) | Owner entscheidet | AI analysiert Optionen, empfiehlt Owner | AI entscheidet wenn Optionen klar gewichtet | `manual` | Hoch |
| **Escalation-Resolution** | Admin löst auf | AI schlägt Resolution vor | AI resolved + reassigned wenn Pattern bekannt | `manual` | Hoch |

### Auto-Bedingungen (Safeguards)

Auto-Level ist nie bedingungslos. Jeder Entscheidungstyp hat **Safeguards** die auf `assisted` zurückfallen:

| Entscheidungstyp | Auto-Bedingung | Fallback auf `assisted` wenn... |
| --- | --- | --- |
| **Review** | AI-Confidence ≥ `auto_review_threshold` | Confidence < Threshold ODER recommendation = "reject" |
| **Epic-Proposals** | Proposal hat Rationale + kein Duplikat + depends_on aufgelöst | Duplikat erkannt ODER depends_on auf abgelehntes Proposal |
| **Epic-Scoping** | Kartograph hat ≥ 80% Code-Coverage im relevanten Bereich | Coverage < 80% ODER < 3 Wiki-Artikel im Bereich |
| **Skill-Merge** | Skill wurde ≥ 3× erfolgreich in Tasks eingesetzt (via `skill_task_links`) | Erster Einsatz ODER bestehende Skill-Duplikat-Warnung |
| **Guard-Merge** | Command ist auf Allowlist + Syntax-valide | Command nicht auf Allowlist ODER Timeout-Risiko |
| **Decision Requests** | Genau 2 Optionen + eine hat ≥ 70% AI-Confidence-Vorteil | Mehr als 2 Optionen ODER keine klare Präferenz |
| **Escalation** | Gleicher Eskalationstyp wurde ≥ 2× gleich resolved (Pattern) | Erstmalige Eskalation ODER kein klares Pattern |

### Datenmodell

Governance-Levels werden in `app_settings` gespeichert als JSON:

```json
{
  "governance": {
    "review": "manual",
    "epic_proposals": "manual",
    "epic_scoping": "manual",
    "skill_merge": "manual",
    "guard_merge": "manual",
    "decisions": "manual",
    "escalations": "manual"
  }
}
```

> **Default: Alles `manual`.** Der Admin schaltet Level einzeln hoch — nie ein globaler "Full Auto"-Schalter. Das erzwingt bewusste Entscheidungen pro Risikokategorie.

### UI: Settings → Governance Tab

```text
┌─────────────────────────────────────────────────────────────────┐
│  ◈  SETTINGS — GOVERNANCE                                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Autonomie-Level pro Entscheidungstyp                           │
│  ─────────────────────────────────────                          │
│                                                                 │
│  Review              [MANUAL ▼]  [ASSISTED]  [AUTO]            │
│  Epic-Proposals      [MANUAL ▼]  [ASSISTED]  [AUTO]            │
│  Epic-Scoping        [MANUAL ▼]  [ASSISTED]  [AUTO]            │
│  Skill-Merge         [MANUAL]    [ASSISTED]  [AUTO ▼]          │
│  Guard-Merge         [MANUAL]    [ASSISTED]  [AUTO ▼]          │
│  Decision Requests   [MANUAL ▼]  [ASSISTED]  [AUTO]            │
│  Escalation          [MANUAL ▼]  [ASSISTED]  [AUTO]            │
│                                                                 │
│  ╔═══════════════════════════════════════════════════════╗      │
│  ║ ⚠ Auto-Level: AI entscheidet autonom.                ║      │
│  ║   Owner wird notifiziert und kann widersprechen.     ║      │
│  ║   Grace Period: 30 Minuten (konfigurierbar)          ║      │
│  ╚═══════════════════════════════════════════════════════╝      │
│                                                                 │
│  [SPEICHERN]                                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Resultierender Autonomie-Loop (Phase 8 + Governance Auto)

Mit Conductor + Reviewer + Governance `auto` sieht der Loop so aus:

```text
Externer Input (Plan, Code, Event)
  → Kartograph erkundet Repo                          ✓ AI (Conductor dispatcht)
  → Stratege plant → Epic-Proposals                    ✓ AI (Conductor dispatcht)
  → Governance "auto": Epic-Proposal auto-accepted     ✓ AI (Safeguards: kein Duplikat, Rationale OK)
  → Governance "auto": Epic auto-scoped                ✓ AI (Safeguard: Kartograph-Coverage ≥ 80%)
  → Architekt zerlegt → Tasks                          ✓ AI (Conductor dispatcht)
  → Worker führt aus                                   ✓ AI (Conductor dispatcht)
  → Reviewer pre-reviewed, auto-approved               ✓ AI (Safeguard: Confidence ≥ 0.90)
  → Owner notifiziert (Grace Period 30 Min)            ◐ Mensch optional
  → Gaertner destilliert                               ✓ AI (Conductor dispatcht)
  → Governance "auto": Skill auto-merged               ✓ AI (Safeguard: ≥ 3 erfolgreiche Einsätze)
```

**Ergebnis:** Der Loop schließt sich. Das System läuft autark mit **optionalem menschlichen Veto** statt mandatorischem menschlichen Handeln.

### Autonomie-Spektrum (schrittweise aktivierbar)

```text
Phase 1–7:  ████████████████░░░░  Mensch macht alles, System unterstützt
Phase 8:    ████████░░░░░░░░░░░░  AI macht Arbeit, Mensch entscheidet
+Conductor: ██████░░░░░░░░░░░░░░  AI macht Arbeit, System orchestriert, Mensch entscheidet
+Assisted:  ████░░░░░░░░░░░░░░░░  AI empfiehlt, Mensch bestätigt (1-Click)
+Auto:      ██░░░░░░░░░░░░░░░░░░  AI entscheidet, Mensch überwacht (Veto-Recht)
```

> **Kein "Full Auto"-Button.** Jeder Schritt ist einzeln aktivierbar. Ein Single-Developer kann Review auf `auto` setzen aber Escalation auf `manual` lassen. Ein Team kann Skill-Merge auf `auto` setzen aber Epic-Proposals auf `assisted`. Die Governance-Matrix gibt volle Kontrolle.

---

## Phase-Einordnung

| Konzept | Phase | Abhängigkeit |
| --- | --- | --- |
| Conductor Backend-Service | Phase 8 | `ai_provider_configs` konfiguriert |
| Reviewer System-Skill | Phase 8 | Conductor + Review-Prompt |
| Governance-Levels (`manual`/`assisted`/`auto`) | Phase 8 | Conductor |
| Auto-Review (Grace Period) | Phase 8 | Reviewer-Skill + Governance `auto` |
| Auto-Merge (Skill/Guard) | Phase 8 | Governance `auto` + `skill_task_links` tracking |
| Auto-Scoping | Phase 8 | Governance `auto` + Kartograph-Coverage-Daten |

> **Kein neuer Phase-Break.** Alle drei Konzepte sind Phase-8-Erweiterungen die den bestehenden Auto-Modus completieren. Conductor ist der Motor, Governance-Levels sind die Steuerung, Reviewer-Skill ist der fehlende siebte Agent.

---

## Sicherheitsprinzipien

1. **Review-Gate wird nie entfernt** — `auto`-Level delegiert die Entscheidung an AI, aber der Review-Schritt existiert immer. Kein Task wird `done` ohne dass jemand (Mensch oder AI) reviewed hat.
2. **Auto-Reject gibt es nicht** — AI kann `reject` empfehlen, aber nie autonom rejekten. Rejects gehen immer an den Owner (Safeguard gegen falsche Ablehnungen).
3. **Grace Period bei Auto-Actens** — Owner hat immer ein Zeitfenster zum Widersprechen.
4. **Audit-Trail vollständig** — Jede AI-Entscheidung wird mit Confidence, Rationale und Governance-Level geloggt.
5. **Fallback auf `assisted`** — Wenn Auto-Bedingungen nicht erfüllt → nie stillschweigend blockieren, sondern Mensch einbeziehen.
6. **Eskalation bleibt deterministisch** — SLA-Timer und Backup-Owner-Ketten funktionieren unverändert.
