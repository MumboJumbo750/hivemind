---
title: "Requirement Capture — Neue Anforderung erfassen"
service_scope: ["system"]
stack: ["prompt-template", "ux-flow"]
confidence: 0.9
source_epics: ["EPIC-PHASE-3"]
skill_type: "system"
---

## Skill: Requirement Capture — Neue Anforderung in Stratege-Prompt übersetzen

### Wann verwenden

Pinne diesen Skill wenn:

- **Stratege:** User möchte eine neue Anforderung/Idee als Epic formulieren lassen
- **Bibliothekar:** Context-Assembly für einen neuen Anforderungs-Draft
- **Kartograph:** Nach Repo-Analyse entstehen neue Erkenntnisse → Anforderungs-Draft erstellen

---

### Konzept: Drei Enrichment-Layer

Der Requirement-Capture-Flow reichert einen rohen User-Text schrittweise an — je nach Phase des Projekts:

| Phase | Layer | Was wird injiziert |
| --- | --- | --- |
| 1–2 | **Basis** | Projektname, Phase, Epics-Übersicht, Tech-Stack |
| 3+ | **pgvector** | Ähnliche Epics (Similarity), relevante Skills, Kapazität |
| 4+ | **Write** | Stratege-Output → `propose_epic` direkt (kein Copy-Paste) |

---

### Phase 1–2: Basis-Enrichment (manuell)

Wenn `hivemind-draft_requirement` noch nicht verfügbar ist, assembliere den Stratege-Prompt so:

```
Kontext für den Strategen:
- Projekt: {Projektname}
- Aktuelle Phase: {Phase}
- Tech-Stack: {aus AGENTS.md oder Projekt-Metadata}
- Offene Epics: {Liste aller Epics mit State}

Neue Anforderung vom User:
"{roher Anforderungstext}"

Auftrag: Analysiere die Anforderung. Prüfe Überschneidungen mit bestehenden Epics.
Formuliere einen Epic-Proposal (Titel, Beschreibung, Rationale, suggested_priority,
suggested_phase, depends_on) — bereit für Triage.
```

---

### Phase 3+: `hivemind-draft_requirement` Tool

```
POST /api/requirements/draft
{
  "text": "Anforderungstext vom User",
  "priority_hint": "high|medium|low",   // optional
  "tags": ["feature", "ux"]             // optional
}
```

**Response:**

```json
{
  "prompt": "... vollständiger Stratege-Prompt ...",
  "enrichment": {
    "similar_epics": [
      { "id": "uuid", "title": "...", "similarity": 0.87 }
    ],
    "relevant_skills": [
      { "id": "uuid", "title": "...", "similarity": 0.79 }
    ],
    "capacity": {
      "in_progress_tasks": 4,
      "blocked_tasks": 1
    }
  },
  "draft_id": "uuid"
}
```

Der `draft_id` verweist auf einen `epic_proposals`-Eintrag mit `state: draft` — wird zu `proposed` sobald der Stratege seinen Output liefert und der User ihn einspielt.

---

### Enrichment-Inhalte im Detail

#### Basis (Phase 1–2)

| Inhalt | Quelle | Zweck |
| --- | --- | --- |
| Projektname + Phase | `projects`-Tabelle | Strategischer Rahmen |
| Tech-Stack | Projekt-Metadata oder AGENTS.md | Stack-Passender Vorschlag |
| Alle Epics (ID, Titel, State) | `epics`-Tabelle | Duplikat-Erkennung durch Strategen |

#### pgvector (Phase 3+)

| Inhalt | Quelle | Zweck |
| --- | --- | --- |
| Top 3 ähnliche Epics | pgvector Similarity auf `epics.description_embedding` | Verhindert Epic-Duplikate |
| Top 5 relevante Skills | pgvector Similarity auf `skills.content_embedding` | Stratege kennt verfügbare Tools |
| In-Progress Task-Count | `tasks`-Tabelle | Kapazitäts-Hinweis für Priorisierung |

---

### Stratege-Prompt Struktur (enriched)

```markdown
Du bist der Stratege im Hivemind-System.

## Projektkontext
**Projekt:** {name} | **Phase:** {phase} | **Stack:** {tech_stack}

## Bestehende Epics ({count})
{epics_list mit State}

## Ähnliche Epics (pgvector, Phase 3+)
{similar_epics mit Similarity-Score}

## Relevante Skills ({count})
{skills_list}

## Neue Anforderung (User-Input)
"{anforderungstext}"

## Auftrag
1. Prüfe ob die Anforderung bereits durch ein bestehendes Epic abgedeckt ist.
   → Falls ja: Empfehle das Epic zu erweitern (update_epic), nicht neu anlegen.
2. Falls neue Anforderung: Formuliere einen Epic-Proposal:
   - **Titel**: kurz, präzise
   - **Beschreibung**: Was & Warum
   - **Rationale**: Ableitung aus der Anforderung
   - **suggested_priority**: critical | high | medium | low
   - **suggested_phase**: {nächste offene Phase-Nummer}
   - **depends_on**: {Epic-IDs die abgeschlossen sein müssen}
3. Identifiziere Risiken oder offene Fragen (DoD-Rahmen).
4. Rufe `hivemind-propose_epic` auf (Phase 4+) oder liste den Proposal als Markdown.
```

---

### UI-Flow (Phase 3 Frontend)

```
Command Deck oder Epic-Übersicht
  → Button: "Neue Anforderung"
  → Modal öffnet sich
    → Freitextfeld: "Beschreibe deine Anforderung..."
    → Optional: Priorität-Hint, Tags
    → Button: "Stratege-Prompt generieren"
  → Aufruf: POST /api/requirements/draft
  → Ergebnis: Volltext-Modal mit Copy-to-Clipboard
  → User kopiert Prompt in AI-Client
  → AI liefert Epic-Proposal als Markdown
  → User fügt Proposal-Text in zweites Textfeld ein → Speichern
  → System erstellt epic_proposal (state: proposed) → Triage Station
```

---

### Abgrenzung: Anforderung vs. Task

| | Anforderung | Task |
| --- | --- | --- |
| **Input** | Roher User-Text | Bestehendes gescoptes Epic |
| **Output** | Stratege-Prompt + Epic-Proposal | Worker-Prompt + Ergebnis-Artifact |
| **Agent** | Stratege | Worker |
| **Granularität** | Epic-Level (Wochen/Monate) | Task-Level (Stunden/Tage) |
| **Review** | Triage Station (EPIC PROPOSAL) | Review-Gate (qa_check) |

---

### Wichtig

- **Anforderung ≠ Task** — keine direkte Task-Erstellung aus Freitext. Immer via Stratege → Architekt → Task.
- **Duplikat-Check immer** — der Stratege soll explizit auf ähnliche Epics hinweisen, bevor er einen neuen Proposal erstellt.
- **Kapazitäts-Hinweis** — wenn viele Tasks in-progress, empfiehlt der Stratege eine niedrigere Priorität oder schlägt eine spätere Phase vor.
