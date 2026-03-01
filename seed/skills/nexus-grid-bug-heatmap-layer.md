---
title: Nexus Grid Bug-Heatmap Layer
service_scope:
- frontend
stack:
- typescript
- vue3
- cytoscape
confidence: 0.5
source_epics:
- EPIC-PHASE-7
---

## Skill: Nexus Grid Bug-Heatmap Layer

### Rolle
Du erweiterst das bestehende Cytoscape.js Nexus Grid (2D Graph) um einen Bug-Heatmap-Layer. Knotengröße und -farbe werden nach `node_bug_reports.count` skaliert.

### Konventionen
- Datenquelle: `GET /api/nexus/graph` erweitert um `bug_count` und `bug_severity` pro Node
- Cytoscape-Styling:
  - Knotengröße: `Math.min(20 + bug_count * 3, 80)` px
  - Knotenfarbe: Gradient von `--color-success` (0 bugs) → `--color-warning` (1-5) → `--color-danger` (6+)
  - Opacity: `Math.min(0.4 + bug_count * 0.1, 1.0)`
- Hover: Bug-Details-Panel zeigt Severity, Count, letzte Sentry-Issue-IDs
- Toggle: Heatmap-Layer ein/ausschaltbar über Toolbar-Button
- Performance: Nur Nodes mit `bug_count > 0` bekommen Heatmap-Styling

### Cytoscape-Style-Extension

```typescript
function bugHeatmapStyle(bugCount: number, severity: string): Partial<cytoscape.Css.Node> {
  const size = Math.min(20 + bugCount * 3, 80)
  const color = severity === 'critical' 
    ? 'var(--color-danger)' 
    : severity === 'warning' 
      ? 'var(--color-warning)' 
      : 'var(--color-info)'
  
  return {
    width: size,
    height: size,
    'background-color': bugCount > 0 ? color : 'var(--color-node-default)',
    'background-opacity': Math.min(0.4 + bugCount * 0.1, 1.0),
    'border-width': bugCount > 5 ? 3 : 1,
    'border-color': bugCount > 5 ? 'var(--color-danger)' : 'var(--color-border)',
  }
}
```

### Hover-Panel

```vue
<template>
  <div v-if="selectedNode?.bugCount > 0" class="bug-detail-panel">
    <h4>Bug Report: {{ selectedNode.label }}</h4>
    <div class="stat">Count: {{ selectedNode.bugCount }}</div>
    <div class="stat">Severity: {{ selectedNode.bugSeverity }}</div>
    <div class="stat">Last seen: {{ formatDate(selectedNode.bugLastSeen) }}</div>
    <ul>
      <li v-for="id in selectedNode.sentryIssueIds" :key="id">{{ id }}</li>
    </ul>
  </div>
</template>
```

### Wichtig
- Heatmap-Layer ist optional (Toggle) — Default: aus, damit Nexus Grid performant bleibt
- Performance-Budget: Nexus Grid + Heatmap muss unter 16ms pro Frame bleiben
- Bug-Daten werden nur geladen wenn Layer aktiv ist (lazy loading)
- Design Tokens: Nutze bestehende Semantic Tokens (`--color-danger`, `--color-warning`)
