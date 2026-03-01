---
title: "Cytoscape.js Nexus Grid (2D Graph)"
service_scope: ["frontend"]
stack: ["typescript", "vue3", "cytoscape"]
version_range: { "cytoscape": ">=3.25" }
confidence: 0.8
source_epics: ["EPIC-PHASE-5"]
guards:
  - title: "TypeScript Linting"
    command: "npx eslint src/"
  - title: "Type Check"
    command: "npx vue-tsc --noEmit"
---

## Skill: Cytoscape.js Nexus Grid (2D Graph)

### Rolle
Du implementierst den Nexus Grid als interaktive 2D-Graph-Visualisierung mit Cytoscape.js.
Der Graph zeigt Code-Nodes mit Fog-of-War-Overlay und ermöglicht Navigation durch die Codebasis.

### Kontext

Der Nexus Grid verbindet drei Ebenen: Code-Struktur, Kartograph-Erkundungsstand (Fog of War)
und Bug-Report-Dichte. Phase 5 implementiert die 2D-Basisversion.

```text
● Kartiert (explored_at gesetzt)
○ Bekannt aber unerkundert (explored_at = NULL)
░ Fog of War (semi-transparent Overlay)
```

### Konventionen

- **Bibliothek:** Cytoscape.js (verbindlich, keine Alternativen)
- **Layout:** `cose` (force-directed) für allgemeine Ansicht
- **Fog-of-War:** CSS-Klassen auf Nodes (`explored` vs `unexplored`)
- **Interaktion:** Pan, Zoom, Click auf Node → Detail-Panel
- **Projekt-Filter:** Dropdown zur Filterung auf einzelnes Projekt
- **Performance:** Optimiert für bis zu 500 Nodes (Phase 5)
- **Vue-Integration:** Composable `useCytoscapeGraph()` für Lifecycle-Management

### Grundstruktur

```typescript
// composables/useCytoscapeGraph.ts
import cytoscape, { type Core, type ElementDefinition } from 'cytoscape'
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'

export function useCytoscapeGraph(container: Ref<HTMLElement | null>) {
  const cy = ref<Core | null>(null)
  const selectedNode = ref<CodeNode | null>(null)

  onMounted(() => {
    if (!container.value) return

    cy.value = cytoscape({
      container: container.value,
      style: graphStyles,
      layout: { name: 'cose', animate: true, animationDuration: 500 },
      minZoom: 0.3,
      maxZoom: 3,
    })

    // Click-Handler: Node → Detail-Panel
    cy.value.on('tap', 'node', (event) => {
      const nodeData = event.target.data()
      selectedNode.value = nodeData as CodeNode
    })

    // Background-Click: Panel schließen
    cy.value.on('tap', (event) => {
      if (event.target === cy.value) {
        selectedNode.value = null
      }
    })
  })

  onBeforeUnmount(() => {
    cy.value?.destroy()
  })

  function setElements(elements: ElementDefinition[]) {
    cy.value?.json({ elements })
    cy.value?.layout({ name: 'cose', animate: true }).run()
  }

  return { cy, selectedNode, setElements }
}
```

### Stylesheet — Fog of War

```typescript
const graphStyles: cytoscape.Stylesheet[] = [
  // Kartierte Nodes (●)
  {
    selector: 'node.explored',
    style: {
      'background-color': 'var(--color-accent-primary)',
      'label': 'data(label)',
      'color': 'var(--color-text-primary)',
      'font-size': '10px',
      'text-valign': 'bottom',
      'text-margin-y': 6,
      'border-width': 2,
      'border-color': 'var(--color-accent-glow)',
      'width': 'mapData(bugCount, 0, 10, 20, 50)',   // Bug-Dichte = Größe
      'height': 'mapData(bugCount, 0, 10, 20, 50)',
    },
  },
  // Unerkundete Nodes (░)
  {
    selector: 'node.unexplored',
    style: {
      'background-color': 'var(--color-surface-secondary)',
      'opacity': 0.4,                                  // Fog of War
      'label': 'data(label)',
      'color': 'var(--color-text-muted)',
      'font-size': '8px',
      'border-width': 1,
      'border-color': 'var(--color-border-subtle)',
      'border-style': 'dashed',
    },
  },
  // Edges
  {
    selector: 'edge',
    style: {
      'width': 1,
      'line-color': 'var(--color-border-default)',
      'target-arrow-color': 'var(--color-border-default)',
      'target-arrow-shape': 'triangle',
      'curve-style': 'bezier',
      'opacity': 0.6,
    },
  },
  // Cross-Project Edges (gestrichelt)
  {
    selector: 'edge.cross-project',
    style: {
      'line-style': 'dashed',
      'line-dash-pattern': [6, 3],
    },
  },
  // Selektierter Node
  {
    selector: 'node:selected',
    style: {
      'border-width': 3,
      'border-color': 'var(--color-accent-highlight)',
      'background-color': 'var(--color-accent-active)',
    },
  },
]
```

### Backend-Endpoint

```python
@router.get("/nexus/graph", response_model=NexusGraphResponse)
async def get_nexus_graph(
    project_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Liefert Nodes + Edges für den Nexus Grid."""
    nodes_query = select(CodeNode)
    if project_id:
        nodes_query = nodes_query.where(CodeNode.project_id == project_id)

    nodes = (await db.execute(nodes_query)).scalars().all()
    node_ids = {n.id for n in nodes}

    edges = (await db.execute(
        select(CodeEdge).where(
            or_(CodeEdge.source_id.in_(node_ids), CodeEdge.target_id.in_(node_ids))
        )
    )).scalars().all()

    # Bug-Counts aggregieren
    bug_counts = dict(await db.execute(
        select(NodeBugReport.node_id, func.sum(NodeBugReport.count))
        .group_by(NodeBugReport.node_id)
    ))

    return NexusGraphResponse(
        nodes=[node_to_cytoscape(n, bug_counts.get(n.id, 0)) for n in nodes],
        edges=[edge_to_cytoscape(e) for e in edges],
    )
```

### Daten-Transformation für Cytoscape

```typescript
function transformToElements(data: NexusGraphResponse): ElementDefinition[] {
  const nodes = data.nodes.map((n) => ({
    data: {
      id: n.id,
      label: n.label,
      path: n.path,
      nodeType: n.node_type,
      projectId: n.project_id,
      bugCount: n.bug_count || 0,
    },
    classes: n.explored_at ? 'explored' : 'unexplored',
  }))

  const edges = data.edges.map((e) => ({
    data: {
      id: e.id,
      source: e.source_id,
      target: e.target_id,
      edgeType: e.edge_type,
    },
    classes: e.cross_project ? 'cross-project' : '',
  }))

  return [...nodes, ...edges]
}
```

### Detail-Panel

Der Click auf einen Node öffnet ein Side-Panel mit:
- Node-Path und Typ
- Verlinkte Wiki-Artikel
- Verlinkte Skills
- Verlinkte Tasks
- Bug-Reports (Anzahl + Severity)
- „Erkunden"-Button (markiert Node als explored)

### Wichtig
- Cytoscape.js Instanz immer in `onBeforeUnmount` destroyen
- Layout-Berechnung kann bei vielen Nodes blockieren → `animate: true` + Web Worker für >200 Nodes
- Design Tokens für alle Farben verwenden (kein Hardcoding)
- Responsive: Graph füllt verfügbaren Container aus

### Verfügbare Tools
- `GET /api/nexus/graph` — Graph-Daten laden (Nodes + Edges + Bug-Counts)
