<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '../../api'
import type { KpiSummaryResponse } from '../../api/types'
import KpiCard from '../../components/domain/KpiCard.vue'

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

onMounted(() => {
  void load(false)
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

@keyframes kpi-shimmer {
  from { background-position: 200% 0; }
  to { background-position: -200% 0; }
}

@media (max-width: 900px) {
  .kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 600px) {
  .kpi-view {
    padding: var(--space-4);
  }

  .kpi-grid {
    grid-template-columns: 1fr;
  }
}
</style>
