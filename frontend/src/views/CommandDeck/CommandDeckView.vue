<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { api } from '../../api'
import type { Epic, EpicRun, EpicRunArtifact, EpicStartResponse, Task, PeerNode, ContextBoundary } from '../../api/types'
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
const epicRunsByEpic = ref<Record<string, EpicRun[]>>({})
const epicRunsLoading = ref<Record<string, boolean>>({})
const epicRunsError = ref<Record<string, string | null>>({})
const epicRunArtifactsByRun = ref<Record<string, EpicRunArtifact[]>>({})
const epicRunArtifactsLoading = ref<Record<string, boolean>>({})

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
watch(selectedProjectId, () => {
  tasksByEpic.value = {}
  epicRunsByEpic.value = {}
  epicRunArtifactsByRun.value = {}
})

async function loadEpicRuns(epicKey: string, force = false) {
  if (epicRunsByEpic.value[epicKey] && !force) return
  epicRunsLoading.value = { ...epicRunsLoading.value, [epicKey]: true }
  epicRunsError.value = { ...epicRunsError.value, [epicKey]: null }
  try {
    const runs = await api.getEpicRuns(epicKey, 8)
    epicRunsByEpic.value = { ...epicRunsByEpic.value, [epicKey]: runs }
    if (runs[0]) await loadEpicRunArtifacts(runs[0].id, force)
  } catch (e: unknown) {
    epicRunsError.value = {
      ...epicRunsError.value,
      [epicKey]: e instanceof Error ? e.message : String(e),
    }
  } finally {
    epicRunsLoading.value = { ...epicRunsLoading.value, [epicKey]: false }
  }
}

async function loadEpicRunArtifacts(runId: string, force = false) {
  if (epicRunArtifactsByRun.value[runId] && !force) return
  epicRunArtifactsLoading.value = { ...epicRunArtifactsLoading.value, [runId]: true }
  try {
    const artifacts = await api.getEpicRunArtifacts(runId)
    epicRunArtifactsByRun.value = { ...epicRunArtifactsByRun.value, [runId]: artifacts }
  } catch {
    epicRunArtifactsByRun.value = { ...epicRunArtifactsByRun.value, [runId]: [] }
  } finally {
    epicRunArtifactsLoading.value = { ...epicRunArtifactsLoading.value, [runId]: false }
  }
}

function latestEpicRun(epicKey: string): EpicRun | null {
  return epicRunsByEpic.value[epicKey]?.[0] ?? null
}

function runAnalysis(run: EpicRun | null | undefined): Record<string, any> {
  return (run?.analysis ?? {}) as Record<string, any>
}

function runExecution(run: EpicRun | null | undefined): Record<string, any> {
  return (runAnalysis(run).execution_analysis ?? {}) as Record<string, any>
}

function runSlotPlan(run: EpicRun | null | undefined): Record<string, any> {
  return (runExecution(run).slot_plan ?? {}) as Record<string, any>
}

function runScheduler(run: EpicRun | null | undefined): Record<string, any> {
  return (runAnalysis(run).scheduler ?? {}) as Record<string, any>
}

function runItems(run: EpicRun | null | undefined, section: string): Record<string, any>[] {
  const value = runExecution(run)[section]
  return Array.isArray(value) ? value : []
}

function runSummaryCount(run: EpicRun | null | undefined, key: string): number {
  const value = runExecution(run).summary?.[key]
  return typeof value === 'number' ? value : 0
}

function runArtifacts(runId: string | null | undefined): EpicRunArtifact[] {
  if (!runId) return []
  return epicRunArtifactsByRun.value[runId] ?? []
}

function runArtifactKinds(runId: string | null | undefined): string[] {
  const kinds = new Set<string>()
  for (const artifact of runArtifacts(runId)) kinds.add(artifact.artifact_type)
  return [...kinds]
}

function formatRunTimestamp(value: string | null | undefined): string {
  if (!value) return '–'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function formatReason(item: Record<string, any>): string {
  const firstReason = Array.isArray(item.reasons) ? item.reasons[0] : null
  return firstReason?.message || 'Keine Details'
}

function artifactSummary(artifact: EpicRunArtifact): string {
  if (artifact.summary) return artifact.summary
  const payload = artifact.payload as Record<string, unknown>
  if (typeof payload.summary === 'string') return payload.summary
  if (typeof payload.note === 'string') return payload.note
  return 'Ohne Kurzbeschreibung'
}

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
    await loadEpicRuns(epicKey)
  }
}

async function refreshEpicTasks(epicKey: string) {
  try {
    tasksByEpic.value[epicKey] = await api.getTasks(epicKey)
  } catch { /* ignore */ }
}

async function refreshEpicRunData(epicKey: string) {
  await loadEpicRuns(epicKey, true)
  const latest = latestEpicRun(epicKey)
  if (latest) {
    selectedEpicRunId.value = latest.id
    await loadEpicRunArtifacts(latest.id, true)
  }
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
  if (epicKey) await refreshEpicRunData(epicKey)
  await loadEpics()
}

// ── Task state transitions ──────────────────────────────────────────────────
const transitioningTasks = ref(new Set<string>())

async function transitionTask(task: Task, targetState: string) {
  transitioningTasks.value.add(task.task_key)
  try {
    const updated = await api.transitionTaskState(task.task_key, targetState)
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
  finally { transitioningTasks.value.delete(task.task_key) }
}

function scopeTask(task: Task) { transitionTask(task, 'scoped') }
function readyTask(task: Task) { transitionTask(task, 'ready') }
function startTask(task: Task) { transitionTask(task, 'in_progress') }

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
    await api.callMcpTool('hivemind-reassign_epic_owner', {
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

// ── Epic Run Operator View ──────────────────────────────────────────────────
const showEpicRunModal = ref(false)
const epicRunEpic = ref<Epic | null>(null)
const epicRunSubmitting = ref(false)
const epicRunResult = ref<EpicStartResponse | null>(null)
const selectedEpicRunId = ref<string | null>(null)
const epicRunMaxParallelWorkers = ref(2)
const epicRunExecutionMode = ref<'local' | 'ide' | 'github_actions' | 'byoai' | ''>('byoai')
const epicRunRespectFileClaims = ref(true)
const epicRunAutoResume = ref(true)

async function openEpicRunModal(epic: Epic) {
  epicRunEpic.value = epic
  epicRunResult.value = null
  selectedEpicRunId.value = latestEpicRun(epic.epic_key)?.id ?? null
  showEpicRunModal.value = true
  await refreshEpicRunData(epic.epic_key)
  selectedEpicRunId.value = latestEpicRun(epic.epic_key)?.id ?? selectedEpicRunId.value
}

async function runEpicStart(dryRun: boolean) {
  if (!epicRunEpic.value) return
  epicRunSubmitting.value = true
  epicsError.value = null
  try {
    const response = await api.startEpic(epicRunEpic.value.epic_key, {
      dry_run: dryRun,
      max_parallel_workers: epicRunMaxParallelWorkers.value,
      execution_mode_preference: epicRunExecutionMode.value || undefined,
      respect_file_claims: epicRunRespectFileClaims.value,
      auto_resume_on_qa_failed: epicRunAutoResume.value,
    })
    epicRunResult.value = response
    selectedEpicRunId.value = response.run_id
    await loadEpics()
    await refreshEpicTasks(epicRunEpic.value.epic_key)
    await refreshEpicRunData(epicRunEpic.value.epic_key)
  } catch (e: unknown) {
    epicsError.value = e instanceof Error ? e.message : String(e)
  } finally {
    epicRunSubmitting.value = false
  }
}

const selectedEpicRun = computed(() => {
  const runId = selectedEpicRunId.value
  if (!runId || !epicRunEpic.value) return null
  return epicRunsByEpic.value[epicRunEpic.value.epic_key]?.find(run => run.id === runId) ?? null
})

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
            <button
              v-if="epic.state === 'scoped' || epic.state === 'in_progress'"
              class="btn-epic-run"
              @click.stop="openEpicRunModal(epic)"
            >
              {{ epic.state === 'scoped' ? 'Epic Start' : 'Run Monitor' }}
            </button>
            <span class="expand-icon">{{ expandedEpics.has(epic.epic_key) ? '▲' : '▼' }}</span>
          </div>
        </div>

        <!-- Task list (expanded) -->
        <div v-if="expandedEpics.has(epic.epic_key)" class="task-list">
          <div class="epic-run-strip">
            <div class="epic-run-strip__header">
              <span class="epic-run-strip__label">Epic Run</span>
              <button class="btn-inline" @click.stop="refreshEpicRunData(epic.epic_key)">Aktualisieren</button>
            </div>
            <div v-if="epicRunsLoading[epic.epic_key]" class="epic-run-strip__empty">Lade Run-Daten…</div>
            <div v-else-if="epicRunsError[epic.epic_key]" class="epic-run-strip__empty epic-run-strip__empty--error">
              {{ epicRunsError[epic.epic_key] }}
            </div>
            <div v-else-if="latestEpicRun(epic.epic_key)" class="epic-run-strip__summary">
              <span class="badge badge--sm" :class="`badge--run-${latestEpicRun(epic.epic_key)?.status}`">
                {{ latestEpicRun(epic.epic_key)?.status }}
              </span>
              <span class="epic-run-chip">{{ latestEpicRun(epic.epic_key)?.dry_run ? 'Dry-Run' : 'Live' }}</span>
              <span class="epic-run-chip">
                Slots {{ runSlotPlan(latestEpicRun(epic.epic_key)).occupied_slots ?? 0 }}/{{ runSlotPlan(latestEpicRun(epic.epic_key)).max_parallel_workers ?? 0 }}
              </span>
              <span class="epic-run-chip">Queued {{ (runSlotPlan(latestEpicRun(epic.epic_key)).queued_runnable ?? []).length }}</span>
              <span class="epic-run-chip">Konflikte {{ runSummaryCount(latestEpicRun(epic.epic_key), 'conflicting') }}</span>
              <span class="epic-run-chip">Blocked {{ runSummaryCount(latestEpicRun(epic.epic_key), 'blocked') }}</span>
              <span class="epic-run-chip">Artefakte {{ runArtifacts(latestEpicRun(epic.epic_key)?.id).length }}</span>
              <span class="epic-run-timestamp">{{ formatRunTimestamp(latestEpicRun(epic.epic_key)?.started_at) }}</span>
            </div>
            <div v-else class="epic-run-strip__empty">Noch kein Epic-Run gestartet.</div>
          </div>
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
                  v-else-if="task.state === 'incoming'"
                  class="btn-scope"
                  :disabled="transitioningTasks.has(task.task_key)"
                  @click.stop="scopeTask(task)"
                >
                  {{ transitioningTasks.has(task.task_key) ? '...' : 'SCOPE →' }}
                </button>
                <button
                  v-else-if="task.state === 'scoped'"
                  class="btn-ready"
                  :disabled="transitioningTasks.has(task.task_key)"
                  @click.stop="readyTask(task)"
                >
                  {{ transitioningTasks.has(task.task_key) ? '...' : 'READY →' }}
                </button>
                <button
                  v-else-if="task.state === 'ready'"
                  class="btn-start"
                  :disabled="transitioningTasks.has(task.task_key)"
                  @click.stop="startTask(task)"
                >
                  {{ transitioningTasks.has(task.task_key) ? '...' : 'START →' }}
                </button>
                <button
                  v-if="['incoming','in_progress','scoped','ready','qa_failed','in_review'].includes(task.state)"
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

    <!-- Epic Run Modal -->
    <HivemindModal v-model:model-value="showEpicRunModal" title="Epic Run Control" size="lg">
      <div v-if="epicRunEpic" class="epic-run-modal">
        <div class="epic-run-modal__hero">
          <div>
            <div class="epic-run-modal__key">{{ epicRunEpic.epic_key }}</div>
            <h3 class="epic-run-modal__title">{{ epicRunEpic.title }}</h3>
          </div>
          <span class="badge" :class="EPIC_STATE_CLASS[epicRunEpic.state] ?? 'badge--muted'">{{ epicRunEpic.state }}</span>
        </div>

        <div class="epic-run-form">
          <label class="form-label">
            Max Parallel Workers
            <input v-model.number="epicRunMaxParallelWorkers" type="number" min="1" max="32" class="form-input" />
          </label>
          <label class="form-label">
            Execution Mode
            <select v-model="epicRunExecutionMode" class="form-select">
              <option value="">Default</option>
              <option value="byoai">BYOAI</option>
              <option value="local">Local</option>
              <option value="ide">IDE</option>
              <option value="github_actions">GitHub Actions</option>
            </select>
          </label>
          <label class="run-toggle">
            <input v-model="epicRunRespectFileClaims" type="checkbox" />
            <span>Datei-Claims respektieren</span>
          </label>
          <label class="run-toggle">
            <input v-model="epicRunAutoResume" type="checkbox" />
            <span>QA-Resume automatisch ziehen</span>
          </label>
        </div>

        <div class="epic-run-actions">
          <button class="btn-close-modal" :disabled="epicRunSubmitting" @click="runEpicStart(true)">
            {{ epicRunSubmitting ? 'Läuft…' : 'Dry-Run analysieren' }}
          </button>
          <button class="btn-create-task" :disabled="epicRunSubmitting" @click="runEpicStart(false)">
            {{ epicRunSubmitting ? 'Starte…' : 'Run starten' }}
          </button>
        </div>

        <div v-if="epicRunResult" class="epic-run-result">
          <div class="epic-run-result__header">
            <span class="badge" :class="`badge--run-${epicRunResult.status}`">{{ epicRunResult.status }}</span>
            <span class="epic-run-chip">{{ epicRunResult.dry_run ? 'Dry-Run' : 'Live-Run' }}</span>
            <span class="epic-run-chip">Startbar: {{ epicRunResult.startable ? 'ja' : 'nein' }}</span>
          </div>
          <div v-if="epicRunResult.blockers.length" class="epic-run-blockers">
            <div v-for="blocker in epicRunResult.blockers" :key="blocker.code" class="epic-run-blocker">
              <strong>{{ blocker.code }}</strong>
              <span>{{ blocker.message }}</span>
            </div>
          </div>
        </div>

        <div v-if="epicRunsByEpic[epicRunEpic.epic_key]?.length" class="epic-run-history">
          <div class="epic-run-history__header">
            <h4>Run-Historie</h4>
            <button class="btn-inline" @click="refreshEpicRunData(epicRunEpic.epic_key)">Refresh</button>
          </div>
          <div class="epic-run-history__list">
            <button
              v-for="run in epicRunsByEpic[epicRunEpic.epic_key]"
              :key="run.id"
              class="epic-run-history__item"
              :class="{ 'epic-run-history__item--active': selectedEpicRunId === run.id }"
              @click="selectedEpicRunId = run.id; loadEpicRunArtifacts(run.id)"
            >
              <span class="badge badge--sm" :class="`badge--run-${run.status}`">{{ run.status }}</span>
              <span>{{ run.dry_run ? 'Dry' : 'Live' }}</span>
              <span>{{ formatRunTimestamp(run.started_at) }}</span>
            </button>
          </div>
        </div>

        <div v-if="selectedEpicRun" class="epic-run-analysis">
          <div class="epic-run-grid">
            <div class="epic-run-panel">
              <h4>Worker Slots</h4>
              <div class="epic-run-statline">
                <span>Belegt {{ runSlotPlan(selectedEpicRun).occupied_slots ?? 0 }}</span>
                <span>Frei {{ runSlotPlan(selectedEpicRun).available_slots_now ?? 0 }}</span>
                <span>Max {{ runSlotPlan(selectedEpicRun).max_parallel_workers ?? 0 }}</span>
              </div>
              <div class="epic-run-statline">
                <span>Dispatch now: {{ (runSlotPlan(selectedEpicRun).dispatch_now ?? []).join(', ') || '–' }}</span>
              </div>
              <div class="epic-run-statline">
                <span>Queued: {{ (runSlotPlan(selectedEpicRun).queued_runnable ?? []).join(', ') || '–' }}</span>
              </div>
            </div>

            <div class="epic-run-panel">
              <h4>Scheduler</h4>
              <div class="epic-run-statline">
                <span>Effektiv {{ runScheduler(selectedEpicRun).effective_max_parallel_workers ?? '–' }}</span>
                <span>Resumes {{ (runScheduler(selectedEpicRun).resumed_task_keys ?? []).length }}</span>
                <span>Dispatches {{ (runScheduler(selectedEpicRun).dispatched_task_keys ?? []).length }}</span>
              </div>
              <div class="epic-run-statline">
                <span>Auto-Resume: {{ runScheduler(selectedEpicRun).auto_resume_on_qa_failed ? 'aktiv' : 'aus' }}</span>
              </div>
            </div>
          </div>

          <div class="epic-run-grid epic-run-grid--lists">
            <div class="epic-run-panel">
              <h4>Runnable / Waiting</h4>
              <div class="epic-run-list">
                <div v-for="item in runItems(selectedEpicRun, 'runnable')" :key="`r-${item.task_key}`" class="epic-run-list__item">
                  <strong>{{ item.task_key }}</strong>
                  <span>bereit</span>
                </div>
                <div v-for="item in runItems(selectedEpicRun, 'waiting')" :key="`w-${item.task_key}`" class="epic-run-list__item">
                  <strong>{{ item.task_key }}</strong>
                  <span>{{ formatReason(item) }}</span>
                </div>
              </div>
            </div>

            <div class="epic-run-panel">
              <h4>Blocked / Konflikte</h4>
              <div class="epic-run-list">
                <div v-for="item in runItems(selectedEpicRun, 'blocked')" :key="`b-${item.task_key}`" class="epic-run-list__item">
                  <strong>{{ item.task_key }}</strong>
                  <span>{{ formatReason(item) }}</span>
                </div>
                <div v-for="item in runItems(selectedEpicRun, 'conflicting')" :key="`c-${item.task_key}`" class="epic-run-list__item">
                  <strong>{{ item.task_key }}</strong>
                  <span>{{ formatReason(item) }}</span>
                </div>
              </div>
            </div>
          </div>

          <div class="epic-run-panel">
            <div class="epic-run-history__header">
              <h4>Artefakte / Folgepfade</h4>
              <span class="epic-run-chip">Kinds: {{ runArtifactKinds(selectedEpicRun.id).join(', ') || '–' }}</span>
            </div>
            <div v-if="epicRunArtifactsLoading[selectedEpicRun.id]" class="epic-run-strip__empty">Lade Artefakte…</div>
            <div v-else class="epic-run-list">
              <div v-for="artifact in runArtifacts(selectedEpicRun.id)" :key="artifact.id" class="epic-run-list__item">
                <strong>{{ artifact.artifact_type }}</strong>
                <span>{{ artifact.task_key || artifact.title }}</span>
                <span>{{ artifactSummary(artifact) }}</span>
              </div>
              <div v-if="!runArtifacts(selectedEpicRun.id).length" class="epic-run-strip__empty">Keine Artefakte für diesen Run.</div>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <button class="btn-close-modal" @click="showEpicRunModal = false">Schließen</button>
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
  padding: var(--space-0-5) var(--space-2);
  border-radius: var(--radius-xs);
  white-space: nowrap;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.badge--sm { font-size: var(--font-size-2xs); padding: 1px var(--space-1); }
.badge--pending  { background: color-mix(in srgb, var(--color-warning) 15%, transparent); color: var(--color-warning); }
.badge--info     { background: color-mix(in srgb, var(--color-accent) 15%, transparent); color: var(--color-accent); }
.badge--active   { background: color-mix(in srgb, var(--color-accent) 25%, transparent); color: var(--color-accent); border: 1px solid var(--color-accent); }
.badge--review   { background: color-mix(in srgb, var(--color-warning) 25%, transparent); color: var(--color-warning); border: 1px solid var(--color-warning); }
.badge--done     { background: color-mix(in srgb, var(--color-success) 15%, transparent); color: var(--color-success); }
.badge--danger   { background: color-mix(in srgb, var(--color-danger) 15%, transparent); color: var(--color-danger); }
.badge--muted    { background: var(--color-surface-alt); color: var(--color-text-muted); }
.badge--run-dry_run,
.badge--run-waiting { background: color-mix(in srgb, var(--color-warning) 18%, transparent); color: var(--color-warning); }
.badge--run-started,
.badge--run-running { background: color-mix(in srgb, var(--color-accent) 18%, transparent); color: var(--color-accent); }
.badge--run-completed { background: color-mix(in srgb, var(--color-success) 18%, transparent); color: var(--color-success); }
.badge--run-blocked { background: color-mix(in srgb, var(--color-danger) 18%, transparent); color: var(--color-danger); }

/* ── Buttons ─────────────────────────────────────────────────────────────── */
.btn-scope {
  background: color-mix(in srgb, var(--color-warning) 15%, transparent);
  color: var(--color-warning);
  border: 1px solid var(--color-warning);
  border-radius: var(--radius-sm);
  font-family: var(--font-heading);
  font-size: var(--font-size-xs);
  padding: var(--space-0-5) var(--space-2);
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
  font-size: var(--font-size-2xs);
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
  font-size: var(--font-size-2xs);
  padding: 1px var(--space-2);
  cursor: pointer;
  letter-spacing: 0.06em;
  transition: background var(--transition-duration) ease;
}
.btn-reenter:hover:not(:disabled) { background: color-mix(in srgb, var(--color-danger) 28%, transparent); }
.btn-reenter:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-prompt {
  background: none;
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-family: var(--font-heading);
  font-size: var(--font-size-2xs);
  padding: 1px var(--space-2);
  cursor: pointer;
  letter-spacing: 0.06em;
  transition: background var(--transition-duration) ease, color var(--transition-duration) ease;
}
.btn-prompt:hover { background: var(--color-accent-10); color: var(--color-accent); }
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
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  font-style: italic;
}

.task-prompt-text {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
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
  font-size: var(--font-size-2xs);
  padding: 1px var(--space-2);
  cursor: pointer;
  letter-spacing: 0.06em;
  transition: background var(--transition-duration) ease;
}
.btn-start:hover:not(:disabled) { background: var(--color-accent-10); }
.btn-start:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-scope {
  background: none;
  color: var(--color-info, #6cb4ee);
  border: 1px solid var(--color-info, #6cb4ee);
  border-radius: var(--radius-sm);
  font-family: var(--font-heading);
  font-size: var(--font-size-2xs);
  padding: 1px var(--space-2);
  cursor: pointer;
  letter-spacing: 0.06em;
  transition: background var(--transition-duration) ease;
}
.btn-scope:hover:not(:disabled) { background: var(--color-info-10); }
.btn-scope:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-ready {
  background: none;
  color: var(--color-success, #66bb6a);
  border: 1px solid var(--color-success, #66bb6a);
  border-radius: var(--radius-sm);
  font-family: var(--font-heading);
  font-size: var(--font-size-2xs);
  padding: 1px var(--space-2);
  cursor: pointer;
  letter-spacing: 0.06em;
  transition: background var(--transition-duration) ease;
}
.btn-ready:hover:not(:disabled) { background: var(--color-success-10); }
.btn-ready:disabled { opacity: 0.5; cursor: not-allowed; }

/* ── Review overlay ─────────────────────────────────────────────────────── */
.review-overlay {
  position: fixed;
  inset: 0;
  background: var(--color-overlay);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-toast);
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
  font-size: var(--font-size-2xs);
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
  padding: var(--space-0-5) var(--space-2);
  cursor: pointer;
  letter-spacing: 0.04em;
  transition: background var(--transition-duration) ease;
}
.btn-architekt:hover { background: color-mix(in srgb, var(--color-accent) 30%, transparent); }
.btn-architekt:disabled { opacity: 0.5; cursor: wait; }

.btn-epic-run {
  background: color-mix(in srgb, var(--color-success) 12%, transparent);
  color: var(--color-success);
  border: 1px solid color-mix(in srgb, var(--color-success) 35%, transparent);
  border-radius: var(--radius-sm);
  font-family: var(--font-heading);
  font-size: var(--font-size-xs);
  padding: var(--space-0-5) var(--space-2);
  cursor: pointer;
  letter-spacing: 0.04em;
}
.btn-epic-run:hover { background: color-mix(in srgb, var(--color-success) 24%, transparent); }

.epic-run-strip {
  padding: var(--space-3) var(--space-5);
  border-bottom: 1px solid var(--color-border);
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--color-accent) 8%, transparent), transparent 45%),
    linear-gradient(180deg, color-mix(in srgb, var(--color-success) 6%, transparent), transparent 90%);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.epic-run-strip__header,
.epic-run-history__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.epic-run-strip__label {
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.epic-run-strip__summary,
.epic-run-statline {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
}

.epic-run-strip__empty {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.epic-run-strip__empty--error {
  color: var(--color-danger);
}

.epic-run-chip {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  padding: var(--space-0-5) var(--space-2-5);
  font-size: var(--font-size-2xs);
  font-family: var(--font-mono);
  color: var(--color-text-muted);
  background: color-mix(in srgb, var(--color-surface-alt) 85%, transparent);
}

.epic-run-timestamp {
  margin-left: auto;
  font-size: var(--font-size-2xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.epic-run-modal {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.epic-run-modal__hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
}

.epic-run-modal__key {
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.epic-run-modal__title {
  margin: var(--space-1) 0 0;
  font-family: var(--font-heading);
}

.epic-run-form,
.epic-run-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
}

.epic-run-grid--lists {
  align-items: start;
}

.run-toggle {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-alt);
  color: var(--color-text);
}

.epic-run-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
}

.epic-run-result,
.epic-run-panel {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface-alt);
  padding: var(--space-4);
}

.epic-run-result__header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}

.epic-run-blockers,
.epic-run-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.epic-run-blocker,
.epic-run-list__item {
  display: grid;
  grid-template-columns: minmax(90px, 130px) minmax(80px, 140px) minmax(0, 1fr);
  gap: var(--space-2);
  align-items: start;
  font-size: var(--font-size-sm);
}

.epic-run-history {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.epic-run-history__list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.epic-run-history__item {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-full);
  border: 1px solid var(--color-border);
  background: var(--color-bg);
  color: var(--color-text);
  cursor: pointer;
  font-size: var(--font-size-2xs);
  font-family: var(--font-mono);
}

.epic-run-history__item--active {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

@media (max-width: 820px) {
  .epic-run-form,
  .epic-run-grid {
    grid-template-columns: 1fr;
  }

  .epic-run-timestamp {
    margin-left: 0;
  }

  .epic-run-actions {
    flex-direction: column;
  }
}

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
  border-radius: var(--radius-full);
  padding: var(--space-0-5) var(--space-2-5);
}
.btn-copy {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-1) var(--space-3);
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
  border-radius: var(--radius-md);
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
  border-radius: var(--radius-sm);
  color: var(--color-text);
  padding: var(--space-2);
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
}

.form-textarea { resize: vertical; }

.btn-close-modal {
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  padding: var(--space-2) var(--space-4);
  cursor: pointer;
  font-size: var(--font-size-sm);
}

.btn-create-task {
  background: var(--color-accent);
  color: var(--color-bg);
  border: none;
  border-radius: var(--radius-sm);
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
  border-radius: var(--radius-lg);
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
  border-radius: var(--radius-md);
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
  gap: var(--space-0-5);
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
  font-size: var(--font-size-2xs);
  font-family: var(--font-mono);
  padding: 1px var(--space-1-5);
  border-radius: var(--radius-xs);
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
  font-size: var(--font-size-2xs);
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
  border-radius: var(--radius-xs);
  color: var(--color-text);
  padding: var(--space-0-5) var(--space-1-5);
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  width: 200px;
}

.btn-inline {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
  padding: var(--space-0-5) var(--space-1);
  border-radius: var(--space-0-5);
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
