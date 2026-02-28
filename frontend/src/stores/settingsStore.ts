import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

type AppMode = 'solo' | 'team'
type McpTransport = 'stdio' | 'http' | 'sse'

const STORAGE_KEY = 'hivemind-settings'

function _load() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') } catch { return {} }
}

export const useSettingsStore = defineStore('settings', () => {
  const saved = _load()
  const mode = ref<AppMode>(saved.mode ?? 'solo')
  const notification_mode = ref<string>(saved.notification_mode ?? 'client')
  const mcpTransport = ref<McpTransport>(saved.mcpTransport ?? 'stdio')
  const loading = ref(false)
  const error = ref<string | null>(null)

  watch([mode, notification_mode, mcpTransport], () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      mode: mode.value,
      notification_mode: notification_mode.value,
      mcpTransport: mcpTransport.value,
    }))
  })

  async function fetchSettings() {
    loading.value = true
    error.value = null
    try {
      const { api } = await import('../api')
      const settings = await api.getSettings()
      mode.value = settings.mode as AppMode
      notification_mode.value = settings.notification_mode
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }

  async function updateMode(newMode: AppMode) {
    const prev = mode.value
    mode.value = newMode // optimistic
    try {
      const { api } = await import('../api')
      const settings = await api.updateSettings(newMode)
      mode.value = settings.mode as AppMode
      notification_mode.value = settings.notification_mode
    } catch (e: unknown) {
      mode.value = prev // rollback
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  return { mode, notification_mode, mcpTransport, loading, error, fetchSettings, updateMode }
})
