<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { api } from '../../api'
import { HivemindCard } from '../../components/ui'

// ─── Types ─────────────────────────────────────────────────────────────────
interface GraphNode {
  id: string
  path: string
  node_type: string
  label: string
  project_id?: string | null
  explored_at?: string | null
  metadata?: Record<string, unknown> | null
  // Computed layout
  x: number
  y: number
  vx: number
  vy: number
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

// ─── State ─────────────────────────────────────────────────────────────────
const graphData = ref<GraphData>({ nodes: [], edges: [], total_nodes: 0, explored_count: 0, unexplored_count: 0 })
const selectedNode = ref<GraphNode | null>(null)
const projectFilter = ref('')
const loading = ref(false)
const error = ref<string | null>(null)

// SVG viewport
const svgRef = ref<SVGSVGElement | null>(null)
const viewBox = ref({ x: -500, y: -400, w: 1000, h: 800 })
const dragging = ref(false)
const dragStart = ref({ x: 0, y: 0 })

// Force simulation
let simRunning = false
let animFrame = 0

// ─── Computed ──────────────────────────────────────────────────────────────
const stats = computed(() => ({
  total: graphData.value.total_nodes,
  explored: graphData.value.explored_count,
  unexplored: graphData.value.unexplored_count,
}))

// ─── Data Loading ──────────────────────────────────────────────────────────
async function loadGraph() {
  loading.value = true
  error.value = null
  try {
    const params: Record<string, unknown> = {}
    if (projectFilter.value) params.project_id = projectFilter.value

    const url = projectFilter.value
      ? `/api/nexus/graph?project_id=${projectFilter.value}`
      : '/api/nexus/graph'
    const data = await fetch(
      `${(import.meta.env.VITE_API_URL as string) ?? 'http://localhost:8000'}${url}`
    ).then(r => r.json())

    // Initialize positions with force layout
    const nodes: GraphNode[] = data.nodes.map((n: Omit<GraphNode, 'x' | 'y' | 'vx' | 'vy'>, i: number) => ({
      ...n,
      x: (Math.cos(2 * Math.PI * i / data.nodes.length)) * 300 + (Math.random() - 0.5) * 50,
      y: (Math.sin(2 * Math.PI * i / data.nodes.length)) * 250 + (Math.random() - 0.5) * 50,
      vx: 0,
      vy: 0,
    }))

    graphData.value = { ...data, nodes }
    startSimulation()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

// ─── Force-Directed Layout Simulation ──────────────────────────────────────
function startSimulation() {
  simRunning = true
  let iterations = 0
  const maxIterations = 200

  function tick() {
    if (!simRunning || iterations >= maxIterations) {
      simRunning = false
      return
    }
    iterations++

    const nodes = graphData.value.nodes
    const edges = graphData.value.edges
    const nodeMap = new Map(nodes.map(n => [n.id, n]))
    const alpha = 1 - iterations / maxIterations

    // Repulsion (all pairs)
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dx = nodes[j].x - nodes[i].x
        const dy = nodes[j].y - nodes[i].y
        const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1)
        const force = (800 * alpha) / (dist * dist)
        const fx = (dx / dist) * force
        const fy = (dy / dist) * force
        nodes[i].vx -= fx
        nodes[i].vy -= fy
        nodes[j].vx += fx
        nodes[j].vy += fy
      }
    }

    // Attraction (edges)
    for (const edge of edges) {
      const src = nodeMap.get(edge.source_id)
      const tgt = nodeMap.get(edge.target_id)
      if (!src || !tgt) continue
      const dx = tgt.x - src.x
      const dy = tgt.y - src.y
      const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1)
      const force = (dist - 120) * 0.01 * alpha
      const fx = (dx / dist) * force
      const fy = (dy / dist) * force
      src.vx += fx
      src.vy += fy
      tgt.vx -= fx
      tgt.vy -= fy
    }

    // Center gravity
    for (const n of nodes) {
      n.vx -= n.x * 0.001 * alpha
      n.vy -= n.y * 0.001 * alpha
    }

    // Apply velocities with damping
    for (const n of nodes) {
      n.vx *= 0.85
      n.vy *= 0.85
      n.x += n.vx
      n.y += n.vy
    }

    // Trigger reactivity
    graphData.value = { ...graphData.value, nodes: [...nodes] }

    animFrame = requestAnimationFrame(tick)
  }

  tick()
}

// ─── SVG Interaction ───────────────────────────────────────────────────────
function onNodeClick(node: GraphNode) {
  selectedNode.value = node
}

function onSvgMouseDown(e: MouseEvent) {
  if ((e.target as SVGElement).tagName === 'svg' || (e.target as SVGElement).classList.contains('graph-bg')) {
    dragging.value = true
    dragStart.value = { x: e.clientX, y: e.clientY }
  }
}

function onSvgMouseMove(e: MouseEvent) {
  if (!dragging.value) return
  const dx = e.clientX - dragStart.value.x
  const dy = e.clientY - dragStart.value.y
  dragStart.value = { x: e.clientX, y: e.clientY }
  viewBox.value = {
    ...viewBox.value,
    x: viewBox.value.x - dx * (viewBox.value.w / (svgRef.value?.clientWidth || 1000)),
    y: viewBox.value.y - dy * (viewBox.value.h / (svgRef.value?.clientHeight || 800)),
  }
}

function onSvgMouseUp() {
  dragging.value = false
}

function onWheel(e: WheelEvent) {
  e.preventDefault()
  const factor = e.deltaY > 0 ? 1.1 : 0.9
  const cx = viewBox.value.x + viewBox.value.w / 2
  const cy = viewBox.value.y + viewBox.value.h / 2
  const nw = viewBox.value.w * factor
  const nh = viewBox.value.h * factor
  viewBox.value = { x: cx - nw / 2, y: cy - nh / 2, w: nw, h: nh }
}

// ─── Node styling helpers ──────────────────────────────────────────────────
function nodeColor(n: GraphNode): string {
  if (!n.explored_at) return 'var(--color-text-muted)'
  const types: Record<string, string> = {
    file: 'var(--color-accent)',
    module: 'var(--color-warning, #f9a825)',
    function: 'var(--color-success, #4caf50)',
    class: 'var(--color-danger, #e53935)',
  }
  return types[n.node_type] || 'var(--color-accent)'
}

function nodeOpacity(n: GraphNode): number {
  return n.explored_at ? 1 : 0.35
}

function nodeRadius(n: GraphNode): number {
  return n.explored_at ? 8 : 5
}

// ─── Lifecycle ─────────────────────────────────────────────────────────────
onMounted(() => loadGraph())
onBeforeUnmount(() => {
  simRunning = false
  if (animFrame) cancelAnimationFrame(animFrame)
})
</script>

<template>
  <div class="nexus-view">
    <!-- Header Bar -->
    <div class="nexus-header">
      <h2 class="nexus-title">Nexus Grid</h2>
      <div class="nexus-stats">
        <span class="stat" title="Total Nodes">{{ stats.total }} Nodes</span>
        <span class="stat stat--explored" title="Explored">{{ stats.explored }} erkundet</span>
        <span class="stat stat--unexplored" title="Unexplored">{{ stats.unexplored }} offen</span>
      </div>
      <input
        v-model="projectFilter"
        class="hm-input nexus-filter"
        placeholder="Project-ID Filter..."
        @change="loadGraph"
      />
    </div>

    <div class="nexus-body">
      <!-- Graph Area -->
      <div class="nexus-graph-container">
        <div v-if="loading" class="graph-loading">Lade Graph...</div>
        <div v-else-if="error" class="graph-error">{{ error }}</div>
        <div v-else-if="graphData.nodes.length === 0" class="graph-empty">
          Keine Code-Nodes vorhanden.
        </div>
        <svg
          v-else
          ref="svgRef"
          class="nexus-svg"
          :viewBox="`${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`"
          @mousedown="onSvgMouseDown"
          @mousemove="onSvgMouseMove"
          @mouseup="onSvgMouseUp"
          @mouseleave="onSvgMouseUp"
          @wheel.prevent="onWheel"
        >
          <!-- Background -->
          <rect class="graph-bg" :x="viewBox.x" :y="viewBox.y" :width="viewBox.w" :height="viewBox.h" fill="transparent" />

          <!-- Edges -->
          <line
            v-for="edge in graphData.edges"
            :key="edge.id"
            :x1="graphData.nodes.find(n => n.id === edge.source_id)?.x ?? 0"
            :y1="graphData.nodes.find(n => n.id === edge.source_id)?.y ?? 0"
            :x2="graphData.nodes.find(n => n.id === edge.target_id)?.x ?? 0"
            :y2="graphData.nodes.find(n => n.id === edge.target_id)?.y ?? 0"
            class="graph-edge"
            :class="{ 'graph-edge--selected': selectedNode && (edge.source_id === selectedNode.id || edge.target_id === selectedNode.id) }"
          />

          <!-- Nodes -->
          <g
            v-for="node in graphData.nodes"
            :key="node.id"
            class="graph-node"
            :class="{ 'graph-node--selected': selectedNode?.id === node.id }"
            @click.stop="onNodeClick(node)"
          >
            <!-- Fog-of-war glow for unexplored -->
            <circle
              v-if="!node.explored_at"
              :cx="node.x"
              :cy="node.y"
              :r="nodeRadius(node) + 4"
              class="fog-ring"
            />
            <circle
              :cx="node.x"
              :cy="node.y"
              :r="nodeRadius(node)"
              :fill="nodeColor(node)"
              :opacity="nodeOpacity(node)"
              class="node-circle"
            />
            <text
              :x="node.x"
              :y="node.y - nodeRadius(node) - 4"
              class="node-label"
              :opacity="nodeOpacity(node)"
            >
              {{ node.label.length > 20 ? node.label.slice(0, 18) + '...' : node.label }}
            </text>
          </g>
        </svg>
      </div>

      <!-- Detail Panel -->
      <aside v-if="selectedNode" class="nexus-detail">
        <HivemindCard>
          <div class="detail-header">
            <h3>{{ selectedNode.label }}</h3>
            <button class="detail-close" @click="selectedNode = null">✕</button>
          </div>
          <dl class="detail-props">
            <dt>Pfad</dt>
            <dd class="mono">{{ selectedNode.path }}</dd>
            <dt>Typ</dt>
            <dd>
              <span class="type-badge" :style="{ background: nodeColor(selectedNode) }">
                {{ selectedNode.node_type }}
              </span>
            </dd>
            <dt>Status</dt>
            <dd>
              <span v-if="selectedNode.explored_at" class="status-explored">
                ✓ Erkundet {{ new Date(selectedNode.explored_at).toLocaleDateString('de-DE') }}
              </span>
              <span v-else class="status-unexplored">○ Nicht erkundet</span>
            </dd>
            <template v-if="selectedNode.project_id">
              <dt>Projekt-ID</dt>
              <dd class="mono">{{ selectedNode.project_id }}</dd>
            </template>
            <template v-if="selectedNode.metadata">
              <dt>Metadaten</dt>
              <dd><pre class="meta-json">{{ JSON.stringify(selectedNode.metadata, null, 2) }}</pre></dd>
            </template>
          </dl>
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
.stat { color: var(--color-text-muted); }
.stat--explored { color: var(--color-success, #4caf50); }
.stat--unexplored { color: var(--color-warning, #f9a825); }

.nexus-filter {
  margin-left: auto;
  max-width: 220px;
  font-size: var(--font-size-xs);
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
.graph-error { color: var(--color-danger); }

.nexus-svg {
  width: 100%;
  height: 100%;
  cursor: grab;
  user-select: none;
}
.nexus-svg:active { cursor: grabbing; }

/* Edges */
.graph-edge {
  stroke: var(--color-border);
  stroke-width: 1;
  opacity: 0.4;
  transition: opacity 0.15s;
}
.graph-edge--selected {
  stroke: var(--color-accent);
  opacity: 0.8;
  stroke-width: 2;
}

/* Nodes */
.graph-node { cursor: pointer; }
.node-circle { transition: r 0.15s; }
.graph-node:hover .node-circle { r: 12; }
.graph-node--selected .node-circle {
  stroke: var(--color-accent);
  stroke-width: 3;
}

.fog-ring {
  fill: none;
  stroke: var(--color-text-muted);
  stroke-width: 1;
  opacity: 0.2;
  stroke-dasharray: 3 3;
}

.node-label {
  font-size: 9px;
  font-family: var(--font-mono);
  fill: var(--color-text);
  text-anchor: middle;
  pointer-events: none;
}

/* Detail Panel */
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
.detail-props dd { margin: 0; color: var(--color-text); }
.mono { font-family: var(--font-mono); font-size: var(--font-size-xs); word-break: break-all; }

.type-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  color: var(--color-bg);
  font-size: var(--font-size-xs);
  font-weight: 600;
}

.status-explored { color: var(--color-success, #4caf50); }
.status-unexplored { color: var(--color-text-muted); }

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

@media (max-width: 768px) {
  .nexus-detail {
    position: absolute;
    right: 0;
    top: 0;
    height: 100%;
    z-index: 10;
    box-shadow: -4px 0 12px rgba(0,0,0,0.2);
  }
}
</style>
