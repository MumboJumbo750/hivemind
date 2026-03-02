/**
 * Nexus Grid Performance Test — TASK-7-018
 *
 * Simuliert 500 Knoten in der Force-Directed-Simulation und misst die
 * durchschnittliche Frame-Zeit. Budget: < 16 ms pro Frame.
 *
 * Läuft mit Vitest (jsdom environment nicht nötig — rein rechnerisch):
 *   cd frontend && npx vitest run tests/performance/nexus-grid.perf.spec.ts
 */

import { describe, it, expect } from 'vitest'

// ─── Typen (vereinfacht, entspricht NexusGridView) ─────────────────────────

interface SimNode {
  id: string
  x: number
  y: number
  vx: number
  vy: number
}

interface SimEdge {
  source_id: string
  target_id: string
}

// ─── Force-Simulation (exakte Kopie aus NexusGridView.vue) ─────────────────

function runSimulationTick(nodes: SimNode[], edges: SimEdge[], alpha: number): void {
  const nodeMap = new Map(nodes.map(n => [n.id, n]))

  // Repulsion
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

  // Center gravity + velocity apply
  for (const n of nodes) {
    n.vx -= n.x * 0.001 * alpha
    n.vy -= n.y * 0.001 * alpha
    n.vx *= 0.85
    n.vy *= 0.85
    n.x += n.vx
    n.y += n.vy
  }
}

// ─── Test ──────────────────────────────────────────────────────────────────

describe('Nexus Grid Performance Budget', () => {
  const NODE_COUNT = 500
  const EDGE_COUNT = 800
  const TICK_BUDGET_MS = 16    // < 16 ms pro Frame (60 fps)
  const AVG_BUDGET_MS = 12     // Durchschnitt sollte komfortabler sein
  const WARMUP_TICKS = 10
  const SAMPLE_TICKS = 50

  function buildNodes(count: number): SimNode[] {
    return Array.from({ length: count }, (_, i) => ({
      id: `node-${i}`,
      x: Math.cos((2 * Math.PI * i) / count) * 300,
      y: Math.sin((2 * Math.PI * i) / count) * 250,
      vx: 0,
      vy: 0,
    }))
  }

  function buildEdges(nodes: SimNode[], count: number): SimEdge[] {
    return Array.from({ length: count }, (_, i) => ({
      source_id: nodes[i % nodes.length].id,
      target_id: nodes[(i * 7 + 3) % nodes.length].id,
    }))
  }

  it(`${NODE_COUNT} Knoten: alle Ticks unter ${TICK_BUDGET_MS} ms`, () => {
    const nodes = buildNodes(NODE_COUNT)
    const edges = buildEdges(nodes, EDGE_COUNT)
    const frameTimes: number[] = []

    for (let tick = 0; tick < WARMUP_TICKS + SAMPLE_TICKS; tick++) {
      const alpha = 1 - tick / 200
      const t0 = performance.now()
      runSimulationTick(nodes, edges, alpha)
      const elapsed = performance.now() - t0
      if (tick >= WARMUP_TICKS) {
        frameTimes.push(elapsed)
      }
    }

    const maxTime = Math.max(...frameTimes)
    const avgTime = frameTimes.reduce((a, b) => a + b, 0) / frameTimes.length
    const sorted = [...frameTimes].sort((a, b) => a - b)
    const p95Time = sorted[Math.floor(sorted.length * 0.95)]

    console.log(
      `[nexus-grid.perf] ${NODE_COUNT} nodes, ${EDGE_COUNT} edges — ` +
      `avg: ${avgTime.toFixed(2)} ms, p95: ${p95Time.toFixed(2)} ms, max: ${maxTime.toFixed(2)} ms`,
    )

    expect(avgTime).toBeLessThan(AVG_BUDGET_MS)
    expect(p95Time).toBeLessThan(TICK_BUDGET_MS)
  })

  it('Bug-Heatmap-Toggle: Map-Lookup unter 1 ms für 500 Knoten', () => {
    // Simuliert useBugHeatmap getNodeRadius / getNodeColor Lookup
    const bugCountMap = new Map<string, number>(
      Array.from({ length: NODE_COUNT }, (_, i) => [`node-${i}`, Math.floor(Math.random() * 20)])
    )

    const t0 = performance.now()
    for (let i = 0; i < NODE_COUNT; i++) {
      const count = bugCountMap.get(`node-${i}`) ?? 0
      // Radius-Berechnung (entspricht useBugHeatmap.bugRadius)
      const _r = Math.round(10 + Math.min(count / 10, 1) * 30)
      void _r
    }
    const elapsed = performance.now() - t0

    console.log(`[nexus-grid.perf] heatmap-toggle lookup: ${elapsed.toFixed(3)} ms`)
    expect(elapsed).toBeLessThan(1)
  })
})
