<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { api } from '../../api'
import type { Epic, Task, PeerNode, ContextBoundary } from '../../api/types'
import EpicScopingModal from '../../components/domain/EpicScopingModal.vue'
import RequirementCaptureModal from '../../components/domain/RequirementCaptureModal.vue'
import TaskReviewPanel from '../../components/domain/TaskReviewPanel.vue'
import SlaCountdown from '../../components/ui/SlaCountdown.vue'
import { HivemindModal } from '../../components/ui'
import { useProjectStore } from '../../stores/projectStore'
import { useAuthStore } from '../../stores/authStore'

const store = useProjectStore()
const authStore = useAuthStore()
const isAdmin = computed(() => authStore.user?.role === 'admin')
const isDeveloper = computed(() => authStore.user?.role === 'developer' || authStore.user?.role === 'admin')

// ── Project selector ────────────────────────────────────────────────────────
const selectedProjectId = ref<string | null>(null)
const projects = computed(() => store.projects)

onMounted(async () => {
  if (!store.projects.length) await store.loadProjects()
  selectedProjectId.value = store.activeProject?.id ?? store.projects[0]?.id ?? null
})

// ── Epics ───────────────────────────────────────────────────────────────────
const epics = ref<Epic[]>([])
const epicsLoading = ref(false)
const epicsError = ref<string | null>(null)

async function loadEpics() {
  if (!selectedProjectId.value) return
  epicsLoading.value = true
  epicsError.value = null
  try {
    epics.value = await api.getEpics(selectedProjectId.value)
  } catch (e: unknown) {
    epicsError.value = e instanceof Error ? e.message : String(e)
  } finally {
    epicsLoading.value = false
  }
}

watch(selectedProjectId, loadEpics, { immediate: true })

// ── Tasks per epic ──────────────────────────────────────────────────────────
const tasksByEpic = ref<Record<string, Task[]>>({})
const expandedEpics = ref<Set<string>>(new Set())

async function toggleEpic(epicKey: string) {
  if (expandedEpics.value.has(epicKey)) {
    expandedEpics.value.delete(epicKey)
  } else {
    expandedEpics.value.add(epicKey)
    if (!tasksByEpic.value[epicKey]) {
      try {
        tasksByEpic.value[epicKey] = await api.getTasks(epicKey)
      } catch { /* ignore */ }
    }
  }
}

async function refreshEpicTasks(epicKey: string) {
  try {
    tasksByEpic.value[epicKey] = await api.getTasks(epicKey)
  } catch { /* ignore */ }
}

// ── Scoping ─────────────────────────────────────────────────────────────────
const scopingEpic = ref<Epic | null>(null)

function openScoping(epic: Epic) { scopingEpic.value = epic }

async function onScopingDone() {
  scopingEpic.value = null
  await loadEpics()
}

// ── Review ──────────────────────────────────────────────────────────────────
const reviewTask = ref<Task | null>(null)

function openReview(task: Task) { reviewTask.value = task }

// ── Worker Prompt (inline, pro Task) ────────────────────────────────────────
interface PromptEntry { text: string; loading: boolean; copied: boolean }
const promptMap = ref(new Map<string, PromptEntry>())
const promptExpanded = ref(new Set<string>())

async function togglePrompt(task: Task) {
  const key = task.task_key
  if (promptExpanded.value.has(key)) {
    promptExpanded.value = new Set([...promptExpanded.value].filter(k => k !== key))
    return
  }
  promptExpanded.value = new Set([...promptExpanded.value, key])
  if (promptMap.value.get(key)?.text) return
  const entry: PromptEntry = { text: '', loading: true, copied: false }
  promptMap.value = new Map(promptMap.value).set(key, entry)
  try {
    const role = task.state === 'in_review' ? 'reviewer' : 'worker'
    const epicId = epics.value.find(e => e.id === task.epic_id)?.id
    const result = await api.getPrompt(role, key, epicId, selectedProjectId.value ?? undefined)
    const parsed = JSON.parse(result[0]?.text || '{}')
    entry.text = parsed.data?.prompt || parsed.prompt || 'Kein Prompt verfügbar.'
  } catch {
    entry.text = 'Fehler beim Laden.'
  } finally {
    entry.loading = false
    promptMap.value = new Map(promptMap.value).set(key, { ...entry })
  }
}

async function copyTaskPrompt(taskKey: string) {
  const entry = promptMap.value.get(taskKey)
  if (!entry) return
  await navigator.clipboard.writeText(entry.text)
  promptMap.value = new Map(promptMap.value).set(taskKey, { ...entry, copied: true })
  setTimeout(() => {
    const e = promptMap.value.get(taskKey)
    if (e) promptMap.value = new Map(promptMap.value).set(taskKey, { ...e, copied: false })
  }, 2000)
}

// ── Reenter from qa_failed ───────────────────────────────────────────────────
const reenteringTasks = ref(new Set<string>())

async function reenterTask(task: Task) {
  reenteringTasks.value.add(task.task_key)
  try {
    await api.reenterTask(task.task_key)
    const epicKey = epics.value.find(e => e.id === task.epic_id)?.epic_key
    if (epicKey) await refreshEpicTasks(epicKey)
  } catch {
    /* ignore — Fehler im UI nicht kritisch */
  } finally {
    reenteringTasks.value.delete(task.task_key)
  }
}

async function onReviewDone() {
  const epicKey = epics.value.find(e => e.id === reviewTask.value?.epic_id)?.epic_key
  reviewTask.value = null
  if (epicKey) await refreshEpicTasks(epicKey)
  await loadEpics()
}

// ── Task state transitions ──────────────────────────────────────────────────
async function startTask(task: Task) {
  try {
    const updated = await api.patchTask(task.task_key, { state: 'in_progress', expected_version: task.version })
    const epicKey = epics.value.find(e => e.id === task.epic_id)?.epic_key
    if (epicKey) {
      const tasks = tasksByEpic.value[epicKey]
      if (tasks) {
        const idx = tasks.findIndex(t => t.task_key === task.task_key)
        if (idx !== -1) tasks[idx] = updated
      }
      await loadEpics()
    }
  } catch { /* ignore silent fail */ }
}

// ── State badge helpers ──────────────────────────────────────────────────────
const EPIC_STATE_CLASS: Record<string, string> = {
  incoming: 'badge--pending',
  scoped: 'badge--info',
  in_progress: 'badge--active',
  done: 'badge--done',
  cancelled: 'badge--muted',
}
const TASK_STATE_CLASS: Record<string, string> = {
  incoming: 'badge--pending',
  scoped: 'badge--info',
  ready: 'badge--info',
  in_progress: 'badge--active',
  in_review: 'badge--review',
  done: 'badge--done',
  qa_failed: 'badge--danger',
  blocked: 'badge--danger',
  escalated: 'badge--danger',
  cancelled: 'badge--muted',
}

const selectedProject = computed(() =>
  store.projects.find(p => p.id === selectedProjectId.value)
)

// ── Node filter (Federation) ─────────────────────────────────────────────────
const peerNodes = ref<PeerNode[]>([])
const nodeFilter = ref<string>('')  // '' = all, 'local' = own node, uuid = specific peer

onMounted(async () => {
  try {
    peerNodes.value = await api.getNodes()
  } catch { /* federation not configured — that's fine */ }
})

// ── Architekt Prompt (TASK-4-009) ────────────────────────────────────────────
const architektLoading = ref<string | null>(null)  // epic_key being loaded
const architektPrompt = ref<string | null>(null)
const architektTokenCount = ref<number | null>(null)
const showArchitektModal = ref(false)
const copySuccess = ref(false)

function epicHasNoTasks(epicKey: string): boolean {
  const tasks = tasksByEpic.value[epicKey]
  return !tasks || tasks.length === 0
}

// ── Backup Owner Edit (TASK-6-014) ───────────────────────────────────────────
const editingBackupOwner = ref<Record<string, boolean>>({})
const backupOwnerInput = ref<Record<string, string>>({})
const backupOwnerSaving = ref<Record<string, boolean>>({})

function startEditBackupOwner(epic: Epic) {
  editingBackupOwner.value[epic.epic_key] = true
  backupOwnerInput.value[epic.epic_key] = epic.backup_owner_id ?? ''
}

function cancelEditBackupOwner(epicKey: string) {
  editingBackupOwner.value[epicKey] = false
  backupOwnerInput.value[epicKey] = ''
}

async function saveBackupOwner(epic: Epic) {
  const userId = backupOwnerInput.value[epic.epic_key]?.trim()
  if (!userId) return
  backupOwnerSaving.value[epic.epic_key] = true
  try {
    await api.callMcpTool('hivemind/reassign_epic_owner', {
      epic_key: epic.epic_key,
      backup_owner_id: userId,
    })
    epic.backup_owner_id = userId
    editingBackupOwner.value[epic.epic_key] = false
  } catch (e: unknown) {
    epicsError.value = (e as Error).message
  } finally {
    backupOwnerSaving.value[epic.epic_key] = false
  }
}

async function runArchitekt(epic: Epic) {
  architektLoading.value = epic.epic_key
  try {
    const result = await api.getPrompt('architekt', undefined, epic.epic_key)
    // result is McpToolResponse[] — each .text is JSON: {"data": {"prompt": "...", "token_count": N}}
    const raw = result.map(r => r.text ?? '').join('\n')
    try {
      const parsed = JSON.parse(raw)
      architektPrompt.value = parsed?.data?.prompt ?? raw
      architektTokenCount.value = parsed?.data?.token_count ?? null
    } catch {
      // Fallback: display raw text if not JSON
      architektPrompt.value = raw
      architektTokenCount.value = null
    }
    copySuccess.value = false
    showArchitektModal.value = true
  } catch (e: unknown) {
    epicsError.value = (e as Error).message
  } finally {
    architektLoading.value = null
  }
}

async function copyPrompt() {
  if (!architektPrompt.value) return
  try {
    await navigator.clipboard.writeText(architektPrompt.value)
    copySuccess.value = true
    setTimeout(() => { copySuccess.value = false }, 2000)
  } catch {
    // Fallback for non-secure contexts
    const ta = document.createElement('textarea')
    ta.value = architektPrompt.value
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
    copySuccess.value = true
    setTimeout(() => { copySuccess.value = false }, 2000)
  }
}

// ── Requirement Capture Modal ────────────────────────────────────────────────
const showRequirementModal = ref(false)

function openRequirementModal() { showRequirementModal.value = true }

function onProposalSaved() {
  showRequirementModal.value = false
}

// ── Task Creation Dialog (TASK-4-009) ────────────────────────────────────────
const showTaskDialog = ref(false)
const taskDialogEpicKey = ref<string>('')
const newTaskTitle = ref('')
const newTaskDescription = ref('')
const newTaskAssignTo = ref<string>('')
const taskCreateLoading = ref(false)
const members = ref<{ project_id: string; user_id: string; role: string; username?: string }[]>([])

async function openTaskDialog(epicKey: string) {
  taskDialogEpicKey.value = epicKey
  newTaskTitle.value = ''
  newTaskDescription.value = ''
  newTaskAssignTo.value = ''
  showTaskDialog.value = true
  // Load project members for assignment dropdown
  if (selectedProjectId.value && !members.value.length) {
    try {
      members.value = await api.getMembers(selectedProjectId.value) as typeof members.value
    } catch { /* ignore */ }
  }
}

async function createTask() {
  if (!newTaskTitle.value.trim()) return
  taskCreateLoading.value = true
  try {
    await api.createTask(taskDialogEpicKey.value, {
      title: newTaskTitle.value.trim(),
      description: newTaskDescription.value.trim() || undefined,
      assigned_to: newTaskAssignTo.value || undefined,
    })
    showTaskDialog.value = false
    await refreshEpicTasks(taskDialogEpicKey.value)
    // Auto-expand the epic if not already expanded
    expandedEpics.value.add(taskDialogEpicKey.value)
  } catch (e: unknown) {
    epicsError.value = (e as Error).message
  } finally {
    taskCreateLoading.value = false
  }
}

// ── Context Boundary (TASK-4-009) ────────────────────────────────────────────
const selectedTaskForBoundary = ref<Task | null>(null)
const taskBoundary = ref<ContextBoundary | null>(null)
const boundaryLoading = ref(false)

async function showTaskDetail(task: Task) {
  selectedTaskForBoundary.value = task
  boundaryLoading.value = true
  taskBoundary.value = null
  try {
    taskBoundary.value = await api.getContextBoundary(task.task_key)
  } catch { /* no boundary — fine */ }
  finally {
    boundaryLoading.value = false
  }
}

function closeTaskDetail() {
  selectedTaskForBoundary.value = null
  taskBoundary.value = null
}
</script>

<template>
  <div class="command-deck">
    <!-- Header -->
    <div class="deck-header">
      <h1 class="deck-title">Command Deck</h1>
      <select
        v-if="projects.length > 1"
        v-model="selectedProjectId"
        class="project-select"
      >
        <option v-for="p in projects" :key="p.id" :value="p.id">
          {{ p.name }}
        </option>
      </select>
      <span v-else-if="selectedProject" class="project-label">
        {{ selectedProject.name }}
      </span>

      <!-- Node filter -->
      <select v-if="peerNodes.length" v-model="nodeFilter" class="node-filter-select">
        <option value="">Alle Nodes</option>
        <option value="local">Lokal (eigener Node)</option>
        <option v-for="peer in peerNodes" :key="peer.id" :value="peer.id">
          {{ peer.node_name }}
        </option>
      </select>

      <!-- Requirement Capture -->
      <button
        v-if="selectedProjectId"
        class="btn-new-requirement"
        @click="openRequirementModal"
      >
        + Neue Anforderung
      </button>
    </div>

    <!-- Loading / Error -->
    <div v-if="epicsLoading" class="deck-state">Lade Epics…</div>
    <div v-else-if="epicsError" class="deck-state deck-state--error">{{ epicsError }}</div>
    <div v-else-if="!epics.length && selectedProjectId" class="deck-state">
      Keine Epics — lege dein erstes Epic an.
    </div>
    <div v-else-if="!selectedProjectId" class="deck-state">
      Kein Projekt ausgewählt.
    </div>

    <!-- Epic list -->
    <div v-else class="epic-list">
      <div
        v-for="epic in epics"
        :key="epic.epic_key"
        class="epic-card"
        :class="`epic-card--${epic.state}`"
      >
        <!-- Epic header row -->
        <div class="epic-header" @click="toggleEpic(epic.epic_key)">
          <div class="epic-header__left">
            <span class="epic-key">{{ epic.epic_key }}</span>
            <span class="epic-title">{{ epic.title }}</span>
          </div>
          <div class="epic-header__right">
            <SlaCountdown :sla_due_at="epic.sla_due_at" />
            <span v-if="epic.backup_owner_id" class="backup-owner-badge" title="Backup Owner zugewiesen">
              👤 Backup
            </span>
            <span class="badge" :class="EPIC_STATE_CLASS[epic.state] ?? 'badge--muted'">
              {{ epic.state }}
            </span>
            <button
              v-if="epic.state === 'incoming'"
              class="btn-scope"
              @click.stop="openScoping(epic)"
            >
              SCOPEN →
            </button>
            <button
              v-if="epic.state === 'scoped' && epicHasNoTasks(epic.epic_key)"
              class="btn-architekt"
              :disabled="architektLoading === epic.epic_key"
              @click.stop="runArchitekt(epic)"
            >
              {{ architektLoading === epic.epic_key ? '…' : 'Architekt starten ▶' }}
            </button>
            <span class="expand-icon">{{ expandedEpics.has(epic.epic_key) ? '▲' : '▼' }}</span>
          </div>
        </div>

        <!-- Task list (expanded) -->
        <div v-if="expandedEpics.has(epic.epic_key)" class="task-list">
          <div
            v-if="!tasksByEpic[epic.epic_key]"
            class="task-loading"
          >Lade…</div>
          <div
            v-else-if="!tasksByEpic[epic.epic_key].length"
            class="task-empty"
          >Keine Tasks</div>
          <template
            v-for="task in tasksByEpic[epic.epic_key]"
            :key="task.task_key"
          >
            <div
              class="task-row"
              @click="showTaskDetail(task)"
            >
              <span class="task-key">{{ task.task_key }}</span>
              <span class="task-title">{{ task.title }}</span>
              <span
                v-if="task.assigned_node_name"
                class="node-badge"
                :class="{ 'node-badge--inactive': peerNodes.find(p => p.id === task.assigned_node_id)?.status === 'inactive' }"
              >
                ⬡ {{ task.assigned_node_name }}
              </span>
              <div class="task-actions">
                <span class="badge badge--sm" :class="TASK_STATE_CLASS[task.state] ?? 'badge--muted'">
                  {{ task.state }}
                </span>
                <button
                  v-if="task.state === 'in_review'"
                  class="btn-review"
                  @click.stop="openReview(task)"
                >
                  REVIEW
                </button>
                <button
                  v-else-if="task.state === 'qa_failed'"
                  class="btn-reenter"
                  :disabled="reenteringTasks.has(task.task_key)"
                  @click.stop="reenterTask(task)"
                >
                  {{ reenteringTasks.has(task.task_key) ? '...' : '↩ ZURÜCK' }}
                </button>
                <button
                  v-else-if="task.state === 'scoped' || task.state === 'ready'"
                  class="btn-start"
                  @click.stop="startTask(task)"
                >
                  START →
                </button>
                <button
                  v-if="['in_progress','scoped','ready','qa_failed','in_review'].includes(task.state)"
                  class="btn-prompt"
                  :class="{ 'btn-prompt--active': promptExpanded.has(task.task_key) }"
                  @click.stop="togglePrompt(task)"
                >
                  {{ promptExpanded.has(task.task_key) ? '▲ PROMPT' : '▼ PROMPT' }}
                </button>
              </div>
            </div>
            <!-- Inline Prompt Panel -->
            <div
              v-if="promptExpanded.has(task.task_key)"
              class="task-prompt-panel"
              @click.stop
            >
              <div v-if="promptMap.get(task.task_key)?.loading" class="task-prompt-loading">Lade Prompt…</div>
              <template v-else>
                <div class="task-prompt-panel__actions">
                  <button
                    class="btn-secondary btn-prompt-copy"
                    @click="copyTaskPrompt(task.task_key)"
                  >
                    {{ promptMap.get(task.task_key)?.copied ? '✓ Kopiert!' : '📋 Kopieren' }}
                  </button>
                </div>
                <pre class="task-prompt-text">{{ promptMap.get(task.task_key)?.text }}</pre>
              </template>
            </div>
          </template>
          <!-- Add Task button -->
          <div v-if="isDeveloper" class="task-add-row">
            <button class="btn-add-task" @click.stop="openTaskDialog(epic.epic_key)">
              + Task hinzufügen
            </button>
          </div>

          <!-- Backup Owner Management (TASK-6-014) -->
          <div v-if="isAdmin" class="backup-owner-row">
            <span class="backup-owner-label">Backup Owner:</span>
            <span v-if="epic.backup_owner_id && !editingBackupOwner[epic.epic_key]" class="backup-owner-value">
              {{ epic.backup_owner_id.slice(0, 8) }}…
              <button class="btn-inline" @click.stop="startEditBackupOwner(epic)">✎</button>
            </span>
            <span v-else-if="!editingBackupOwner[epic.epic_key]" class="backup-owner-value backup-owner-value--empty">
              Nicht gesetzt
              <button class="btn-inline" @click.stop="startEditBackupOwner(epic)">+ Zuweisen</button>
            </span>
            <div v-else class="backup-owner-edit" @click.stop>
              <input
                v-model="backupOwnerInput[epic.epic_key]"
                class="backup-owner-input"
                placeholder="User-ID eingeben…"
              />
              <button
                class="btn-inline btn-inline--save"
                :disabled="backupOwnerSaving[epic.epic_key]"
                @click.stop="saveBackupOwner(epic)"
              >✓</button>
              <button class="btn-inline" @click.stop="cancelEditBackupOwner(epic.epic_key)">✕</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Epic Scoping Modal -->
    <EpicScopingModal
      v-if="scopingEpic"
      :epic="scopingEpic"
      :project-id="selectedProjectId!"
      @done="onScopingDone"
      @cancel="scopingEpic = null"
    />

    <!-- Task Review Panel (modal-style overlay) -->
    <Teleport to="body">
      <div v-if="reviewTask" class="review-overlay" @click.self="reviewTask = null">
        <div class="review-panel-wrapper">
          <TaskReviewPanel
            :task="reviewTask"
            @close="reviewTask = null"
            @done="onReviewDone"
          />
        </div>
      </div>
    </Teleport>

    <!-- Architekt Prompt Modal -->
    <HivemindModal v-model:model-value="showArchitektModal" title="Architekt-Prompt" size="lg">
      <div class="architekt-prompt-header">
        <span v-if="architektTokenCount" class="token-badge">~{{ architektTokenCount }} Tokens</span>
        <button class="btn-copy" @click="copyPrompt">
          {{ copySuccess ? '✓ Kopiert' : '⎘ Kopieren' }}
        </button>
      </div>
      <pre class="architekt-prompt-content">{{ architektPrompt }}</pre>
      <template #footer>
        <button class="btn-close-modal" @click="showArchitektModal = false">Schließen</button>
      </template>
    </HivemindModal>

    <!-- Task Creation Dialog -->
    <HivemindModal v-model:model-value="showTaskDialog" title="Neuen Task erstellen">
      <div class="task-form">
        <label class="form-label">
          Titel *
          <input v-model="newTaskTitle" type="text" class="form-input" placeholder="Task-Titel…" />
        </label>
        <label class="form-label">
          Beschreibung
          <textarea v-model="newTaskDescription" class="form-textarea" rows="3" placeholder="Beschreibung (optional)…" />
        </label>
        <label class="form-label">
          Zuweisen an
          <select v-model="newTaskAssignTo" class="form-select">
            <option value="">Nicht zugewiesen</option>
            <option v-for="m in members" :key="m.user_id" :value="m.user_id">
              {{ m.username || m.user_id }}
            </option>
          </select>
        </label>
      </div>
      <template #footer>
        <button class="btn-close-modal" @click="showTaskDialog = false">Abbrechen</button>
        <button
          class="btn-create-task"
          :disabled="!newTaskTitle.trim() || taskCreateLoading"
          @click="createTask"
        >
          {{ taskCreateLoading ? 'Erstelle…' : 'Task erstellen' }}
        </button>
      </template>
    </HivemindModal>

    <!-- Task Detail with Context Boundary -->
    <Teleport to="body">
      <div v-if="selectedTaskForBoundary" class="review-overlay" @click.self="closeTaskDetail">
        <div class="task-detail-panel">
          <header class="task-detail-header">
            <span class="task-key">{{ selectedTaskForBoundary.task_key }}</span>
            <h3>{{ selectedTaskForBoundary.title }}</h3>
            <button class="btn-close-x" @click="closeTaskDetail">✕</button>
          </header>
          <p v-if="selectedTaskForBoundary.description" class="task-detail-desc">
            {{ selectedTaskForBoundary.description }}
          </p>
          <div class="task-detail-meta">
            <span class="badge badge--sm" :class="TASK_STATE_CLASS[selectedTaskForBoundary.state] ?? 'badge--muted'">
              {{ selectedTaskForBoundary.state }}
            </span>
            <span v-if="selectedTaskForBoundary.assigned_node_name">
              ⬡ {{ selectedTaskForBoundary.assigned_node_name }}
            </span>
          </div>

          <!-- Context Boundary -->
          <div v-if="boundaryLoading" class="boundary-loading">Lade Context Boundary…</div>
          <div v-else-if="taskBoundary" class="context-boundary">
            <h4 class="boundary-title">
              Context Boundary (vom Architekt)
              <span class="boundary-info" title="Vom Architekt gesetzte Einschränkungen für diesen Task">ⓘ</span>
            </h4>
            <div class="boundary-grid">
              <div v-if="taskBoundary.allowed_skills?.length" class="boundary-item">
                <span class="boundary-label">Erlaubte Skills</span>
                <span class="boundary-value">{{ taskBoundary.allowed_skills.length }} Skills</span>
              </div>
              <div v-if="taskBoundary.allowed_docs?.length" class="boundary-item">
                <span class="boundary-label">Erlaubte Docs</span>
                <span class="boundary-value">{{ taskBoundary.allowed_docs.length }} Docs</span>
              </div>
              <div v-if="taskBoundary.max_token_budget" class="boundary-item">
                <span class="boundary-label">Max Token Budget</span>
                <span class="boundary-value">{{ taskBoundary.max_token_budget.toLocaleString() }}</span>
              </div>
              <div v-if="taskBoundary.external_access?.length" class="boundary-item">
                <span class="boundary-label">External Access</span>
                <span class="boundary-value">{{ taskBoundary.external_access.join(', ') }}</span>
              </div>
            </div>
          </div>
          <div v-else class="boundary-none">Keine Context Boundary gesetzt.</div>
        </div>
      </div>
    </Teleport>

    <!-- Requirement Capture Modal -->
    <RequirementCaptureModal
      v-model="showRequirementModal"
      :project-id="selectedProjectId"
      @proposal-saved="onProposalSaved"
    />
  </div>
</template>

<style scoped>
/* ── Layout ─────────────────────────────────────────────────────────────── */
.command-deck {
  padding: var(--space-6);
  max-width: 900px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.deck-header {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  border-bottom: 1px solid var(--color-border);
  padding-bottom: var(--space-4);
}

.deck-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-xl);
  color: var(--color-text);
  margin: 0;
  letter-spacing: 0.05em;
  flex: 1;
}

.project-select {
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
  padding: var(--space-1) var(--space-3);
}

.project-label {
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.deck-state {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  padding: var(--space-8) 0;
  text-align: center;
}
.deck-state--error { color: var(--color-danger); }

/* ── Epic cards ─────────────────────────────────────────────────────────── */
.epic-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.epic-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
  transition: border-color var(--transition-duration) ease;
}
.epic-card--in_progress { border-color: var(--color-accent); }
.epic-card--incoming { border-color: var(--color-warning); }

.epic-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  cursor: pointer;
  user-select: none;
  gap: var(--space-3);
}
.epic-header:hover { background: var(--color-surface-alt); }

.epic-header__left {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex: 1;
  min-width: 0;
}

.epic-key {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
}

.epic-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-sm);
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.epic-header__right {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

.expand-icon {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

/* ── Task list ──────────────────────────────────────────────────────────── */
.task-list {
  border-top: 1px solid var(--color-border);
  background: var(--color-bg);
}

.task-loading, .task-empty {
  padding: var(--space-3) var(--space-5);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.task-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-5);
  border-bottom: 1px solid var(--color-border);
  transition: background var(--transition-duration) ease;
}
.task-row:last-child { border-bottom: none; }
.task-row:hover { background: var(--color-surface); }

.task-key {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
  min-width: 100px;
}

.task-title {
  flex: 1;
  font-size: var(--font-size-sm);
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

/* ── Badges ─────────────────────────────────────────────────────────────── */
.badge {
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  padding: 2px 7px;
  border-radius: 3px;
  white-space: nowrap;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.badge--sm { font-size: 9px; padding: 1px 5px; }
.badge--pending  { background: color-mix(in srgb, var(--color-warning) 15%, transparent); color: var(--color-warning); }
.badge--info     { background: color-mix(in srgb, var(--color-accent) 15%, transparent); color: var(--color-accent); }
.badge--active   { background: color-mix(in srgb, var(--color-accent) 25%, transparent); color: var(--color-accent); border: 1px solid var(--color-accent); }
.badge--review   { background: color-mix(in srgb, var(--color-warning) 25%, transparent); color: var(--color-warning); border: 1px solid var(--color-warning); }
.badge--done     { background: color-mix(in srgb, var(--color-success) 15%, transparent); color: var(--color-success); }
.badge--danger   { background: color-mix(in srgb, var(--color-danger) 15%, transparent); color: var(--color-danger); }
.badge--muted    { background: var(--color-surface-alt); color: var(--color-text-muted); }

/* ── Buttons ─────────────────────────────────────────────────────────────── */
.btn-scope {
  background: color-mix(in srgb, var(--color-warning) 15%, transparent);
  color: var(--color-warning);
  border: 1px solid var(--color-warning);
  border-radius: var(--radius-sm);
  font-family: var(--font-heading);
  font-size: var(--font-size-xs);
  padding: 2px var(--space-2);
  cursor: pointer;
  letter-spacing: 0.04em;
  transition: background var(--transition-duration) ease;
}
.btn-scope:hover { background: color-mix(in srgb, var(--color-warning) 30%, transparent); }

.btn-review {
  background: color-mix(in srgb, var(--color-warning) 20%, transparent);
  color: var(--color-warning);
  border: 1px solid var(--color-warning);
  border-radius: var(--radius-sm);
  font-family: var(--font-heading);
  font-size: 9px;
  padding: 1px var(--space-2);
  cursor: pointer;
  letter-spacing: 0.06em;
  transition: background var(--transition-duration) ease;
}
.btn-review:hover { background: color-mix(in srgb, var(--color-warning) 35%, transparent); }

.btn-reenter {
  background: color-mix(in srgb, var(--color-danger) 15%, transparent);
  color: var(--color-danger);
  border: 1px solid var(--color-danger);
  border-radius: var(--radius-sm);
  font-family: var(--font-heading);
  font-size: 9px;
  padding: 1px var(--space-2);
  cursor: pointer;
  letter-spacing: 0.06em;
  transition: background var(--transition-duration) ease;
}
.btn-reenter:hover:not(:disabled) { background: color-mix(in srgb, var(--color-danger) 28%, transparent); }
.btn-reenter:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-prompt {
  background: none;
  color: var(--color-muted, #888);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-family: var(--font-heading);
  font-size: 9px;
  padding: 1px var(--space-2);
  cursor: pointer;
  letter-spacing: 0.06em;
  transition: background var(--transition-duration) ease, color var(--transition-duration) ease;
}
.btn-prompt:hover { background: color-mix(in srgb, var(--color-accent) 10%, transparent); color: var(--color-accent); }
.btn-prompt--active { color: var(--color-accent); border-color: var(--color-accent); }

.task-prompt-panel {
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-top: none;
  border-radius: 0 0 var(--radius-sm) var(--radius-sm);
  padding: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.task-prompt-panel__actions {
  display: flex;
  gap: var(--space-2);
}

.btn-prompt-copy {
  font-size: var(--font-size-sm);
  padding: var(--space-1) var(--space-2);
}

.task-prompt-loading {
  color: var(--color-muted, #888);
  font-size: var(--font-size-sm);
  font-style: italic;
}

.task-prompt-text {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
  font-family: var(--font-mono);
  font-size: 11px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 280px;
  overflow-y: auto;
  margin: 0;
  line-height: 1.5;
}

.btn-start {
  background: none;
  color: var(--color-accent);
  border: 1px solid var(--color-accent);
  border-radius: var(--radius-sm);
  font-family: var(--font-heading);
  font-size: 9px;
  padding: 1px var(--space-2);
  cursor: pointer;
  letter-spacing: 0.06em;
  transition: background var(--transition-duration) ease;
}
.btn-start:hover { background: color-mix(in srgb, var(--color-accent) 15%, transparent); }

/* ── Review overlay ─────────────────────────────────────────────────────── */
.review-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 500;
}

.review-panel-wrapper {
  width: 520px;
  max-width: calc(100vw - var(--space-8));
  max-height: 85vh;
  overflow-y: auto;
}

/* ── Node filter & badge ────────────────────────────────────────────────── */
.node-filter-select {
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-1) var(--space-3);
  color: var(--color-text);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
}

.node-badge {
  font-family: var(--font-mono);
  font-size: 9px;
  padding: 1px var(--space-2);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  color: var(--color-accent);
  border: 1px solid var(--color-accent);
  white-space: nowrap;
}

.node-badge--inactive {
  color: var(--color-text-muted);
  border-color: var(--color-border);
  background: color-mix(in srgb, var(--color-text-muted) 10%, transparent);
}

/* ── Architekt Button ───────────────────────────────────────────────────── */
.btn-architekt {
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  color: var(--color-accent);
  border: 1px solid var(--color-accent);
  border-radius: var(--radius-sm);
  font-family: var(--font-heading);
  font-size: var(--font-size-xs);
  padding: 2px var(--space-2);
  cursor: pointer;
  letter-spacing: 0.04em;
  transition: background var(--transition-duration) ease;
}
.btn-architekt:hover { background: color-mix(in srgb, var(--color-accent) 30%, transparent); }
.btn-architekt:disabled { opacity: 0.5; cursor: wait; }

.architekt-prompt-header {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}
.token-badge {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 999px;
  padding: 2px 10px;
}
.btn-copy {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding: 4px 12px;
  font-size: var(--font-size-sm);
  color: var(--color-text);
  cursor: pointer;
  transition: all 0.15s ease;
}
.btn-copy:hover {
  background: var(--color-accent);
  color: var(--color-bg);
  border-color: var(--color-accent);
}
.architekt-prompt-content {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: var(--space-4);
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-x: auto;
  color: var(--color-text);
  margin: 0;
  max-height: 60vh;
  overflow-y: auto;
}

/* ── Add Task ───────────────────────────────────────────────────────────── */
.task-add-row {
  padding: var(--space-2) var(--space-5);
  border-top: 1px dashed var(--color-border);
}

.btn-add-task {
  background: none;
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  padding: var(--space-1) var(--space-3);
  cursor: pointer;
  transition: all 0.15s ease;
}
.btn-add-task:hover {
  color: var(--color-accent);
  border-color: var(--color-accent);
}

/* ── Task Form ──────────────────────────────────────────────────────────── */
.task-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.form-label {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.form-input,
.form-textarea,
.form-select {
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  color: var(--color-text);
  padding: var(--space-2);
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
}

.form-textarea { resize: vertical; }

.btn-close-modal {
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  color: var(--color-text);
  padding: var(--space-2) var(--space-4);
  cursor: pointer;
  font-size: var(--font-size-sm);
}

.btn-create-task {
  background: var(--color-accent);
  color: var(--color-bg);
  border: none;
  border-radius: 6px;
  padding: var(--space-2) var(--space-4);
  cursor: pointer;
  font-weight: 600;
  font-size: var(--font-size-sm);
}
.btn-create-task:disabled { opacity: 0.5; cursor: not-allowed; }

/* ── Task Detail Panel ──────────────────────────────────────────────────── */
.task-detail-panel {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  width: 520px;
  max-width: calc(100vw - var(--space-8));
  max-height: 85vh;
  overflow-y: auto;
  padding: var(--space-6);
}

.task-detail-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}
.task-detail-header h3 {
  flex: 1;
  font-family: var(--font-heading);
  margin: 0;
}

.btn-close-x {
  background: none;
  border: none;
  color: var(--color-text-muted);
  font-size: var(--font-size-lg);
  cursor: pointer;
}

.task-detail-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text);
  margin: 0 0 var(--space-3);
  line-height: 1.5;
}

.task-detail-meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}

/* ── Context Boundary ───────────────────────────────────────────────────── */
.context-boundary {
  background: color-mix(in srgb, var(--color-accent) 5%, transparent);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: var(--space-4);
}

.boundary-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-sm);
  margin: 0 0 var(--space-3);
  color: var(--color-accent);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.boundary-info {
  font-size: var(--font-size-xs);
  cursor: help;
  color: var(--color-text-muted);
}

.boundary-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-2);
}

.boundary-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.boundary-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.boundary-value {
  font-size: var(--font-size-sm);
  color: var(--color-text);
  font-weight: 600;
}

.boundary-loading,
.boundary-none {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  padding: var(--space-3) 0;
}

.task-row { cursor: pointer; }

/* ── Backup Owner (TASK-6-014) ───────────────────────────────────────────── */
.backup-owner-badge {
  font-size: 10px;
  font-family: var(--font-mono);
  padding: 1px 6px;
  border-radius: 3px;
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  color: var(--color-accent);
}

.backup-owner-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-top: 1px solid var(--color-border);
  font-size: var(--font-size-xs);
}

.backup-owner-label {
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.backup-owner-value {
  color: var(--color-text);
  font-family: var(--font-mono);
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.backup-owner-value--empty {
  color: var(--color-text-muted);
  font-style: italic;
}

.backup-owner-edit {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.backup-owner-input {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 3px;
  color: var(--color-text);
  padding: 2px 6px;
  font-size: 11px;
  font-family: var(--font-mono);
  width: 200px;
}

.btn-inline {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--color-text-muted);
  font-size: 12px;
  padding: 2px 4px;
  border-radius: 2px;
  transition: all 0.15s;
}
.btn-inline:hover { color: var(--color-text); background: var(--color-surface-alt); }
.btn-inline--save { color: var(--color-success); }
.btn-inline--save:hover { color: var(--color-success); }

.btn-new-requirement {
  background: color-mix(in srgb, var(--color-accent) 12%, transparent);
  color: var(--color-accent);
  border: 1px solid color-mix(in srgb, var(--color-accent) 35%, transparent);
  border-radius: var(--radius-sm);
  padding: var(--space-1) var(--space-3);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  font-weight: 600;
  cursor: pointer;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  white-space: nowrap;
  margin-left: auto;
}
.btn-new-requirement:hover {
  background: color-mix(in srgb, var(--color-accent) 20%, transparent);
}
</style>
