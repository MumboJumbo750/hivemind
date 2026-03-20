<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../../api'
import type { GovernanceAuditEntry, GovernanceAuditListResponse, GovernanceAuditStats } from '../../api/types'

// ── State ───────────────────────────────────────────────────────────────────
const data = ref<GovernanceAuditListResponse | null>(null)
const stats = ref<GovernanceAuditStats | null>(null)
const loading = ref(true)
const error = ref('')

// ── Filters ─────────────────────────────────────────────────────────────────
const filterType = ref('')
const filterLevel = ref('')
const filterStatus = ref('')
const page = ref(1)
const pageSize = 30

const governanceTypes = ['review', 'epic_proposal', 'epic_scoping', 'skill_merge', 'guard_merge', 'decision_request', 'escalation']
const levelOptions = ['manual', 'assisted', 'auto']
const statusOptions = ['pending_human', 'auto_fallback', 'executed', 'vetoed']

// ── Expanded detail ─────────────────────────────────────────────────────────
const expandedRows = ref<Set<string>>(new Set())

function toggleExpand(id: string) {
  if (expandedRows.value.has(id)) expandedRows.value.delete(id)
  else expandedRows.value.add(id)
}

// ── Load ────────────────────────────────────────────────────────────────────
async function load() {
  loading.value = true
  error.value = ''
  try {
    const params: Record<string, unknown> = { page: page.value, page_size: pageSize }
    if (filterType.value) params.governance_type = filterType.value
    if (filterLevel.value) params.governance_level = filterLevel.value
    if (filterStatus.value) params.status = filterStatus.value

    data.value = await api.getGovernanceAudit(params as Parameters<typeof api.getGovernanceAudit>[0])
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Fehler beim Laden'
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  try {
    stats.value = await api.getGovernanceAuditStats()
  } catch { /* optional */ }
}

function applyFilters() {
  page.value = 1
  expandedRows.value.clear()
  void load()
}

function resetFilters() {
  filterType.value = ''
  filterLevel.value = ''
  filterStatus.value = ''
  page.value = 1
  expandedRows.value.clear()
  void load()
}

watch(page, () => void load())
onMounted(() => { void load(); void loadStats() })

// ── Computed ────────────────────────────────────────────────────────────────
const totalPages = computed(() => {
  if (!data.value) return 1
  return Math.max(1, Math.ceil(data.value.total_count / pageSize))
})

// Group stats for display
const statsByType = computed(() => {
  if (!stats.value) return []
  const map = new Map<string, number>()
  for (const s of stats.value.stats) {
    map.set(s.governance_type, (map.get(s.governance_type) ?? 0) + s.count)
  }
  return Array.from(map.entries()).map(([type, count]) => ({ type, count }))
})

// ── Helpers ─────────────────────────────────────────────────────────────────
function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('de-DE', {
    day: '2-digit', month: '2-digit', year: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

function levelClass(l: string): string {
  const map: Record<string, string> = {
    manual: 'level--manual',
    assisted: 'level--assisted',
    auto: 'level--auto',
  }
  return map[l] ?? ''
}

function isVetoed(entry: GovernanceAuditEntry): boolean {
  return entry.governance_level === 'assisted' && entry.executed_at !== null
}

function confidenceClass(c: number | null): string {
  if (c === null) return ''
  if (c < 0.5) return 'conf--low'
  if (c < 0.8) return 'conf--mid'
  return 'conf--high'
}
</script>

<template>
  <div class="ga-view">
    <!-- Header -->
    <header class="ga-header">
      <h2 class="ga-title">Governance Audit Trail</h2>
      <button class="ga-refresh" @click="load(); loadStats()" :disabled="loading">
        {{ loading ? 'Lade…' : 'Aktualisieren' }}
      </button>
    </header>

    <!-- Stats Panel -->
    <section v-if="stats" class="ga-stats">
      <article class="stat-card">
        <span class="stat-card__value">{{ stats.total }}</span>
        <span class="stat-card__label">Gesamt</span>
      </article>
      <article class="stat-card stat-card--accent">
        <span class="stat-card__value">{{ stats.auto_approve_rate }}%</span>
        <span class="stat-card__label">Auto-Approve Rate</span>
      </article>
      <article class="stat-card" :class="stats.veto_count > 0 ? 'stat-card--warn' : ''">
        <span class="stat-card__value">{{ stats.veto_count }}</span>
        <span class="stat-card__label">Veto / Override</span>
      </article>
      <article v-for="s in statsByType" :key="s.type" class="stat-card">
        <span class="stat-card__value">{{ s.count }}</span>
        <span class="stat-card__label">{{ s.type }}</span>
      </article>
    </section>

    <!-- Filters -->
    <section class="ga-filters">
      <select v-model="filterType" class="ga-select" @change="applyFilters">
        <option value="">Alle Typen</option>
        <option v-for="t in governanceTypes" :key="t" :value="t">{{ t }}</option>
      </select>
      <select v-model="filterLevel" class="ga-select" @change="applyFilters">
        <option value="">Alle Level</option>
        <option v-for="l in levelOptions" :key="l" :value="l">{{ l }}</option>
      </select>
      <select v-model="filterStatus" class="ga-select" @change="applyFilters">
        <option value="">Alle Status</option>
        <option v-for="s in statusOptions" :key="s" :value="s">{{ s }}</option>
      </select>
      <button class="ga-btn ga-btn--ghost" @click="resetFilters">Reset</button>
    </section>

    <!-- Error -->
    <p v-if="error" class="ga-error">{{ error }}</p>

    <!-- Loading -->
    <div v-if="loading && !data" class="ga-skeleton-wrap">
      <div v-for="i in 5" :key="i" class="ga-skeleton-row" />
    </div>

    <!-- Table -->
    <div v-else-if="data && data.data.length > 0" class="ga-table-wrap">
      <table class="ga-table">
        <thead>
          <tr>
            <th>Typ</th>
            <th>Level</th>
            <th>Status</th>
            <th>Rolle</th>
            <th>Action</th>
            <th>Confidence</th>
            <th>Target</th>
            <th>Erstellt</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="e in data.data" :key="e.id">
            <tr class="ga-row" :class="{ 'ga-row--vetoed': isVetoed(e) }" @click="toggleExpand(e.id)">
              <td><span class="ga-badge ga-badge--type">{{ e.governance_type }}</span></td>
              <td><span class="ga-badge" :class="levelClass(e.governance_level)">{{ e.governance_level }}</span></td>
              <td><span class="ga-badge ga-badge--status">{{ e.status }}</span></td>
              <td class="ga-mono">{{ e.agent_role }}</td>
              <td>{{ e.action ?? '–' }}</td>
              <td>
                <span v-if="e.confidence !== null" class="ga-conf" :class="confidenceClass(e.confidence)">
                  {{ Math.round(e.confidence * 100) }}%
                </span>
                <span v-else class="ga-muted">–</span>
              </td>
              <td class="ga-mono ga-target">{{ e.target_type }} / {{ e.target_ref }}</td>
              <td class="ga-date">{{ formatDate(e.created_at) }}</td>
            </tr>
            <!-- Expanded detail -->
            <tr v-if="expandedRows.has(e.id)" class="ga-expand-row">
              <td colspan="8">
                <div class="ga-expand">
                  <dl class="ga-dl">
                    <dt>ID</dt><dd class="ga-mono">{{ e.id }}</dd>
                    <dt v-if="e.dispatch_id">Dispatch</dt>
                    <dd v-if="e.dispatch_id" class="ga-mono">{{ e.dispatch_id }}</dd>
                    <dt v-if="e.prompt_type">Prompt Type</dt>
                    <dd v-if="e.prompt_type">{{ e.prompt_type }}</dd>
                    <dt v-if="e.executed_at">Ausgeführt</dt>
                    <dd v-if="e.executed_at">{{ formatDate(e.executed_at) }}</dd>
                  </dl>
                  <template v-if="e.rationale">
                    <h4 class="ga-expand__sub">Rationale</h4>
                    <p class="ga-expand__text">{{ e.rationale }}</p>
                  </template>
                  <template v-if="e.payload">
                    <h4 class="ga-expand__sub">Payload</h4>
                    <pre class="ga-expand__pre">{{ JSON.stringify(e.payload, null, 2) }}</pre>
                  </template>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>

      <!-- Pagination -->
      <div class="ga-pagination">
        <button class="ga-btn" :disabled="page <= 1" @click="page--">&larr; Zurück</button>
        <span class="ga-page-info">Seite {{ page }} / {{ totalPages }} ({{ data.total_count }} Einträge)</span>
        <button class="ga-btn" :disabled="!data.has_more" @click="page++">Weiter &rarr;</button>
      </div>
    </div>

    <!-- Empty -->
    <p v-else class="ga-empty">Keine Governance-Entscheidungen gefunden.</p>
  </div>
</template>

<style scoped>
.ga-view {
  padding: var(--space-6);
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.ga-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.ga-title {
  margin: 0;
  font-family: var(--font-heading);
  font-size: var(--font-size-2xl);
  color: var(--color-text);
}

.ga-refresh {
  background: var(--color-surface-alt);
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--font-size-sm);
}
.ga-refresh:hover:not(:disabled) { background: var(--color-border); }

/* ── Stats ─────────────────────────────────────────────────────────────── */
.ga-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--space-3);
}

.stat-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-1);
}
.stat-card--accent { border-color: var(--color-accent); }
.stat-card--warn { border-color: var(--color-warning); }

.stat-card__value {
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--color-text);
  font-family: var(--font-mono);
}
.stat-card--accent .stat-card__value { color: var(--color-accent); }
.stat-card--warn .stat-card__value { color: var(--color-warning); }

.stat-card__label {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  text-align: center;
}

/* ── Filters ───────────────────────────────────────────────────────────── */
.ga-filters {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  align-items: end;
}

.ga-select {
  background: var(--color-surface);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
  font-size: var(--font-size-sm);
  min-width: 140px;
}

.ga-btn {
  background: var(--color-surface-alt);
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--font-size-sm);
}
.ga-btn:hover:not(:disabled) { background: var(--color-border); }
.ga-btn:disabled { opacity: 0.4; cursor: default; }
.ga-btn--ghost { border-color: transparent; }

/* ── Table ─────────────────────────────────────────────────────────────── */
.ga-table-wrap { overflow-x: auto; }

.ga-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.ga-table th {
  text-align: left;
  padding: var(--space-2) var(--space-3);
  color: var(--color-text-muted);
  font-weight: 600;
  border-bottom: 1px solid var(--color-border);
  font-size: var(--font-size-xs);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.ga-table td {
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--color-border);
  vertical-align: middle;
}

.ga-row {
  cursor: pointer;
  transition: background 0.15s;
}
.ga-row:hover { background: var(--color-surface-alt); }
.ga-row--vetoed {
  border-left: 3px solid var(--color-warning);
}

.ga-mono {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
}

.ga-target {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ga-date {
  white-space: nowrap;
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
}

.ga-muted { color: var(--color-text-muted); }

/* ── Badges ────────────────────────────────────────────────────────────── */
.ga-badge {
  display: inline-block;
  padding: 1px var(--space-2);
  border-radius: var(--radius-full);
  font-size: var(--font-size-2xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.ga-badge--type {
  background: var(--color-accent-10);
  color: var(--color-accent);
}
.ga-badge--status {
  background: var(--color-surface-alt);
  color: var(--color-text-muted);
}

.level--manual { background: var(--color-surface-alt); color: var(--color-text-muted); }
.level--assisted { background: var(--color-warning-10); color: var(--color-warning); }
.level--auto { background: var(--color-success-10); color: var(--color-success); }

.ga-conf {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  font-weight: 600;
}
.conf--low { color: var(--color-danger); }
.conf--mid { color: var(--color-warning); }
.conf--high { color: var(--color-success); }

/* ── Expanded Row ──────────────────────────────────────────────────────── */
.ga-expand-row td {
  padding: 0;
  border-bottom: 1px solid var(--color-border);
}

.ga-expand {
  background: var(--color-surface-alt);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.ga-dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--space-1) var(--space-4);
  font-size: var(--font-size-xs);
  margin: 0;
}
.ga-dl dt {
  color: var(--color-text-muted);
  font-weight: 600;
}
.ga-dl dd { margin: 0; }

.ga-expand__sub {
  margin: var(--space-2) 0 var(--space-1);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.ga-expand__text {
  font-size: var(--font-size-sm);
  line-height: 1.5;
  margin: 0;
}

.ga-expand__pre {
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
.ga-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  padding-top: var(--space-3);
}

.ga-page-info {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

/* ── States ────────────────────────────────────────────────────────────── */
.ga-error {
  color: var(--color-danger);
  padding: var(--space-3);
  background: var(--color-danger-10);
  border-radius: var(--radius-sm);
}

.ga-empty {
  text-align: center;
  color: var(--color-text-muted);
  padding: var(--space-8) 0;
}

.ga-skeleton-wrap {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.ga-skeleton-row {
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
  .ga-filters { flex-direction: column; }
  .ga-stats { grid-template-columns: repeat(2, 1fr); }
}
</style>
