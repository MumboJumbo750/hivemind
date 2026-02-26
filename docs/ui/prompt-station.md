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
│  [▶ IN AI-CLIENT EINFÜGEN]    [◈ PROMPT ANPASSEN]              │
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

**Technisch:** Der Button ruft `hivemind/get_prompt { "type": "worker", "task_id": "TASK-88", "assembled": true }` auf. Das Backend liefert den vollständig aufgelösten Prompt-Text. Gerendert als **TipTap read-only** (→ [Markdown-Rendering-Strategie](./concept.md#markdown-rendering-strategie)).

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
- `deadline_at` (optional, wenn SLA/Decision relevant)

---

## States der Prompt Station

| State | Anzeige | User-Aktion |
| --- | --- | --- |
| `idle` | "System in Ordnung — kein Agent erforderlich" | Nichts |
| `agent_required` | Agent-Name + fertiger Prompt + Warum-Jetzt-Badge | Prompt kopieren und in AI-Client einfügen |
| `waiting_for_mcp` | "Warte auf MCP-Rückmeldung..." + Spinner | Nichts — AI arbeitet |
| `completed` | Kurze Erfolgsbestätigung + nächster Schritt | Nächsten Prompt abarbeiten oder abwarten |
| `human_action_required` | "Jetzt bist DU dran" + klare Deadline/Begründung (z.B. Review, Scoping, Decision) | Manuelle Aktion im Command Deck |
| `api_key_mode` | Kein Prompt sichtbar — läuft automatisch | Monitoring |

---

## Menschliche Aktionen (kein AI-Prompt)

Manche Schritte erfordern eine **menschliche Entscheidung** — kein AI-Prompt, sondern eine UI-Aktion:

| System-Event | Anzeige | UI-Aktion |
| --- | --- | --- |
| Task wird `in_review` | "Jetzt bist DU dran: Review TASK-88" | → Command Deck öffnen, DoD-Checkliste |
| Epic ist `incoming` | "Epic EPIC-12 wartet auf Scoping" | → Command Deck öffnen, Scoping-Modal |
| Decision Request offen | "Entscheidung erforderlich: EPIC-12" | → Command Deck öffnen, Decision-Request-Modal |

Die Prompt Station unterscheidet klar zwischen "AI-Prompt ausführen" und "Du musst jetzt etwas tun".

---

## Agent-zu-State Mapping

| System-Event | Agent | Prompt-Typ | Menschliche Aktion |
| --- | --- | --- | --- |
| Neues Projekt / Repo | Kartograph | Initial-Kartograph | — |
| Kartierung unvollständig | Kartograph | Follow-up-Kartograph | — |
| Epic wird `scoped` | Architekt | Architektur-Prompt | — |
| Task wird `ready` (Phase 1-2) | Bibliothekar → Worker | Bibliothekar → Worker | — |
| Task wird `ready` (Phase F+) | Mercenary Briefing (UI) → Bibliothekar → Worker | Briefing-State → Worker | Loadout bestätigen |
| Task wird `in_review` | — | — | Owner reviewed DoD |
| Epic ist `incoming` | — | — | Owner scopet Epic |
| Task wird `done` | Gaertner | Gaertner-Prompt | — |
| `[UNROUTED]`-Event | Triage | Triage-Prompt | — |
| Decision Request offen | — | — | Owner entscheidet |

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
