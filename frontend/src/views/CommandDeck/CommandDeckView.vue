<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { api } from '../../api'
import type { Epic, Task, PeerNode } from '../../api/types'
import EpicScopingModal from '../../components/domain/EpicScopingModal.vue'
import TaskReviewPanel from '../../components/domain/TaskReviewPanel.vue'
import SlaCountdown from '../../components/ui/SlaCountdown.vue'
import { useProjectStore } from '../../stores/projectStore'

const store = useProjectStore()

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
          <div
            v-for="task in tasksByEpic[epic.epic_key]"
            :key="task.task_key"
            class="task-row"
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
                @click="openReview(task)"
              >
                REVIEW
              </button>
              <button
                v-else-if="task.state === 'scoped' || task.state === 'ready'"
                class="btn-start"
                @click="startTask(task)"
              >
                START →
              </button>
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
</style>
