<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useProjectStore } from '../../stores/projectStore'
import { useMcpStore } from '../../stores/mcpStore'
import { api } from '../../api'
import { HivemindCard, HivemindDropdown } from '../../components/ui'
import TokenRadar from '../../components/ui/TokenRadar.vue'
import McpStatusIndicator from '../../components/ui/McpStatusIndicator.vue'
import QueueBadge from '../../components/ui/QueueBadge.vue'
import ProjectCreateDialog from '../../components/domain/ProjectCreateDialog.vue'
import { useAutoMode } from '../../composables/useAutoMode'

const projectStore = useProjectStore()
const mcpStore = useMcpStore()
const showCreateDialog = ref(false)

// Auto-Mode (TASK-8-023)
const { isAutoMode, overrideManual, enterManualMode, exitManualMode, setConductorEnabled } = useAutoMode()

interface ConductorDispatch {
  id: string
  trigger_id: string
  dispatched_at: string
  status: string
  tokens_used?: number | null
}

const conductorDispatches = ref<ConductorDispatch[]>([])
const conductorDispatchesLoading = ref(false)
const conductorTokenTotal = ref(0)

async function loadConductorStatus() {
  try {
    const settings = await api.getSettings() as Record<string, unknown>
    const enabled = !!(settings as Record<string, unknown>)['hivemind_conductor_enabled']
    setConductorEnabled(enabled)
    if (enabled) {
      await loadConductorDispatches()
    }
  } catch {
    // Settings load failure is non-critical
  }
}

async function loadConductorDispatches() {
  conductorDispatchesLoading.value = true
  try {
    const BASE_URL = (import.meta.env.VITE_API_URL as string) ?? 'http://localhost:8000'
    const res = await fetch(`${BASE_URL}/api/admin/conductor/dispatches?limit=10`, {
      headers: { 'Content-Type': 'application/json' },
    })
    if (res.ok) {
      const data = await res.json() as { dispatches?: ConductorDispatch[]; total_tokens?: number } | ConductorDispatch[]
      const dispatches = Array.isArray(data) ? data : data.dispatches ?? []
      conductorDispatches.value = dispatches
      conductorTokenTotal.value = Array.isArray(data) ? 0 : data.total_tokens ?? 0
    }
  } catch {
    // Non-critical — endpoint may not exist yet
    conductorDispatches.value = []
  } finally {
    conductorDispatchesLoading.value = false
  }
}

// Token Radar state
const tokenCount = ref(0)
const tokenMax = ref(8000)

// Worker Prompt Flow (in_progress / scoped / ready)
const workerPrompt = ref('')
const workerPromptLoading = ref(false)
const workerPromptCopied = ref(false)

const showWorkerPrompt = computed(() => {
  const s = projectStore.activeTask?.state
  return s === 'in_progress' || s === 'scoped' || s === 'ready'
})

async function loadWorkerPrompt() {
  if (!projectStore.activeTask) return
  workerPromptLoading.value = true
  workerPromptCopied.value = false
  try {
    const result = await api.getPrompt(
      'worker',
      projectStore.activeTask.task_key,
      projectStore.activeEpic?.id,
      projectStore.activeProject?.id,
    )
    const parsed = JSON.parse(result[0]?.text || '{}')
    workerPrompt.value = parsed.data?.prompt || parsed.prompt || 'Kein Prompt verfügbar.'
  } catch {
    workerPrompt.value = 'Fehler beim Laden des Worker-Prompts.'
  } finally {
    workerPromptLoading.value = false
  }
}

async function copyWorkerPrompt() {
  await navigator.clipboard.writeText(workerPrompt.value)
  workerPromptCopied.value = true
  setTimeout(() => { workerPromptCopied.value = false }, 2000)
}

// Task wechselt → Prompt-Cache leeren
watch(
  () => projectStore.activeTask?.task_key,
  () => {
    workerPrompt.value = ''
    taskAgentRole.value = recommendedAgentRoleForTask()
  },
)

// QA-Failed Prompt Flow
const qaFailedPrompt = ref('')
const qaFailedLoading = ref(false)
const qaFailedCopied = ref(false)

const showQaFailedPanel = computed(() =>
  projectStore.activeTask?.state === 'qa_failed'
)

async function loadQaFailedPrompt() {
  if (!projectStore.activeTask) return
  qaFailedLoading.value = true
  qaFailedCopied.value = false
  try {
    const result = await api.getPrompt(
      'worker',
      projectStore.activeTask.task_key,
      projectStore.activeEpic?.id,
      projectStore.activeProject?.id,
    )
    const parsed = JSON.parse(result[0]?.text || '{}')
    qaFailedPrompt.value = parsed.data?.prompt || parsed.prompt || 'Kein Prompt verfügbar.'
  } catch {
    qaFailedPrompt.value = 'Fehler beim Laden des Worker-Prompts.'
  } finally {
    qaFailedLoading.value = false
  }
}

async function copyQaFailedPrompt() {
  await navigator.clipboard.writeText(qaFailedPrompt.value)
  qaFailedCopied.value = true
  setTimeout(() => { qaFailedCopied.value = false }, 2000)
}

const reenterLoading = ref(false)
const reenterError = ref<string | null>(null)

async function handleReenter() {
  if (!projectStore.activeTask) return
  reenterLoading.value = true
  reenterError.value = null
  try {
    await api.reenterTask(projectStore.activeTask.task_key)
    await projectStore.refreshActiveTask()
    qaFailedPrompt.value = ''
  } catch (e: unknown) {
    reenterError.value = e instanceof Error ? e.message : String(e)
  } finally {
    reenterLoading.value = false
  }
}

// Gaertner Prompt Flow (TASK-5-021)
const showGaertnerPrompt = ref(false)
const gaertnerPrompt = ref('')
const gaertnerLoading = ref(false)
const gaertnerCopied = ref(false)
const gaertnerTaskKey = ref('')

// SSE listener for task_done → trigger Gaertner prompt
let sseSource: EventSource | null = null

function startSSE() {
  const base = (import.meta.env.VITE_API_URL as string) ?? 'http://localhost:8000'
  sseSource = new EventSource(`${base}/api/events`)
  sseSource.addEventListener('task_done', (evt) => {
    try {
      const data = JSON.parse(evt.data)
      gaertnerTaskKey.value = data.task_key || ''
      showGaertnerPrompt.value = true
      loadGaertnerPrompt(data.task_key)
    } catch { /* ignore parse errors */ }
  })
}

async function loadGaertnerPrompt(taskKey?: string) {
  gaertnerLoading.value = true
  gaertnerCopied.value = false
  try {
    const result = await api.getPrompt(
      'gaertner',
      taskKey || gaertnerTaskKey.value || undefined,
      projectStore.activeEpic?.id,
      projectStore.activeProject?.id,
    )
    const parsed = JSON.parse(result[0]?.text || '{}')
    gaertnerPrompt.value = parsed.data?.prompt || parsed.prompt || 'Kein Prompt verfügbar.'
  } catch {
    gaertnerPrompt.value = 'Fehler beim Laden des Gaertner-Prompts.'
  } finally {
    gaertnerLoading.value = false
  }
}

async function copyGaertnerPrompt() {
  await navigator.clipboard.writeText(gaertnerPrompt.value)
  gaertnerCopied.value = true
  setTimeout(() => { gaertnerCopied.value = false }, 2000)
}

// ─── Execute Prompt State ──────────────────────────────────────────────
interface ExecuteResult {
  status: string
  content?: string
  tool_calls?: { name: string; arguments: Record<string, unknown> }[]
  input_tokens?: number
  output_tokens?: number
  message?: string
}

const executing = ref(false)
const executeResult = ref<ExecuteResult | null>(null)
const executeError = ref<string | null>(null)

const gaertnerExecuting = ref(false)
const gaertnerExecuteResult = ref<ExecuteResult | null>(null)
const gaertnerExecuteError = ref<string | null>(null)

const TASK_AGENT_OPTIONS = [
  { label: 'Worker', value: 'worker', icon: '⚙' },
  { label: 'Reviewer', value: 'reviewer', icon: '🔍' },
  { label: 'Gaertner', value: 'gaertner', icon: '🌱' },
  { label: 'Kartograph', value: 'kartograph', icon: '🗺' },
  { label: 'Architekt', value: 'architekt', icon: '🏗' },
  { label: 'Stratege', value: 'stratege', icon: '🧭' },
  { label: 'Triage', value: 'triage', icon: '🧪' },
]

const taskAgentRole = ref('worker')

function recommendedAgentRoleForTask(): string {
  const state = projectStore.activeTask?.state
  if (state === 'in_progress') return 'worker'
  if (state === 'scoped') return 'worker'
  if (state === 'in_review') return 'reviewer'
  if (state === 'qa_failed') return 'worker'
  return 'worker'
}

const taskAgentLabel = computed(() =>
  TASK_AGENT_OPTIONS.find((item) => item.value === taskAgentRole.value)?.label ?? taskAgentRole.value,
)

function promptTypeForAgentRole(agentRole: string): string {
  return agentRole === 'reviewer' ? 'review' : agentRole
}

async function buildTaskExecutionPrompt(agentRole: string): Promise<string> {
  const promptType = promptTypeForAgentRole(agentRole)
  const taskKey = ['worker', 'review', 'gaertner', 'kartograph'].includes(promptType)
    ? projectStore.activeTask?.task_key
    : undefined
  const epicRef = agentRole === 'architekt' ? projectStore.activeEpic?.epic_key : undefined
  const projectId = agentRole === 'stratege' ? projectStore.activeProject?.id : undefined

  const result = await api.getPrompt(promptType, taskKey, epicRef, projectId)
  const parsed = JSON.parse(result[0]?.text || '{}') as {
    data?: { prompt?: string }
    prompt?: string
    error?: { message?: string }
  }
  const prompt = parsed.data?.prompt || parsed.prompt
  if (!prompt) {
    throw new Error(parsed.error?.message || 'Kein Prompt verfügbar.')
  }
  return prompt
}

async function executeTaskPrompt() {
  if (!projectStore.activeTask) return
  executing.value = true
  executeResult.value = null
  executeError.value = null
  try {
    const prompt = await buildTaskExecutionPrompt(taskAgentRole.value)
    const result = await api.executePrompt(
      taskAgentRole.value,
      prompt,
      projectStore.activeTask.task_key,
      projectStore.activeEpic?.epic_key,
    )
    executeResult.value = result
    if (result.status === 'failed' || result.status === 'no_provider') {
      executeError.value = result.message ?? 'Unbekannter Fehler'
    }
  } catch (e: unknown) {
    executeError.value = e instanceof Error ? e.message : String(e)
  } finally {
    executing.value = false
  }
}

async function executeGaertnerPrompt() {
  gaertnerExecuting.value = true
  gaertnerExecuteResult.value = null
  gaertnerExecuteError.value = null
  try {
    const result = await api.executePrompt(
      'gaertner',
      gaertnerPrompt.value,
      gaertnerTaskKey.value || undefined,
      projectStore.activeEpic?.id,
    )
    gaertnerExecuteResult.value = result
    if (result.status === 'failed' || result.status === 'no_provider') {
      gaertnerExecuteError.value = result.message ?? 'Unbekannter Fehler'
    }
  } catch (e: unknown) {
    gaertnerExecuteError.value = e instanceof Error ? e.message : String(e)
  } finally {
    gaertnerExecuting.value = false
  }
}

function dismissResult() {
  executeResult.value = null
  executeError.value = null
}

function dismissGaertnerResult() {
  gaertnerExecuteResult.value = null
  gaertnerExecuteError.value = null
}

// Inline-Review state
const checkedCriteria = ref<boolean[]>([])
const reviewComment = ref('')
const reviewLoading = ref(false)
const reviewError = ref<string | null>(null)

// Inline-Scoping state
const scopingPriority = ref('medium')
const scopingSlaDeadline = ref('')
const scopingDod = ref('')
const scopingLoading = ref(false)
const scopingError = ref<string | null>(null)

const priorityOptions = [
  { label: 'Low', value: 'low' },
  { label: 'Medium', value: 'medium' },
  { label: 'High', value: 'high' },
  { label: 'Critical', value: 'critical' },
]

const showReviewPanel = computed(() =>
  projectStore.activeTask?.state === 'in_review'
)

const showScopingPanel = computed(() =>
  projectStore.activeEpic?.state === 'incoming' && !showReviewPanel.value
)

// ── Task-Navigation ────────────────────────────────────────────────────────
const taskIndex = computed(() => {
  if (!projectStore.activeTask) return -1
  return projectStore.epicTasks.findIndex(t => t.id === projectStore.activeTask!.id)
})

const hasPrevTask = computed(() => taskIndex.value > 0)
const hasNextTask = computed(() => taskIndex.value < projectStore.epicTasks.length - 1)

function prevTask() {
  const idx = taskIndex.value
  if (idx > 0) {
    projectStore.selectTask(projectStore.epicTasks[idx - 1])
    workerPrompt.value = ''
  }
}

function nextTask() {
  const idx = taskIndex.value
  if (idx < projectStore.epicTasks.length - 1) {
    projectStore.selectTask(projectStore.epicTasks[idx + 1])
    workerPrompt.value = ''
  }
}

async function copyToClipboard(text: string) {
  await navigator.clipboard.writeText(text)
}

async function handleApprove() {
  if (!projectStore.activeTask) return
  reviewLoading.value = true
  reviewError.value = null
  try {
    await api.approveTask(projectStore.activeTask.task_key)
    await projectStore.refreshActiveTask()
    reviewComment.value = ''
    checkedCriteria.value = []
  } catch (e: unknown) {
    reviewError.value = e instanceof Error ? e.message : String(e)
  } finally {
    reviewLoading.value = false
  }
}

async function handleReject() {
  if (!projectStore.activeTask) return
  reviewLoading.value = true
  reviewError.value = null
  try {
    await api.rejectTask(projectStore.activeTask.task_key, reviewComment.value || undefined)
    await projectStore.refreshActiveTask()
    reviewComment.value = ''
    checkedCriteria.value = []
  } catch (e: unknown) {
    reviewError.value = e instanceof Error ? e.message : String(e)
  } finally {
    reviewLoading.value = false
  }
}

async function handleScope() {
  if (!projectStore.activeEpic) return
  scopingLoading.value = true
  scopingError.value = null
  try {
    await api.patchEpicState(projectStore.activeEpic.epic_key, {
      state: 'scoped',
      priority: scopingPriority.value,
      sla_due_at: scopingSlaDeadline.value || undefined,
      dod_framework: scopingDod.value ? { criteria: scopingDod.value.split('\n').filter(Boolean) } : undefined,
    })
    await projectStore.refreshActiveEpic()
  } catch (e: unknown) {
    scopingError.value = e instanceof Error ? e.message : String(e)
  } finally {
    scopingLoading.value = false
  }
}

onMounted(() => {
  projectStore.loadProjects()
  mcpStore.startPolling()
  startSSE()
  void loadConductorStatus()
})

onUnmounted(() => {
  mcpStore.stopPolling()
  if (sseSource) { sseSource.close(); sseSource = null }
})
</script>

<template>
  <div class="prompt-station">
    <!-- Leer-State -->
    <div v-if="!projectStore.loading && !projectStore.activeProject" class="prompt-station__empty">
      <p class="empty-text">Kein Projekt aktiv.</p>
      <button class="btn-primary" @click="showCreateDialog = true">+ Projekt anlegen</button>
      <ProjectCreateDialog v-model="showCreateDialog" />
    </div>

    <!-- Loading -->
    <div v-else-if="projectStore.loading" class="prompt-station__loading">
      <span>Lade...</span>
    </div>

    <!-- Fehler -->
    <div v-else-if="projectStore.error" class="prompt-station__error">
      <span class="error-text">Fehler: {{ projectStore.error }}</span>
    </div>

    <!-- Aktiver Task -->
    <template v-else>

      <!-- Agent Queue Header with Token Radar + MCP Status -->
      <div class="agent-queue-header">
        <McpStatusIndicator />
        <TokenRadar :current="tokenCount" :max="tokenMax" :size="100" />
      </div>

      <!-- Auto-Mode Monitoring View (TASK-8-023) -->
      <div v-if="isAutoMode" class="auto-mode-monitor">
        <div class="auto-mode-header">
          <div class="auto-mode-title-row">
            <span class="auto-mode-dot" />
            <h2 class="auto-mode-title">CONDUCTOR AKTIV</h2>
          </div>
          <button class="btn-secondary auto-mode-override" @click="enterManualMode">
            Manuell eingreifen
          </button>
        </div>

        <div class="auto-mode-stats">
          <div class="auto-stat">
            <span class="auto-stat__label">TOKEN GESAMT</span>
            <span class="auto-stat__value mono">{{ conductorTokenTotal.toLocaleString('de-DE') }}</span>
          </div>
          <div class="auto-stat">
            <span class="auto-stat__label">DISPATCHES</span>
            <span class="auto-stat__value mono">{{ conductorDispatches.length }}</span>
          </div>
        </div>

        <div class="auto-mode-dispatches">
          <div class="auto-dispatches__label">LETZTE DISPATCHES</div>
          <div v-if="conductorDispatchesLoading" class="auto-dispatches__empty">Lade...</div>
          <div v-else-if="conductorDispatches.length === 0" class="auto-dispatches__empty">
            Noch keine Dispatches — Conductor wartet.
          </div>
          <ul v-else class="dispatch-list">
            <li
              v-for="d in conductorDispatches"
              :key="d.id"
              class="dispatch-item"
              :class="`dispatch-item--${d.status}`"
            >
              <span class="dispatch-key mono">{{ d.trigger_id }}</span>
              <span class="dispatch-status" :class="`dispatch-status--${d.status}`">{{ d.status }}</span>
              <span class="dispatch-time mono">{{ new Date(d.dispatched_at).toLocaleTimeString('de-DE') }}</span>
              <span v-if="d.tokens_used" class="dispatch-tokens mono">{{ d.tokens_used }} tok</span>
            </li>
          </ul>
        </div>
      </div>

      <!-- "Zurück zum Auto-Modus" button when overriding -->
      <div v-if="!isAutoMode && overrideManual" class="auto-mode-back-bar">
        <span class="auto-mode-back-label">Manueller Eingriff aktiv</span>
        <button class="btn-secondary" @click="exitManualMode">
          Zurück zum Auto-Modus
        </button>
      </div>

      <!-- Prompt-Bereich: nur sichtbar wenn KEIN Auto-Modus aktiv -->
      <template v-if="!isAutoMode">

      <!-- Epic-Selektor -->
      <div v-if="projectStore.availableEpics.length > 1" class="epic-selector">
        <span class="epic-selector__label">EPIC</span>
        <div class="epic-selector__list">
          <button
            v-for="epic in projectStore.availableEpics.filter(e => !['done','cancelled'].includes(e.state))"
            :key="epic.epic_key"
            class="epic-selector__btn"
            :class="{ 'epic-selector__btn--active': epic.epic_key === projectStore.activeEpic?.epic_key }"
            @click="projectStore.selectEpic(epic)"
          >
            {{ epic.epic_key }}
          </button>
        </div>
      </div>
      <HivemindCard v-if="projectStore.activeTask" class="prompt-station__task">
        <div class="task-header">
          <h2 class="task-title">{{ projectStore.activeTask.title }}</h2>
          <span class="task-state">{{ projectStore.activeTask.state }}</span>
        </div>
        <!-- Task-Navigation -->
        <div v-if="projectStore.epicTasks.length > 1" class="task-nav">
          <button
            class="task-nav__btn task-nav__btn--prev"
            :disabled="!hasPrevTask"
            @click="prevTask"
          >
            <span class="task-nav__arrow">←</span>
            <span v-if="hasPrevTask" class="task-nav__hint">
              <span class="task-nav__hint-key mono">{{ projectStore.epicTasks[taskIndex - 1].task_key }}</span>
              <span class="task-nav__hint-state" :data-state="projectStore.epicTasks[taskIndex - 1].state">{{ projectStore.epicTasks[taskIndex - 1].state }}</span>
            </span>
          </button>
          <div class="task-nav__center">
            <span class="task-nav__pos mono">{{ taskIndex + 1 }} / {{ projectStore.epicTasks.length }}</span>
            <span class="task-nav__key mono">{{ projectStore.activeTask?.task_key }}</span>
          </div>
          <button
            class="task-nav__btn task-nav__btn--next"
            :disabled="!hasNextTask"
            @click="nextTask"
          >
            <span v-if="hasNextTask" class="task-nav__hint">
              <span class="task-nav__hint-state" :data-state="projectStore.epicTasks[taskIndex + 1].state">{{ projectStore.epicTasks[taskIndex + 1].state }}</span>
              <span class="task-nav__hint-key mono">{{ projectStore.epicTasks[taskIndex + 1].task_key }}</span>
            </span>
            <span class="task-nav__arrow">→</span>
          </button>
        </div>
        <p class="task-description">{{ projectStore.activeTask.description }}</p>
        <div class="prompt-actions">
          <button class="btn-secondary" @click="copyToClipboard(projectStore.activeTask.description ?? '')">
            📋 Beschreibung kopieren
          </button>
          <HivemindDropdown :items="TASK_AGENT_OPTIONS" v-model="taskAgentRole">
            <template #trigger>
              <button class="btn-secondary btn-agent-select" :disabled="executing">
                {{ taskAgentLabel }} ▾
              </button>
            </template>
          </HivemindDropdown>
          <button
            class="btn-primary"
            @click="executeTaskPrompt"
            :disabled="executing"
          >
            {{ executing ? '⏳ Wird ausgeführt...' : '▶ Ausführen' }}
          </button>
        </div>

        <!-- Worker-Prompt laden (in_progress / scoped / ready) -->
        <div v-if="showWorkerPrompt" class="worker-prompt-section">
          <div class="worker-prompt-actions">
            <button class="btn-secondary" @click="loadWorkerPrompt" :disabled="workerPromptLoading">
              {{ workerPromptLoading ? '⏳ Lädt...' : '↻ Worker-Prompt laden' }}
            </button>
            <button
              v-if="workerPrompt"
              class="btn-primary"
              @click="copyWorkerPrompt"
              :disabled="workerPromptLoading"
            >
              {{ workerPromptCopied ? '✓ Kopiert!' : '📋 Worker-Prompt kopieren' }}
            </button>
          </div>
          <pre v-if="workerPrompt" class="worker-prompt-text">{{ workerPrompt }}</pre>
        </div>

        <!-- Execute Result -->
        <div v-if="executeResult" class="execute-result" :class="`execute-result--${executeResult.status}`">
          <div class="execute-result__header">
            <span class="execute-result__status">{{ executeResult.status === 'completed' ? '✓ Erfolgreich' : executeResult.status === 'no_provider' ? '⚠ Kein Provider' : '✗ Fehler' }}</span>
            <button class="execute-result__dismiss" @click="dismissResult">✕</button>
          </div>
          <div v-if="executeResult.content" class="execute-result__content">
            <pre>{{ executeResult.content }}</pre>
          </div>
          <div v-if="executeResult.tool_calls?.length" class="execute-result__tools">
            <strong>Tool-Calls:</strong>
            <ul>
              <li v-for="(tc, i) in executeResult.tool_calls" :key="i">
                <code>{{ tc.name }}</code>
              </li>
            </ul>
          </div>
          <div v-if="executeResult.input_tokens" class="execute-result__tokens mono">
            {{ executeResult.input_tokens }} in / {{ executeResult.output_tokens }} out Tokens
          </div>
          <p v-if="executeError" class="error-text">{{ executeError }}</p>
        </div>
      </HivemindCard>

      <!-- Inline-Review-Panel -->
      <HivemindCard v-if="showReviewPanel && projectStore.activeTask" class="prompt-station__review">
        <h3 class="panel-title">Review: {{ projectStore.activeTask.title }}</h3>
        <ul class="dod-checklist">
          <li
            v-for="(criterion, i) in projectStore.activeTask.definition_of_done?.criteria ?? []"
            :key="i"
            class="dod-item"
          >
            <label>
              <input type="checkbox" v-model="checkedCriteria[i]" />
              {{ criterion }}
            </label>
          </li>
        </ul>
        <textarea
          v-model="reviewComment"
          class="hm-input"
          placeholder="Kommentar (optional)"
          rows="3"
        />
        <p v-if="reviewError" class="error-text">{{ reviewError }}</p>
        <div class="review-actions">
          <button class="btn-danger" @click="handleReject" :disabled="reviewLoading">
            ✗ ABLEHNEN
          </button>
          <button class="btn-success" @click="handleApprove" :disabled="reviewLoading">
            ✓ GENEHMIGEN
          </button>
        </div>
      </HivemindCard>

      <!-- QA-Failed Panel -->
      <HivemindCard v-if="showQaFailedPanel && projectStore.activeTask" class="prompt-station__qa-failed">
        <div class="qa-failed-header">
          <h3 class="panel-title">⚠ QA Fehlgeschlagen — {{ projectStore.activeTask.title }}</h3>
          <span class="qa-failed-count mono">Versuch {{ projectStore.activeTask.qa_failed_count }}</span>
        </div>
        <div v-if="projectStore.activeTask.review_comment" class="qa-failed-reason">
          <span class="qa-failed-reason__label">ABLEHNUNGSGRUND</span>
          <p class="qa-failed-reason__text">{{ projectStore.activeTask.review_comment }}</p>
        </div>
        <p class="qa-failed-hint">
          Der Worker-Prompt enthält den Ablehnungskommentar — bitte erneut ausführen.
        </p>
        <div v-if="qaFailedLoading" class="gaertner-loading">Lade Worker-Prompt...</div>
        <pre v-else-if="qaFailedPrompt" class="gaertner-prompt-text">{{ qaFailedPrompt }}</pre>
        <div class="qa-failed-actions">
          <button
            class="btn-primary"
            @click="handleReenter"
            :disabled="reenterLoading"
          >
            {{ reenterLoading ? '⏳ Übergang...' : '↩ Zurück zur Arbeit' }}
          </button>
          <button class="btn-secondary" @click="loadQaFailedPrompt" :disabled="qaFailedLoading">
            {{ qaFailedLoading ? '⏳ Lädt...' : '↻ Worker-Prompt laden' }}
          </button>
          <button
            v-if="qaFailedPrompt"
            class="btn-secondary"
            @click="copyQaFailedPrompt"
            :disabled="qaFailedLoading"
          >
            {{ qaFailedCopied ? '✓ Kopiert!' : '📋 Worker-Prompt kopieren' }}
          </button>
        </div>
        <p v-if="reenterError" class="error-text">{{ reenterError }}</p>
      </HivemindCard>

      <!-- Inline-Scoping-Panel -->
      <HivemindCard v-if="showScopingPanel && projectStore.activeEpic" class="prompt-station__scoping">
        <h3 class="panel-title">Epic scopen: {{ projectStore.activeEpic.title }}</h3>
        <div class="scoping-field">
          <label class="field-label">Priorität</label>
          <HivemindDropdown :items="priorityOptions" v-model="scopingPriority">
            <template #trigger>
              <button class="btn-secondary">Priorität: {{ scopingPriority }}</button>
            </template>
          </HivemindDropdown>
        </div>
        <div class="scoping-field">
          <label class="field-label">SLA-Deadline</label>
          <input type="date" v-model="scopingSlaDeadline" class="hm-input" />
        </div>
        <div class="scoping-field">
          <label class="field-label">Definition of Done</label>
          <textarea
            v-model="scopingDod"
            class="hm-input"
            placeholder="Definition of Done (Kurztext)"
            rows="3"
          />
        </div>
        <p v-if="scopingError" class="error-text">{{ scopingError }}</p>
        <button class="btn-primary" @click="handleScope" :disabled="scopingLoading">
          {{ scopingLoading ? '...' : 'EPIC SCOPEN →' }}
        </button>
      </HivemindCard>

      <!-- Kein aktiver Task -->
      <div v-if="!projectStore.activeTask && projectStore.activeProject" class="prompt-station__no-task">
        <p class="empty-text">Kein aktiver Task in diesem Epic.</p>
      </div>

      <!-- Gaertner Prompt Flow (TASK-5-021) -->
      <HivemindCard v-if="showGaertnerPrompt" class="prompt-station__gaertner">
        <div class="gaertner-header">
          <h3 class="panel-title">🌱 Gaertner — Nächster Schritt</h3>
          <button class="gaertner-close" @click="showGaertnerPrompt = false">✕</button>
        </div>
        <p v-if="gaertnerTaskKey" class="gaertner-context">
          Task <strong>{{ gaertnerTaskKey }}</strong> abgeschlossen — Gaertner-Prompt bereit.
        </p>
        <div v-if="gaertnerLoading" class="gaertner-loading">Lade Gaertner-Prompt...</div>
        <pre v-else class="gaertner-prompt-text">{{ gaertnerPrompt }}</pre>
        <div class="gaertner-actions">
          <button class="btn-primary" @click="copyGaertnerPrompt" :disabled="gaertnerLoading">
            {{ gaertnerCopied ? '✓ Kopiert!' : '📋 Kopieren' }}
          </button>
          <button
            class="btn-primary btn-execute"
            @click="executeGaertnerPrompt"
            :disabled="gaertnerLoading || gaertnerExecuting"
          >
            {{ gaertnerExecuting ? '⏳ Wird ausgeführt...' : '▶ Ausführen' }}
          </button>
          <button class="btn-secondary" @click="loadGaertnerPrompt()">↻ Neu laden</button>
        </div>

        <!-- Gaertner Execute Result -->
        <div v-if="gaertnerExecuteResult" class="execute-result" :class="`execute-result--${gaertnerExecuteResult.status}`">
          <div class="execute-result__header">
            <span class="execute-result__status">{{ gaertnerExecuteResult.status === 'completed' ? '✓ Erfolgreich' : gaertnerExecuteResult.status === 'no_provider' ? '⚠ Kein Provider' : '✗ Fehler' }}</span>
            <button class="execute-result__dismiss" @click="dismissGaertnerResult">✕</button>
          </div>
          <div v-if="gaertnerExecuteResult.content" class="execute-result__content">
            <pre>{{ gaertnerExecuteResult.content }}</pre>
          </div>
          <div v-if="gaertnerExecuteResult.tool_calls?.length" class="execute-result__tools">
            <strong>Tool-Calls:</strong>
            <ul>
              <li v-for="(tc, i) in gaertnerExecuteResult.tool_calls" :key="i">
                <code>{{ tc.name }}</code>
              </li>
            </ul>
          </div>
          <div v-if="gaertnerExecuteResult.input_tokens" class="execute-result__tokens mono">
            {{ gaertnerExecuteResult.input_tokens }} in / {{ gaertnerExecuteResult.output_tokens }} out Tokens
          </div>
          <p v-if="gaertnerExecuteError" class="error-text">{{ gaertnerExecuteError }}</p>
        </div>
      </HivemindCard>

      </template><!-- end !isAutoMode prompt block -->
    </template>
  </div>
</template>

<style scoped>
.prompt-station {
  padding: var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  max-width: 800px;
}

.agent-queue-header {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-4);
}

.prompt-station__empty,
.prompt-station__loading,
.prompt-station__error,
.prompt-station__no-task {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  align-items: flex-start;
}

.empty-text {
  color: var(--color-text-muted);
  font-size: var(--font-size-base);
  margin: 0;
}

.task-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.task-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-xl);
  color: var(--color-text);
  margin: 0;
}

.task-state {
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-full);
  background: var(--color-surface-alt);
  color: var(--color-accent);
  white-space: nowrap;
}

.task-description {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  line-height: 1.6;
  margin: 0 0 var(--space-3);
}

.panel-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-lg);
  color: var(--color-text);
  margin: 0 0 var(--space-4);
}

.dod-checklist {
  list-style: none;
  padding: 0;
  margin: 0 0 var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.dod-item label {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--color-text);
  font-size: var(--font-size-sm);
  cursor: pointer;
}

.hm-input {
  width: 100%;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
  padding: var(--space-2) var(--space-3);
  box-sizing: border-box;
  resize: vertical;
}
.hm-input:focus {
  border-color: var(--input-focus-border);
  outline: none;
}

.review-actions {
  display: flex;
  gap: var(--space-3);
  margin-top: var(--space-4);
}

.scoping-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin-bottom: var(--space-3);
}

.field-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.error-text {
  color: var(--color-danger);
  font-size: var(--font-size-sm);
  margin: var(--space-2) 0 0;
}

.btn-primary {
  background: var(--button-primary-bg);
  color: var(--button-primary-text);
  border: none;
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-4);
  font-family: var(--font-heading);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: background var(--transition-duration) ease;
}
.btn-primary:hover { background: var(--button-primary-hover-bg); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-secondary {
  background: var(--color-surface-alt);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-4);
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
  cursor: pointer;
}
.btn-secondary:hover { border-color: var(--color-accent); color: var(--color-accent); }

.btn-success {
  background: var(--color-success);
  color: var(--color-bg);
  border: none;
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-4);
  font-family: var(--font-heading);
  font-size: var(--font-size-sm);
  cursor: pointer;
  font-weight: 600;
}
.btn-success:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-danger {
  background: var(--button-danger-bg);
  color: white;
  border: none;
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-4);
  font-family: var(--font-heading);
  font-size: var(--font-size-sm);
  cursor: pointer;
  font-weight: 600;
}
.btn-danger:disabled { opacity: 0.5; cursor: not-allowed; }

/* Epic selector */
.epic-selector {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}
.epic-selector__label {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  letter-spacing: 0.08em;
  white-space: nowrap;
}
.epic-selector__list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}
.epic-selector__btn {
  background: var(--color-surface-alt);
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  padding: var(--space-0-5) var(--space-2);
  cursor: pointer;
  transition: all var(--transition-duration) ease;
}
.epic-selector__btn:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
}
.epic-selector__btn--active {
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  border-color: var(--color-accent);
  color: var(--color-accent);
}

/* Task Navigation */
.task-nav {
  display: flex;
  align-items: center;
  gap: 0;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
  margin-bottom: var(--space-3);
  background: var(--color-surface-alt);
}

.task-nav__btn {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
  transition: background var(--transition-duration) ease, color var(--transition-duration) ease;
  flex: 1;
  min-width: 0;
}
.task-nav__btn--prev { justify-content: flex-start; border-right: 1px solid var(--color-border); }
.task-nav__btn--next { justify-content: flex-end; border-left: 1px solid var(--color-border); }
.task-nav__btn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--color-accent) 8%, transparent);
  color: var(--color-accent);
}
.task-nav__btn:disabled { opacity: 0.3; cursor: not-allowed; }

.task-nav__arrow {
  font-size: 1rem;
  flex-shrink: 0;
}

.task-nav__hint {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  min-width: 0;
  overflow: hidden;
}
.task-nav__btn--next .task-nav__hint { align-items: flex-end; }

.task-nav__hint-key {
  font-size: var(--font-size-xs);
  color: inherit;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 120px;
}

.task-nav__hint-state {
  font-size: var(--font-size-2xs);
  font-family: var(--font-mono);
  letter-spacing: 0.04em;
  opacity: 0.7;
}
.task-nav__hint-state[data-state="in_progress"] { color: var(--color-accent); opacity: 1; }
.task-nav__hint-state[data-state="in_review"]   { color: var(--color-warning); opacity: 1; }
.task-nav__hint-state[data-state="qa_failed"]   { color: var(--color-danger);  opacity: 1; }
.task-nav__hint-state[data-state="done"]        { color: var(--color-success); opacity: 1; }

.task-nav__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  padding: var(--space-2) var(--space-3);
  flex-shrink: 0;
}

.task-nav__pos {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  letter-spacing: 0.06em;
}

.task-nav__key {
  font-size: var(--font-size-xs);
  color: var(--color-accent);
  letter-spacing: 0.08em;
}

/* QA-Failed Panel */
.prompt-station__qa-failed {
  border-left: 3px solid var(--color-danger);
  background: color-mix(in srgb, var(--color-danger) 4%, var(--color-surface));
}

.qa-failed-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-3);
}

.qa-failed-count {
  font-size: var(--font-size-xs);
  color: var(--color-danger);
  background: color-mix(in srgb, var(--color-danger) 15%, transparent);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-full);
}

.qa-failed-reason {
  background: color-mix(in srgb, var(--color-danger) 8%, var(--color-surface-alt));
  border: 1px solid color-mix(in srgb, var(--color-danger) 30%, transparent);
  border-radius: var(--radius-sm);
  padding: var(--space-3);
  margin-bottom: var(--space-3);
}

.qa-failed-reason__label {
  display: block;
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--color-danger);
  margin-bottom: var(--space-1);
}

.qa-failed-reason__text {
  font-size: var(--font-size-sm);
  color: var(--color-text);
  margin: 0;
  line-height: 1.5;
}

.qa-failed-hint {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  margin: 0 0 var(--space-3);
}

.qa-failed-actions {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-3);
}

/* Gaertner Prompt Flow (TASK-5-021) */
.prompt-station__gaertner {
  border-left: 3px solid var(--color-success);
}

.gaertner-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-2);
}

.gaertner-close {
  background: none;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: var(--font-size-sm);
}

.gaertner-context {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  margin: 0 0 var(--space-3);
}

.gaertner-loading {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  padding: var(--space-4) 0;
}

.gaertner-prompt-text {
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
  margin: 0 0 var(--space-3);
  line-height: 1.5;
}

.worker-prompt-section {
  margin-top: var(--space-3);
  border-top: 1px solid var(--color-border);
  padding-top: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.worker-prompt-actions {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.worker-prompt-text {
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 320px;
  overflow-y: auto;
  margin: 0;
  line-height: 1.5;
}

.gaertner-actions {
  display: flex;
  gap: var(--space-2);
}

/* ── Auto-Mode Monitor (TASK-8-023) ─────────────────────────────────────── */

.auto-mode-monitor {
  border: 1px solid color-mix(in srgb, var(--color-success, #3cff9a) 40%, transparent);
  border-left: 3px solid var(--color-success, #3cff9a);
  background: color-mix(in srgb, var(--color-success, #3cff9a) 5%, var(--color-surface));
  border-radius: var(--radius-md);
  padding: var(--space-4) var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.auto-mode-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
}

.auto-mode-title-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.auto-mode-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--color-success, #3cff9a);
  box-shadow: 0 0 8px var(--color-success, #3cff9a);
  animation: pulse-dot 1.8s ease-in-out infinite;
  flex-shrink: 0;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; box-shadow: 0 0 8px var(--color-success, #3cff9a); }
  50% { opacity: 0.5; box-shadow: 0 0 20px var(--color-success, #3cff9a); }
}

.auto-mode-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-lg);
  color: var(--color-success, #3cff9a);
  letter-spacing: 0.1em;
  margin: 0;
}

.auto-mode-override {
  flex-shrink: 0;
  border-color: var(--color-success, #3cff9a);
  color: var(--color-success, #3cff9a);
}

.auto-mode-stats {
  display: flex;
  gap: var(--space-5);
}

.auto-stat {
  display: flex;
  flex-direction: column;
  gap: var(--space-0-5);
}

.auto-stat__label {
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--color-text-muted);
}

.auto-stat__value {
  font-size: var(--font-size-xl);
  color: var(--color-text);
}

.auto-mode-dispatches {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.auto-dispatches__label {
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--color-text-muted);
}

.auto-dispatches__empty {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  font-style: italic;
}

.dispatch-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-0-5);
}

.dispatch-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  background: var(--color-surface-alt);
  font-size: var(--font-size-xs);
}

.dispatch-key {
  flex: 1;
  color: var(--color-text);
}

.dispatch-status {
  font-size: var(--font-size-2xs);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 1px var(--space-1-5);
  border-radius: var(--radius-xs);
}
.dispatch-status--success,
.dispatch-status--done { background: var(--color-success); color: var(--color-bg); }
.dispatch-status--pending { background: var(--color-text-muted); color: var(--color-bg); }
.dispatch-status--failed,
.dispatch-status--error { background: var(--color-danger); color: white; }

.dispatch-time {
  color: var(--color-text-muted);
  white-space: nowrap;
}

.dispatch-tokens {
  color: var(--color-text-muted);
  white-space: nowrap;
}

.auto-mode-back-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface-alt);
}

.auto-mode-back-label {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

/* ── Prompt Actions / Execute ───────────────────────────────────────────── */

.prompt-actions {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  flex-wrap: wrap;
}

.btn-execute {
  background: var(--color-accent);
}

.btn-agent-select {
  min-width: 132px;
}

.execute-result {
  margin-top: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
  background: var(--color-surface-alt);
}

.execute-result--completed {
  border-color: color-mix(in srgb, var(--color-success) 50%, transparent);
  background: color-mix(in srgb, var(--color-success) 5%, var(--color-surface));
}

.execute-result--failed,
.execute-result--no_provider {
  border-color: color-mix(in srgb, var(--color-danger) 50%, transparent);
  background: color-mix(in srgb, var(--color-danger) 5%, var(--color-surface));
}

.execute-result__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-2);
}

.execute-result__status {
  font-weight: 600;
  font-size: var(--font-size-sm);
}

.execute-result__dismiss {
  background: none;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: var(--font-size-base);
  padding: var(--space-0-5) var(--space-1-5);
}

.execute-result__dismiss:hover {
  color: var(--color-text);
}

.execute-result__content pre {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  max-height: 300px;
  overflow-y: auto;
  margin: 0;
}

.execute-result__tools {
  margin-top: var(--space-2);
  font-size: var(--font-size-sm);
}

.execute-result__tools ul {
  margin: var(--space-1) 0 0 var(--space-4);
  padding: 0;
}

.execute-result__tools code {
  font-family: var(--font-mono);
  background: color-mix(in srgb, var(--color-text) 8%, transparent);
  padding: 1px var(--space-1);
  border-radius: var(--radius-xs);
}

.execute-result__tokens {
  margin-top: var(--space-2);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}
</style>
