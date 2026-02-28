<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useTriageStore } from '../../stores/triageStore'
import HivemindCard from '../../components/ui/HivemindCard.vue'
import HivemindModal from '../../components/ui/HivemindModal.vue'
import { api } from '../../api'
import type { Epic } from '../../api/types'

const store = useTriageStore()

// SSE connection
let eventSource: EventSource | null = null

// Epic selection for routing
const showRouteModal = ref(false)
const routeTargetId = ref<string | null>(null)
const selectedEpicId = ref('')
const availableEpics = ref<Epic[]>([])
const routeLoading = ref(false)

// Ignore dialog
const showIgnoreModal = ref(false)
const ignoreTargetId = ref<string | null>(null)
const ignoreReason = ref('')
const ignoreLoading = ref(false)

// Pagination
const page = ref(1)
const pageSize = 20
const paginatedItems = computed(() => {
  const start = 0
  const end = page.value * pageSize
  return store.filteredItems.slice(start, end)
})
const hasMore = computed(() => paginatedItems.value.length < store.filteredItems.length)

const tabs = [
  { key: 'unrouted' as const, label: 'Unrouted' },
  { key: 'routed' as const, label: 'Routed' },
  { key: 'ignored' as const, label: 'Ignored' },
  { key: 'all' as const, label: 'All' },
]

function getSourceIcon(system: string) {
  switch (system) {
    case 'youtrack': return '🔷'
    case 'sentry': return '🔴'
    case 'federation': return '🟣'
    default: return '⚪'
  }
}

function getSourceClass(system: string) {
  switch (system) {
    case 'youtrack': return 'badge-youtrack'
    case 'sentry': return 'badge-sentry'
    case 'federation': return 'badge-federation'
    default: return 'badge-default'
  }
}

function getSummary(item: { payload: Record<string, unknown> }) {
  const p = item.payload
  return (p.summary as string) || (p.title as string) || (p.external_id as string) || '(no summary)'
}

function formatTime(iso: string) {
  const d = new Date(iso)
  return d.toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' })
}

async function openRouteModal(eventId: string) {
  routeTargetId.value = eventId
  try {
    const projects = await api.getProjects()
    if (projects.length > 0) {
      const epics = await api.getEpics(projects[0].id)
      availableEpics.value = epics
    }
  } catch { /* ignore */ }
  showRouteModal.value = true
}

async function confirmRoute() {
  if (!routeTargetId.value || !selectedEpicId.value) return
  routeLoading.value = true
  try {
    await store.routeEvent(routeTargetId.value, selectedEpicId.value)
    showRouteModal.value = false
    routeTargetId.value = null
    selectedEpicId.value = ''
  } finally {
    routeLoading.value = false
  }
}

function openIgnoreModal(eventId: string) {
  ignoreTargetId.value = eventId
  ignoreReason.value = ''
  showIgnoreModal.value = true
}

async function confirmIgnore() {
  if (!ignoreTargetId.value) return
  ignoreLoading.value = true
  try {
    await store.ignoreEvent(ignoreTargetId.value, ignoreReason.value || undefined)
    showIgnoreModal.value = false
    ignoreTargetId.value = null
  } finally {
    ignoreLoading.value = false
  }
}

function connectSSE() {
  const baseUrl = (import.meta.env.VITE_API_URL as string) ?? 'http://localhost:8000'
  eventSource = new EventSource(`${baseUrl}/api/events/triage`)
  eventSource.addEventListener('triage_routed', () => store.loadItems())
  eventSource.addEventListener('triage_ignored', () => store.loadItems())
  eventSource.addEventListener('new_event', (e) => {
    try {
      const data = JSON.parse(e.data)
      store.addItem(data)
    } catch { /* ignore */ }
  })
}

onMounted(() => {
  store.loadItems()
  connectSSE()
})

onUnmounted(() => {
  eventSource?.close()
})
</script>

<template>
  <div class="triage-station">
    <header class="triage-header">
      <h1>Triage Station</h1>
      <span class="triage-count">{{ store.filteredItems.length }} items</span>
    </header>

    <!-- Filter Tabs -->
    <nav class="triage-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        :class="['tab-btn', { active: store.filter === tab.key }]"
        @click="store.filter = tab.key; page = 1"
      >
        {{ tab.label }}
      </button>
    </nav>

    <!-- Loading -->
    <div v-if="store.loading" class="triage-loading">Loading...</div>
    <div v-else-if="store.error" class="triage-error">{{ store.error }}</div>

    <!-- Item list -->
    <div v-else class="triage-list">
      <HivemindCard
        v-for="item in paginatedItems"
        :key="item.id"
        class="triage-item"
      >
        <div class="item-row">
          <span :class="['source-badge', getSourceClass(item.system)]">
            {{ getSourceIcon(item.system) }} {{ item.system }}
          </span>
          <span class="item-summary">{{ getSummary(item) }}</span>
          <span class="item-entity">{{ item.entity_type }}</span>
          <span class="item-time">{{ formatTime(item.created_at) }}</span>
          <span :class="['routing-badge', `state-${item.routing_state}`]">
            {{ item.routing_state }}
          </span>
          <div class="item-actions" v-if="item.routing_state === 'unrouted'">
            <button class="btn btn-route" @click="openRouteModal(item.id)">Zuordnen</button>
            <button class="btn btn-ignore" @click="openIgnoreModal(item.id)">Ignorieren</button>
          </div>
        </div>
        <div class="item-payload">
          <code>{{ JSON.stringify(item.payload, null, 2).slice(0, 200) }}</code>
        </div>
      </HivemindCard>

      <div v-if="paginatedItems.length === 0" class="triage-empty">
        No items in this filter.
      </div>

      <button v-if="hasMore" class="btn btn-load-more" @click="page++">
        Load more
      </button>
    </div>

    <!-- Route Modal -->
    <HivemindModal v-model="showRouteModal" title="Event zuordnen">
      <div class="modal-body">
        <label class="field-label">Epic auswählen</label>
        <select v-model="selectedEpicId" class="field-select">
          <option value="" disabled>— Epic wählen —</option>
          <option v-for="epic in availableEpics" :key="epic.id" :value="epic.epic_key">
            {{ epic.epic_key }} — {{ epic.title }}
          </option>
        </select>
      </div>
      <template #footer>
        <button class="btn" @click="showRouteModal = false">Abbrechen</button>
        <button class="btn btn-primary" :disabled="!selectedEpicId || routeLoading" @click="confirmRoute">
          {{ routeLoading ? 'Routing...' : 'Zuordnen' }}
        </button>
      </template>
    </HivemindModal>

    <!-- Ignore Modal -->
    <HivemindModal v-model="showIgnoreModal" title="Event ignorieren">
      <div class="modal-body">
        <label class="field-label">Grund (optional)</label>
        <textarea v-model="ignoreReason" class="field-textarea" rows="3" placeholder="Grund angeben..."></textarea>
      </div>
      <template #footer>
        <button class="btn" @click="showIgnoreModal = false">Abbrechen</button>
        <button class="btn btn-danger" :disabled="ignoreLoading" @click="confirmIgnore">
          {{ ignoreLoading ? 'Ignoring...' : 'Ignorieren' }}
        </button>
      </template>
    </HivemindModal>
  </div>
</template>

<style scoped>
.triage-station {
  padding: var(--space-6, 1.5rem);
  max-width: 1200px;
  margin: 0 auto;
}

.triage-header {
  display: flex;
  align-items: center;
  gap: var(--space-4, 1rem);
  margin-bottom: var(--space-4, 1rem);
}

.triage-header h1 {
  font-size: 1.5rem;
  color: var(--color-text);
  margin: 0;
}

.triage-count {
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

.triage-tabs {
  display: flex;
  gap: var(--space-2, 0.5rem);
  margin-bottom: var(--space-4, 1rem);
  border-bottom: 1px solid var(--color-border);
  padding-bottom: var(--space-2, 0.5rem);
}

.tab-btn {
  background: none;
  border: none;
  color: var(--color-text-muted);
  padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
  cursor: pointer;
  border-radius: 4px;
  font-size: 0.875rem;
  transition: all 150ms;
}

.tab-btn:hover {
  color: var(--color-text);
  background: var(--color-surface-alt);
}

.tab-btn.active {
  color: var(--color-accent);
  background: var(--color-surface-alt);
  font-weight: 600;
}

.triage-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3, 0.75rem);
}

.triage-item {
  padding: var(--space-3, 0.75rem);
}

.item-row {
  display: flex;
  align-items: center;
  gap: var(--space-3, 0.75rem);
  flex-wrap: wrap;
}

.source-badge {
  font-size: 0.75rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
  white-space: nowrap;
}

.badge-youtrack { background: rgba(59, 130, 246, 0.2); color: #60a5fa; }
.badge-sentry { background: rgba(239, 68, 68, 0.2); color: #f87171; }
.badge-federation { background: rgba(168, 85, 247, 0.2); color: #c084fc; }
.badge-default { background: var(--color-surface-alt); color: var(--color-text-muted); }

.item-summary {
  flex: 1;
  color: var(--color-text);
  font-weight: 500;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-entity {
  color: var(--color-text-muted);
  font-size: 0.75rem;
}

.item-time {
  color: var(--color-text-muted);
  font-size: 0.75rem;
  white-space: nowrap;
}

.routing-badge {
  font-size: 0.7rem;
  padding: 2px 6px;
  border-radius: 3px;
  font-weight: 600;
  text-transform: uppercase;
}

.state-unrouted { background: rgba(255, 176, 32, 0.2); color: var(--color-warning); }
.state-routed { background: rgba(60, 255, 154, 0.2); color: var(--color-success); }
.state-ignored { background: var(--color-surface-alt); color: var(--color-text-muted); }
.state-escalated { background: rgba(255, 77, 109, 0.2); color: var(--color-danger); }

.item-actions {
  display: flex;
  gap: var(--space-2, 0.5rem);
}

.item-payload {
  margin-top: var(--space-2, 0.5rem);
  padding: var(--space-2, 0.5rem);
  background: var(--color-bg);
  border-radius: 4px;
  overflow: hidden;
}

.item-payload code {
  font-size: 0.7rem;
  color: var(--color-text-muted);
  white-space: pre-wrap;
  word-break: break-all;
}

.btn {
  padding: 6px 12px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
  font-size: 0.8rem;
  transition: all 150ms;
}

.btn:hover { background: var(--color-surface-alt); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-route { border-color: var(--color-accent); color: var(--color-accent); }
.btn-ignore { border-color: var(--color-text-muted); color: var(--color-text-muted); }
.btn-primary { background: var(--color-accent); color: var(--color-bg); border-color: var(--color-accent); }
.btn-danger { background: var(--color-danger); color: white; border-color: var(--color-danger); }
.btn-load-more { width: 100%; padding: 10px; text-align: center; }

.triage-loading, .triage-empty, .triage-error {
  text-align: center;
  padding: var(--space-6, 1.5rem);
  color: var(--color-text-muted);
}

.triage-error { color: var(--color-danger); }

.modal-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3, 0.75rem);
}

.field-label {
  color: var(--color-text);
  font-size: 0.875rem;
  font-weight: 500;
}

.field-select, .field-textarea {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: var(--color-text);
  padding: 8px;
  font-size: 0.875rem;
  width: 100%;
}

.field-textarea {
  resize: vertical;
  font-family: inherit;
}

@media (max-width: 768px) {
  .item-row {
    flex-direction: column;
    align-items: flex-start;
  }
  .item-actions {
    width: 100%;
  }
  .item-actions .btn {
    flex: 1;
  }
}
</style>
