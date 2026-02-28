/**
 * useFederationSSE — EventSource client for GET /api/events.
 * Connects to the SSE stream and converts events into toast notifications
 * and notification tray items. Includes exponential backoff reconnect.
 *
 * TASK-F-015
 */
import { onMounted, onUnmounted, ref } from 'vue'
import { useToast } from './useToast'

const BASE_URL = (import.meta.env.VITE_API_URL as string) ?? 'http://localhost:8000'

export function useFederationSSE() {
  const toast = useToast()
  const connected = ref(false)
  let eventSource: EventSource | null = null
  let retryDelay = 1000
  let retryTimer: ReturnType<typeof setTimeout> | null = null

  function connect() {
    if (eventSource) {
      eventSource.close()
    }

    eventSource = new EventSource(`${BASE_URL}/api/events`)

    eventSource.onopen = () => {
      connected.value = true
      retryDelay = 1000 // reset on success
    }

    eventSource.onerror = () => {
      connected.value = false
      eventSource?.close()
      eventSource = null
      // Exponential backoff reconnect (max 30s)
      retryTimer = setTimeout(connect, retryDelay)
      retryDelay = Math.min(retryDelay * 2, 30000)
    }

    // ─── Event handlers ────────────────────────────────────────────────
    eventSource.addEventListener('node_status', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        if (data.status === 'active') {
          toast.success(`Peer "${data.node_name}" ist online.`)
        } else if (data.status === 'inactive') {
          toast.warning(`Peer "${data.node_name}" ist offline.`)
        }
      } catch { /* ignore parse errors */ }
    })

    eventSource.addEventListener('federation_skill', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        const nodeName = data.origin_node_name ?? 'Unbekannt'
        toast.info(`Neuer Skill von ${nodeName}: ${data.title}`)
      } catch { /* ignore parse errors */ }
    })

    eventSource.addEventListener('task_assigned', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        const nodeName = data.assigned_node_name ?? 'Unbekannt'
        toast.info(`Task "${data.task_title}" an ${nodeName} delegiert.`)
      } catch { /* ignore parse errors */ }
    })
  }

  function disconnect() {
    if (retryTimer) {
      clearTimeout(retryTimer)
      retryTimer = null
    }
    eventSource?.close()
    eventSource = null
    connected.value = false
  }

  onMounted(connect)
  onUnmounted(disconnect)

  return { connected }
}
