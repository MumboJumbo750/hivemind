---
slug: "agent-konzept"
title: "Agent-Konzept — Wie die Agenten zusammenarbeiten"
tags: ["agenten", "workflow", "konzept"]
linked_epics: ["EPIC-PHASE-3", "EPIC-PHASE-4", "EPIC-PHASE-5"]
---

# Agent-Konzept — Wie die Agenten zusammenarbeiten

## Die 7 Agenten

Hivemind nutzt spezialisierte Agenten die in einer definierten Reihenfolge arbeiten. In Phase 1–7 sind Agenten *Prompt-Rollen* — der Mensch führt den generierten Prompt im AI-Client aus. Ab Phase 8 arbeiten sie autonom.

| Agent | Aufgabe | Metapher |
| --- | --- | --- |
| **Kartograph** | Fog-of-War Explorer, Repo-Analyse, Wiki-Autor | Soldat der jeden Hügel besteigt |
| **Stratege** | Plan → Epics, Roadmap, Dependencies | General mit der Landkarte |
| **Architekt** | Epic → Tasks, Context Boundaries, Zuweisung | Feldherr der Einsatzbefehle gibt |
| **Worker** | Task-Ausführung, Guard-Prüfung, Ergebnislieferung | Soldat im Feld |
| **Gaertner** | Skill-Destillation, Decision Records, Doc-Updates | Gärtner nach der Ernte |
| **Triage** | Event-Routing, Proposals, Dead Letters | Feldlazarett-Triage |
| **Reviewer** | Code-Review, DoD-Prüfung (Phase 8) | Qualitätsprüfer |

## Workflow-Reihenfolge

```
Kartograph → Stratege → Architekt → Worker → Gaertner
                                       ↑         |
                                       └─────────┘
                                     (Skill-Feedback-Loop)
```

1. **Kartograph** erkundet das System und schreibt Wiki + Docs
2. **Stratege** leitet daraus Epics ab
3. **Architekt** zerlegt Epics in Tasks mit Context Boundaries
4. **Worker** führt Tasks aus und liefert Ergebnisse
5. **Gaertner** destilliert wiederverwendbare Skills aus Ergebnissen
6. **Triage** routet eingehende Events und Proposals

## BYOAI-Prinzip

In Phase 1–7 generiert Hivemind den Prompt, aber der Mensch entscheidet:
- Welcher AI-Client genutzt wird (Claude, GPT, Gemini, Ollama, ...)
- Ob der Prompt ausgeführt wird
- Ob das Ergebnis akzeptiert wird

Die Prompt Station zeigt an welcher Agent als nächstes dran ist und liefert den fertigen Prompt.
