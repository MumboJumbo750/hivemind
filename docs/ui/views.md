# UI-Views — Detailspezifikation

← [UI-Konzept](./concept.md) | [Index](../../masterplan.md)

---

## Command Deck

**Zweck:** Zentrale Übersicht aller Epics und Tasks — State Machine, SLA-Monitoring, menschliche Aktionen.

```text
┌─ COMMAND DECK ──────────────────────────────────────────────────┐
│  PROJEKT: hivemind-backend          [+ EPIC ANLEGEN]  [FILTER ▾]│
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  EPIC-12 · Auth-System              [OWNER: Max]  [SLA: 3 Tage]│
│  ● scoped  →→  [ARCHITEKT STARTEN ▶]                           │
│                                                                 │
│    TASK-88  FastAPI Auth-Endpoint       ● in_review  [REVIEW ▶]│
│    TASK-89  JWT Token Validation        ● in_progress           │
│    TASK-90  Session Management          ○ ready      [START ▶]  │
│                                                                 │
│  EPIC-13 · Dashboard                [OWNER: Anna] [SLA: 5 Tage]│
│  ● incoming  →→  [SCOPEN ▶]                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Menschliche Aktionen im Command Deck

**Epic Scoping Modal** (wenn Epic `incoming`):

```text
┌─ EPIC SCOPEN ───────────────────────────────────────────────────┐
│  EPIC-13 · Dashboard                                            │
│                                                                 │
│  Priorität:    [HIGH ▾]                                         │
│  SLA-Deadline: [2026-03-15]                                     │
│  Owner:        [Anna ▾]                                         │
│  Backup-Owner: [Max ▾]                                          │
│                                                                 │
│  Definition of Done (Rahmen):                                   │
│  [ ] Alle kritischen Flows haben Tests                          │
│  [ ] API-Dokumentation aktuell                                  │
│  [+ KRITERIUM HINZUFÜGEN]                                       │
│                                                                 │
│  [ABBRECHEN]                    [EPIC SCOPEN → scoped ▶]       │
└─────────────────────────────────────────────────────────────────┘
```

**Review Panel** (wenn Task `in_review`):

```text
┌─ REVIEW: TASK-88 ───────────────────────────────────────────────┐
│  FastAPI Auth-Endpoint                                          │
│  Worker: ◈ AI-Client (claude)    Eingereicht: vor 12 Min.      │
│                                                                 │
│  ERGEBNIS:  (TipTap read-only — HivemindViewer)                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ [Submitted Result Content — gerendert als Markdown]      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  GUARDS:                                                        │
│  ✓ no hardcoded secrets       passed                           │
│  ✓ ruff check .               passed (0 errors)               │
│  ✓ pytest --cov-fail-under=80 passed (coverage: 87%)          │
│  ✗ ./tests/integration/auth.sh FAILED                         │
│    → Connection refused: localhost:5432                         │
│                                                                 │
│  DEFINITION OF DONE:                                            │
│  ☑ Unit tests >= 80% Coverage                                  │
│  ☑ API-Dokumentation aktualisiert                              │
│  ☐ PR-Review abgeschlossen          ← FEHLT                    │
│                                                                 │
│  Kommentar (optional):  [________________________]              │
│                                                                 │
│  [✗ ABLEHNEN → qa_failed]           [✓ GENEHMIGEN → done]     │
└─────────────────────────────────────────────────────────────────┘
```

**Review-Struktur (Pflicht):**

1. **Hard Gates (systemisch):**
   - `result` vorhanden
   - Guard-Status pro Guard (`passed|failed|skipped`) — siehe [kanonische Guard-Enforcement-Timeline](../features/guards.md#kanonische-guard-enforcement-timeline) für phasenabhängiges Verhalten
   - Eintrag in `in_review` ist technisch zulässig
2. **Owner Judgment (fachlich):**
   - DoD-Checkliste und manuelle Qualitätsentscheidung
   - Review-Kommentar mit konkreten Nachbesserungspunkten bei `qa_failed`

**Guard-Provenance-Hinweis (Phase 5–7):**

- Guard-Ergebnisse sind in Phase 5–7 self-reported und müssen im Review sichtbar als solche markiert sein.
- Jede Guard-Zeile zeigt daher: `source` (`self-reported` | `system-executed`) und `checked_at`.
- Bei `source=self-reported` und leer/unklarer Ausgabe zeigt die UI einen Warnhinweis für den Reviewer.

**AI-Review-Empfehlung (Phase 8, Governance `assisted` oder `auto`):**

```text
┌─ AI-REVIEW-EMPFEHLUNG ─────────────────────────────────────────┐
│  🔍 Reviewer-Agent          Confidence: ████████░░ 92%         │
│  Empfehlung: ✓ APPROVE                                         │
│                                                                 │
│  Checklist:                                                     │
│  ☑ Endpoint liefert 200 bei gültigen Credentials               │
│  ☑ Error-Handling für 401/403 vorhanden                        │
│  ☑ Guard-Ergebnisse konsistent mit Implementierung             │
│  ☑ Skill-Instruktionen befolgt                                 │
│                                                                 │
│  Bedenken: Keine                                                │
│                                                                 │
│  [REVIEW-DETAILS ANZEIGEN ▾]                                   │
│                                                                 │
│  ─── GOVERNANCE: ASSISTED ──────────────────────────────────── │
│  [✓ AI-EMPFEHLUNG BESTÄTIGEN]   [✗ TROTZDEM ABLEHNEN]         │
│                                                                 │
│  ─── GOVERNANCE: AUTO ──────────────────────────────────────── │
│  Auto-Approve in: 15:00 Min.  [⏸ EINGREIFEN]                  │
└─────────────────────────────────────────────────────────────────┘
```

> Bei `governance.review = 'manual'` wird kein Reviewer-Agent dispatcht und dieses Panel ist nicht sichtbar. Das klassische Review-Panel (oben) wird unverändert genutzt.
> Bei `governance.review = 'auto'` und Confidence < Threshold: Fallback auf `assisted` (Owner muss bestätigen).

**Context Boundary Panel** (read-only, im Task-Detail ab Phase 4):

```text
┌─ CONTEXT BOUNDARY: TASK-88 ─────────────────────────────────────┐
│  Gesetzt von: ◎ Architekt                                       │
│                                                                 │
│  SKILLS (gepinnt):                                              │
│  ◈ FastAPI Endpoint erstellen  v3  — 420 Tokens                │
│  ◈ Pydantic Schema erstellen   v1  — 180 Tokens                │
│                                                                 │
│  DOCS:                                                          │
│  ◈ EPIC-12 Architektur-Doc     — 210 Tokens                    │
│                                                                 │
│  Token-Budget:  810 / 8000 ████░░░░░░░░  (10%)                 │
│                                                                 │
│  External Access: sentry (Phase 8)                             │
└─────────────────────────────────────────────────────────────────┘
```

**Decision Records Panel** (kollabierbar im Epic-Detail, ab Phase 5):

```text
┌─ DECISION RECORDS: EPIC-12 ─────────────────────────────────────┐
│  ⊕ GAERTNER · 2026-03-10                                        │
│  JWT statt Session Cookies gewählt                              │
│  "Stateless Auth ermöglicht horizontale Skalierung. Session-    │
│   Cookies würden shared Redis erfordern."                       │
│  [TASK-88 verknüpft]                                           │
│                                                                 │
│  ⊕ GAERTNER · 2026-03-08                                        │
│  Pydantic v2 statt v1 — Breaking Change bewusst akzeptiert     │
│  [TASK-89 verknüpft]                                           │
│                                                          [2/2 ▾]│
└─────────────────────────────────────────────────────────────────┘
```

---

## Triage Station

**Zweck:** Manuelle Entscheidungen für alles was nicht automatisch geroutet werden kann.

```text
┌─ TRIAGE STATION ────────────────────────────────────────────────┐
│  [UNROUTED: 3]  [PROPOSALS: 4]  [RESTRUCTURE: 1]               │
│  [ESCALATED: 1]  [DEAD LETTER: 1]                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ⚠ [UNROUTED]                                      SLA: 2h     │
│  Sentry: NullPointerException in CartService                    │
│  Vorgeschlagen: EPIC-12, EPIC-14   ← Phase 3–6: Keyword-Match    │
│  (Similarity-Scores erscheinen erst ab Phase 7: pgvector aktiv) │
│  [→ EPIC-12 ZUWEISEN]  [→ EPIC-14]  [NEU ANLEGEN]  [IGNORIEREN]│
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

`[DEAD LETTER]` Requeue-Aktion ruft `POST /api/triage/dead-letters/:id/requeue` auf (REST-Alias — kein direkter MCP-Call aus dem UI).

> **Routing-Vorschläge in Phase 3–6:** Die Triage Station zeigt Epic-Vorschläge basierend auf Keyword-Matching (ILIKE). Similarity-Scores (z.B. `EPIC-12 (0.71)`) erscheinen erst ab Phase 7, wenn pgvector-Routing aktiviert ist und Embeddings für Epics berechnet wurden. In Phase 3–6 ist die Score-Anzeige ausgeblendet.

**Tab: PROPOSALS** — Skill-Proposals, Guard-Proposals, Skill-Changes, Guard-Changes

```text
┌─ TRIAGE: PROPOSALS ─────────────────────────────────────────────┐
│  [SKILL PROPOSALS: 2]  [GUARD PROPOSALS: 1]                    │
│  [SKILL CHANGES: 1]    [GUARD CHANGES: 1]                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ◈ [SKILL PROPOSAL]                                             │
│  "PostgreSQL Index-Optimierung" — ⊕ Gaertner                   │
│  service_scope: backend · stack: postgres                       │
│  [DIFF ANZEIGEN ▾]   [MERGEN ✓]   [ABLEHNEN ✗]                │
│                                                                 │
│  ◈ [GUARD PROPOSAL]                                             │
│  "Python Linting — ruff check ." — ◬ Kartograph                │
│  scope: backend · type: executable                             │
│  command: ruff check .                                          │
│  [DIFF ANZEIGEN ▾]   [MERGEN ✓]   [ABLEHNEN ✗]                │
│                                                                 │
│  ◈ [SKILL CHANGE]                                               │
│  "FastAPI Endpoint erstellen" v3 → v4 — ⊕ Gaertner             │
│  [DIFF ANZEIGEN ▾]   [AKZEPTIEREN ✓]   [ABLEHNEN ✗]           │
│                                                                 │
│  ◈ [GUARD CHANGE]                                               │
│  "Unit Tests" — Coverage 80 → 90% — ⊕ Gaertner                │
│  [DIFF ANZEIGEN ▾]   [AKZEPTIEREN ✓]   [ABLEHNEN ✗]           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Tab: RESTRUCTURE** — Epic Restructure Proposals vom Kartograph

```text
┌─ TRIAGE: RESTRUCTURE ───────────────────────────────────────────┐
│                                                                 │
│  ◬ [RESTRUCTURE PROPOSAL]                       vor 2 Std.     │
│  EPIC-12 + EPIC-15 sollten zusammengeführt werden              │
│                                                                 │
│  BEGRÜNDUNG:                                                    │
│  "Auth-System und User-Management überschneiden sich in 70%    │
│   der Tasks. Separate Epics erzeugen künstliche Abhängigkeiten."│
│                                                                 │
│  VORSCHLAG:                                                     │
│  → Neues Epic "Identity & Auth" fasst EPIC-12 + EPIC-15        │
│  → Alle Tasks migrieren, SLA-Deadline vom engsten Epic         │
│                                                                 │
│  [PROPOSAL IGNORIEREN ✗]          [EPIC ANPASSEN → öffnet ▶]  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Tab: ESCALATED

```text
┌─ TRIAGE: ESCALATED ─────────────────────────────────────────────┐
│                                                                 │
│  ⚠ [ESCALATED]   3x qa_failed                     SLA: ÜBER 72h│
│  TASK-89 · JWT Token Validation                                 │
│  EPIC-12 · Auth-System  [OWNER: Max]                           │
│  Grund: qa_failed_count = 3 — Worker kann nicht vorankommen    │
│                                                                 │
│  [OWNER WECHSELN ▾]   [TASK ANZEIGEN ▶]   [LÖSEN → in_progress]│
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Arsenal / Skill Lab

**🎮 Game Mode:** ARSENAL | **💼 Pro Mode:** SKILL LAB

**Zweck:** Skills und Guards verwalten, Proposals reviewen, Versionshistorie einsehen. Das Arsenal enthält alles was ein Mercenary für eine Quest braucht — Skills als Wissen und Guards als Qualitätssicherung.

```text
┌─ ARSENAL ───────────────────────────────────────────────────────┐
│  [SKILLS]  [GUARDS]                                             │
├─────────────────────────────────────────────────────────────────┤
│  [ALLE]  [AKTIV]  [SYSTEM]  [PENDING MERGE]  [DEPRECATED]      │
│                                                         [SUCHEN]│
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ● FastAPI Endpoint erstellen         v3  backend · python      │
│    Confidence: ████████░░ 0.92        Owner: Max               │
│    [ANZEIGEN]  [CHANGE PROPOSAL]                               │
│                                                                 │
│  ⚔ JWT Patterns                      v2  [◈ ben-hivemind]      │
│    Confidence: ███████░░░ 0.87        read-only (federated)    │
│    [ANZEIGEN]                                                   │
│                                                                 │
│  ◈ hivemind-worker                   v2  system · hivemind     │
│    [SYSTEM]  Agent-Rollen-Skill                                │
│    [ANZEIGEN]  [CHANGE PROPOSAL]                               │
│                                                                 │
│  ◌ PostgreSQL Index-Optimierung       v1  [PENDING MERGE]      │
│    Von: ⊕ Gaertner · Eingereicht: heute                        │
│    [DIFF ▾]   [MERGEN ✓]   [ABLEHNEN ✗]                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Skill-Detail mit Composition-View:**

```text
┌─ SKILL: FastAPI Endpoint erstellen ─────────────────────────────┐
│  v3  backend · python · fastapi    Confidence: 0.92             │
│                                                                 │
│  KOMPOSITION (extends-Kette):                                   │
│  [coding-general] → [coding-python] → [FastAPI Endpoint ●]    │
│                                                                 │
│  GUARDS (eingebaut):                                            │
│  ◌ ruff check .           executable                           │
│  ◌ pytest tests/unit/     executable                           │
│                                                                 │
│  INHALT:  (TipTap read-only — HivemindViewer)                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ ## Skill: FastAPI Endpoint erstellen                     │  │
│  │ Erstelle einen FastAPI-Endpoint mit Pydantic v2…         │  │
│  │                                                          │  │
│  │ ```python                                                │  │
│  │ @router.post("/items", response_model=ItemOut)           │  │
│  │ async def create_item(data: ItemIn, db = Depends()):     │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  VERSIONS-HISTORY:                                              │
│  ● v3  2026-03-10  Pydantic v2 Response Models                 │
│  ● v2  2026-02-20  Async-Pattern ergänzt                       │
│  ● v1  2026-01-15  Initialversion — ⊕ Gaertner                 │
│                                                                 │
│  [CHANGE PROPOSAL ERSTELLEN]                                    │
└─────────────────────────────────────────────────────────────────┘
```

**Guard-Tab:**

```text
┌─ ARSENAL: GUARDS ───────────────────────────────────────────────┐
│  [SKILLS]  [GUARDS ●]                                           │
├─────────────────────────────────────────────────────────────────┤
│  [ALLE]  [GLOBAL]  [PROJEKT]  [SKILL]  [PENDING MERGE]         │
│                                                         [SUCHEN]│
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ● no hardcoded secrets             global · declarative       │
│    Gilt für: alle Projekte, alle Tasks                         │
│    [DETAIL]  [CHANGE PROPOSAL]                                 │
│                                                                 │
│  ● ruff check .                     project · executable       │
│    Gilt für: hivemind-backend · scope: backend                 │
│    command: ruff check .                                        │
│    [DETAIL]  [CHANGE PROPOSAL]                                 │
│                                                                 │
│  ◌ pytest --cov-fail-under=90       [PENDING MERGE]            │
│    Von: ⊕ Gaertner — Änderung: 80 → 90%                       │
│    [DIFF ▾]   [MERGEN ✓]   [ABLEHNEN ✗]                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Wiki

**Zweck:** Projektübergreifende Wissensbasis — lesen, navigieren, verlinken. Kartograph und Admins können manuell bearbeiten.

```text
┌─ WIKI ──────────────────────────────────────────────────────────┐
│  [SUCHEN...]                                [TAGS ▾]  [+ NEU ✎]│
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  FastAPI > Authentication > JWT                                 │
│                                                                 │
│  # JWT-Authentifizierung in Hivemind                           │
│  Tags: #backend #auth #fastapi                                 │
│  Verknüpft mit: EPIC-12                                        │
│  Zuletzt bearbeitet: ◈ Kartograph · 2026-03-10                 │
│                                                                 │
│  [TipTap read-only — HivemindViewer]                            │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  [MIT EPIC VERKNÜPFEN]  [✎ BEARBEITEN] (Kartograph + Admin) │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**Wiki-Editor** (Kartograph + Admin — `HivemindEditor`, TipTap `editable: true`):

```text
┌─ WIKI BEARBEITEN ───────────────────────────────────────────────┐
│  Titel: [JWT-Authentifizierung in Hivemind        ]             │
│  Tags:  [#backend] [#auth] [#fastapi] [+ TAG]                  │
│                                                                 │
│  [B] [I] [H1] [H2] [Code] [```] [Tabelle] [Link]              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                                                          │  │
│  │  TipTap Editor (HivemindEditor)                          │  │
│  │  Bearbeitung direkt im gerenderten Dokument —            │  │
│  │  kein Split-View, WYSIWYG.                               │  │
│  │                                                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  [ABBRECHEN]                              [SPEICHERN ✓]        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Notification Tray

**Zweck:** SLA-Alerts, offene Decision Requests und kritische Events — sichtbar aus jeder Ansicht.

```text
System Bar: [◈ HIVEMIND] ... [🔔 3] ... [Lvl. 5]

Aufgeklappt:
┌─ NOTIFICATIONS ─────────────────────────────────────────────────┐
│  ⚠ SLA-WARNUNG                                        vor 5 Min.│
│  EPIC-12 läuft in 4 Stunden ab                                  │
│  [EPIC ÖFFNEN ▶]                                               │
│                                                                 │
│  ◈ ENTSCHEIDUNG ERFORDERLICH                          vor 1 Std.│
│  Decision Request für TASK-89 wartet auf dich                   │
│  [IM COMMAND DECK ÖFFNEN ▶]                                    │
│                                                                 │
│  ☆ GUILD SUPPORT                                     vor 2 Std.│
│  ben-hivemind hat deinen delegierten Task-88 abgeschlossen.     │
│  → [+150 Bonus-EXP] [Loot-Box Badge gesendet]                  │
│                                                                 │
│                              [ALLE MARKIEREN ALS GELESEN]       │
└─────────────────────────────────────────────────────────────────┘
```

**Action-Queue-Modell (Pflicht):**

- Das Tray zeigt Benachrichtigungen in drei Gruppen: `ACTION NOW`, `SOON`, `FYI`.
- Gruppierung basiert auf operativer Dringlichkeit, nicht nur auf Erstellungszeit.
- Pro Eintrag werden angezeigt: `typ`, `zeit`, `warum`, `naechste Aktion`.

Empfohlene Zuordnung:

| Gruppe | Typen |
| --- | --- |
| `ACTION NOW` | `sla_breach`, `escalation`, `decision_escalated_admin`, `dead_letter`, `peer_offline` |
| `SOON` | `sla_warning`, `decision_request`, `decision_escalated_backup`, `guard_failed`, `review_requested`, `task_delegated`, `guard_proposal`, `restructure_proposal` |
| `FYI` | alle übrigen Info-/Status-Events |

**Notification-Typen (kanonische Liste → [data-model.md](../architecture/data-model.md)):**

| Typ | Auslöser | Priorität | Ziel-View |
| --- | --- | --- | --- |
| `sla_warning` | SLA-Deadline < 4h | Kritisch (rot) | Command Deck |
| `sla_breach` | SLA überschritten | Kritisch (rot) | Command Deck |
| `decision_request` | Worker erstellt Decision Request | Hoch (amber) | Command Deck → Modal |
| `decision_escalated_backup` | 48h ohne Auflösung | Hoch (amber) | Command Deck → Modal |
| `decision_escalated_admin` | 72h ohne Auflösung | Hoch (amber) | Triage → Escalated |
| `escalation` | Task eskaliert (3x qa_failed) | Hoch (amber) | Triage → Escalated |
| `guard_failed` | Guard-Result failed gemeldet | Normal (amber) | Command Deck → Review |
| `review_requested` | Task geht in in_review | Normal (blau) | Command Deck → Review |
| `task_assigned` | Task wird einem User zugewiesen | Normal (blau) | Command Deck |
| `skill_proposal` | Neuer Proposal eingereicht | Normal (blau) | Triage → Proposals |
| `guard_proposal` | Neuer Guard-Proposal eingereicht | Normal (blau) | Triage → Proposals |
| `restructure_proposal` | Kartograph schlägt Restructure vor | Normal (blau) | Triage → Restructure |
| `task_done` | Task abgeschlossen | Info (grün) | Command Deck |
| `skill_merged` | Admin hat gemergt | Info (grün) | Arsenal |
| `dead_letter` | Sync fehlgeschlagen | Normal (amber) | Triage → Dead Letter |
| `task_delegated` | Task wurde einem Peer-Node delegiert (`assigned_node_id` gesetzt) | Normal (blau) | Command Deck |
| `peer_task_done` | Peer hat delegierten Task abgeschlossen | Info (grün) | Command Deck |
| `peer_online` | Peer-Node ist beigetreten | Info (grün) | Gilde |
| `peer_offline` | Peer-Node nicht erreichbar | Normal (amber) | Gilde |
| `federated_skill` | Neuer Skill von Peer-Node verfügbar | Info (blau) | Arsenal |
| `discovery_session` | Peer erkundet Codebase-Area | Info (blau) | Nexus Grid |

---

## Settings

**Zweck:** System-Konfiguration — MCP, AI-Provider, Solo/Team-Modus, Theme, Projekt-Mitglieder, Audit.

```text
┌─ SETTINGS ──────────────────────────────────────────────────────┐
│  [SYSTEM]  [PROJEKT]  [AUDIT]  [KI]  [FEDERATION]              │
└────────────────────────────────────────────────────────────────┘
```

> **Tab-Sichtbarkeit:** FEDERATION-Tab ist nur sichtbar wenn `HIVEMIND_FEDERATION_ENABLED=true`. AUDIT-Tab ab Phase 4, KI-Tab ab Phase 8. SYSTEM und PROJEKT sind ab Phase 1 verfügbar.

### Spotlight — Globale Suche (Ctrl+K / ⌘K)

Globale Schnellsuche die aus jeder Ansicht erreichbar ist. Sucht über alle sichtbaren Entitäten.

```text
┌─ SPOTLIGHT ─────────────────────────────────────────────────────┐
│  🔍 [JWT Token Validation...                               ] ✕  │
├─────────────────────────────────────────────────────────────────┤
│  TASKS (3)                                                      │
│  ● TASK-89  JWT Token Validation          ● in_progress  EPIC-12│
│  ○ TASK-92  JWT Refresh Token             ○ ready        EPIC-7 │
│  ✓ TASK-71  JWT Payload Parsing           ✓ done         EPIC-4 │
│                                                                 │
│  SKILLS (1)                                                     │
│  ⚔ JWT Patterns  v2  [◈ ben-hivemind]  0.87 confidence         │
│                                                                 │
│  WIKI (1)                                                       │
│  📄 JWT-Authentifizierung in Hivemind  #backend #auth           │
│                                                                 │
│  CODE-NODES (2)                                                 │
│  ◬ auth/security/jwt_handler.py         [◈ alex-hivemind]       │
│  ◬ core/auth/token_utils.py             [◈ alex-hivemind]       │
│                                                                 │
│  [↑↓ navigieren]  [Enter: öffnen]  [Esc: schliessen]            │
└─────────────────────────────────────────────────────────────────┘
```

**Suchverhalten:**

| Kategorie | Ab Phase | Suchfelder |
| --- | --- | --- |
| Tasks + Epics | 2 | `title`, `description`, `external_id` (TASK-X / EPIC-X) |
| Skills | 4 | `title`, `service_scope`, `stack` |
| Wiki-Artikel | 5 | `title`, `content` (Volltext), Tags |
| Code-Nodes | 5 | `path`, `summary` |

- **Tastenkürzel:** `Ctrl+K` (Windows/Linux), `⌘K` (macOS)
- **Ergebnisse** werden nach Kategorie gruppiert, max. 3 Einträge pro Kategorie — "Alle zeigen" expandiert die Gruppe
- **RBAC:** Spotlight respektiert den Context Boundary Filter — `developer` sieht nur Entitäten in den eigenen Epics; `admin` und `kartograph` sehen alles
- **Fuzzy-Match:** Client-seitige Fuzzy-Suche für schnelle Response; Backend-Fallback für Volltext-Wiki und Code-Nodes

---

### Tab: SYSTEM (Phase 1)

```text
┌─ SETTINGS: SYSTEM ──────────────────────────────────────────────┐
│                                                                 │
│  MODUS                                                          │
│  ○ Solo   ● Team                                               │
│                                                                 │
│  MCP-TRANSPORT                                                  │
│  ● stdio (lokal)   ○ HTTP/SSE (Team/Remote)                    │
│  MCP-Endpoint: [http://localhost:8000/mcp    ]                  │
│                                                                 │
│  INTERFACE-TONE                                                 │
│  🎮 ● Game Mode   💼 ○ Pro Mode                                │
│     (sci-fi, metaphorisch)  (professionell, neutral)           │
│                                                                 │
│  THEME                                                          │
│  ● space-neon   ○ industrial-amber   ○ operator-mono           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Tab: SYSTEM — Webhook-Konfiguration (Phase 3 Erweiterung)

Ab Phase 3 erscheint im SYSTEM-Tab ein Webhook-Bereich (nur sichtbar wenn `current_phase >= 3`):

```text
┌─ SETTINGS: SYSTEM — WEBHOOKS ───────────────────────────────────┐
│                                                                 │
│  WEBHOOK-ENDPOINTS                                              │
│  ──────────────────────────────────────────────────────────     │
│  Dein Webhook-Empfänger (für YouTrack / Sentry):                │
│  https://192.168.1.10:8000/webhooks/ingest    [KOPIEREN]        │
│  Auth-Token:  [whk_••••••••••••••••]  [REGENERIEREN]           │
│                                                                 │
│  YOUTRACK                                                       │
│  ○ Deaktiviert  ● Aktiv                                         │
│  Erwartete Events: [issue.created ▾] [issue.updated ▾]         │
│  [+ EVENT HINZUFÜGEN]                                           │
│                                                                 │
│  SENTRY                                                         │
│  ○ Deaktiviert  ● Aktiv                                         │
│  Projekt-Slug: [hivemind-backend     ]                          │
│  Erwartete Events: [issue.created ▾]                            │
│                                                                 │
│  LETZTER EMPFANG                                                │
│  YouTrack:  vor 3 Min.  ✓  (ISSUE-42: NullPointerException)    │
│  Sentry:    vor 2 Std.  ✓  (3 Events ingested)                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Hinweis:** Der `/webhooks/ingest`-Endpoint nimmt alle Events entgegen und schreibt sie als `direction='inbound'` in `sync_outbox`. Routing (Event → Epic) erfolgt manuell in der Triage Station.

---

### Tab: PROJEKT — Mitgliederverwaltung (Phase 2)

```text
┌─ SETTINGS: PROJEKT ─────────────────────────────────────────────┐
│  PROJEKT: hivemind-backend                    [+ MITGLIED LADEN]│
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Max Mustermann    max@team.dev    [ADMIN  ▾]  [ENTFERNEN ✗]   │
│  Anna Schmidt      anna@team.dev   [DEVELOPER▾] [ENTFERNEN ✗]  │
│  CI-System         ci@team.dev    [SERVICE ▾]  [ENTFERNEN ✗]   │
│                                                                 │
│  ROLLEN:                                                        │
│  developer   — lesen + schreiben nur im eigenen Epic-Scope      │
│  admin       — globales Schreiben, Triagieren, Mergen           │
│  service     — technische Integration, nur Lesen                │
│  kartograph  — Wiki + Code-Nodes anlegen/bearbeiten, Kartierung │
│                                                                 │
│  (Globale Admin-Rechte erfordern users.role = admin im System)  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Tab: AUDIT — Audit-Log (Phase 4)

```text
┌─ SETTINGS: AUDIT ───────────────────────────────────────────────┐
│  [FILTER: Actor ▾]  [Tool ▾]  [Status ▾]  [Zeitraum ▾]        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  2026-03-10 14:32  ◈ Worker (claude)    submit_result          │
│  TASK-88 · EPIC-12                      ✓ success              │
│  [PAYLOAD ANZEIGEN ▾]                                          │
│                                                                 │
│  2026-03-10 14:30  ◈ Worker (claude)    report_guard_result     │
│  TASK-88 · guard: ruff check .          ✓ passed               │
│  [PAYLOAD ANZEIGEN ▾]                                          │
│                                                                 │
│  2026-03-10 14:15  ◈ Kartograph (claude) create_wiki_article   │
│  "JWT-Authentifizierung in Hivemind"    ✓ success              │
│  [PAYLOAD ANZEIGEN ▾]                                          │
│                                                                 │
│  Payload-Retention: 90 Tage  (volle Input/Output-Daten)        │
│  Summary-Retention: 1 Jahr   (Actor, Tool, Status)             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Tab: FEDERATION — Peer-Verwaltung (Phase F)

```text
┌─ SETTINGS: FEDERATION ──────────────────────────────────────────┐
│                                                                 │
│  DIESE NODE                                                     │
│  ID:    f3a9-...  Name: alex-hivemind                           │
│  URL:   http://192.168.1.10:8000                                │
│  Key:   ed25519:pub:AbCd...  [KOPIEREN]                        │
│                                                                 │
│  PEERS                                       [+ PEER HINZUFÜGEN]│
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ● ben-hivemind     192.168.1.11:8000   zuletzt: vor 2 Min.    │
│    Key verified ✓   Status: aktiv                               │
│    [PING]  [KEY ANZEIGEN]  [BLOCKIEREN ✗]                      │
│                                                                 │
│  ● clara-hivemind   192.168.1.12:8000   zuletzt: vor 1 Std.    │
│    Key verified ✓   Status: aktiv                               │
│    [PING]  [KEY ANZEIGEN]  [BLOCKIEREN ✗]                      │
│                                                                 │
│  ○ old-node         192.168.1.99:8000   zuletzt: vor 3 Tagen   │
│    Status: inaktiv                                              │
│    [PING]  [ENTFERNEN ✗]                                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Shared Epic Dashboard (Phase F)

**Zweck:** Überblick über alle Epics mit Peer-zugewiesenen Tasks — Fortschritt über Node-Grenzen hinweg sichtbar machen.

```text
┌─ COMMAND DECK ──────────────────────────────────────────────────┐
│  EPIC-7 · Auth-System               [OWNER: Alex] [SLA: 4 Tage]│
│  ● in_progress  →→  [ARCHITEKT STARTEN ▶]                      │
│                                                                 │
│    TASK-1   FastAPI Auth-Endpoint     ● in_progress  [lokal]   │
│    TASK-2   JWT Token Validation      ✓ done  [◈ ben-hivemind] │
│    TASK-3   Session Management        ○ ready  →→ [START ▶]    │
│                                                                 │
│                                  [NODE-FILTER: alle ▾]         │
└─────────────────────────────────────────────────────────────────┘
```

**Task-Badge bei Peer-Assignment:**

```text
[◈ ben-hivemind]   → Task liegt auf Peer-Node
[lokal]            → Task liegt auf dieser Node
[◈ ben-hivemind ●] → Task auf Peer-Node, gerade in Bearbeitung
[◈ ben-hivemind ✓] → Task auf Peer-Node abgeschlossen
```

**Skill-Badge bei Federation:**

```text
Im Skill Lab erscheint bei federierten Skills ein Origin-Badge:
◈ FastAPI Endpoint erstellen  v3  [von: ben-hivemind]  read-only
```

---

### Tab: KI — AI-Provider (Phase 8)

```text
┌─ SETTINGS: KI ──────────────────────────────────────────────────┐
│                                                                 │
│  GLOBAL-FALLBACK                                                │
│  Modus: ● Manuell (BYOAI)   ○ Automatisch (API-Key)            │
│  Provider: [Anthropic ▾]  Modell: [claude-sonnet-4 ▾]          │
│  API-Key:  [sk-ant-••••••••••••••••]  [TESTEN]                 │
│                                                                 │
│  ─── PER-AGENT-ROLLE ────────────────────────────────────────── │
│                                                                 │
│  Kartograph   [✓ Auto]  Google    gemini-2.5-pro   200K  [⚙]  │
│  Stratege     [✓ Auto]  Anthropic claude-sonnet-4  100K  [⚙]  │
│  Architekt    [✓ Auto]  OpenAI    gpt-4o           128K  [⚙]  │
│  Worker       [✓ Auto]  Ollama    llama3.3         8K    [⚙]  │
│  Gaertner     [  Global-Fallback ]                        [⚙]  │
│  Triage       [  Global-Fallback ]                        [⚙]  │
│                                                                 │
│  [⚙] öffnet: Provider, Modell, Endpoint, API-Key,             │
│       Token-Budget, RPM-Limit, Enabled-Toggle                   │
│                                                                 │
│  Token Budget Default: [8000    ]                               │
│  Memory Token Ratio:   [0.3     ]                               │
│  Audit Retention (Tage): [90    ]                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Verhalten:**
- Rollen ohne eigenen Eintrag nutzen den Global-Fallback-Provider
- Rollen mit `enabled: false` fallen auf BYOAI-Modus zurück (Prompt Station zeigt Prompt)
- Hybrid-Betrieb ist explizit vorgesehen — nicht alle Rollen müssen automatisiert sein
- [⚙]-Button öffnet ein Modal mit allen Feldern aus `ai_provider_configs`
- Test-Button pro Rolle sendet einen Ping-Prompt an den konfigurierten Provider

### Settings: Governance (Phase 8)

```text
┌─ SETTINGS: GOVERNANCE ──────────────────────────────────────────┐
│                                                                 │
│  AUTONOMIE-SPEKTRUM                                             │
│  ░░░░░░░░████████░░░░░░░░  ASSISTED (4/7 Typen auf assisted)  │
│  Manual ◄─────────────────────────────────────────────► Auto    │
│                                                                 │
│  ─── PRO ENTSCHEIDUNGSTYP ──────────────────────────────────── │
│                                                                 │
│  Review             [assisted ▾]  Confidence ≥ [0.85]  Grace [15 Min] │
│  Epic-Proposal      [assisted ▾]                                │
│  Epic-Scoping       [manual   ▾]                                │
│  Skill-Merge        [auto     ▾]  Confidence ≥ [0.90]  Grace [30 Min] │
│  Guard-Merge        [auto     ▾]  Confidence ≥ [0.90]  Grace [30 Min] │
│  Decision-Request   [assisted ▾]                                │
│  Escalation         [manual   ▾]                                │
│                                                                 │
│  ─── SAFEGUARDS ────────────────────────────────────────────── │
│  ⚠ Review: Auto-Reject ist NICHT möglich (immer menschlich)   │
│  ⚠ Grace Period: Owner kann IMMER innerhalb der Frist eingreifen│
│  ⚠ Kein "Full Auto"-Button — jeder Typ einzeln konfigurierbar │
│                                                                 │
│  [ÄNDERUNGEN SPEICHERN]                                         │
└─────────────────────────────────────────────────────────────────┘
```

**Verhalten:**
- Governance-Levels werden in `app_settings.governance` als JSON gespeichert
- Änderungen erfordern `admin`-Berechtigung
- Autonomie-Spektrum-Leiste visualisiert den aktuellen Gesamt-Autonomiegrad
- Bei Auto-Stufe: Confidence-Threshold und Grace-Period konfigurierbar pro Typ
- Safeguards sind read-only und zeigen die systemischen Einschränkungen

> Vollständige Spezifikation: [autonomy-loop.md — Governance-Levels](../features/autonomy-loop.md#3-governance-levels)

---

## Mercenary Loadout Screen (Phase 4 Basis, Phase F Erweiterung)

**🎮 Game Mode:** MERCENARY BRIEFING | **💼 Pro Mode:** WORKER VORBEREITEN

**Zweck:** Bevor eine Quest/Task startet, wechselt die Prompt Station in den Briefing-State. Der Kommandant (Architekt-Agent) stellt das Loadout zusammen — welche Skills aus dem Arsenal bekommt der Mercenary für diese Mission? Dieser Moment ist bewusst ritualisiert.

**Auslöser:** Task wechselt zu `ready` (Architekt hat Dekomposition + Context Boundary gesetzt) → Prompt Station wechselt in Briefing-State bevor der Worker-Prompt generiert wird.

**Phasen-Verfügbarkeit:**
- **Phase 4:** Basis-Loadout mit lokalen Skills + Budget-Prüfung (Arsenal verfügbar)
- **Phase F:** Zusätzlich Federated Skills im Skill-Picker (Peer-Skills wählbar mit `[◈ peer-name]` Badge)
- **Phase 1–3:** Kein Loadout-Screen — Bibliothekar wählt Skills automatisch oder per Prompt

```text
┌─ BEFEHLSSTATION ──────────────────────────────────────────────────┐
│                                                                   │
│  ⚔ MERCENARY BRIEFING                         [← ZURÜCK ZU QUEUE]│
│  ─────────────────────────────────────────────────────────────── │
│                                                                   │
│  QUEST:  TASK-42 · "Implement JWT Refresh Token"                  │
│  EPIC:   EPIC-7  · "Auth-System"                                  │
│  SLA:    ████████░░  3 Tage  ·  Priorität: HIGH                   │
│                                                                   │
│  ─── LOADOUT ZUSAMMENSTELLEN ─────────────────────────────────── │
│                                                                   │
│  ⚔ FastAPI Auth Pattern    v3   [lokal]             420 Token    │
│  ⚔ JWT Patterns            v2   [◈ ben-hivemind]    310 Token    │
│  ⚔ Pydantic v2             v1   [lokal]             180 Token    │
│                                                   ─────────────  │
│                                [+ SKILL HINZUFÜGEN ▾]  910 Token │
│                                                                   │
│  ─── GUARDS ──────────────────────────────────────────────────── │
│  ✓ ruff check .              ✓ pytest --cov 80%                  │
│  ✓ no hardcoded secrets      (aus Skill-Guards + Projekt-Guards)  │
│                                                                   │
│  ─── TOKEN BUDGET ────────────────────────────────────────────── │
│  ███████████░░░░░░░░░░  910 / 8000  (11%)  ← Loadout-Gewicht     │
│                                                                   │
│         [◄ LOADOUT VERWERFEN]   [⚔ QUEST STARTEN → Prompt ▶]    │
└───────────────────────────────────────────────────────────────────┘
```

**Skill-Picker (wenn "+ SKILL HINZUFÜGEN" gedrückt):**

```text
┌─ SKILL AUSWÄHLEN ─────────────────────────────────────────────────┐
│  [SUCHEN...]                          [LOKAL]  [FEDERATED]  [ALLE]│
├───────────────────────────────────────────────────────────────────┤
│  ⚔ FastAPI Auth Pattern    v3  lokal           0.92  420 Token   │
│  ⚔ JWT Patterns            v2  ◈ ben-hivemind  0.87  310 Token   │
│  ⚔ Vue3 Composables        v1  ◈ clara-hivemind 0.81 180 Token   │
│  ⚔ Pydantic v2             v1  lokal           0.95  180 Token   │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ │
│  Budget-Auswirkung: + 180 Token → 1090 / 8000                    │
│                                           [ABBRECHEN]  [PINNEN ✓] │
└───────────────────────────────────────────────────────────────────┘
```

---

## Nexus Grid — Weltkarte (Phase 5 + Phase F)

**🎮 Game Mode:** WELTKARTE | **💼 Pro Mode:** NEXUS GRID

**Zweck:** Visueller Code-Graph der Codebase — Fog of War, Bug-Heatmap, Discovery Sessions der Gilde. Die Weltkarte ist das kollektive Gedächtnis der Gilde.

```text
┌─ WELTKARTE ───────────────────────────────────────────────────────┐
│  [FILTER ▾]  [LAYER ▾]  [HEATMAP]  [PEERS ▾]     [2D] [3D🔒]    │
├───────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░       │
│  ░░░░  [◬ clara erkundet frontend/ · · ·]  ░░░░░░░░░░░░░░       │
│  ░░░░░░   (Sektor löst sich mittels "Scan-Welle" auf)   ░░░░       │
│  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░       │
│                                                                   │
│          ●───────●───────●  ← auth/ (alex, cyan)                 │
│          │       │                                                │
│          ●───────⚻───────●───●  ← api/ (alex, cyan)             │
│                  │                                                │
│              [⚠ Bug-Partikel "Störung"]                           │
│                     ●────●────●  ← worker/ (ben, magenta)        │
│                          │                                        │
│                     ░░░░░░░░░░░  ← Fog of War                    │
│                                                                   │
│  LEGENDE:                                                         │
│  ● Cyan     = diese Node (alex)                                   │
│  ● Magenta  = ben-hivemind                                        │
│  ● Amber    = clara-hivemind                                      │
│  ░ Grau     = unerkundeter Bereich (Fog of War)                   │
│  [◬ ...]    = aktive Discovery Session (pulsiert)                 │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

**Node-Detail (Klick auf kartiertem Node):**

```text
┌─ NODE DETAIL ─────────────────────────────────────────────────────┐
│  auth/security/jwt_handler.py              [◈ von: alex-hivemind] │
│  Erkundet: 2026-03-10 · Scout: ◬ Kartograph                      │
│                                                                   │
│  VERKNÜPFT MIT: EPIC-12 · Auth-System                            │
│  BUGS: ⚠ 2 offene Sentry-Reports (severity: high)                │
│  SKILLS: ⚔ JWT Patterns v2 · ⚔ FastAPI Auth v3                  │
│                                                                   │
│  KANTEN (Abhängigkeiten):                                         │
│  → auth/models/user.py    (import)                                │
│  → core/config.py         (import)                                │
│  ← api/routes/auth.py     (call)                                  │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

**Discovery Session Banner (wenn Peer aktiv erkundet):**

```text
┌─ WELTKARTE ─────────────────── [◬ DISCOVERY SESSION AKTIV] ──────┐
│  ◬ clara-hivemind erkundet: frontend/components/  (seit 8 Min.)  │
│  Ben sieht dies und wählt worker/ → kein Doppelaufwand           │
│  [SESSION ÜBERNEHMEN]  [IGNORIEREN ✗]                            │
└───────────────────────────────────────────────────────────────────┘
```

---

## Gilde (Phase F)

**🎮 Game Mode:** GILDE | **💼 Pro Mode:** FEDERATION

**Zweck:** Das Herzstück der Federation — Übersicht aller verbundenen Nodes, geteilter Quests und Gildenwissen. Hier sieht der Kommandant was seine Mitstreiter tun.

```text
┌─ GILDE ───────────────────────────────────────────────────────────┐
│                                              [+ PEER HINZUFÜGEN]  │
│  ─── MEINE BASE ──────────────────────────────────────────────── │
│  ◈ alex-hivemind   [DU]                                           │
│    Commander-Level 5 (███████░░░░ 700 / 1000 EXP)                 │
│    Quests aktiv: 2  ·  Skills im Arsenal: 8  ·  Karte: 120 Nodes │
│    Node-ID: f3a9-...  ·  Key: ed25519:pub:AbCd...  [KOPIEREN]    │
│    [Trophäenschrank / Achivements: 🥇 🥈 🥉 (3 freigeschaltet)]  │
│                                                                   │
│  ─── GILDENMITGLIEDER ────────────────────────────────────────── │
│                                                                   │
│  ● ben-hivemind         online   zuletzt: vor 3 Min.             │
│    Quest aktiv: TASK-42 "JWT Refresh Token"   [◈ DEINE QUEST]    │
│    ⚔ Gildenwissen: 4 Skills   🗺 Weltkarte: 80 Nodes beigetragen  │
│    [Level 7] [🥇 Master Architect] [🥈 Guild Contributor]         │
│    [QUEST ANSEHEN ▶]  [PING]  [BLOCKIEREN ✗]                     │
│                                                                   │
│  ● clara-hivemind       online   zuletzt: vor 45 Min.            │
│    ◬ Erkundet: frontend/components/   [DISCOVERY SESSION]        │
│    ⚔ Gildenwissen: 7 Skills   🗺 Weltkarte: 480 Nodes beigetragen │
│    [Level 8] [🥇 Fog Clearer] [🥉 SLA Savior]                     │
│    [SESSION ANSEHEN ▶]  [PING]  [BLOCKIEREN ✗]                   │
│                                                                   │
│  ○ old-node             offline  zuletzt: vor 3 Tagen             │
│    ⚠ 2 Nachrichten ausstehend (Outbox-Retry)                     │
│    [PING]  [ENTFERNEN ✗]                                         │
│                                                                   │
│  ─── GILDENWISSEN ─────────────────────────────────────────────  │
│  ⚔ JWT Patterns         v2  [◈ ben-hivemind]   [ÜBERNEHMEN ▶]   │
│  ⚔ Vue3 Composables     v1  [◈ clara-hivemind] [ÜBERNEHMEN ▶]   │
│  ⚔ PostgreSQL Indexing  v1  [◈ ben-hivemind]   [ÜBERNEHMEN ▶]   │
│                                          [ALLE ANZEIGEN →]       │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

`[ÜBERNEHMEN]` erzeugt einen lokalen Draft-Fork via
`hivemind-fork_federated_skill { "source_skill_id": "...", "target_project_id": "uuid|null" }`.

**Leer-State (keine Peers konfiguriert):**

```text
┌─ GILDE ───────────────────────────────────────────────────────────┐
│                                                                   │
│  🎮  Du kämpfst noch allein.                                      │
│  💼  Keine verbundenen Nodes konfiguriert.                        │
│                                                                   │
│  Verbinde dich mit Peers im selben VPN-Netzwerk                   │
│  um gemeinsam die Karte zu erkunden und Quests zu teilen.        │
│                                                                   │
│  [+ ERSTEN PEER HINZUFÜGEN ▶]   [peers.yaml importieren]         │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

### Leaderboard (Gilde-Unterbereich, Phase F)

```text
┌─ GILDE: RANGLISTE ────────────────────────────────────────────────┐
│  [ÜBERSICHT]  [RANGLISTE ●]  [GILDENWISSEN]                      │
├───────────────────────────────────────────────────────────────────┤
│                                                                   │
│  DIESE WOCHE                                          [ZEITRAUM ▾]│
│                                                                   │
│  #1  ◈ alex-hivemind      Lvl 6  ████████████░  2340 EXP  [≡]   │
│      🥇 Fog Clearer · 🥈 Centurion                                │
│                                                                   │
│  #2  ◈ ben-hivemind       Lvl 5  ██████████░░  1180 EXP  [≡]    │
│      🥇 Master Architect · 🥈 Guild Contributor                   │
│                                                                   │
│  #3  ◈ clara-hivemind     Lvl 4  ████████░░░░   720 EXP  [≡]    │
│      🥇 Fog Clearer · 🥉 SLA Savior                               │
│                                                                   │
│  ─── DEINE STATS ─────────────────────────────────────────────── │
│  Quests erledigt: 42  ·  Skills erstellt: 8  ·  Reviews: 31     │
│  Nodes erkundet: 120  ·  Clean Runs: 34/42 (81%)                │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

> Das Leaderboard ist nur sichtbar wenn Federation aktiv ist (≥ 2 Nodes). Im Solo-Modus wird statt der Rangliste ein persönlicher Stats-Überblick im Profil angezeigt.

---

## Profil (Phase 2)

**🎮 Game Mode:** KOMMANDANTENPROFIL | **💼 Pro Mode:** PROFIL

**Zweck:** Persönliche Zentrale des Users — Avatar, Level, Badges, Statistiken und persönliche Einstellungen (Theme, Tone). Erreichbar über Klick auf den Username/Avatar in der System Bar.

**Zugangspunkte:**
- System Bar: Klick auf Username/Avatar → Dropdown: `[PROFIL ▶]` `[EINSTELLUNGEN ▶]` `[ABMELDEN]`
- Gilde-View: Klick auf eigenen Node oder Peer-Node → öffnet Profil-Detail (Peer: read-only)

```text
┌─ KOMMANDANTENPROFIL ──────────────────────────────────────────────┐
│                                                                   │
│  ─── IDENTITÄT ───────────────────────────────────────────────── │
│                                                                   │
│  ┌────────┐                                                       │
│  │        │  Max Mustermann (@max)                                │
│  │ AVATAR │  max@team.dev                                         │
│  │        │  Frontend-Architekt und Schwarm-Kommandant            │
│  └────────┘  [AVATAR ÄNDERN]  [PROFIL BEARBEITEN ✎]              │
│              Rolle: admin · Projekte: 3                           │
│                                                                   │
│  ─── LEVEL & FORTSCHRITT ─────────────────────────────────────── │
│                                                                   │
│  ★ Lvl 5 — MEISTER-KOMMANDANT                                    │
│  ████████████████░░░░░░░░  700 / 1000 EXP bis Lvl 6              │
│                                                                   │
│  +50 EXP letzte Quest · +20 Clean Run Bonus · +10 SLA Bonus      │
│                                                                   │
│  ─── TROPHÄENSCHRANK ─────────────────────────────────────────── │
│                                                                   │
│  🥇 Erster Strike            Ersten Task abschließen              │
│  🥇 Fog Clearer              200 Code-Nodes erkundet              │
│  🥈 Centurion                100 Tasks abgeschlossen              │
│  🥈 Gilden-Schreiber         20 Wiki-Artikel erstellt             │
│  🥉 Erster Richter           Ersten Task reviewed                 │
│  ░░ Makellose Serie          5 Tasks ohne qa_failed  [LOCKED]     │
│  ░░ Söldner                  Ersten Peer-Task erfüllt [LOCKED]    │
│                                          [ALLE BADGES ANZEIGEN ▾] │
│                                                                   │
│  ─── STATISTIKEN ─────────────────────────────────────────────── │
│                                                                   │
│  Quests erledigt:  42       Clean Runs:    34/42 (81%)            │
│  Reviews:          31       Skills erstellt:  8                   │
│  Wiki-Artikel:     15       Code-Nodes:    120                    │
│  Avg. Review-Zeit: 18 Min.  Avg. Task-Zeit:  4.2 Std.            │
│                                                                   │
│  ─── PERSÖNLICHE EINSTELLUNGEN ───────────────────────────────── │
│                                                                   │
│  THEME                                                            │
│  ● space-neon   ○ industrial-amber   ○ operator-mono              │
│                                                                   │
│  INTERFACE-TONE                                                   │
│  🎮 ● Game Mode   💼 ○ Pro Mode                                   │
│                                                                   │
│  BENACHRICHTIGUNGEN                                               │
│  ☑ SLA-Warnungen     ☑ Review-Anfragen    ☑ Skill-Proposals      │
│  ☑ Eskalationen      ☐ Peer-Events (FYI)  ☐ EXP-Notifications    │
│                                                                   │
│  [ÄNDERUNGEN SPEICHERN]                                           │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

### Avatar-Upload

```text
┌─ AVATAR ÄNDERN ───────────────────────────────────────────────────┐
│                                                                   │
│  ┌──────────────┐        Upload (max 2 MB, WebP/PNG/JPG)        │
│  │              │        [DATEI AUSWÄHLEN]                       │
│  │   VORSCHAU   │                                                │
│  │              │        Oder: Initialen-Avatar verwenden         │
│  └──────────────┘        [AUTO-GENERIEREN ▶]                     │
│                                                                   │
│  AVATAR-RAHMEN  (freigeschaltet durch Level-Ups)                 │
│  ○ Kein Rahmen         [verfügbar]                               │
│  ● Silber-Rahmen       [Lvl 5 — freigeschaltet ✓]               │
│  ○ Gold-Rahmen         [Lvl 8 — 🔒 gesperrt]                    │
│  ○ Holo-Rahmen         [Lvl 10 — 🔒 gesperrt]                   │
│                                                                   │
│  [ABBRECHEN]                              [SPEICHERN ✓]          │
└───────────────────────────────────────────────────────────────────┘
```

**Technisch:**
- Upload via `POST /api/users/me/avatar` (multipart/form-data, max 2 MB, WebP/PNG/JPG)
- Backend konvertiert zu WebP (max 256x256px), speichert in `HIVEMIND_UPLOAD_DIR/avatars/<uuid>.webp`
- Avatar-Rahmen werden aus `level_thresholds.unlocks` abgeleitet — nur freigeschaltete Rahmen auswählbar
- Initialen-Avatar: generiert serverseitig aus `display_name` oder `username` (deterministisches Farb-Hashing)
- Profil-Daten: `PATCH /api/users/me` mit `display_name`, `bio`, `preferred_theme`, `preferred_tone`, `avatar_frame`

### Peer-Profil (read-only, Phase F)

Klick auf einen Peer in der Gilde-View öffnet ein read-only Profil-Panel:

```text
┌─ PEER-PROFIL: ben-hivemind ───────────────────────────────────────┐
│                                                                   │
│  ┌────────┐  ben-hivemind                                         │
│  │ AVATAR │  "Backend-Spezialist, JWT-Enthusiast"                 │
│  │ [GOLD] │  ● online · zuletzt vor 3 Min.                       │
│  └────────┘  Level 7 — Legenden-Kommandant                       │
│              ████████████████████░░░  3200 / 4000 EXP             │
│                                                                   │
│  BADGES: 🥇 Master Architect · 🥈 Guild Contributor · 🥉 Söldner │
│                                                                   │
│  BEITRÄGE ZUR GILDE:                                              │
│  ⚔ Skills geteilt: 4    🗺 Nodes beigetragen: 80                 │
│  Delegierte Quests erledigt: 6                                    │
│                                                                   │
│  AKTIVE QUEST: TASK-42 "JWT Refresh Token"                        │
│  [QUEST ANSEHEN ▶]                                                │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

### Einstellungs-Hierarchie: Per-User vs. Global

| Einstellung | Per-User (`users`-Tabelle) | Global (`app_settings`) | Verhalten |
| --- | --- | --- | --- |
| Theme | `preferred_theme` | `app_settings['default_theme']` | User-Pref überschreibt Global; neuer User erbt Global |
| Tone | `preferred_tone` | `app_settings['default_tone']` | User-Pref überschreibt Global; neuer User erbt Global |
| Notification-Filter | `users.notification_preferences` (JSONB) | — | Rein per-User; Default: alle aktiv |
| Solo/Team-Modus | — | `app_settings['hivemind_mode']` | Rein global (betrifft alle User) |
| MCP-Transport | — | `app_settings` | Rein global |
| AI-Provider | — | `ai_provider_configs` | Rein global (Admin) |

> **Design-Entscheidung:** Theme und Tone sind bewusst per-User — in einem Team-Setup möchte ein Entwickler vielleicht `operator-mono` (fokussiert) nutzen während ein anderer `space-neon` (verspielt) bevorzugt. Die globale Einstellung in Settings → SYSTEM wird damit zum **Default für neue User** degradiert.

---

## Memory Ledger Browser (Phase 5)

**🎮 Game Mode:** AGENTEN-GEDÄCHTNIS | **💼 Pro Mode:** MEMORY LEDGER

**Zweck:** Einsicht in das Arbeitsgedächtnis der Agenten — was haben sie beobachtet, welche Fakten extrahiert, welche offenen Fragen existieren? Der Memory Ledger Browser macht das sonst unsichtbare Agent-Wissen für Menschen zugänglich.

**Verfügbar ab:** Phase 5 (Memory Ledger Backend ab Phase 3, UI ab Phase 5)

**Zugang:** Erreichbar als kollabierbare Sektion im Context Panel (rechts), oder als eigene Ansicht via Spotlight (Ctrl+K → "Memory").

```text
┌─ MEMORY LEDGER ───────────────────────────────────────────────────┐
│  [SCOPE: Projekt ▾]  [AGENT: Alle ▾]  [EBENE: Alle ▾]  [SUCHEN] │
├───────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ─── OFFENE FRAGEN (3) ──────────────────────────────────────── │
│  ❓ Warum ist OAuth-Flow auskommentiert? (auth/oauth.py)          │
│     Quelle: ◬ Kartograph · Session 3 · 2026-03-10                │
│     [IN WIKI SUCHEN]  [EINTRAG ANZEIGEN ▾]                       │
│                                                                   │
│  ❓ Refresh-Token-Handling fehlt komplett — Design-Entscheidung?  │
│     Quelle: ◬ Kartograph · Session 3 · 2026-03-10                │
│                                                                   │
│  ❓ Ist die Redis-Anbindung für Sessions noch geplant?            │
│     Quelle: ◎ Architekt · Session 1 · 2026-03-09                 │
│                                                                   │
│  ─── ZUSAMMENFASSUNGEN (L2) ─────────────────────────────────── │
│                                                                   │
│  📋 Auth-Subsystem (Session 3)               ◬ Kartograph         │
│     "JWT-basiert (RS256, python-jose), FastAPI-Middleware-Pattern. │
│      OAuth2 existiert aber deaktiviert. Config via Env-Vars."     │
│     Fakten: 7 · Quellen: 4 Observations · Graduiert: ✗           │
│     [DETAILS ▾]  [QUELL-EINTRÄGE ▾]                              │
│                                                                   │
│  📋 Worker-Subsystem (Session 5)             ◬ Kartograph         │
│     "Celery-basiert, Redis broker. 3 Task-Typen: sync, async,    │
│      scheduled. Dead-letter-Queue vorhanden."                     │
│     Fakten: 12 · Quellen: 8 Observations · Graduiert: ✓ → Wiki   │
│     [WIKI-ARTIKEL ANZEIGEN ▶]                                     │
│                                                                   │
│  ─── FAKTEN (L1) ────────────────────────────────────────────── │
│                                                                   │
│  auth/jwt         algorithm     RS256                             │
│  auth/jwt         library       python-jose                       │
│  auth/jwt         class         JWTValidator                      │
│  auth/middleware   pattern       FastAPI Depends() Middleware      │
│  auth/oauth       status        auskommentiert, TODO              │
│  auth/config      secret_src    ENV:JWT_SECRET                    │
│  auth/config      expiry        1h                                │
│  ...                                          [ALLE FAKTEN (47)] │
│                                                                   │
│  ─── SKILL-CANDIDATES ────────────────────────────────────────── │
│  💡 "Repo nutzt überall Repository-Pattern: Service-Layer +       │
│      Depends(). Könnte ein Skill werden."                         │
│     Von: ◬ Kartograph · Tags: pattern, skill-candidate, fastapi  │
│     Status: ● unverarbeitet                                       │
│     [→ AN GAERTNER WEITERLEITEN]                                  │
│                                                                   │
│  💡 "Bei OAuth: Token-Refresh muss vor Request-Retry stehen"     │
│     Von: ◆ Worker · Tags: pattern, skill-candidate, oauth        │
│     Status: ✓ verarbeitet → Skill "OAuth Refresh Pattern" v1     │
│                                                                   │
│  ─── ABDECKUNGS-STATUS ───────────────────────────────────────── │
│  Observations gesamt: 84                                          │
│  Durch Summaries abgedeckt: 71 (85%)                              │
│  Unbedeckt: 13  [UNBEDECKTE ANZEIGEN ▾]                          │
│  Graduiert zu Wiki/Skill: 4 Summaries                             │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

### Memory im Context Panel (kompakte Ansicht)

Wenn ein Task oder Epic selektiert ist, zeigt das Context Panel einen Memory-Abschnitt:

```text
┌─ CONTEXT PANEL: TASK-88 ─────────────────────────────────────────┐
│  ...                                                              │
│  ─── AGENTEN-GEDÄCHTNIS ──────────────────────────────────────── │
│  📋 1 Summary · 7 Fakten · 1 offene Frage                        │
│  Letzte Aktivität: ◬ Kartograph · vor 2 Std.                     │
│  [MEMORY LEDGER ÖFFNEN ▶]                                        │
│  ...                                                              │
└───────────────────────────────────────────────────────────────────┘
```

### Memory-Integrity-Warnung

Wenn unbedeckte Observations einen kritischen Anteil erreichen (> 30%), zeigt die Prompt Station einen Hinweis:

```text
⚠ MEMORY-WARNUNG: 13 Beobachtungen noch nicht verdichtet (15%).
  Empfehlung: Kartograph-Follow-up für Kompaktierung.
  [KOMPAKTIERUNG ANFORDERN ▶]
```

---

## Conductor Dashboard (Phase 8)

**Zweck:** Monitoring des automatisierten Agent-Dispatchings — welche Agenten laufen, welche sind gescheitert, wie ausgelastet sind die AI-Provider? Eingebettet als Unterbereich in Settings → Tab "KI".

```text
┌─ SETTINGS: KI — CONDUCTOR STATUS ──────────────────────────────┐
│                                                                 │
│  CONDUCTOR: ● AKTIV                          [PAUSIEREN ⏸]      │
│  Dispatches heute: 47   ·   Fehler: 2   ·   Ø Latenz: 3.2s    │
│                                                                 │
│  ─── AKTIVE DISPATCHES ─────────────────────────────────────── │
│  ◆ Worker    TASK-92  → Ollama llama3.3       seit 45s  [⟳]    │
│  ⊕ Gaertner  TASK-88  → Anthropic claude      seit 12s  [⟳]    │
│  ◬ Kartograph (idle)                                            │
│                                                                 │
│  ─── PROVIDER-AUSLASTUNG ───────────────────────────────────── │
│  Ollama     ████████░░  8/10 RPM   gpu1: ✓  gpu2: ✓  gpu3: ⚠  │
│  Anthropic  ██░░░░░░░░  2/10 RPM                                │
│  Google     ░░░░░░░░░░  0/5 RPM    (idle)                      │
│                                                                 │
│  ─── LETZTE DISPATCHES ─────────────────────────────────────── │
│  14:32  ◆ Worker    TASK-91  ✓ completed  3.1s  Ollama          │
│  14:30  ⊕ Gaertner  TASK-87  ✓ completed  8.4s  Anthropic      │
│  14:28  ◬ Kartograph         ✗ failed     —     Google          │
│         → Error: 429 Rate Limit Exceeded (retry in 12s)         │
│  14:15  ◈ Reviewer  TASK-90  ✓ completed  5.2s  Anthropic      │
│         → Confidence: 0.94 → auto-approved (Grace: 15 Min.)    │
│                                                                 │
│  [VOLLSTÄNDIGES DISPATCH-LOG → AUDIT-TAB ▶]                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```
