# Gaertner — Wissenskonsolidierung & Skill-Destillation

← [Agenten-Übersicht](./overview.md) | [Index](../../masterplan.md)

Der Gaertner ist der **Wissenspfleger** des Systems. Er destilliert Gelerntes in wiederverwendbare Skills, aktualisiert Docs und dokumentiert getroffene Entscheidungen. Dabei arbeitet er aus **drei Quellen**: abgeschlossenen Tasks, Review-Feedback aus `qa_failed`-Schleifen und Skill-Kandidaten die andere Agenten im Memory Ledger markiert haben.

> Analogie: Ein Gärtner der nach der Ernte (Task done) die Samen (Skills) für die nächste Saison aufbereitet — und zusätzlich die Fundstücke einsammelt, die Kartograph und Stratege als vielversprechende Keimlinge markiert haben.

---

## Kernaufgaben

1. **Skill-Destillation** — Extrahiert wiederverwendbare Instruktionen aus abgeschlossenen Tasks
2. **Skill-Candidate-Harvesting** — Konsumiert `skill-candidate`-markierte Memory Entries anderer Agenten und formalisiert sie zu Skill-Proposals
3. **Skill-Change-Proposals** — Schlägt Verbesserungen an bestehenden Skills vor
4. **Decision Records** — Dokumentiert getroffene Entscheidungen als ADRs (Architecture Decision Records)
5. **Doc-Updates** — Aktualisiert Epic-Docs basierend auf Task-Ergebnissen
6. **Wiki-Updates** — Ergänzt oder erstellt erklärende Wiki-Artikel wenn Wissen nicht in einen Skill passt
7. **Skill-Proposal-Einreichung** — Reicht fertige Proposals zur Review ein

---

## RBAC

Der Gaertner arbeitet als `developer` oder `admin`:

| Permission | Beschreibung |
| --- | --- |
| `propose_skill` | Neuen Skill vorschlagen (→ `draft`) |
| `submit_skill_proposal` | Proposal zur Review einreichen (`draft → pending_merge`) |
| `read_any_skill` | Alle aktiven Skills sehen (für Duplikat-Prüfung) |
| `read_any_doc` | Alle Docs sehen (für Updates) |
| `create_wiki_article` / `update_wiki_article` | Langfristiges Betriebswissen im Wiki konservieren |

> Wie der Architekt ist "Gaertner" keine eigene RBAC-Rolle, sondern eine **Workflow-Funktion**. Die Rechte kommen aus der `developer`- oder `admin`-Rolle.

---

## Typischer Workflow

### Workflow A: Task-basierte Destillation (wie bisher)

```
1. Task geht auf `done` (Owner hat im Review genehmigt)
   → Prompt Station zeigt: "Jetzt: Gaertner"
   → Gaertner-Prompt enthält den abgeschlossenen Task als Kontext

2. User fügt Gaertner-Prompt in AI-Client ein
   → AI analysiert: Was wurde gelernt? Gibt es wiederverwendbare Muster?

3. AI destilliert neuen Skill (falls sinnvoll):
   hivemind-propose_skill {
     "title": "PostgreSQL Index-Optimierung",
     "content": "## Skill: PostgreSQL Index-Optimierung\n\n### Rolle\n...",
     "service_scope": ["backend"],
     "stack": ["postgresql"]
   }

4. AI aktualisiert bestehenden Skill (falls relevant):
   hivemind-propose_skill_change {
     "skill_id": "uuid",
     "diff": "### Ergänzung\n- Composite Indexes bevorzugen bei ...",
     "rationale": "Aus TASK-88 gelernt: Composite Index war 3x schneller"
   }

5. AI dokumentiert Entscheidung:
   hivemind-create_decision_record {
     "epic_id": "EPIC-12",
     "decision": "JWT statt Session-Auth für API-Endpoints",
     "rationale": "Stateless, bessere Skalierbarkeit, Team-Konsens"
   }

6. AI aktualisiert Epic-Doc:
   hivemind-update_doc { "id": "uuid", "content": "..." }

7. AI reicht Skill-Proposal zur Review ein:
   hivemind-submit_skill_proposal { "skill_id": "uuid" }
   → lifecycle: draft → pending_merge
   → Bei `governance.skill_merge != manual` dispatcht der Conductor anschliessend Triage fuer den Review-Entscheid

8. Falls das Wissen eher Referenzdokumentation ist:
   hivemind-create_wiki_article / hivemind-update_wiki_article
```

### Workflow B: Skill-Candidate-Harvesting (NEU)

Andere Agenten markieren Pattern-Beobachtungen im Memory Ledger mit dem Tag `skill-candidate` (→ [Memory Ledger — Skill-Candidate-Tagging](../features/memory-ledger.md#skill-candidate-tagging)). Der Gaertner konsumiert diese als zusätzliche Input-Quelle.

```
1. Gaertner-Prompt enthält ZUSÄTZLICH zum Task:
   hivemind-search_memories { "query": "skill-candidate", "scope": "project", "level": "all" }
   → Kartograph hat 3 Pattern-Beobachtungen mit tag "skill-candidate" markiert
   → Stratege hat 1 Planungs-Pattern markiert
   → Worker hat 1 Debugging-Pattern bei Multi-Session-Task markiert

2. AI bewertet Skill-Kandidaten:
   → Ist das Pattern wiederverwendbar? Nur task-spezifisch?
   → Gibt es bereits einen ähnlichen Skill?
   → Kann ich es aus dem Memory-Kontext formalisieren oder brauche ich mehr Detail?

3a. Bei ausreichendem Kontext → direkt propose_skill:
    hivemind-propose_skill {
      "title": "Repository-Pattern mit Service-Layer",
      "content": "...",
      "service_scope": ["backend"],
      "stack": ["python", "fastapi"]
    }
    → Rationale referenziert Quelle: "Basierend auf Kartograph Memory [uuid]"

3b. Bei unzureichendem Kontext → Drill-Down:
    hivemind-search_memories { "query": "repository pattern", "level": "L0" }
    → Rohdaten des Kartographen laden für mehr Detail

4. Nach Proposal: Memory-Entry als verarbeitet markieren:
   hivemind-save_memory {
     "content": "Skill-Candidate [uuid] verarbeitet → Skill-Proposal erstellt",
     "tags": ["skill-candidate-processed"]
   }
```

> **Warum nicht alle Agenten direkt Skills vorschlagen?** Skill-Proposals brauchen formale Qualität (Frontmatter, Guards, Handlungsorientierung). Der Gaertner ist darauf spezialisiert. Andere Agenten können unkompliziert Pattern flaggen (`skill-candidate`), ohne sich um das Skill-Format kümmern zu müssen. **Ausnahme: Der Kartograph** hat direktes `propose_skill`-Recht — er sieht das gesamte Repo und entdeckt Codebase-weite Patterns die sofort formalisierbar sind (→ [Kartograph](./kartograph.md)).

---

## Auslöser

Der Gaertner wird in vier Situationen aktiv:

| Auslöser | Kontext | Ziel |
| --- | --- | --- |
| **Task → `done`** | Einzelner abgeschlossener Task | Skills/Docs aus dem Task ableiten |
| **Task → `qa_failed`** | Review-Kommentar + Fehlmuster | Skill-/Doc-Anpassungen aus dem Feedback ableiten |
| **Epic komplett** | Alle Tasks eines Epics `done` | Übergreifende Patterns destillieren, Epic-Doc finalisieren |
| **Skill-Candidates vorhanden** | Memory Entries mit Tag `skill-candidate` im Scope | Von anderen Agenten markierte Patterns zu formalen Skills destillieren |

---

## MCP-Tools

```text
-- Skill-Destillation
hivemind-propose_skill          { "title": "...", "content": "...", "service_scope": [...] }
hivemind-propose_skill_change   { "skill_id": "uuid", "diff": "...", "rationale": "..." }
hivemind-submit_skill_proposal  { "skill_id": "uuid" }

-- Dokumentation
hivemind-create_decision_record { "epic_id": "EPIC-12", "decision": "...", "rationale": "..." }
hivemind-update_doc             { "id": "uuid", "content": "..." }
hivemind-create_wiki_article    { "title": "...", "content": "...", "tags": [...] }
hivemind-update_wiki_article    { "id": "uuid", "content": "..." }

-- Skill-Candidate-Harvesting (Memory Ledger)
hivemind-search_memories        { "query": "skill-candidate", "scope": "project", "level": "all" }
hivemind-get_memory_context     { "scope": "project", "scope_id": "uuid" }
hivemind-save_memory            { "content": "...", "tags": ["skill-candidate-processed"] }
```

---

## Skill-Qualitätskriterien

Der Gaertner-Prompt enthält Leitfragen für die Skill-Erstellung:

1. **Wiederverwendbar?** — Ist das Pattern Task-spezifisch oder generalisierbar?
2. **Abgrenzung klar?** — Gibt es bereits einen ähnlichen Skill? → `propose_skill_change` statt neuer Skill
3. **Handlungsorientiert?** — Beschreibt der Skill *wie* etwas gemacht wird, nicht nur *was*?
4. **Testbar?** — Können Guards definiert werden die die Skill-Einhaltung prüfen?
5. **Scope richtig?** — Global oder projektspezifisch?

---

## Solo-Modus

Im Solo-Modus ist der Entwickler selbst der Gaertner. Der Gaertner-Prompt erinnert daran, nach jedem abgeschlossenen Task innezuhalten und das Gelernte zu konservieren — ein strukturierter Reflexionsprozess.

---

## Abgrenzung

| | Gaertner | Kartograph | Worker |
| --- | --- | --- | --- |
| Timing | Nach Task-Abschluss + bei Skill-Candidates | Initial + iterativ | Während Task |
| Input | Abgeschlossener Task + Ergebnisse + Skill-Candidates anderer Agenten | Unbekanntes Repository | Ready Task + Context |
| Output | Skill-Proposals, Decision Records, Doc-Updates | Wiki, Epic-Docs, System-Karte, Skill-Proposals (direkt) | Task-Ergebnis + Artefakte |
| Skill-Rechte | `propose_skill`, `propose_skill_change` (formale Destillation) | `propose_skill`, `propose_skill_change` (Codebase-Patterns) | Nur `skill-candidate`-Tagging via Memory |
| Fokus | Konservieren & Destillieren | Entdecken & Kartieren | Ausführen & Liefern |

### Skill-Proposal-Rechte — Wer darf was?

| Fähigkeit | Gaertner | Kartograph | Alle anderen |
| --- | --- | --- | --- |
| `propose_skill` formal | ✓ | ✓ | — |
| `propose_skill_change` | ✓ | ✓ | — |
| `skill-candidate` taggen (Memory) | ✓ | ✓ | ✓ |
| `submit_skill_proposal` | ✓ | ✓ | — |

> **Warum nur Gaertner + Kartograph?** Skill-Proposals erfordern formale Qualität (Frontmatter, Guards, handlungsorientierter Body). Der Gaertner ist darauf spezialisiert (post-Task-Reflexion), der Kartograph sieht als einziger Agent das gesamte Repo und entdeckt Codebase-weite Patterns. Andere Agenten können Patterns low-cost über `skill-candidate`-Tags flaggen — der Gaertner formalisiert sie dann.
