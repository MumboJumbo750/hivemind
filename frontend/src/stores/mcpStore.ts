import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'

export const useMcpStore = defineStore('mcp', () => {
  const connected = ref(false)
  const toolsCount = ref(0)
  const transport = ref('unknown')
  const lastCheck = ref<string | null>(null)
  let pollInterval: ReturnType<typeof setInterval> | null = null

  async function checkStatus() {
    try {
      const tools = await api.getMcpTools()
      connected.value = true
      toolsCount.value = tools.length
      transport.value = 'HTTP'
      lastCheck.value = new Date().toISOString()
    } catch {
      connected.value = false
      lastCheck.value = new Date().toISOString()
    }
  }

  function startPolling(intervalMs = 30_000) {
    if (pollInterval) return
    checkStatus()
    pollInterval = setInterval(checkStatus, intervalMs)
  }

  function stopPolling() {
    if (pollInterval) {
      clearInterval(pollInterval)
      pollInterval = null
    }
  }

  return { connected, toolsCount, transport, lastCheck, checkStatus, startPolling, stopPolling }
})
