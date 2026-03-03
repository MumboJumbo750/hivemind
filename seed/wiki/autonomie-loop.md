---
slug: autonomie-loop
title: "Autonomie-Loop — Von BYOAI zur vollen Autonomie"
tags: [autonomie, conductor, reviewer, governance, phase-8]
linked_epics: [EPIC-PHASE-8]
---

# Autonomie-Loop — Von BYOAI zur vollen Autonomie

Hivemind startet als manuelles BYOAI-System (Bring Your Own AI) und skaliert schrittweise zur vollständigen AI-Autonomie — ohne Architekturbruch.

## Phase 1–7: Manueller Modus (BYOAI)

```
Prompt Station → User kopiert Prompt → AI-Client → MCP-Tool-Aufrufe
```

Der User ist in der Schleife: Prompts werden angezeigt, kopiert, und Ergebnisse über MCP-Tools zurückgespielt.

## Phase 8: Auto-Modus

```
State-Transition → Conductor dispatcht Agent → AI-Provider → MCP-Tools → nächster Agent
```

### Conductor-Orchestrator
Event-driven Service: Reagiert auf State-Transitions und dispatcht den passenden Agenten. 12 Dispatch-Regeln, Cooldown, Idempotenz. Deaktivierbar pro Projekt.

### Reviewer-Agent
7. Agent-Rolle: Prüft Task-Ergebnisse automatisiert gegen DoD, Guards und Skills. Confidence-basiert: `approve`, `reject` oder `needs_human_review`.

### Governance-Levels
3 Stufen pro Entscheidungstyp:
- **manual:** Mensch entscheidet (wie bisher)
- **assisted:** AI empfiehlt, Mensch bestätigt (1-Click)
- **auto:** AI entscheidet mit Grace Period

7 konfigurierbare Typen: `review`, `epic_proposal`, `epic_scoping`, `skill_merge`, `guard_merge`, `decision_request`, `escalation`.

## Schrittweise Migration

Einzelne Rollen können unabhängig automatisiert werden. Nicht-konfigurierte Rollen fallen auf BYOAI zurück. So kann ein Team zuerst den Worker automatisieren und den Reviewer manuell lassen.
