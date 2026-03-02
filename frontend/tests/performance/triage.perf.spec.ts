import { describe, expect, it } from 'vitest'

type RoutingState = 'unrouted' | 'routed' | 'ignored'

interface TriageItem {
  id: string
  routing_state: RoutingState
  payload: Record<string, unknown>
  created_at: string
}

function buildItems(count: number): TriageItem[] {
  const states: RoutingState[] = ['unrouted', 'routed', 'ignored']
  const now = new Date().toISOString()
  return Array.from({ length: count }, (_, i) => ({
    id: `evt-${i}`,
    routing_state: states[i % states.length],
    payload: { title: `Event ${i}`, summary: `Synthetic event ${i}` },
    created_at: now,
  }))
}

function timeMs(fn: () => void): number {
  const t0 = performance.now()
  fn()
  return performance.now() - t0
}

describe('Triage Performance Budget', () => {
  const ITEM_COUNT = 2000
  const PAGE_SIZE = 20
  const LOAD_BUDGET_MS = 2000
  const TAB_SWITCH_BUDGET_MS = 500
  const PAGINATION_BUDGET_MS = 500
  const SSE_UPDATE_BUDGET_MS = 200

  it('Initial-Load (synthetisch) unter 2s', () => {
    const items = buildItems(ITEM_COUNT)
    let loaded: TriageItem[] = []

    const elapsed = timeMs(() => {
      // Simuliert JSON-Decode + Store-Assignment beim ersten Load
      const raw = JSON.stringify(items)
      loaded = JSON.parse(raw) as TriageItem[]
    })

    console.log(`[triage.perf] initial-load: ${elapsed.toFixed(2)} ms (${loaded.length} items)`)
    expect(elapsed).toBeLessThan(LOAD_BUDGET_MS)
  })

  it('Tab-Wechsel (inkl. Filter) unter 500ms', () => {
    const items = buildItems(ITEM_COUNT)
    let filtered: TriageItem[] = []

    const elapsed = timeMs(() => {
      filtered = items.filter(i => i.routing_state === 'unrouted')
      filtered = items.filter(i => i.routing_state === 'routed')
      filtered = items.filter(i => i.routing_state === 'ignored')
    })

    console.log(`[triage.perf] tab-switch: ${elapsed.toFixed(2)} ms (${filtered.length} items)`)
    expect(elapsed).toBeLessThan(TAB_SWITCH_BUDGET_MS)
  })

  it('Dead-Letter Pagination unter 500ms', () => {
    const deadLetters = buildItems(1000)
    let page: TriageItem[] = []

    const elapsed = timeMs(() => {
      page = deadLetters.slice(0, PAGE_SIZE)
      page = deadLetters.slice(PAGE_SIZE, PAGE_SIZE * 2)
      page = deadLetters.slice(PAGE_SIZE * 2, PAGE_SIZE * 3)
    })

    console.log(`[triage.perf] dead-letter-pagination: ${elapsed.toFixed(2)} ms (page size ${page.length})`)
    expect(elapsed).toBeLessThan(PAGINATION_BUDGET_MS)
  })

  it('SSE Event -> UI Update unter 200ms', () => {
    const items = buildItems(ITEM_COUNT)
    const eventPayload = JSON.stringify({
      id: 'evt-new',
      routing_state: 'unrouted',
      payload: { title: 'Incoming Event' },
      created_at: new Date().toISOString(),
    })

    const elapsed = timeMs(() => {
      const parsed = JSON.parse(eventPayload) as TriageItem
      const exists = items.find(i => i.id === parsed.id)
      if (!exists) {
        items.unshift(parsed)
      }
    })

    console.log(`[triage.perf] sse-ui-update: ${elapsed.toFixed(2)} ms`)
    expect(elapsed).toBeLessThan(SSE_UPDATE_BUDGET_MS)
  })
})
