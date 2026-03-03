<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import cytoscape from 'cytoscape'
import type { Core, ElementDefinition, EventObjectNode } from 'cytoscape'
import { HivemindCard } from '../../components/ui'
import { useBugHeatmap } from '../../composables/useBugHeatmap'
import NexusGrid3D from '../../components/domain/NexusGrid3D.vue'
import type { Node3DItem, Edge3DItem } from '../../api/types'

interface GraphNode {
  id: string
  path: string
  node_type: string
  label: string
  project_id?: string | null
  explored_at?: string | null
  metadata?: Record<string, unknown> | null
}

interface GraphEdge {
  id: string
  source_id: string
  target_id: string
  edge_type: string
}

interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
  total_nodes: number
  explored_count: number
  unexplored_count: number
}

interface HoverState {
  visible: boolean
  nodeId: string
  x: number
  y: number
}

const API_BASE = (import.meta.env.VITE_API_URL as string) ?? 'http://localhost:8000'

const graphData = ref<GraphData>({
  nodes: [],
  edges: [],
  total_nodes: 0,
  explored_count: 0,
  unexplored_count: 0,
})

const selectedNode = ref<GraphNode | null>(null)
const projectFilter = ref('')
const loading = ref(false)
const error = ref<string | null>(null)

// ── 3D Mode (TASK-8-025) ─────────────────────────────────────────────────
const viewMode = ref<'2d' | '3d'>('2d')
const graph3dNodes = ref<Node3DItem[]>([])
const graph3dEdges = ref<Edge3DItem[]>([])
const loading3d = ref(false)
const error3d = ref<string | null>(null)

async function load3DGraph(): Promise<void> {
  loading3d.value = true
  error3d.value = null
  try {
    const url = projectFilter.value
      ? `/api/nexus/graph3d?page=0&page_size=500&project_id=${projectFilter.value}`
      : '/api/nexus/graph3d?page=0&page_size=500'
    const response = await fetch(`${API_BASE}${url}`)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json() as { nodes: Node3DItem[]; edges: Edge3DItem[] }
    graph3dNodes.value = data.nodes ?? []
    graph3dEdges.value = data.edges ?? []
  } catch (e: unknown) {
    error3d.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading3d.value = false
  }
}

async function switchTo3D(): Promise<void> {
  viewMode.value = '3d'
  if (graph3dNodes.value.length === 0) {
    await load3DGraph()
  }
}

const {
  heatmapEnabled,
  toggleHeatmap,
  loadBugCounts,
  getNodeRadius,
  getNodeColor,
  getBugSummary,
  getBugCount,
  error: heatmapError,
} = useBugHeatmap(() => projectFilter.value || undefined)

const cyContainerRef = ref<HTMLDivElement | null>(null)
const hoverState = ref<HoverState>({ visible: false, nodeId: '', x: 0, y: 0 })

let cy: Core | null = null
let eventSource: EventSource | null = null
let reconnectTimer: number | null = null
let refreshTimer: number | null = null

const nodeMap = computed(() => new Map(graphData.value.nodes.map(node => [node.id, node])))

const stats = computed(() => ({
  total: graphData.value.total_nodes,
  explored: graphData.value.explored_count,
  unexplored: graphData.value.unexplored_count,
}))

const selectedBugSummary = computed(() => {
  if (!selectedNode.value) return { count: 0, lastSeen: null as string | null, stackTraceHashPreview: null as string | null }
  return getBugSummary(selectedNode.value.id)
})

const hoveredNode = computed<GraphNode | null>(() => nodeMap.value.get(hoverState.value.nodeId) ?? null)

const hoveredBugSummary = computed(() => {
  if (!hoveredNode.value) return { count: 0, lastSeen: null as string | null, stackTraceHashPreview: null as string | null }
  return getBugSummary(hoveredNode.value.id)
})

const showHoverPanel = computed(() => heatmapEnabled.value && hoverState.value.visible && !!hoveredNode.value)

function resolveColorToken(token: string, fallback: string): string {
  if (typeof window === 'undefined' || typeof document === 'undefined') return fallback
  const value = getComputedStyle(document.documentElement).getPropertyValue(token).trim()
  return value || fallback
}

function nodeBaseColor(node: GraphNode): string {
  if (!node.explored_at) return resolveColorToken('--color-text-muted', '#7f92b3')

  const types: Record<string, [string, string]> = {
    file: ['--color-accent', '#20e3ff'],
    module: ['--color-warning', '#ffb020'],
    function: ['--color-success', '#3cff9a'],
    class: ['--color-danger', '#ff4d6d'],
  }

  const [token, fallback] = types[node.node_type] ?? ['--color-accent', '#20e3ff']
  return resolveColorToken(token, fallback)
}

function nodeBaseRadius(node: GraphNode): number {
  return node.explored_at ? 8 : 5
}

function nodeOpacity(node: GraphNode): number {
  return node.explored_at ? 1 : 0.35
}

function truncateLabel(label: string): string {
  return label.length > 20 ? `${label.slice(0, 18)}...` : label
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString('de-DE')
}

function graphElements(): ElementDefinition[] {
  const nodes = graphData.value.nodes.map(node => {
    const radius = nodeBaseRadius(node)
    return {
      group: 'nodes',
      data: {
        id: node.id,
        label: truncateLabel(node.label),
        fullLabel: node.label,
        baseColor: nodeBaseColor(node),
        baseDiameter: radius * 2,
      },
    } as ElementDefinition
  })

  const edges = graphData.value.edges.map(edge => ({
    group: 'edges',
    data: {
      id: edge.id,
      source: edge.source_id,
      target: edge.target_id,
      edge_type: edge.edge_type,
    },
  } as ElementDefinition))

  return [...nodes, ...edges]
}

function updateHoverPosition(event: EventObjectNode): void {
  const container = cyContainerRef.value
  if (!container) return

  const panelWidth = 280
  const panelHeight = 120
  const offset = 14
  const rendered = event.renderedPosition ?? event.position

  const maxX = Math.max(0, container.clientWidth - panelWidth - 8)
  const maxY = Math.max(0, container.clientHeight - panelHeight - 8)

  const x = Math.max(0, Math.min(maxX, rendered.x + offset))
  const y = Math.max(0, Math.min(maxY, rendered.y + offset))

  hoverState.value = {
    ...hoverState.value,
    x,
    y,
  }
}

function showNodeHover(event: EventObjectNode): void {
  if (!heatmapEnabled.value) return

  const nodeId = event.target.id()
  if (!nodeMap.value.has(nodeId)) return

  hoverState.value = {
    ...hoverState.value,
    visible: true,
    nodeId,
  }
  updateHoverPosition(event)
}

function hideNodeHover(): void {
  hoverState.value = {
    ...hoverState.value,
    visible: false,
  }
}

function applyHeatmapStyles(): void {
  if (!cy) return

  cy.batch(() => {
    cy!.nodes().forEach(nodeEle => {
      const id = nodeEle.id()
      const graphNode = nodeMap.value.get(id)
      if (!graphNode) return

      const baseRadius = nodeBaseRadius(graphNode)
      const diameter = getNodeRadius(id, baseRadius) * 2
      const color = getNodeColor(id, nodeBaseColor(graphNode))
      const opacity = nodeOpacity(graphNode)

      nodeEle.style('width', diameter)
      nodeEle.style('height', diameter)
      nodeEle.style('background-color', color)
      nodeEle.style('opacity', opacity)
    })
  })
}

function destroyGraph(): void {
  if (cy) {
    cy.destroy()
    cy = null
  }
}

function initGraph(): void {
  const container = cyContainerRef.value
  if (!container) return

  destroyGraph()

  cy = cytoscape({
    container,
    elements: graphElements(),
    layout: {
      name: 'cose',
      animate: false,
      fit: true,
      padding: 28,
      idealEdgeLength: 110,
      edgeElasticity: 90,
      nodeRepulsion: 5000,
    },
    style: [
      {
        selector: 'node',
        style: {
          'background-color': 'data(baseColor)',
          width: 'data(baseDiameter)',
          height: 'data(baseDiameter)',
          label: 'data(label)',
          'font-size': 9,
          color: resolveColorToken('--color-text', '#e6f0ff'),
          'text-valign': 'top',
          'text-margin-y': -6,
          'text-halign': 'center',
          opacity: 1,
        },
      },
      {
        selector: 'edge',
        style: {
          width: 1,
          'line-color': resolveColorToken('--color-border', '#223a63'),
          opacity: 0.4,
        },
      },
      {
        selector: 'node:selected',
        style: {
          'border-width': 3,
          'border-color': resolveColorToken('--color-accent', '#20e3ff'),
        },
      },
      {
        selector: 'edge:selected',
        style: {
          width: 2,
          'line-color': resolveColorToken('--color-accent', '#20e3ff'),
          opacity: 0.8,
        },
      },
    ],
    wheelSensitivity: 0.22,
  })

  cy.on('tap', 'node', event => {
    const nodeId = event.target.id()
    selectedNode.value = nodeMap.value.get(nodeId) ?? null
  })

  cy.on('tap', event => {
    if (event.target === cy) {
      selectedNode.value = null
      hideNodeHover()
    }
  })

  cy.on('mouseover', 'node', event => {
    showNodeHover(event)
  })

  cy.on('mousemove', 'node', event => {
    showNodeHover(event)
  })

  cy.on('mouseout', 'node', () => {
    hideNodeHover()
  })

  applyHeatmapStyles()
}

async function loadGraph(): Promise<void> {
  loading.value = true
  error.value = null

  try {
    const url = projectFilter.value
      ? `/api/nexus/graph?project_id=${projectFilter.value}`
      : '/api/nexus/graph'

    const response = await fetch(`${API_BASE}${url}`)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${url}`)
    }

    const data = (await response.json()) as GraphData
    graphData.value = data

    if (selectedNode.value && !nodeMap.value.has(selectedNode.value.id)) {
      selectedNode.value = null
    }

    await nextTick()
    initGraph()

    if (heatmapEnabled.value) {
      await loadBugCounts()
      applyHeatmapStyles()
    }
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

async function onHeatmapToggle(): Promise<void> {
  await toggleHeatmap()
  applyHeatmapStyles()
}

function scheduleHeatmapRefresh(): void {
  if (!heatmapEnabled.value) return
  if (refreshTimer !== null) return

  refreshTimer = window.setTimeout(() => {
    refreshTimer = null
    void (async () => {
      await loadBugCounts()
      applyHeatmapStyles()
    })()
  }, 300)
}

function onBugAggregated(event: Event): void {
  if (!heatmapEnabled.value) return

  const message = event as MessageEvent<string>
  if (!message.data) return

  try {
    const payload = JSON.parse(message.data) as { node_id?: string }
    if (payload.node_id && !nodeMap.value.has(payload.node_id)) return
    scheduleHeatmapRefresh()
  } catch {
    scheduleHeatmapRefresh()
  }
}

function connectBugSSE(): void {
  if (eventSource) return

  eventSource = new EventSource(`${API_BASE}/api/events`)
  eventSource.addEventListener('bug_aggregated', onBugAggregated)

  eventSource.onerror = () => {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    if (reconnectTimer === null) {
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null
        connectBugSSE()
      }, 3000)
    }
  }
}

function disconnectBugSSE(): void {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }

  if (reconnectTimer !== null) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }

  if (refreshTimer !== null) {
    clearTimeout(refreshTimer)
    refreshTimer = null
  }
}

onMounted(() => {
  void loadGraph()
  connectBugSSE()
})

onBeforeUnmount(() => {
  disconnectBugSSE()
  destroyGraph()
})
</script>

<template>
  <div class="nexus-view">
    <div class="nexus-header">
      <h2 class="nexus-title">Nexus Grid</h2>

      <div class="nexus-stats">
        <span class="stat" title="Total Nodes">{{ stats.total }} Nodes</span>
        <span class="stat stat--explored" title="Explored">{{ stats.explored }} erkundet</span>
        <span class="stat stat--unexplored" title="Unexplored">{{ stats.unexplored }} offen</span>
      </div>

      <!-- View mode toggle: 2D / 3D -->
      <div class="view-mode-toggle">
        <button
          class="view-mode-btn"
          :class="{ 'view-mode-btn--active': viewMode === '2d' }"
          @click="viewMode = '2d'"
        >2D</button>
        <button
          class="view-mode-btn"
          :class="{ 'view-mode-btn--active': viewMode === '3d' }"
          @click="switchTo3D"
        >3D</button>
      </div>

      <button
        v-if="viewMode === '2d'"
        class="heatmap-toggle"
        :class="{ 'heatmap-toggle--active': heatmapEnabled }"
        @click="onHeatmapToggle"
      >
        Bug-Heatmap
      </button>

      <input
        v-model="projectFilter"
        class="hm-input nexus-filter"
        placeholder="Project-ID Filter..."
        @change="loadGraph"
      />
    </div>

    <div class="nexus-body">
      <div class="nexus-graph-container">
        <!-- ── 2D Cytoscape View ── -->
        <template v-if="viewMode === '2d'">
          <div v-if="loading" class="graph-loading">Lade Graph...</div>
          <div v-else-if="error" class="graph-error">{{ error }}</div>
          <div v-else-if="graphData.nodes.length === 0" class="graph-empty">Keine Code-Nodes vorhanden.</div>

          <div v-else ref="cyContainerRef" class="nexus-cy-container" />

          <div
            v-if="showHoverPanel && hoveredNode"
            class="bug-hover-panel"
            :style="{ left: `${hoverState.x}px`, top: `${hoverState.y}px` }"
          >
            <div class="bug-hover-title">{{ hoveredNode.label }}</div>
            <dl class="bug-hover-list">
              <dt>Bugs</dt>
              <dd class="mono">{{ hoveredBugSummary.count }}</dd>
              <dt>Last Seen</dt>
              <dd class="mono">{{ formatDateTime(hoveredBugSummary.lastSeen) }}</dd>
              <dt>Stack Hash</dt>
              <dd class="mono">{{ hoveredBugSummary.stackTraceHashPreview ?? '-' }}</dd>
            </dl>
          </div>
        </template>

        <!-- ── 3D Three.js View ── -->
        <template v-else>
          <div v-if="loading3d" class="graph-loading">Lade 3D-Graph...</div>
          <div v-else-if="error3d" class="graph-error">{{ error3d }}</div>
          <NexusGrid3D
            v-else
            :nodes="graph3dNodes"
            :edges="graph3dEdges"
            class="nexus-3d-container"
          />
        </template>
      </div>

      <aside v-if="selectedNode" class="nexus-detail">
        <HivemindCard>
          <div class="detail-header">
            <h3>{{ selectedNode.label }}</h3>
            <button class="detail-close" @click="selectedNode = null">x</button>
          </div>

          <dl class="detail-props">
            <dt>Pfad</dt>
            <dd class="mono">{{ selectedNode.path }}</dd>

            <dt>Typ</dt>
            <dd>
              <span class="type-badge" :style="{ background: getNodeColor(selectedNode.id, nodeBaseColor(selectedNode)) }">
                {{ selectedNode.node_type }}
              </span>
            </dd>

            <dt>Status</dt>
            <dd>
              <span v-if="selectedNode.explored_at" class="status-explored">
                Erkundet {{ new Date(selectedNode.explored_at).toLocaleDateString('de-DE') }}
              </span>
              <span v-else class="status-unexplored">Nicht erkundet</span>
            </dd>

            <template v-if="heatmapEnabled">
              <dt>Bugs</dt>
              <dd class="mono">{{ getBugCount(selectedNode.id) }}</dd>

              <dt>Last Seen</dt>
              <dd class="mono">{{ formatDateTime(selectedBugSummary.lastSeen) }}</dd>

              <dt>Stack Hash</dt>
              <dd class="mono">{{ selectedBugSummary.stackTraceHashPreview ?? '-' }}</dd>
            </template>

            <template v-if="selectedNode.project_id">
              <dt>Projekt-ID</dt>
              <dd class="mono">{{ selectedNode.project_id }}</dd>
            </template>

            <template v-if="selectedNode.metadata">
              <dt>Metadaten</dt>
              <dd><pre class="meta-json">{{ JSON.stringify(selectedNode.metadata, null, 2) }}</pre></dd>
            </template>
          </dl>

          <p v-if="heatmapEnabled && heatmapError" class="heatmap-error">{{ heatmapError }}</p>
        </HivemindCard>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.nexus-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.nexus-header {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface);
  flex-shrink: 0;
}

.nexus-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-lg);
  color: var(--color-text);
  margin: 0;
  white-space: nowrap;
}

.nexus-stats {
  display: flex;
  gap: var(--space-3);
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
}

.stat {
  color: var(--color-text-muted);
}

.stat--explored {
  color: var(--color-success, #3cff9a);
}

.stat--unexplored {
  color: var(--color-warning, #ffb020);
}

.nexus-filter {
  max-width: 220px;
  font-size: var(--font-size-xs);
}

/* ── View mode toggle (2D / 3D) ── */
.view-mode-toggle {
  display: flex;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  overflow: hidden;
  flex-shrink: 0;
}

.view-mode-btn {
  background: transparent;
  border: none;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  padding: var(--space-1) var(--space-3);
  cursor: pointer;
  transition: background var(--transition-duration) ease, color var(--transition-duration) ease;
  white-space: nowrap;
}

.view-mode-btn + .view-mode-btn {
  border-left: 1px solid var(--color-border);
}

.view-mode-btn--active {
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  color: var(--color-accent);
}

.view-mode-btn:not(.view-mode-btn--active):hover {
  background: var(--color-surface-alt);
  color: var(--color-text);
}

.heatmap-toggle {
  margin-left: auto;
  background: color-mix(in srgb, var(--color-border) 30%, transparent);
  border: 1px solid var(--color-border);
  color: var(--color-text-muted);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  padding: var(--space-1) var(--space-3);
  cursor: pointer;
  white-space: nowrap;
}

.heatmap-toggle--active {
  background: color-mix(in srgb, var(--color-danger) 15%, transparent);
  border-color: var(--color-danger);
  color: var(--color-danger);
}

.nexus-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.nexus-graph-container {
  flex: 1;
  position: relative;
  background: var(--color-bg);
  overflow: hidden;
}

.nexus-cy-container {
  width: 100%;
  height: 100%;
}

.nexus-3d-container {
  width: 100%;
  height: 100%;
}

.graph-loading,
.graph-error,
.graph-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.graph-error {
  color: var(--color-danger);
}

.bug-hover-panel {
  position: absolute;
  width: 280px;
  max-width: calc(100% - 16px);
  pointer-events: none;
  border: 1px solid var(--color-border);
  background: color-mix(in srgb, var(--color-surface) 94%, transparent);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.35);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
  z-index: 20;
}

.bug-hover-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-sm);
  color: var(--color-text);
  margin-bottom: var(--space-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.bug-hover-list {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 2px var(--space-2);
  margin: 0;
  font-size: var(--font-size-xs);
}

.bug-hover-list dt {
  color: var(--color-text-muted);
  font-weight: 600;
}

.bug-hover-list dd {
  margin: 0;
  color: var(--color-text);
}

.nexus-detail {
  width: 320px;
  border-left: 1px solid var(--color-border);
  padding: var(--space-3);
  overflow-y: auto;
  background: var(--color-surface);
  flex-shrink: 0;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.detail-header h3 {
  font-family: var(--font-heading);
  font-size: var(--font-size-base);
  color: var(--color-text);
  margin: 0;
  word-break: break-all;
}

.detail-close {
  background: none;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: var(--font-size-sm);
}

.detail-props {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--space-1) var(--space-3);
  font-size: var(--font-size-xs);
  margin-top: var(--space-3);
}

.detail-props dt {
  color: var(--color-text-muted);
  font-weight: 600;
}

.detail-props dd {
  margin: 0;
  color: var(--color-text);
}

.mono {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  word-break: break-all;
}

.type-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  color: var(--color-bg);
  font-size: var(--font-size-xs);
  font-weight: 600;
}

.status-explored {
  color: var(--color-success, #3cff9a);
}

.status-unexplored {
  color: var(--color-text-muted);
}

.meta-json {
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2);
  font-family: var(--font-mono);
  font-size: 10px;
  overflow-x: auto;
  margin: 0;
  white-space: pre-wrap;
}

.heatmap-error {
  margin-top: var(--space-3);
  color: var(--color-danger);
  font-size: var(--font-size-xs);
}

@media (max-width: 768px) {
  .nexus-detail {
    position: absolute;
    right: 0;
    top: 0;
    height: 100%;
    z-index: 30;
    box-shadow: -4px 0 12px rgba(0, 0, 0, 0.2);
  }

  .nexus-header {
    flex-wrap: wrap;
  }

  .heatmap-toggle {
    margin-left: 0;
  }
}
</style>
