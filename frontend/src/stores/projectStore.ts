import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'
import type { Project, Epic, Task } from '../api/types'

export const useProjectStore = defineStore('project', () => {
  const projects = ref<Project[]>([])
  const activeProject = ref<Project | null>(null)
  const activeEpic = ref<Epic | null>(null)
  const activeTask = ref<Task | null>(null)
  const availableEpics = ref<Epic[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function loadProjects() {
    loading.value = true
    try {
      projects.value = await api.getProjects()
      if (projects.value.length > 0 && !activeProject.value) {
        await setActiveProject(projects.value[0])
      }
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }

  async function setActiveProject(project: Project) {
    activeProject.value = project
    const epics = await api.getEpics(project.id)
    availableEpics.value = epics
    activeEpic.value = epics.find(e => !['done', 'cancelled'].includes(e.state)) ?? epics[0] ?? null
    if (activeEpic.value) {
      const tasks = await api.getTasks(activeEpic.value.epic_key)
      activeTask.value = tasks.find(t => ['in_progress', 'in_review'].includes(t.state)) ?? tasks[0] ?? null
    }
  }

  async function selectEpic(epic: Epic) {
    activeEpic.value = epic
    const tasks = await api.getTasks(epic.epic_key)
    activeTask.value = tasks.find(t => ['in_progress', 'in_review'].includes(t.state)) ?? tasks[0] ?? null
  }

  async function refreshActiveTask() {
    if (!activeEpic.value) return
    const tasks = await api.getTasks(activeEpic.value.epic_key)
    activeTask.value = tasks.find(t => t.id === activeTask.value?.id) ?? null
  }

  async function refreshActiveEpic() {
    if (!activeProject.value) return
    const epics = await api.getEpics(activeProject.value.id)
    if (activeEpic.value) {
      const updated = epics.find(e => e.id === activeEpic.value!.id)
      if (updated) activeEpic.value = updated
    }
  }

  return { projects, activeProject, activeEpic, activeTask, availableEpics, loading, error, loadProjects, setActiveProject, selectEpic, refreshActiveTask, refreshActiveEpic }
})
