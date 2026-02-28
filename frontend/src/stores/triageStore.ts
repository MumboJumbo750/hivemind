import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api'
import type { TriageItem } from '../api/types'

export const useTriageStore = defineStore('triage', () => {
  const items = ref<TriageItem[]>([])
  const filter = ref<'unrouted' | 'routed' | 'ignored' | 'all'>('unrouted')
  const loading = ref(false)
  const error = ref<string | null>(null)

  const filteredItems = computed(() => {
    if (filter.value === 'all') return items.value
    return items.value.filter(i => i.routing_state === filter.value)
  })

  async function loadItems() {
    loading.value = true
    error.value = null
    try {
      items.value = await api.getTriageItems()
    } catch (e: unknown) {
      error.value = (e as Error).message
    } finally {
      loading.value = false
    }
  }

  async function routeEvent(eventId: string, epicId: string) {
    const result = await api.callMcpTool('hivemind/route_event', { event_id: eventId, epic_id: epicId })
    // Update local state
    const item = items.value.find(i => i.id === eventId)
    if (item) item.routing_state = 'routed'
    return result
  }

  async function ignoreEvent(eventId: string, reason?: string) {
    const result = await api.callMcpTool('hivemind/ignore_event', { event_id: eventId, reason: reason ?? '' })
    const item = items.value.find(i => i.id === eventId)
    if (item) item.routing_state = 'ignored'
    return result
  }

  function addItem(item: TriageItem) {
    // Prepend new SSE items
    const exists = items.value.find(i => i.id === item.id)
    if (!exists) items.value.unshift(item)
  }

  return { items, filter, filteredItems, loading, error, loadItems, routeEvent, ignoreEvent, addItem }
})
