<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useProjectStore } from '../../stores/projectStore'
import { useMcpStore } from '../../stores/mcpStore'
import { api } from '../../api'
import { HivemindCard, HivemindDropdown } from '../../components/ui'
import TokenRadar from '../../components/ui/TokenRadar.vue'
import McpStatusIndicator from '../../components/ui/McpStatusIndicator.vue'
import QueueBadge from '../../components/ui/QueueBadge.vue'
import ProjectCreateDialog from '../../components/domain/ProjectCreateDialog.vue'

const projectStore = useProjectStore()
const mcpStore = useMcpStore()
const showCreateDialog = ref(false)

// Token Radar state
const tokenCount = ref(0)
const tokenMax = ref(8000)

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
        <p class="task-description">{{ projectStore.activeTask.description }}</p>
        <button class="btn-secondary" @click="copyToClipboard(projectStore.activeTask.description ?? '')">
          📋 Kopieren
        </button>
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
            {{ gaertnerCopied ? '✓ Kopiert!' : '📋 In Zwischenablage kopieren' }}
          </button>
          <button class="btn-secondary" @click="loadGaertnerPrompt()">↻ Neu laden</button>
        </div>
      </HivemindCard>
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
  padding: 2px var(--space-2);
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

.gaertner-actions {
  display: flex;
  gap: var(--space-2);
}
</style>
