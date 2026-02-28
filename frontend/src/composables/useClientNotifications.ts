import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api } from '../api'
import type { Epic, Task } from '../api/types'
import { useAuthStore } from '../stores/authStore'
import { useProjectStore } from '../stores/projectStore'

export interface ClientNotification {
  id: string
  type: 'sla_warning' | 'review_requested' | 'task_assigned'
  title: string
  timestamp: string
  level: 'warning' | 'danger' | 'info'
}

export function useClientNotifications() {
  const auth = useAuthStore()
  const projectStore = useProjectStore()
  const epics = ref<Epic[]>([])
  const tasks = ref<Task[]>([])
  let interval: ReturnType<typeof setInterval> | null = null

  async function load() {
    if (!projectStore.activeProject) return
    try {
      epics.value = await api.getEpics(projectStore.activeProject.id)
      const allTasks: Task[] = []
      for (const epic of epics.value) {
        const t = await api.getTasks(epic.epic_key)
        allTasks.push(...t)
      }
      tasks.value = allTasks
    } catch {
      // ignore polling errors
    }
  }

  const notifications = computed<ClientNotification[]>(() => {
    const now = Date.now()
    const result: ClientNotification[] = []

    for (const epic of epics.value) {
      if (epic.sla_due_at) {
        const due = new Date(epic.sla_due_at).getTime()
        if (due > now && due < now + 4 * 3_600_000) {
          result.push({
            id: `sla-${epic.id}`,
            type: 'sla_warning',
            title: `SLA läuft ab: ${epic.title}`,
            timestamp: epic.sla_due_at,
            level: 'danger',
          })
        }
      }
    }

    for (const task of tasks.value) {
      if (task.state === 'in_review') {
        result.push({
          id: `review-${task.id}`,
          type: 'review_requested',
          title: `Review angefordert: ${task.title}`,
          timestamp: new Date().toISOString(),
          level: 'warning',
        })
      }
      if (auth.user && (task as Task & { assigned_to?: string }).assigned_to === auth.user.id
          && task.state !== 'done' && task.state !== 'cancelled') {
        result.push({
          id: `assigned-${task.id}`,
          type: 'task_assigned',
          title: `Dir zugewiesen: ${task.title}`,
          timestamp: new Date().toISOString(),
          level: 'info',
        })
      }
    }

    return result
  })

  onMounted(async () => {
    await load()
    interval = setInterval(load, 60_000)
  })

  onUnmounted(() => {
    if (interval !== null) clearInterval(interval)
  })

  return { notifications, load }
}
