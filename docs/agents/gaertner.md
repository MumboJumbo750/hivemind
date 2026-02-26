# Gaertner — Wissenskonsolidierung & Skill-Destillation

← [Agenten-Übersicht](./overview.md) | [Index](../../masterplan.md)

Der Gaertner ist der **Wissenspfleger** des Systems. Nach Abschluss eines Tasks destilliert er das Gelernte in wiederverwendbare Skills, aktualisiert Docs und dokumentiert getroffene Entscheidungen.

> Analogie: Ein Gärtner der nach der Ernte (Task done) die Samen (Skills) für die nächste Saison aufbereitet und das Wissen für die Nachwelt konserviert.

---

## Kernaufgaben

1. **Skill-Destillation** — Extrahiert wiederverwendbare Instruktionen aus abgeschlossenen Tasks
2. **Skill-Change-Proposals** — Schlägt Verbesserungen an bestehenden Skills vor
3. **Decision Records** — Dokumentiert getroffene Entscheidungen als ADRs (Architecture Decision Records)
4. **Doc-Updates** — Aktualisiert Epic-Docs basierend auf Task-Ergebnissen
5. **Skill-Proposal-Einreichung** — Reicht fertige Proposals zur Admin-Review ein

---

## RBAC

Der Gaertner arbeitet als `developer` oder `admin`:

| Permission | Beschreibung |
| --- | --- |
| `propose_skill` | Neuen Skill vorschlagen (→ `draft`) |
| `submit_skill_proposal` | Proposal zur Review einreichen (`draft → pending_merge`) |
| `read_any_skill` | Alle aktiven Skills sehen (für Duplikat-Prüfung) |
| `read_any_doc` | Alle Docs sehen (für Updates) |

> Wie der Architekt ist "Gaertner" keine eigene RBAC-Rolle, sondern eine **Workflow-Funktion**. Die Rechte kommen aus der `developer`- oder `admin`-Rolle.

---

## Typischer Workflow

```
1. Task geht auf `done` (Owner hat im Review genehmigt)
   → Prompt Station zeigt: "Jetzt: Gaertner"
   → Gaertner-Prompt enthält den abgeschlossenen Task als Kontext

2. User fügt Gaertner-Prompt in AI-Client ein
   → AI analysiert: Was wurde gelernt? Gibt es wiederverwendbare Muster?

3. AI destilliert neuen Skill (falls sinnvoll):
   hivemind/propose_skill {
     "title": "PostgreSQL Index-Optimierung",
     "content": "## Skill: PostgreSQL Index-Optimierung\n\n### Rolle\n...",
     "service_scope": ["backend"],
     "stack": ["postgresql"]
   }

4. AI aktualisiert bestehenden Skill (falls relevant):
   hivemind/propose_skill_change {
     "skill_id": "uuid",
     "diff": "### Ergänzung\n- Composite Indexes bevorzugen bei ...",
     "rationale": "Aus TASK-88 gelernt: Composite Index war 3x schneller"
   }

5. AI dokumentiert Entscheidung:
   hivemind/create_decision_record {
     "epic_id": "uuid",
     "decision": "JWT statt Session-Auth für API-Endpoints",
     "rationale": "Stateless, bessere Skalierbarkeit, Team-Konsens"
   }

6. AI aktualisiert Epic-Doc:
   hivemind/update_doc { "id": "uuid", "content": "..." }

7. AI reicht Skill-Proposal zur Review ein:
   hivemind/submit_skill_proposal { "skill_id": "uuid" }
   → lifecycle: draft → pending_merge
   → Admin-Notification: "Neues Skill-Proposal wartet auf Review"
```

---

## Auslöser

Der Gaertner wird in zwei Situationen aktiv:

| Auslöser | Kontext | Ziel |
| --- | --- | --- |
| **Task → `done`** | Einzelner abgeschlossener Task | Skills/Docs aus dem Task ableiten |
| **Epic komplett** | Alle Tasks eines Epics `done` | Übergreifende Patterns destillieren, Epic-Doc finalisieren |

---

## MCP-Tools

```text
hivemind/propose_skill          { "title": "...", "content": "...", "service_scope": [...] }
hivemind/propose_skill_change   { "skill_id": "uuid", "diff": "...", "rationale": "..." }
hivemind/submit_skill_proposal  { "skill_id": "uuid" }
hivemind/create_decision_record { "epic_id": "uuid", "decision": "...", "rationale": "..." }
hivemind/update_doc             { "id": "uuid", "content": "..." }
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
| Timing | Nach Task-Abschluss | Initial + iterativ | Während Task |
| Input | Abgeschlossener Task + Ergebnisse | Unbekanntes Repository | Ready Task + Context |
| Output | Skill-Proposals, Decision Records, Doc-Updates | Wiki, Epic-Docs, System-Karte | Task-Ergebnis + Artefakte |
| Fokus | Konservieren & Destillieren | Entdecken & Kartieren | Ausführen & Liefern |
