# Prompt Station

← [UI-Konzept](./concept.md) | [Index](../../masterplan.md)

Die Prompt Station ist das **Herzstück der BYOAI-Interaktion in Phase 1–7**. Sie erkennt wann das System auf einen Agenten wartet, nennt welchen, und liefert den fertigen Prompt.

---

## Kernkonzept

```text
Hivemind-State                Prompt Station               User-Aktion
      |                              |                           |
 Epic scoped                         |                           |
      |→ "Jetzt: Architekt"  ──────→ |── Prompt anzeigen ──────→ |
      |                              |                           |──→ AI-Client
      |←─── MCP-Calls ──────────────────────────────────────────|←── AI führt aus
      |                              |                           |
 Tasks created                       |                           |
      |→ "Jetzt: Bibliothekar" ────→ |── Nächster Prompt ──────→ |
```

Der User muss **nicht verstehen** wie das System intern funktioniert. Er sieht nur: "Jetzt ist X dran — hier ist dein Prompt."

---

## UI-Mockup: Aktiver Prompt

```text
┌─────────────────────────────────────────────────────────────────┐
│  ◈  PROMPT STATION                              [WARTESCHLANGE] │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  AGENT ERFORDERLICH                     [EPIC-12 / TASK-88]    │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                 │
│  ◈  WORKER                                                      │
│     Implementiere TASK-88: FastAPI Auth-Endpoint                │
│                                                                 │
│  ┌─ PROMPT ──────────────────── [VOLLTEXT ▤]  [KOPIEREN] ──────┐│
│  │  ## Rolle: Worker                                           ││
│  │  Du arbeitest an TASK-88 im Rahmen von EPIC-12.            ││
│  │                                                             ││
│  │  [Skill: FastAPI Endpoint — 420 Tokens]                    ││
│  │  [Doc: EPIC-12 Architektur — 210 Tokens]                   ││
│  │                                                             ││
│  │                         630 / 8000 Tokens  ████░░░░░░░░░  ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                 │
│  [▶ IN AI-CLIENT EINFÜGEN]    [◈ PROMPT ANPASSEN] ← Phase 2+  │
│                                                                 │
│  Warte auf MCP-Rückmeldung...  ◌◌◌  (MCP verbunden ✓)         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Volltext-Modal (Button: VOLLTEXT ▤)

Der Prompt wird standardmäßig **kompakt** angezeigt — Skill- und Doc-Referenzen sind kollabiert mit Token-Zählung. Das reicht zum Kopieren. Der [VOLLTEXT]-Button öffnet ein Modal mit dem vollständig assemblierten Text — alle Referenzen expandiert — genau so wie er an den AI-Client übergeben wird.

```text
┌─ PROMPT: VOLLTEXT ──────────────────────────────────────────────┐
│  ◈ WORKER — TASK-88                              [SCHLIESSEN ✗] │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ## Rolle: Worker                                               │
│                                                                 │
│  Du arbeitest an TASK-88 im Rahmen von EPIC-12.                │
│                                                                 │
│  ### Dein Auftrag                                               │
│  Implementiere den FastAPI Auth-Endpoint gemäß Spezifikation.   │
│                                                                 │
│  ### Kontext                                                    │
│  ─── Skill: FastAPI Endpoint erstellen (v3) ──────────────────  │
│  Erstelle einen FastAPI-Endpoint mit Pydantic v2 Response       │
│  Models. Nutze `Depends()` für Dependency Injection...          │
│  [voller Skill-Text expandiert]                                 │
│                                                                 │
│  ─── Doc: EPIC-12 Architektur ─────────────────────────────── │
│  Die Auth-Architektur basiert auf JWT-Tokens. Refresh-Tokens    │
│  werden in HttpOnly Cookies gespeichert...                      │
│  [voller Doc-Text expandiert]                                   │
│                                                                 │
│  ### Guards — müssen vor in_review bestehen                     │
│  [global]    ◌ no hardcoded secrets                            │
│  [skill]     ◌ ruff check .                                    │
│  [skill]     ◌ pytest --cov-fail-under=80                      │
│                                                                 │
│                          630 / 8000 Tokens  ████░░░░░░░░░       │
│                                                                 │
│                                          [VOLLTEXT KOPIEREN ▶] │
└─────────────────────────────────────────────────────────────────┘
```

**Technisch:** Der Button ruft `hivemind-get_prompt { "type": "worker", "task_id": "TASK-88", "assembled": true }` auf. Das Backend liefert den vollständig aufgelösten Prompt-Text. Gerendert als **TipTap read-only** (→ [Markdown-Rendering-Strategie](./concept.md#markdown-rendering-strategie)).

> **Markdown-Minifizierung beim Kopieren:** Die Buttons [KOPIEREN] und [VOLLTEXT KOPIEREN] liefern den **minifizierten** Prompt-Text in die Zwischenablage (überflüssige Leerzeilen, Trailing Whitespace entfernt via [QMD](https://github.com/ajithraghavan/qmd)). Die Anzeige im Modal bleibt unverändert lesbar. Spart ~10–20 % Tokens. Steuerbar via `HIVEMIND_PROMPT_MINIFY` (→ [Prompt-Minifizierung](../agents/prompt-pipeline.md#prompt-minifizierung-markdown-kompression)).

---

## UI-Mockup: Warteschlange

```text
┌─ PROMPT QUEUE ──────────────────────────────────────────────────┐
│  [1] ◈ WORKER    — TASK-88  [AKTIV — IN BEARBEITUNG] [SLA <4h] │
│  [2] ◈ WORKER    — TASK-89  [WARTEND]            [DECISION OFFEN]│
│  [3] ⊕ GAERTNER  — TASK-82  [WARTEND]            [FOLLOW-UP]     │
│                                              [ALLE ANZEIGEN ▾] │
└─────────────────────────────────────────────────────────────────┘
```

**Priorisierung:** Eskalierte Items > Offene Decision Requests > SLA-nahe Tasks > Normale Tasks

### Vollständige Prioritätstabelle

Die Queue-Priorisierung ist deterministisch. Innerhalb derselben Prioritätsstufe wird nach `sla_due_at` (aufsteigend, früheste zuerst) sortiert; bei gleicher Deadline nach `created_at` (aufsteigend). Tasks ohne SLA (`sla_due_at = NULL`) erscheinen **nach** allen Tasks mit SLA innerhalb derselben Prioritätsstufe (`NULLS LAST` in SQL-Sortierung).

| Priorität | Agent-Typ | Event-Typ | reason_code | Beispiel |
| --- | --- | --- | --- | --- |
| **P0** (Kritisch) | — | Eskalierter Task (Admin-Aktion erforderlich) | `escalated` | Task 3x qa_failed oder Decision-SLA > 72h |
| **P1** (Hoch) | — | Offener Decision Request (Owner-Entscheidung blockiert Worker) | `decision_open` | Worker wartet auf Antwort |
| **P2** (Dringend) | Worker / Architekt | SLA-naher Task (< 4h bis Deadline) | `sla_critical` | TASK-88 SLA läuft ab |
| **P3** (Normal) | Triage | Unrouted Events (manuelles Routing erforderlich) | `triage_unrouted` | Sentry-Event ohne Epic-Zuordnung |
| **P4** (Normal) | Kartograph | Follow-up-Kartierung (Fog of War reduzieren) | `kartograph_followup` | "frontend/ noch nicht kartiert" |
| **P5** (Normal) | Worker | Normaler Task (kein SLA-Druck) | `normal` | TASK-90 ready → Worker-Prompt |
| **P6** (Niedrig) | Gaertner | Follow-up nach Task-Done (Skill-Destillation) | `gaertner_followup` | TASK-88 done → Skill extrahieren |
| **P7** (Niedrig) | Bibliothekar | Context-Update (kein blockierender Vorgang) | `context_update` | Wiki-Embedding veraltet |

> **Human-Action-Items** (Review, Scoping, Decision) werden **über** der normalen Queue angezeigt, da sie keine AI-Prompts sind. Sie erscheinen im `human_action_required`-State der Prompt Station mit eigenem visuellen Bereich.

### Entscheidungs-Transparenz ("Warum jetzt?")

Jeder Queue-Eintrag zeigt ein kompaktes **Warum-Jetzt-Badge**. Dadurch ist die Priorisierung nachvollziehbar, ohne Triage öffnen zu müssen.

| Badge | Bedeutung |
| --- | --- |
| `ESCALATED` | Task ist eskaliert und braucht Admin/Owner-Entscheidung |
| `DECISION OFFEN` | Offener Decision Request blockiert den Flow |
| `SLA <4h` | Deadline ist kritisch nah |
| `FOLLOW-UP` | Folgeaktion nach abgeschlossenem vorherigen Schritt |
| `NORMAL` | regulär eingeplante Aufgabe ohne Sonderdruck |

Pflichtmetadaten pro Queue-Eintrag:

- `reason_code` (z.B. `sla_critical`, `decision_open`, `escalated`)
- `reason_detail` (kurzer Freitext, max. 80 Zeichen)
- `sla_due_at` (optional, wenn SLA/Decision relevant)

---

## States der Prompt Station

| State | Anzeige | User-Aktion |
| --- | --- | --- |
| `idle` | "System in Ordnung — kein Agent erforderlich" | Nichts |
| `agent_required` | Agent-Name + fertiger Prompt + Warum-Jetzt-Badge | Prompt kopieren und in AI-Client einfügen |
| `waiting_for_mcp` | "Warte auf MCP-Rückmeldung..." + Spinner (Timeout: `HIVEMIND_MCP_WAITING_TIMEOUT_SECONDS`, Default: 300s / 5 Min.) | Nichts — AI arbeitet; bei Timeout → State wechselt auf `agent_required` mit Badge `TIMEOUT` |
| `completed` | Kurze Erfolgsbestätigung + nächster Schritt | Nächsten Prompt abarbeiten oder abwarten |
| `human_action_required` | "Jetzt bist DU dran" + klare Deadline/Begründung (z.B. Review, Scoping, Decision) | Manuelle Aktion im Command Deck |
| `api_key_mode` | Kein Prompt sichtbar — läuft automatisch | Monitoring |

---

## `human_action_required` — Ableitungslogik

Der Backend-Endpoint `GET /api/prompt-station/status` berechnet den aktuellen State. Der `human_action_required`-State wird ausgelöst wenn **mindestens eine** der folgenden Bedingungen zutrifft (für den aktuellen User):

```sql
-- Priorisiert nach Dringlichkeit (erste Zeile gewinnt):

-- P0: Tasks in_review wo User Epic-Owner oder assigned_to ist
SELECT 'in_review_task' AS reason, t.id, t.task_key, t.title, e.sla_due_at
FROM tasks t
JOIN epics e ON t.epic_id = e.id
WHERE t.state = 'in_review'
  AND (e.owner_id = :current_user_id OR t.assigned_to = :current_user_id)
  AND e.state NOT IN ('done', 'cancelled')

-- P1: Offene Decision Requests (Owner oder Admin)
UNION ALL
SELECT 'decision_request' AS reason, dr.task_id, t.task_key, dr.payload->>'blocker', dr.sla_due_at
FROM decision_requests dr
JOIN tasks t ON dr.task_id = t.id
JOIN epics e ON t.epic_id = e.id
WHERE dr.state = 'open'
  AND (e.owner_id = :current_user_id OR :is_admin = TRUE)

-- P2: Epics incoming wo User Epic-Owner ist
UNION ALL
SELECT 'epic_incoming' AS reason, e.id, e.epic_key, e.title, NULL
FROM epics e
WHERE e.state = 'incoming'
  AND e.owner_id = :current_user_id

ORDER BY
  CASE reason
    WHEN 'in_review_task'   THEN 0   -- P0
    WHEN 'decision_request' THEN 1   -- P1
    WHEN 'epic_incoming'    THEN 2   -- P2
    ELSE                         3
  END,
  sla_due_at NULLS LAST
LIMIT 10;
```

**Payload an das Frontend:**

```json
{
  "station_state": "human_action_required",
  "actions": [
    {
      "type": "in_review_task",
      "task_key": "TASK-88",
      "title": "FastAPI Auth-Endpoint",
      "sla_due_at": "2026-03-10T18:00:00Z",
      "link": "/command-deck?task=TASK-88&action=review"
    },
    {
      "type": "epic_incoming",
      "epic_key": "EPIC-13",
      "title": "Dashboard",
      "sla_due_at": null,
      "link": "/command-deck?epic=EPIC-13&action=scope"
    }
  ]
}
```

Die Prompt Station zeigt die erste Aktion prominent ("Jetzt bist DU dran") und die restlichen als Stack darunter ("+ 1 weitere Aktion").

---

## Menschliche Aktionen (kein AI-Prompt)

Manche Schritte erfordern eine **menschliche Entscheidung** — kein AI-Prompt, sondern eine UI-Aktion:

| System-Event | Anzeige | UI-Aktion |
| --- | --- | --- |
| Task wird `in_review` | "Jetzt bist DU dran: Review TASK-88" | Phase 1: Review **inline in Prompt Station** (vereinfachtes Review-Panel mit DoD-Checkliste + Approve/Reject). Ab Phase 2: → Command Deck öffnen, DoD-Checkliste |
| Epic ist `incoming` | "Epic EPIC-12 wartet auf Scoping" | Phase 1: Scoping **inline in Prompt Station** (Minimal-Formular: Titel, Beschreibung, Priorität). Ab Phase 2: → Command Deck öffnen, Scoping-Modal |
| Decision Request offen | "Entscheidung erforderlich: EPIC-12" | → Command Deck öffnen, Decision-Request-Modal (ab Phase 6) |

> **Phase 1 ohne Command Deck:** Da der Command Deck erst in Phase 2 verfügbar ist, bietet die Prompt Station in Phase 1 eingebettete Mini-Formulare für Review und Scoping. Diese sind funktional identisch, aber visuell kompakter. Ab Phase 2 delegiert die Prompt Station an den Command Deck.

Die Prompt Station unterscheidet klar zwischen "AI-Prompt ausführen" und "Du musst jetzt etwas tun".

---

## Agent-zu-State Mapping

| System-Event | Agent | Prompt-Typ | Menschliche Aktion |
| --- | --- | --- | --- |
| Neues Projekt / Repo | Kartograph | Initial-Kartograph | — |
| Kartierung unvollständig | Kartograph | Follow-up-Kartograph | — |
| Epic wird `scoped` | Architekt | Architektur-Prompt | — |
| Task wird `ready` (Phase 1-2) | Bibliothekar → Worker | Bibliothekar → Worker | — |
| Task wird `ready` (Phase 4+) | Mercenary Briefing (UI) → Bibliothekar → Worker | Briefing-State → Worker | Loadout bestätigen |
| Task wird `ready` (Phase F: federated Skills verfügbar) | Mercenary Briefing (UI) → Bibliothekar → Worker | Briefing-State + Peer-Skills → Worker | Loadout bestätigen |
| Task wird `in_review` | — | — | Owner reviewed DoD |
| Epic ist `incoming` | — | — | Owner scopet Epic |
| Task wird `done` | Gaertner | Gaertner-Prompt | — |
| `[UNROUTED]`-Event | Triage | Triage-Prompt | — |
| Decision Request offen | — | — | Owner entscheidet |

---

## Prompt Anpassen (ab Phase 2)

Der `[◈ PROMPT ANPASSEN]`-Button öffnet einen Inline-Editor direkt in der Prompt Station. Der User kann den assemblierten Prompt-Text bearbeiten bevor er ihn kopiert.

### Interaktionsmodell

```text
1. Prompt Station zeigt kompakten Prompt (assembliert via GET /api/prompts/:id/assembled)
2. User klickt [◈ PROMPT ANPASSEN]
   → Prompt-Card wechselt von read-only (HivemindViewer) auf bearbeitbar (HivemindEditor)
   → Edit-Toolbar erscheint; Prompt-Text wird vollständig expandiert (wie Volltext-Modal)
3. User editiert den Text (freie Bearbeitung, kein strukturiertes Formular)
4. [SPEICHERN UND KOPIEREN ▶]
   → POST /api/prompts/:id/override { "override_text": "..." }
   → Text wird in Zwischenablage kopiert
   → Override ist in prompt_history.override_text gespeichert (auditierbar)
   → UI zeigt Badge "ANGEPASST" auf dem Prompt-Eintrag
5. [ZURÜCKSETZEN]
   → Override wird verworfen; assemblierter Originaltext wird erneut geladen
```

### Semantik des Overrides

- Override gilt nur für diesen Queue-Eintrag — beim nächsten Prompt (andere Task/Agent-Kombination) ist kein Override aktiv
- Override überschreibt den assemblierten Text vollständig (kein Diff, kein Merge)
- Wenn ein Override aktiv ist, zeigt die Prompt Station einen visuellen Hinweis: `[ANGEPASST ⚠ Original abweichend]`
- AI-Calls via MCP-Tools bleiben unverändert — nur der Kontext-Prompt ist modifiziert

> **Kein Backend-Rerender nötig:** Der Override-Text ist das finale Dokument. Der User trägt die Verantwortung für Konsistenz mit dem System-State (Guards, Skills, Context Boundary).

---

## Automations-Pfad (Phase 8)

```text
Phase 1-7: Manuell
  Prompt Station → User kopiert → AI-Client → MCP

Phase 8: Semi-automatisch (API-Key konfiguriert)
  Prompt Station → [AUTO] → Hivemind schickt direkt an API → MCP
  User sieht nur noch Monitoring-Ansicht, kann jederzeit eingreifen

Konfiguration: Settings → AI Provider → API Key eingeben
Kein Architekturbruch: gleicher Prompt, gleiche MCP-Calls, gleiche Validierung
```
