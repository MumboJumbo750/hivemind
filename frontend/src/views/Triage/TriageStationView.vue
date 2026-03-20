<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useTriageStore } from '../../stores/triageStore'
import HivemindCard from '../../components/ui/HivemindCard.vue'
import HivemindModal from '../../components/ui/HivemindModal.vue'
import SlaCountdown from '../../components/ui/SlaCountdown.vue'
import DecisionRequestDialog from '../../components/domain/DecisionRequestDialog.vue'
import { api } from '../../api'
import type { Epic, EpicProposal, Task, DecisionRequest } from '../../api/types'
import { useAuthStore } from '../../stores/authStore'
import DeadLetterList from '../../components/domain/DeadLetterList.vue'

const store = useTriageStore()
const authStore = useAuthStore()
const isTriageAdmin = computed(() => authStore.user?.role === 'admin')

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
  { key: 'escalated' as const, label: 'Escalated' },
  { key: 'decisions' as const, label: 'Decisions' },
  { key: 'proposals' as const, label: 'Epic Proposals' },
  { key: 'dlq' as const, label: 'Dead Letters' },
  { key: 'all' as const, label: 'All' },
]

const activeTriageTab = ref<string>('unrouted')

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

function getProjectLabel(item: { payload: Record<string, unknown>; project_id?: string | null }) {
  const ctx = item.payload.project_context as Record<string, unknown> | undefined
  return (ctx?.project_slug as string) || item.project_id || 'unmatched'
}

function getRoutingReason(item: { routing_detail?: Record<string, unknown> | null }) {
  const reason = (item.routing_detail?.reason as string) || ''
  const dispatchStatus = (item.routing_detail?.dispatch_status as string) || ''
  const dispatchMode = (item.routing_detail?.dispatch_mode as string) || ''
  const suffix = dispatchStatus ? ` · Dispatch: ${dispatchStatus}${dispatchMode ? ` (${dispatchMode})` : ''}` : ''
  return `${reason}${suffix}`.trim()
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

// ── Epic Proposals (TASK-4-010) ──────────────────────────────────────────────
const proposals = ref<EpicProposal[]>([])
const proposalsLoading = ref(false)
const proposalsError = ref<string | null>(null)
const proposalCount = ref(0)

// Proposal detail
const selectedProposal = ref<EpicProposal | null>(null)
const showProposalDetail = ref(false)

// Reject modal
const showProposalRejectModal = ref(false)
const proposalRejectReason = ref('')
const proposalRejectLoading = ref(false)
const proposalAcceptLoading = ref(false)

// ── Escalated Tasks (TASK-6-011) ─────────────────────────────────────────────
const escalatedTasks = ref<Task[]>([])
const escalatedLoading = ref(false)
const escalatedError = ref<string | null>(null)
const resolveLoading = ref<string | null>(null) // task_key being resolved

async function loadEscalatedTasks() {
  escalatedLoading.value = true
  escalatedError.value = null
  try {
    const result = await api.callMcpTool('hivemind-list_tasks', { state: 'escalated' })
    const text = result[0]?.text
    if (text) {
      const parsed = JSON.parse(text)
      escalatedTasks.value = Array.isArray(parsed.data) ? parsed.data : (Array.isArray(parsed) ? parsed : [])
    }
  } catch (e: unknown) {
    escalatedError.value = (e as Error).message
  } finally {
    escalatedLoading.value = false
  }
}

async function resolveEscalation(task: Task) {
  if (!confirm(`Task "${task.task_key}" de-eskalieren?`)) return
  resolveLoading.value = task.task_key
  try {
    await api.callMcpTool('hivemind-resolve_escalation', { task_key: task.task_key })
    await loadEscalatedTasks()
  } catch (e: unknown) {
    escalatedError.value = (e as Error).message
  } finally {
    resolveLoading.value = null
  }
}

// ── Decision Requests (TASK-6-011) ───────────────────────────────────────────
const decisionRequests = ref<DecisionRequest[]>([])
const decisionsLoading = ref(false)
const decisionsError = ref<string | null>(null)
const selectedDecisionRequest = ref<DecisionRequest | null>(null)
const showDecisionDialog = ref(false)
const dlqCount = ref(0)

async function loadDecisionRequests() {
  decisionsLoading.value = true
  decisionsError.value = null
  try {
    const result = await api.callMcpTool('hivemind-list_decision_requests', { state: 'open' })
    const text = result[0]?.text
    if (text) {
      const parsed = JSON.parse(text)
      decisionRequests.value = Array.isArray(parsed.data) ? parsed.data : (Array.isArray(parsed) ? parsed : [])
    }
  } catch (e: unknown) {
    decisionsError.value = (e as Error).message
  } finally {
    decisionsLoading.value = false
  }
}

function openDecisionDialog(dr: DecisionRequest) {
  selectedDecisionRequest.value = dr
  showDecisionDialog.value = true
}

async function onDecisionResolved() {
  showDecisionDialog.value = false
  selectedDecisionRequest.value = null
  await loadDecisionRequests()
}

async function loadDlqCount() {
  try {
    const res = await api.getDeadLetters({ limit: 1 })
    dlqCount.value = res.total
  } catch {
    // Keep previous badge value if count fetch fails.
  }
}

function onDlqCountUpdated(value: number) {
  dlqCount.value = value
}

// Helper to check if any dependency is rejected
function getDependencyWarnings(proposal: EpicProposal): EpicProposal[] {
  if (!proposal.depends_on?.length) return []
  return proposals.value.filter(
    p => proposal.depends_on!.includes(p.id) && p.state === 'rejected'
  )
}

function truncate(text: string, len: number): string {
  return text.length > len ? text.slice(0, len) + '…' : text
}

function proposalStateBadgeClass(state: string): string {
  switch (state) {
    case 'proposed': return 'badge-proposed'
    case 'accepted': return 'badge-accepted'
    case 'rejected': return 'badge-rejected'
    default: return ''
  }
}

async function loadProposals() {
  proposalsLoading.value = true
  proposalsError.value = null
  try {
    const res = await api.getEpicProposals({ state: 'proposed' })
    proposals.value = res.data
    proposalCount.value = res.total_count
  } catch (e: unknown) {
    proposalsError.value = (e as Error).message
  } finally {
    proposalsLoading.value = false
  }
}

function openProposalDetail(p: EpicProposal) {
  selectedProposal.value = p
  showProposalDetail.value = true
}

async function acceptProposal(p: EpicProposal) {
  if (!confirm(`Proposal "${p.title}" akzeptieren?`)) return
  proposalAcceptLoading.value = true
  try {
    await api.acceptEpicProposal(p.id)
    showProposalDetail.value = false
    selectedProposal.value = null
    await loadProposals()
  } catch (e: unknown) {
    proposalsError.value = (e as Error).message
  } finally {
    proposalAcceptLoading.value = false
  }
}

function openProposalRejectModal() {
  proposalRejectReason.value = ''
  showProposalRejectModal.value = true
}

async function confirmRejectProposal() {
  if (!selectedProposal.value || !proposalRejectReason.value.trim()) return
  proposalRejectLoading.value = true
  try {
    await api.rejectEpicProposal(selectedProposal.value.id, proposalRejectReason.value)
    showProposalRejectModal.value = false
    showProposalDetail.value = false
    selectedProposal.value = null
    await loadProposals()
  } catch (e: unknown) {
    proposalsError.value = (e as Error).message
  } finally {
    proposalRejectLoading.value = false
  }
}

function formatProposalDate(iso: string) {
  return new Date(iso).toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' })
}

function connectSSE() {
  const baseUrl = (import.meta.env.VITE_API_URL as string) ?? 'http://localhost:8000'
  eventSource = new EventSource(`${baseUrl}/api/events/triage`)
  eventSource.addEventListener('triage_routed', () => store.loadItems())
  eventSource.addEventListener('triage_ignored', () => store.loadItems())
  eventSource.addEventListener('triage_dlq_updated', () => loadDlqCount())
  eventSource.addEventListener('dlq_requeued', () => loadDlqCount())
  eventSource.addEventListener('dlq_discarded', () => loadDlqCount())
  eventSource.addEventListener('new_event', (e) => {
    try {
      const data = JSON.parse(e.data)
      store.addItem(data)
    } catch { /* ignore */ }
  })
  eventSource.addEventListener('epic_proposal_created', () => loadProposals())
}

onMounted(() => {
  store.loadItems()
  loadProposals()
  loadEscalatedTasks()
  loadDecisionRequests()
  loadDlqCount()
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
        :class="['tab-btn', { active: activeTriageTab === tab.key }]"
        @click="activeTriageTab = tab.key; if (tab.key !== 'proposals' && tab.key !== 'escalated' && tab.key !== 'decisions' && tab.key !== 'dlq') { store.filter = tab.key as 'unrouted' | 'routed' | 'ignored' | 'all'; } page = 1"
      >
        {{ tab.label }}
        <span v-if="tab.key === 'proposals' && proposalCount > 0" class="proposal-badge-count">
          {{ proposalCount }}
        </span>
        <span v-if="tab.key === 'escalated' && escalatedTasks.length > 0" class="escalated-badge-count">
          {{ escalatedTasks.length }}
        </span>
        <span v-if="tab.key === 'decisions' && decisionRequests.length > 0" class="decision-badge-count">
          {{ decisionRequests.length }}
        </span>
        <span v-if="tab.key === 'dlq' && dlqCount > 0" class="dlq-badge-count">
          {{ dlqCount }}
        </span>
      </button>
    </nav>

    <!-- Loading -->
    <div v-if="activeTriageTab !== 'proposals' && activeTriageTab !== 'escalated' && activeTriageTab !== 'decisions' && activeTriageTab !== 'dlq' && store.loading" class="triage-loading">Loading...</div>
    <div v-else-if="activeTriageTab !== 'proposals' && activeTriageTab !== 'escalated' && activeTriageTab !== 'decisions' && activeTriageTab !== 'dlq' && store.error" class="triage-error">{{ store.error }}</div>

    <!-- ─── Proposals Tab ─────────────────────────────────────────────────── -->
    <div v-else-if="activeTriageTab === 'proposals'" class="proposals-section">
      <div v-if="proposalsLoading" class="triage-loading">Lade Proposals…</div>
      <div v-else-if="proposalsError" class="triage-error">{{ proposalsError }}</div>
      <div v-else-if="!proposals.length" class="triage-empty">Keine offenen Proposals.</div>
      <div v-else class="proposals-list">
        <HivemindCard
          v-for="p in proposals"
          :key="p.id"
          class="proposal-card"
          @click="openProposalDetail(p)"
        >
          <div class="proposal-row">
            <div class="proposal-main">
              <h3 class="proposal-title">{{ p.title }}</h3>
              <div class="proposal-meta">
                <span class="proposal-proposer">{{ p.proposed_by_username || '–' }}</span>
                <span :class="['proposal-state', proposalStateBadgeClass(p.state)]">{{ p.state }}</span>
              </div>
              <p class="proposal-rationale" v-if="p.rationale">
                {{ truncate(p.rationale, 100) }}
              </p>
            </div>
            <div class="proposal-tags" v-if="p.depends_on?.length">
              <span v-for="depId in p.depends_on" :key="depId" class="dep-tag">
                {{ proposals.find(x => x.id === depId)?.title || depId.slice(0, 8) }}
              </span>
            </div>
          </div>
          <!-- Dependency Warning -->
          <div v-if="getDependencyWarnings(p).length" class="dep-warning">
            ⚠ Abhängigkeit abgelehnt: {{ getDependencyWarnings(p).map(d => d.title).join(', ') }}
          </div>
        </HivemindCard>
      </div>
    </div>

    <!-- ─── Escalated Tasks Tab (TASK-6-011) ─────────────────────────────── -->
    <div v-else-if="activeTriageTab === 'escalated'" class="escalated-section">
      <div v-if="escalatedLoading" class="triage-loading">Lade eskalierte Tasks…</div>
      <div v-else-if="escalatedError" class="triage-error">{{ escalatedError }}</div>
      <div v-else-if="!escalatedTasks.length" class="triage-empty">Keine eskalierten Tasks.</div>
      <div v-else class="escalated-list">
        <HivemindCard
          v-for="task in escalatedTasks"
          :key="task.id"
          class="escalated-card"
        >
          <div class="escalated-row">
            <div class="escalated-main">
              <div class="escalated-header">
                <span class="escalated-key">{{ task.task_key }}</span>
                <span class="routing-badge state-escalated">ESCALATED</span>
                <span v-if="task.qa_failed_count > 0" class="qa-badge">
                  QA failed {{ task.qa_failed_count }}×
                </span>
              </div>
              <h3 class="escalated-title">{{ task.title }}</h3>
              <p v-if="task.description" class="escalated-desc">{{ task.description?.slice(0, 120) }}</p>
            </div>
            <div class="escalated-actions" v-if="isTriageAdmin">
              <button
                class="btn btn-primary"
                :disabled="resolveLoading === task.task_key"
                @click="resolveEscalation(task)"
              >
                {{ resolveLoading === task.task_key ? 'Resolving…' : 'De-eskalieren' }}
              </button>
            </div>
          </div>
        </HivemindCard>
      </div>
    </div>

    <!-- ─── Decision Requests Tab (TASK-6-011) ────────────────────────────── -->
    <div v-else-if="activeTriageTab === 'decisions'" class="decisions-section">
      <div v-if="decisionsLoading" class="triage-loading">Lade Decision Requests…</div>
      <div v-else-if="decisionsError" class="triage-error">{{ decisionsError }}</div>
      <div v-else-if="!decisionRequests.length" class="triage-empty">Keine offenen Decision Requests.</div>
      <div v-else class="decisions-list">
        <HivemindCard
          v-for="dr in decisionRequests"
          :key="dr.id"
          class="decision-card"
          @click="openDecisionDialog(dr)"
        >
          <div class="decision-row">
            <div class="decision-main">
              <div class="decision-header">
                <span :class="['dr-state', `dr-state--${dr.state}`]">{{ dr.state }}</span>
                <SlaCountdown :sla_due_at="dr.sla_due_at" />
              </div>
              <h3 class="decision-title">
                {{ (dr.payload?.question as string) || (dr.payload?.title as string) || dr.id.slice(0, 8) }}
              </h3>
              <p v-if="dr.payload?.context" class="decision-context">
                {{ (dr.payload.context as string).slice(0, 120) }}
              </p>
            </div>
            <div class="decision-meta">
              <span class="decision-time">{{ formatTime(dr.created_at) }}</span>
            </div>
          </div>
        </HivemindCard>
      </div>
    </div>

    <!-- ─── Dead Letter Queue Tab (TASK-7-015) ──────────────────────────── -->
    <div
      v-else-if="activeTriageTab === 'dlq'"
      class="dlq-section"
    >
      <DeadLetterList @count-updated="onDlqCountUpdated" />
    </div>

    <!-- ─── Standard Triage List ──────────────────────────────────────────── -->
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
          <span class="item-project">{{ getProjectLabel(item) }}</span>
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
        <div v-if="getRoutingReason(item)" class="item-reason">{{ getRoutingReason(item) }}</div>
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

    <!-- Proposal Detail Modal -->
    <HivemindModal v-model="showProposalDetail" :title="selectedProposal?.title || 'Proposal'" size="lg">
      <template v-if="selectedProposal">
        <div class="proposal-detail">
          <div class="proposal-detail__meta">
            <span :class="['proposal-state', proposalStateBadgeClass(selectedProposal.state)]">
              {{ selectedProposal.state }}
            </span>
            <span class="proposal-detail__proposer">Von: {{ selectedProposal.proposed_by_username || '–' }}</span>
            <span class="proposal-detail__date">{{ formatProposalDate(selectedProposal.created_at) }}</span>
          </div>
          <div class="proposal-detail__description">
            <h4>Beschreibung</h4>
            <p>{{ selectedProposal.description }}</p>
          </div>
          <div v-if="selectedProposal.rationale" class="proposal-detail__rationale">
            <h4>Begründung</h4>
            <p>{{ selectedProposal.rationale }}</p>
          </div>
          <div v-if="selectedProposal.depends_on?.length" class="proposal-detail__deps">
            <h4>Abhängigkeiten</h4>
            <div class="dep-list">
              <span
                v-for="depId in selectedProposal.depends_on"
                :key="depId"
                :class="['dep-tag', { 'dep-tag--rejected': proposals.find(x => x.id === depId)?.state === 'rejected' }]"
              >
                {{ proposals.find(x => x.id === depId)?.title || depId.slice(0, 8) }}
                <span v-if="proposals.find(x => x.id === depId)" class="dep-state">
                  ({{ proposals.find(x => x.id === depId)?.state }})
                </span>
              </span>
            </div>
          </div>
          <div v-if="getDependencyWarnings(selectedProposal).length" class="dep-warning">
            ⚠ Abhängigkeit abgelehnt: {{ getDependencyWarnings(selectedProposal).map(d => d.title).join(', ') }}
          </div>
        </div>
      </template>
      <template #footer v-if="isTriageAdmin && selectedProposal?.state === 'proposed'">
        <button class="btn" @click="showProposalDetail = false">Schließen</button>
        <button
          class="btn btn-danger"
          @click="openProposalRejectModal"
        >
          Ablehnen
        </button>
        <button
          class="btn btn-primary"
          :disabled="proposalAcceptLoading"
          @click="selectedProposal && acceptProposal(selectedProposal)"
        >
          {{ proposalAcceptLoading ? 'Akzeptiere…' : 'Akzeptieren' }}
        </button>
      </template>
    </HivemindModal>

    <!-- Proposal Reject Modal -->
    <HivemindModal v-model="showProposalRejectModal" title="Proposal ablehnen">
      <div class="modal-body">
        <label class="field-label">Begründung (Pflicht)</label>
        <textarea v-model="proposalRejectReason" class="field-textarea" rows="3" placeholder="Begründung eingeben…" />
      </div>
      <template #footer>
        <button class="btn" @click="showProposalRejectModal = false">Abbrechen</button>
        <button class="btn btn-danger" :disabled="!proposalRejectReason.trim() || proposalRejectLoading" @click="confirmRejectProposal">
          {{ proposalRejectLoading ? 'Wird abgelehnt…' : 'Ablehnen' }}
        </button>
      </template>
    </HivemindModal>

    <!-- Decision Request Dialog (TASK-6-010) -->
    <DecisionRequestDialog
      v-model:open="showDecisionDialog"
      :request="selectedDecisionRequest"
      @resolved="onDecisionResolved"
    />
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
  font-size: var(--font-size-2xl);
  color: var(--color-text);
  margin: 0;
}

.triage-count {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
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
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
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
  font-size: var(--font-size-xs);
  font-weight: 600;
  padding: var(--space-0-5) var(--space-2);
  border-radius: var(--radius-sm);
  text-transform: uppercase;
  white-space: nowrap;
}

.badge-youtrack { background: var(--color-info-20); color: var(--primitive-blue-400); }
.badge-sentry { background: var(--color-danger-20); color: var(--primitive-red-400); }
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

.item-project {
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  color: var(--color-accent);
  border: 1px solid color-mix(in srgb, var(--color-accent) 45%, transparent);
  border-radius: var(--radius-sm);
  padding: var(--space-0-5) var(--space-1-5);
}

.item-entity {
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
}

.item-time {
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
  white-space: nowrap;
}

.routing-badge {
  font-size: var(--font-size-2xs);
  padding: var(--space-0-5) var(--space-1-5);
  border-radius: var(--radius-xs);
  font-weight: 600;
  text-transform: uppercase;
}

.state-unrouted { background: var(--color-warning-20); color: var(--color-warning); }
.state-routed { background: var(--color-success-20); color: var(--color-success); }
.state-ignored { background: var(--color-surface-alt); color: var(--color-text-muted); }
.state-escalated { background: var(--color-danger-20); color: var(--color-danger); }

.item-actions {
  display: flex;
  gap: var(--space-2, 0.5rem);
}

.item-payload {
  margin-top: var(--space-2, 0.5rem);
  padding: var(--space-2, 0.5rem);
  background: var(--color-bg);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.item-reason {
  margin-top: var(--space-2, 0.5rem);
  color: var(--color-warning);
  font-size: var(--font-size-xs);
}

.item-payload code {
  font-size: var(--font-size-2xs);
  color: var(--color-text-muted);
  white-space: pre-wrap;
  word-break: break-all;
}

.btn {
  padding: var(--space-1-5) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
  font-size: var(--font-size-sm);
  transition: all 150ms;
}

.btn:hover { background: var(--color-surface-alt); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-route { border-color: var(--color-accent); color: var(--color-accent); }
.btn-ignore { border-color: var(--color-text-muted); color: var(--color-text-muted); }
.btn-primary { background: var(--color-accent); color: var(--color-bg); border-color: var(--color-accent); }
.btn-danger { background: var(--color-danger); color: white; border-color: var(--color-danger); }
.btn-load-more { width: 100%; padding: var(--space-2-5); text-align: center; }

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
  font-size: var(--font-size-sm);
  font-weight: 500;
}

.field-select, .field-textarea {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  padding: var(--space-2);
  font-size: var(--font-size-sm);
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

/* ── Proposals (TASK-4-010) ─────────────────────────────────────────────── */
.proposal-badge-count {
  background: var(--color-accent);
  color: var(--color-bg);
  border-radius: var(--radius-full);
  font-size: var(--font-size-2xs);
  padding: 1px var(--space-1-5);
  margin-left: var(--space-1);
  font-weight: 700;
}

.proposals-section {
  margin-top: var(--space-2);
}

.proposals-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.proposal-card {
  cursor: pointer;
  transition: border-color 0.15s ease;
}
.proposal-card:hover {
  border-color: var(--color-accent);
}

.proposal-row {
  display: flex;
  justify-content: space-between;
  gap: var(--space-3);
}

.proposal-main {
  flex: 1;
  min-width: 0;
}

.proposal-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-base);
  margin: 0 0 var(--space-1);
  color: var(--color-text);
}

.proposal-meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}

.proposal-proposer {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.proposal-state {
  font-size: var(--font-size-2xs);
  font-family: var(--font-mono);
  padding: 1px var(--space-1-5);
  border-radius: var(--radius-xs);
  text-transform: uppercase;
}
.badge-proposed { background: var(--color-warning-20); color: var(--color-warning); }
.badge-accepted { background: var(--color-success-20); color: var(--color-success); }
.badge-rejected { background: var(--color-danger-20); color: var(--color-danger); }

.proposal-rationale {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  margin: 0;
  line-height: 1.4;
}

.proposal-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  align-items: flex-start;
}

.dep-tag {
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  padding: 1px var(--space-1-5);
  border-radius: var(--radius-sm);
  background: var(--color-accent-10);
  color: var(--color-accent);
  white-space: nowrap;
}
.dep-tag--rejected {
  background: var(--color-danger-10);
  color: var(--color-danger);
}

.dep-warning {
  background: var(--color-danger-10);
  border: 1px solid var(--color-danger);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
  font-size: var(--font-size-xs);
  color: var(--color-danger);
  margin-top: var(--space-2);
}

/* Proposal Detail */
.proposal-detail {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.proposal-detail__meta {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.proposal-detail__description h4,
.proposal-detail__rationale h4,
.proposal-detail__deps h4 {
  font-family: var(--font-heading);
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  margin: 0 0 var(--space-1);
}

.proposal-detail__description p,
.proposal-detail__rationale p {
  margin: 0;
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--color-text);
}

.dep-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.dep-state {
  font-size: var(--font-size-2xs);
  opacity: 0.7;
}

/* ── Dead Letter Queue (TASK-7-015) ─────────────────────────────────────── */
.dlq-section {
  margin-top: var(--space-2);
}

/* ── Escalated Tasks (TASK-6-011) ───────────────────────────────────────── */
.escalated-section, .decisions-section {
  margin-top: var(--space-2);
}

.escalated-list, .decisions-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.escalated-card, .decision-card {
  padding: var(--space-3);
}
.decision-card { cursor: pointer; transition: border-color 0.15s ease; }
.decision-card:hover { border-color: var(--color-accent); }

.escalated-row, .decision-row {
  display: flex;
  justify-content: space-between;
  gap: var(--space-3);
  align-items: flex-start;
}

.escalated-main, .decision-main {
  flex: 1;
  min-width: 0;
}

.escalated-header, .decision-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-1);
}

.escalated-key {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--color-accent);
}

.qa-badge {
  font-size: var(--font-size-2xs);
  font-family: var(--font-mono);
  padding: 1px var(--space-1-5);
  border-radius: var(--radius-xs);
  background: var(--color-danger-10);
  color: var(--color-danger);
}

.escalated-title, .decision-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-base);
  margin: 0 0 var(--space-1);
  color: var(--color-text);
}

.escalated-desc, .decision-context {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  margin: 0;
  line-height: 1.4;
}

.escalated-actions {
  flex-shrink: 0;
}

.decision-meta {
  flex-shrink: 0;
}

.decision-time {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.dr-state {
  font-size: var(--font-size-2xs);
  font-family: var(--font-mono);
  padding: 1px var(--space-1-5);
  border-radius: var(--radius-xs);
  text-transform: uppercase;
  font-weight: 600;
}
.dr-state--open { background: var(--color-warning-20); color: var(--color-warning); }
.dr-state--resolved { background: var(--color-success-20); color: var(--color-success); }
.dr-state--expired { background: var(--color-danger-20); color: var(--color-danger); }

.escalated-badge-count {
  background: var(--color-danger);
  color: white;
  border-radius: var(--radius-full);
  font-size: var(--font-size-2xs);
  padding: 1px var(--space-1-5);
  margin-left: var(--space-1);
  font-weight: 700;
}

.decision-badge-count {
  background: var(--color-warning);
  color: var(--color-bg);
  border-radius: var(--radius-full);
  font-size: var(--font-size-2xs);
  padding: 1px var(--space-1-5);
  margin-left: var(--space-1);
  font-weight: 700;
}

.dlq-badge-count {
  background: var(--color-success-20);
  color: var(--color-success);
  border: 1px solid color-mix(in srgb, var(--color-success) 55%, transparent);
  border-radius: var(--radius-full);
  font-size: var(--font-size-2xs);
  padding: 1px var(--space-1-5);
  margin-left: var(--space-1);
  font-weight: 700;
}
</style>
