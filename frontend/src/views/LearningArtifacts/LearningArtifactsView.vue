<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../../api'
import type { LearningArtifact, LearningListResponse, LearningStatsResponse } from '../../api/types'

// ── State ───────────────────────────────────────────────────────────────────
const data = ref<LearningListResponse | null>(null)
const stats = ref<LearningStatsResponse | null>(null)
const detail = ref<LearningArtifact | null>(null)
const loading = ref(true)
const error = ref('')

// ── Filters ─────────────────────────────────────────────────────────────────
const filterRole = ref('')
const filterType = ref('')
const filterStatus = ref('')
const filterConfidence = ref(0)
const page = ref(1)
const pageSize = 30

const artifactTypes = ['agent_output', 'review_feedback', 'governance_recommendation', 'execution_learning']
const statusOptions = ['observation', 'proposal', 'suppressed']
const roleOptions = ['worker', 'reviewer', 'gaertner', 'triage', 'stratege', 'architekt']

// ── Load ────────────────────────────────────────────────────────────────────
async function load() {
  loading.value = true
  error.value = ''
  try {
    const params: Record<string, unknown> = { page: page.value, page_size: pageSize }
    if (filterRole.value) params.agent_role = filterRole.value
    if (filterType.value) params.artifact_type = filterType.value
    if (filterStatus.value) params.status = filterStatus.value
    if (filterConfidence.value > 0) params.min_confidence = filterConfidence.value / 100

    data.value = await api.getLearningArtifacts(params as Parameters<typeof api.getLearningArtifacts>[0])
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Fehler beim Laden'
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  try {
    stats.value = await api.getLearningStats()
  } catch { /* stats sind optional */ }
}

function applyFilters() {
  page.value = 1
  void load()
}

function resetFilters() {
  filterRole.value = ''
  filterType.value = ''
  filterStatus.value = ''
  filterConfidence.value = 0
  page.value = 1
  void load()
}

watch(page, () => void load())

onMounted(() => {
  void load()
  void loadStats()
})

// ── Computed ────────────────────────────────────────────────────────────────
const totalPages = computed(() => {
  if (!data.value) return 1
  return Math.max(1, Math.ceil(data.value.total_count / pageSize))
})

// Group stats by type for display cards
const statsByType = computed(() => {
  if (!stats.value) return []
  const map = new Map<string, number>()
  for (const s of stats.value.stats) {
    map.set(s.artifact_type, (map.get(s.artifact_type) ?? 0) + s.count)
  }
  return Array.from(map.entries()).map(([type, count]) => ({ type, count }))
})

// ── Detail Modal ────────────────────────────────────────────────────────────
function openDetail(artifact: LearningArtifact) {
  detail.value = artifact
}

function closeDetail() {
  detail.value = null
}

// ── Helpers ─────────────────────────────────────────────────────────────────
function confidenceClass(c: number | null): string {
  if (c === null) return 'badge--neutral'
  if (c < 0.5) return 'badge--danger'
  if (c < 0.8) return 'badge--warning'
  return 'badge--success'
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('de-DE', {
    day: '2-digit', month: '2-digit', year: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

function typeLabel(t: string): string {
  const labels: Record<string, string> = {
    agent_output: 'Agent Output',
    review_feedback: 'Review Feedback',
    governance_recommendation: 'Governance',
    execution_learning: 'Execution Learning',
  }
  return labels[t] ?? t
}
</script>

<template>
  <div class="la-view">
    <!-- Header -->
    <header class="la-header">
      <h2 class="la-title">Learning Artifacts</h2>
      <button class="la-refresh" @click="load(); loadStats()" :disabled="loading">
        {{ loading ? 'Lade…' : 'Aktualisieren' }}
      </button>
    </header>

    <!-- Stats Panel -->
    <section v-if="stats" class="la-stats">
      <article class="stat-card">
        <span class="stat-card__value">{{ stats.total }}</span>
        <span class="stat-card__label">Gesamt</span>
      </article>
      <article v-for="s in statsByType" :key="s.type" class="stat-card">
        <span class="stat-card__value">{{ s.count }}</span>
        <span class="stat-card__label">{{ typeLabel(s.type) }}</span>
      </article>
      <article class="stat-card stat-card--accent">
        <span class="stat-card__value">{{ stats.skill_candidates }}</span>
        <span class="stat-card__label">Skill Candidates</span>
      </article>
    </section>

    <!-- Filters -->
    <section class="la-filters">
      <select v-model="filterRole" class="la-select" @change="applyFilters">
        <option value="">Alle Rollen</option>
        <option v-for="r in roleOptions" :key="r" :value="r">{{ r }}</option>
      </select>
      <select v-model="filterType" class="la-select" @change="applyFilters">
        <option value="">Alle Typen</option>
        <option v-for="t in artifactTypes" :key="t" :value="t">{{ typeLabel(t) }}</option>
      </select>
      <select v-model="filterStatus" class="la-select" @change="applyFilters">
        <option value="">Alle Status</option>
        <option v-for="s in statusOptions" :key="s" :value="s">{{ s }}</option>
      </select>
      <div class="la-slider-group">
        <label class="la-slider-label">Confidence ≥ {{ filterConfidence }}%</label>
        <input type="range" v-model.number="filterConfidence" min="0" max="100" step="5"
               class="la-slider" @change="applyFilters" />
      </div>
      <button class="la-btn la-btn--ghost" @click="resetFilters">Reset</button>
    </section>

    <!-- Error -->
    <p v-if="error" class="la-error">{{ error }}</p>

    <!-- Loading skeleton -->
    <div v-if="loading && !data" class="la-skeleton-wrap">
      <div v-for="i in 5" :key="i" class="la-skeleton-row">
        <div class="skeleton-line skeleton-line--lg" />
      </div>
    </div>

    <!-- Table -->
    <div v-else-if="data && data.data.length > 0" class="la-table-wrap">
      <table class="la-table">
        <thead>
          <tr>
            <th>Typ</th>
            <th>Status</th>
            <th>Rolle</th>
            <th>Summary</th>
            <th>Confidence</th>
            <th>Erstellt</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in data.data" :key="a.id" class="la-row" @click="openDetail(a)">
            <td><span class="badge badge--type">{{ typeLabel(a.artifact_type) }}</span></td>
            <td><span class="badge badge--status">{{ a.status }}</span></td>
            <td>{{ a.agent_role ?? '–' }}</td>
            <td class="la-summary">{{ a.summary }}</td>
            <td>
              <span v-if="a.confidence !== null" class="badge" :class="confidenceClass(a.confidence)">
                {{ Math.round(a.confidence * 100) }}%
              </span>
              <span v-else class="la-muted">–</span>
            </td>
            <td class="la-date">{{ formatDate(a.created_at) }}</td>
          </tr>
        </tbody>
      </table>

      <!-- Pagination -->
      <div class="la-pagination">
        <button class="la-btn" :disabled="page <= 1" @click="page--">← Zurück</button>
        <span class="la-page-info">Seite {{ page }} / {{ totalPages }} ({{ data.total_count }} Einträge)</span>
        <button class="la-btn" :disabled="!data.has_more" @click="page++">Weiter →</button>
      </div>
    </div>

    <!-- Empty -->
    <p v-else class="la-empty">Keine Learning Artifacts gefunden.</p>

    <!-- Detail Modal -->
    <Teleport to="body">
      <div v-if="detail" class="la-modal-overlay" @click.self="closeDetail">
        <div class="la-modal">
          <header class="la-modal__header">
            <h3>{{ typeLabel(detail.artifact_type) }}</h3>
            <button class="la-modal__close" @click="closeDetail">&times;</button>
          </header>
          <div class="la-modal__body">
            <dl class="la-dl">
              <dt>Status</dt><dd><span class="badge badge--status">{{ detail.status }}</span></dd>
              <dt>Rolle</dt><dd>{{ detail.agent_role ?? '–' }}</dd>
              <dt>Source</dt><dd>{{ detail.source_type }} / {{ detail.source_ref }}</dd>
              <dt>Confidence</dt>
              <dd>
                <span v-if="detail.confidence !== null" class="badge" :class="confidenceClass(detail.confidence)">
                  {{ Math.round(detail.confidence * 100) }}%
                </span>
                <span v-else>–</span>
              </dd>
              <dt>Erstellt</dt><dd>{{ formatDate(detail.created_at) }}</dd>
              <dt v-if="detail.task_id">Task ID</dt>
              <dd v-if="detail.task_id">{{ detail.task_id }}</dd>
              <dt v-if="detail.epic_id">Epic ID</dt>
              <dd v-if="detail.epic_id">{{ detail.epic_id }}</dd>
            </dl>
            <h4 class="la-modal__sub">Summary</h4>
            <p class="la-modal__text">{{ detail.summary }}</p>
            <template v-if="detail.detail">
              <h4 class="la-modal__sub">Detail</h4>
              <pre class="la-modal__pre">{{ JSON.stringify(detail.detail, null, 2) }}</pre>
            </template>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.la-view {
  padding: var(--space-6);
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.la-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.la-title {
  margin: 0;
  font-family: var(--font-heading);
  font-size: var(--font-size-2xl);
  color: var(--color-text);
}

.la-refresh {
  background: var(--color-surface-alt);
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--font-size-sm);
  transition: background var(--transition-duration) ease;
}
.la-refresh:hover:not(:disabled) { background: var(--color-border); }

/* ── Stats ─────────────────────────────────────────────────────────────── */
.la-stats {
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

.stat-card__value {
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--color-text);
  font-family: var(--font-mono);
}
.stat-card--accent .stat-card__value { color: var(--color-accent); }

.stat-card__label {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* ── Filters ───────────────────────────────────────────────────────────── */
.la-filters {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  align-items: end;
}

.la-select {
  background: var(--color-surface);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
  font-size: var(--font-size-sm);
  min-width: 140px;
}

.la-slider-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.la-slider-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.la-slider {
  width: 120px;
  accent-color: var(--color-accent);
}

.la-btn {
  background: var(--color-surface-alt);
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--font-size-sm);
  transition: background var(--transition-duration) ease;
}
.la-btn:hover:not(:disabled) { background: var(--color-border); }
.la-btn:disabled { opacity: 0.4; cursor: default; }
.la-btn--ghost { border-color: transparent; }

/* ── Table ─────────────────────────────────────────────────────────────── */
.la-table-wrap { overflow-x: auto; }

.la-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.la-table th {
  text-align: left;
  padding: var(--space-2) var(--space-3);
  color: var(--color-text-muted);
  font-weight: 600;
  border-bottom: 1px solid var(--color-border);
  font-size: var(--font-size-xs);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.la-table td {
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--color-border);
  vertical-align: middle;
}

.la-row {
  cursor: pointer;
  transition: background var(--transition-duration) ease;
}
.la-row:hover { background: var(--color-surface-alt); }

.la-summary {
  max-width: 400px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.la-date {
  white-space: nowrap;
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
}

.la-muted { color: var(--color-text-muted); }

/* ── Badges ────────────────────────────────────────────────────────────── */
.badge {
  display: inline-block;
  padding: 1px var(--space-2);
  border-radius: var(--radius-full);
  font-size: var(--font-size-2xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.badge--type {
  background: var(--color-accent-10);
  color: var(--color-accent);
}
.badge--status {
  background: var(--color-surface-alt);
  color: var(--color-text-muted);
}
.badge--success {
  background: var(--color-success-10);
  color: var(--color-success);
}
.badge--warning {
  background: var(--color-warning-10);
  color: var(--color-warning);
}
.badge--danger {
  background: var(--color-danger-10);
  color: var(--color-danger);
}
.badge--neutral {
  background: var(--color-surface-alt);
  color: var(--color-text-muted);
}

/* ── Pagination ────────────────────────────────────────────────────────── */
.la-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  padding-top: var(--space-3);
}

.la-page-info {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

/* ── Error / Empty / Skeleton ──────────────────────────────────────────── */
.la-error {
  color: var(--color-danger);
  padding: var(--space-3);
  background: var(--color-danger-10);
  border-radius: var(--radius-sm);
}

.la-empty {
  text-align: center;
  color: var(--color-text-muted);
  padding: var(--space-8) 0;
}

.la-skeleton-wrap {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.la-skeleton-row {
  height: 40px;
  background: var(--color-surface-alt);
  border-radius: var(--radius-sm);
  animation: pulse 1.5s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 1; }
}

/* ── Modal ─────────────────────────────────────────────────────────────── */
.la-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.la-modal {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  width: 90%;
  max-width: 700px;
  max-height: 80vh;
  overflow-y: auto;
}

.la-modal__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-4) var(--space-5);
  border-bottom: 1px solid var(--color-border);
}
.la-modal__header h3 {
  margin: 0;
  font-family: var(--font-heading);
  font-size: var(--font-size-lg);
}

.la-modal__close {
  background: none;
  border: none;
  color: var(--color-text-muted);
  font-size: var(--font-size-2xl);
  cursor: pointer;
  line-height: 1;
}
.la-modal__close:hover { color: var(--color-text); }

.la-modal__body {
  padding: var(--space-5);
}

.la-dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--space-2) var(--space-4);
  font-size: var(--font-size-sm);
  margin: 0;
}
.la-dl dt {
  color: var(--color-text-muted);
  font-weight: 600;
}
.la-dl dd { margin: 0; }

.la-modal__sub {
  margin: var(--space-4) 0 var(--space-2);
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.la-modal__text {
  font-size: var(--font-size-sm);
  line-height: 1.6;
}

.la-modal__pre {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-3);
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  overflow-x: auto;
  max-height: 300px;
}

/* ── Responsive ────────────────────────────────────────────────────────── */
@media (max-width: 768px) {
  .la-filters { flex-direction: column; }
  .la-stats { grid-template-columns: repeat(2, 1fr); }
}
</style>
