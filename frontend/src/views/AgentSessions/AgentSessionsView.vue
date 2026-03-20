<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../../api'
import type { AgentSession, AgentSessionListResponse } from '../../api/types'

// ── State ───────────────────────────────────────────────────────────────────
const data = ref<AgentSessionListResponse | null>(null)
const loading = ref(true)
const error = ref('')

// ── Filters ─────────────────────────────────────────────────────────────────
const filterRole = ref('')
const filterPolicy = ref('')
const filterStatus = ref('')
const page = ref(1)
const pageSize = 30

const roleOptions = ['worker', 'reviewer', 'gaertner', 'triage', 'stratege', 'architekt']
const policyOptions = ['stateless', 'attempt', 'epic', 'project']
const statusOptions = ['active', 'completed', 'expired']

// ── Expanded detail ─────────────────────────────────────────────────────────
const expandedRows = ref<Set<string>>(new Set())

function toggleExpand(id: string) {
  if (expandedRows.value.has(id)) {
    expandedRows.value.delete(id)
  } else {
    expandedRows.value.add(id)
  }
}

// ── Load ────────────────────────────────────────────────────────────────────
async function load() {
  loading.value = true
  error.value = ''
  try {
    const params: Record<string, unknown> = { page: page.value, page_size: pageSize }
    if (filterRole.value) params.agent_role = filterRole.value
    if (filterPolicy.value) params.thread_policy = filterPolicy.value
    if (filterStatus.value) params.status = filterStatus.value

    data.value = await api.getAgentSessions(params as Parameters<typeof api.getAgentSessions>[0])
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Fehler beim Laden'
  } finally {
    loading.value = false
  }
}

function applyFilters() {
  page.value = 1
  expandedRows.value.clear()
  void load()
}

function resetFilters() {
  filterRole.value = ''
  filterPolicy.value = ''
  filterStatus.value = ''
  page.value = 1
  expandedRows.value.clear()
  void load()
}

watch(page, () => void load())
onMounted(() => void load())

// ── Computed ────────────────────────────────────────────────────────────────
const totalPages = computed(() => {
  if (!data.value) return 1
  return Math.max(1, Math.ceil(data.value.total_count / pageSize))
})

// ── Helpers ─────────────────────────────────────────────────────────────────
function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('de-DE', {
    day: '2-digit', month: '2-digit', year: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

function duration(start: string, last: string): string {
  const ms = new Date(last).getTime() - new Date(start).getTime()
  if (ms < 60_000) return `${Math.round(ms / 1000)}s`
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)}m`
  return `${(ms / 3_600_000).toFixed(1)}h`
}

function policyClass(p: string): string {
  const map: Record<string, string> = {
    stateless: 'policy--stateless',
    attempt: 'policy--attempt',
    epic: 'policy--epic',
    project: 'policy--project',
  }
  return map[p] ?? ''
}

function statusClass(s: string): string {
  const map: Record<string, string> = {
    active: 'status--active',
    completed: 'status--completed',
    expired: 'status--expired',
  }
  return map[s] ?? ''
}

function tokenInfo(meta: Record<string, unknown> | null): { input: number; output: number } | null {
  if (!meta) return null
  const input = typeof meta.input_tokens === 'number' ? meta.input_tokens : 0
  const output = typeof meta.output_tokens === 'number' ? meta.output_tokens : 0
  if (input === 0 && output === 0) return null
  return { input, output }
}
</script>

<template>
  <div class="as-view">
    <!-- Header -->
    <header class="as-header">
      <h2 class="as-title">Agent Sessions</h2>
      <button class="as-refresh" @click="load" :disabled="loading">
        {{ loading ? 'Lade…' : 'Aktualisieren' }}
      </button>
    </header>

    <!-- Filters -->
    <section class="as-filters">
      <select v-model="filterRole" class="as-select" @change="applyFilters">
        <option value="">Alle Rollen</option>
        <option v-for="r in roleOptions" :key="r" :value="r">{{ r }}</option>
      </select>
      <select v-model="filterPolicy" class="as-select" @change="applyFilters">
        <option value="">Alle Policies</option>
        <option v-for="p in policyOptions" :key="p" :value="p">{{ p }}</option>
      </select>
      <select v-model="filterStatus" class="as-select" @change="applyFilters">
        <option value="">Alle Status</option>
        <option v-for="s in statusOptions" :key="s" :value="s">{{ s }}</option>
      </select>
      <button class="as-btn as-btn--ghost" @click="resetFilters">Reset</button>
    </section>

    <!-- Error -->
    <p v-if="error" class="as-error">{{ error }}</p>

    <!-- Loading -->
    <div v-if="loading && !data" class="as-skeleton-wrap">
      <div v-for="i in 5" :key="i" class="as-skeleton-row" />
    </div>

    <!-- Table -->
    <div v-else-if="data && data.data.length > 0" class="as-table-wrap">
      <table class="as-table">
        <thead>
          <tr>
            <th>Rolle</th>
            <th>Policy</th>
            <th>Status</th>
            <th>Dispatches</th>
            <th>Dauer</th>
            <th>Gestartet</th>
            <th>Letzte Aktivität</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="s in data.data" :key="s.id">
            <tr class="as-row" @click="toggleExpand(s.id)">
              <td class="as-role">{{ s.agent_role }}</td>
              <td><span class="as-badge" :class="policyClass(s.thread_policy)">{{ s.thread_policy }}</span></td>
              <td><span class="as-badge" :class="statusClass(s.status)">{{ s.status }}</span></td>
              <td class="as-mono">{{ s.dispatch_count }}</td>
              <td class="as-mono">{{ duration(s.started_at, s.last_activity_at) }}</td>
              <td class="as-date">{{ formatDate(s.started_at) }}</td>
              <td class="as-date">{{ formatDate(s.last_activity_at) }}</td>
            </tr>
            <!-- Expanded detail -->
            <tr v-if="expandedRows.has(s.id)" class="as-expand-row">
              <td colspan="7">
                <div class="as-expand">
                  <dl class="as-dl">
                    <dt>Thread Key</dt><dd class="as-mono">{{ s.thread_key }}</dd>
                    <dt>Session ID</dt><dd class="as-mono">{{ s.id }}</dd>
                    <dt v-if="s.task_id">Task ID</dt><dd v-if="s.task_id" class="as-mono">{{ s.task_id }}</dd>
                    <dt v-if="s.epic_id">Epic ID</dt><dd v-if="s.epic_id" class="as-mono">{{ s.epic_id }}</dd>
                    <dt v-if="s.project_id">Project ID</dt><dd v-if="s.project_id" class="as-mono">{{ s.project_id }}</dd>
                    <template v-if="tokenInfo(s.session_metadata)">
                      <dt>Token Input</dt><dd class="as-mono">{{ tokenInfo(s.session_metadata)!.input.toLocaleString() }}</dd>
                      <dt>Token Output</dt><dd class="as-mono">{{ tokenInfo(s.session_metadata)!.output.toLocaleString() }}</dd>
                    </template>
                  </dl>
                  <template v-if="s.summary">
                    <h4 class="as-expand__sub">Summary</h4>
                    <p class="as-expand__text">{{ s.summary }}</p>
                  </template>
                  <template v-if="s.session_metadata">
                    <h4 class="as-expand__sub">Metadata</h4>
                    <pre class="as-expand__pre">{{ JSON.stringify(s.session_metadata, null, 2) }}</pre>
                  </template>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>

      <!-- Pagination -->
      <div class="as-pagination">
        <button class="as-btn" :disabled="page <= 1" @click="page--">&larr; Zurück</button>
        <span class="as-page-info">Seite {{ page }} / {{ totalPages }} ({{ data.total_count }} Sessions)</span>
        <button class="as-btn" :disabled="!data.has_more" @click="page++">Weiter &rarr;</button>
      </div>
    </div>

    <!-- Empty -->
    <p v-else class="as-empty">Keine Agent Sessions gefunden.</p>
  </div>
</template>

<style scoped>
.as-view {
  padding: var(--space-6);
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.as-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.as-title {
  margin: 0;
  font-family: var(--font-heading);
  font-size: var(--font-size-2xl);
  color: var(--color-text);
}

.as-refresh {
  background: var(--color-surface-alt);
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--font-size-sm);
}
.as-refresh:hover:not(:disabled) { background: var(--color-border); }

/* ── Filters ───────────────────────────────────────────────────────────── */
.as-filters {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  align-items: end;
}

.as-select {
  background: var(--color-surface);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
  font-size: var(--font-size-sm);
  min-width: 140px;
}

.as-btn {
  background: var(--color-surface-alt);
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--font-size-sm);
}
.as-btn:hover:not(:disabled) { background: var(--color-border); }
.as-btn:disabled { opacity: 0.4; cursor: default; }
.as-btn--ghost { border-color: transparent; }

/* ── Table ─────────────────────────────────────────────────────────────── */
.as-table-wrap { overflow-x: auto; }

.as-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.as-table th {
  text-align: left;
  padding: var(--space-2) var(--space-3);
  color: var(--color-text-muted);
  font-weight: 600;
  border-bottom: 1px solid var(--color-border);
  font-size: var(--font-size-xs);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.as-table td {
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--color-border);
  vertical-align: middle;
}

.as-row {
  cursor: pointer;
  transition: background 0.15s;
}
.as-row:hover { background: var(--color-surface-alt); }

.as-role {
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--color-accent);
}

.as-mono {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
}

.as-date {
  white-space: nowrap;
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
}

/* ── Badges ────────────────────────────────────────────────────────────── */
.as-badge {
  display: inline-block;
  padding: 1px var(--space-2);
  border-radius: var(--radius-full);
  font-size: var(--font-size-2xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.policy--stateless { background: var(--color-surface-alt); color: var(--color-text-muted); }
.policy--attempt { background: var(--color-accent-10); color: var(--color-accent); }
.policy--epic { background: var(--color-warning-10); color: var(--color-warning); }
.policy--project { background: var(--color-success-10); color: var(--color-success); }

.status--active { background: var(--color-success-10); color: var(--color-success); }
.status--completed { background: var(--color-surface-alt); color: var(--color-text-muted); }
.status--expired { background: var(--color-danger-10); color: var(--color-danger); }

/* ── Expanded Row ──────────────────────────────────────────────────────── */
.as-expand-row td {
  padding: 0;
  border-bottom: 1px solid var(--color-border);
}

.as-expand {
  background: var(--color-surface-alt);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.as-dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--space-1) var(--space-4);
  font-size: var(--font-size-xs);
  margin: 0;
}
.as-dl dt {
  color: var(--color-text-muted);
  font-weight: 600;
}
.as-dl dd { margin: 0; }

.as-expand__sub {
  margin: var(--space-2) 0 var(--space-1);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.as-expand__text {
  font-size: var(--font-size-sm);
  line-height: 1.5;
  margin: 0;
}

.as-expand__pre {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-3);
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  overflow-x: auto;
  max-height: 300px;
  margin: 0;
}

/* ── Pagination ────────────────────────────────────────────────────────── */
.as-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  padding-top: var(--space-3);
}

.as-page-info {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

/* ── States ────────────────────────────────────────────────────────────── */
.as-error {
  color: var(--color-danger);
  padding: var(--space-3);
  background: var(--color-danger-10);
  border-radius: var(--radius-sm);
}

.as-empty {
  text-align: center;
  color: var(--color-text-muted);
  padding: var(--space-8) 0;
}

.as-skeleton-wrap {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.as-skeleton-row {
  height: 40px;
  background: var(--color-surface-alt);
  border-radius: var(--radius-sm);
  animation: pulse 1.5s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 1; }
}

@media (max-width: 768px) {
  .as-filters { flex-direction: column; }
}
</style>
