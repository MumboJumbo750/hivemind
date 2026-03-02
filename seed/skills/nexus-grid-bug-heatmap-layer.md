---
title: "Nexus Grid Bug-Heatmap Layer [DEPRECATED]"
service_scope: ["frontend"]
stack: ["typescript", "vue3", "cytoscape", "sse"]
skill_type: "domain"
confidence: 0.5
source_epics: ["EPIC-PHASE-7"]
---

## Deprecated Skill

Dieser Skill ist im konsolidierten Cytoscape-Nexus-Skill aufgegangen.

Nutze stattdessen:
- `seed/skills/cytoscape-nexus-grid.md`

Enthaltene Themen im neuen Skill:
- Heatmap-Toggle und Lazy Loading
- Hover-Details (`count`, `last_seen`, `stack_trace_hash`-Preview)
- SSE-Refresh bei `bug_aggregated`
- Batch-Updates mit `cy.batch()`
