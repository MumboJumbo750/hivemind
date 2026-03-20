<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { api } from '../../api'
import type { KpiHistoryResponse, KpiSummaryResponse } from '../../api/types'
import KpiCard from '../../components/domain/KpiCard.vue'

// ── Summary (existing) ──────────────────────────────────────────────────────

const data = ref<KpiSummaryResponse | null>(null)
const loading = ref(true)
const error = ref('')
const refreshing = ref(false)
let pollHandle: ReturnType<typeof globalThis.setInterval> | null = null

async function load(manual = false): Promise<void> {
  const isInitial = data.value === null

  if (manual || !isInitial) {
    refreshing.value = true
  } else {
    loading.value = true
  }

  error.value = ''

  try {
    data.value = await api.getKpiSummary()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'KPI load failed'
  } finally {
    if (manual || !isInitial) {
      refreshing.value = false
    } else {
      loading.value = false
    }
  }
}

const lastUpdatedText = computed(() => {
  const iso = data.value?.computed_at
  if (!iso) return 'Last updated: unknown'

  const updatedAt = new Date(iso).getTime()
  if (Number.isNaN(updatedAt)) return 'Last updated: unknown'

  const diffMinutes = Math.max(0, Math.floor((Date.now() - updatedAt) / 60_000))
  if (diffMinutes === 0) return 'Last updated: just now'
  if (diffMinutes === 1) return 'Last updated: 1 minute ago'
  return `Last updated: ${diffMinutes} minutes ago`
})

function startPolling(): void {
  if (pollHandle) return
  pollHandle = globalThis.setInterval(() => {
    void load(false)
  }, 60_000)
}

function stopPolling(): void {
  if (!pollHandle) return
  globalThis.clearInterval(pollHandle)
  pollHandle = null
}

// ── History / Sparklines (TASK-8-026) ──────────────────────────────────────

const historyDays = ref<7 | 30>(7)
const historyData = ref<KpiHistoryResponse | null>(null)
const historyLoading = ref(false)
const historyError = ref('')

const SERIES_LABELS: Record<string, string> = {
  tasks_done: 'Tasks abgeschlossen',
  tasks_in_progress: 'Tasks in Arbeit',
  cycle_time_avg_hours: 'Durchlaufzeit (h)',
  bug_rate: 'Bug-Rate',
  skill_coverage: 'Skill-Abdeckung',
  review_pass_rate: 'Review-Erfolgsquote',
}

async function loadHistory(): Promise<void> {
  historyLoading.value = true
  historyError.value = ''
  try {
    historyData.value = await api.getKpiHistory(historyDays.value)
  } catch (e: unknown) {
    historyError.value = e instanceof Error ? e.message : 'History load failed'
  } finally {
    historyLoading.value = false
  }
}

/**
 * Compute SVG polyline points string from a value array.
 * The chart area is 200×40 (viewBox units).
 */
function sparklinePoints(values: number[]): string {
  if (values.length === 0) return ''
  const minV = Math.min(...values)
  const maxV = Math.max(...values)
  const range = maxV - minV || 1
  const w = 200
  const h = 40
  const pad = 2
  return values
    .map((v, i) => {
      const x = pad + (i / Math.max(values.length - 1, 1)) * (w - pad * 2)
      const y = (h - pad) - ((v - minV) / range) * (h - pad * 2)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
}

function seriesAllZero(values: number[]): boolean {
  return values.every((v) => v === 0)
}

const seriesEntries = computed(() => {
  if (!historyData.value) return []
  return Object.entries(historyData.value.series).map(([key, points]) => ({
    key,
    label: SERIES_LABELS[key] ?? key,
    values: points.map((p) => p.value),
    dates: points.map((p) => p.date),
    allZero: seriesAllZero(points.map((p) => p.value)),
    points: sparklinePoints(points.map((p) => p.value)),
  }))
})

watch(historyDays, () => {
  void loadHistory()
})

onMounted(() => {
  void load(false)
  void loadHistory()
  startPolling()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<template>
  <div class="kpi-view">
    <header class="kpi-header">
      <h2 class="kpi-title">KPI Dashboard</h2>
      <button
        class="kpi-refresh"
        :disabled="loading || refreshing"
        @click="load(true)"
      >
        {{ refreshing ? 'Refreshing...' : 'Refresh' }}
      </button>
    </header>

    <p v-if="error" class="kpi-error">{{ error }}</p>

    <div v-if="loading && !data" class="kpi-grid" aria-label="KPI skeleton loading">
      <article v-for="index in 6" :key="`skeleton-${index}`" class="kpi-skeleton" aria-hidden="true">
        <div class="skeleton-line skeleton-line--sm" />
        <div class="skeleton-line skeleton-line--lg" />
        <div class="skeleton-line skeleton-line--md" />
      </article>
    </div>

    <div v-else-if="data && data.kpis.length > 0" class="kpi-grid">
      <KpiCard
        v-for="kpi in data.kpis"
        :key="kpi.kpi"
        :kpi="kpi.kpi"
        :value="kpi.value"
        :target="kpi.target"
        :status="kpi.status"
      />
    </div>

    <p v-else class="kpi-empty">No KPI data available.</p>

    <p class="kpi-updated">{{ lastUpdatedText }}</p>

    <!-- ── Time Series Section (TASK-8-026) ─────────────────────────────── -->
    <section class="history-section">
      <div class="history-header">
        <h3 class="history-title">Trend-Verlauf</h3>
        <div class="history-toggle" role="group" aria-label="Zeitraum auswählen">
          <button
            class="toggle-btn"
            :class="{ 'toggle-btn--active': historyDays === 7 }"
            @click="historyDays = 7"
          >
            7 Tage
          </button>
          <button
            class="toggle-btn"
            :class="{ 'toggle-btn--active': historyDays === 30 }"
            @click="historyDays = 30"
          >
            30 Tage
          </button>
        </div>
      </div>

      <p v-if="historyError" class="kpi-error">{{ historyError }}</p>

      <div v-if="historyLoading" class="history-grid">
        <article v-for="i in 6" :key="`hsk-${i}`" class="sparkline-card kpi-skeleton" aria-hidden="true">
          <div class="skeleton-line skeleton-line--sm" />
          <div class="skeleton-line skeleton-line--lg" style="height: 40px" />
        </article>
      </div>

      <div v-else-if="seriesEntries.length > 0" class="history-grid">
        <article
          v-for="series in seriesEntries"
          :key="series.key"
          class="sparkline-card"
        >
          <p class="sparkline-label">{{ series.label }}</p>
          <div v-if="series.allZero" class="sparkline-empty">
            Keine historischen Daten
          </div>
          <template v-else>
            <svg
              class="sparkline-svg"
              viewBox="0 0 200 40"
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              <polyline
                class="sparkline-line"
                :points="series.points"
                fill="none"
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            <div class="sparkline-meta">
              <span class="sparkline-date">{{ series.dates[0] }}</span>
              <span class="sparkline-date">{{ series.dates[series.dates.length - 1] }}</span>
            </div>
          </template>
        </article>
      </div>
    </section>
  </div>
</template>

<style scoped>
.kpi-view {
  padding: var(--space-6);
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.kpi-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
}

.kpi-title {
  margin: 0;
  font-family: var(--font-heading);
  font-size: var(--font-size-xl);
  color: var(--color-text);
}

.kpi-refresh {
  background: color-mix(in srgb, var(--color-accent) 12%, transparent);
  border: 1px solid var(--color-accent);
  color: var(--color-accent);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
}

.kpi-refresh:disabled { opacity: 0.5; cursor: not-allowed; }

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-4);
}

.kpi-skeleton {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  background: color-mix(in srgb, var(--color-surface-alt) 80%, transparent);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.skeleton-line {
  height: 10px;
  border-radius: var(--radius-sm);
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--color-surface-alt) 90%, transparent),
    color-mix(in srgb, var(--color-text-muted) 20%, transparent),
    color-mix(in srgb, var(--color-surface-alt) 90%, transparent)
  );
  background-size: 200% 100%;
  animation: kpi-shimmer 1.2s linear infinite;
}

.skeleton-line--sm { width: 35%; }
.skeleton-line--md { width: 55%; }
.skeleton-line--lg { width: 70%; height: 24px; }

.kpi-empty {
  margin: 0;
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  text-align: center;
  padding: var(--space-8);
}

.kpi-error {
  margin: 0;
  color: var(--color-danger);
  font-size: var(--font-size-sm);
}

.kpi-updated {
  margin: 0;
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  text-align: right;
}

/* ── History / Sparklines ───────────────────────────────────────────────── */

.history-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  border-top: 1px solid var(--color-border);
  padding-top: var(--space-5);
}

.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
}

.history-title {
  margin: 0;
  font-family: var(--font-heading);
  font-size: var(--font-size-lg);
  color: var(--color-text);
}

.history-toggle {
  display: flex;
  gap: var(--space-1);
}

.toggle-btn {
  background: transparent;
  border: 1px solid var(--color-border);
  color: var(--color-text-muted);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  padding: var(--space-1) var(--space-3);
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
}

.toggle-btn:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.toggle-btn--active {
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.history-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-4);
}

.sparkline-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
  background: color-mix(in srgb, var(--color-surface-alt) 60%, transparent);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.sparkline-label {
  margin: 0;
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sparkline-svg {
  width: 100%;
  height: 40px;
  display: block;
}

.sparkline-line {
  stroke: var(--color-accent);
}

.sparkline-empty {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  text-align: center;
  padding: var(--space-3) 0;
  opacity: 0.6;
}

.sparkline-meta {
  display: flex;
  justify-content: space-between;
}

.sparkline-date {
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  color: var(--color-text-muted);
  opacity: 0.7;
}

@keyframes kpi-shimmer {
  from { background-position: 200% 0; }
  to { background-position: -200% 0; }
}

@media (max-width: 900px) {
  .kpi-grid,
  .history-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 600px) {
  .kpi-view {
    padding: var(--space-4);
  }

  .kpi-grid,
  .history-grid {
    grid-template-columns: 1fr;
  }
}
</style>
