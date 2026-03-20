<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { api } from '../api'
import type { SyncProviderState, SyncStatusResponse } from '../api/types'

type Severity = 'good' | 'warn' | 'bad'

interface QueueCard {
  key: string
  label: string
  value: number
  severity: Severity
}

const status = ref<SyncStatusResponse | null>(null)
const loading = ref(true)
const refreshing = ref(false)
const error = ref('')

let pollHandle: ReturnType<typeof globalThis.setInterval> | null = null

async function loadStatus(manual = false): Promise<void> {
  if (manual) refreshing.value = true
  else loading.value = true
  error.value = ''

  try {
    status.value = await api.getSyncStatus()
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Sync status could not be loaded'
  } finally {
    if (manual) refreshing.value = false
    else loading.value = false
  }
}

function backlogSeverity(count: number, warnAt: number, badAt: number): Severity {
  if (count >= badAt) return 'bad'
  if (count >= warnAt) return 'warn'
  return 'good'
}

function deliveredSeverity(count: number): Severity {
  if (count === 0) return 'warn'
  return 'good'
}

const queueCards = computed<QueueCard[]>(() => {
  if (!status.value) return []
  const queue = status.value.queue
  return [
    {
      key: 'pending_outbound',
      label: 'Pending outbound',
      value: queue.pending_outbound,
      severity: backlogSeverity(queue.pending_outbound, 8, 20),
    },
    {
      key: 'pending_inbound',
      label: 'Pending inbound',
      value: queue.pending_inbound,
      severity: backlogSeverity(queue.pending_inbound, 10, 25),
    },
    {
      key: 'dead_letters',
      label: 'Dead letters',
      value: queue.dead_letters,
      severity: backlogSeverity(queue.dead_letters, 1, 5),
    },
    {
      key: 'delivered_today',
      label: 'Delivered today',
      value: queue.delivered_today,
      severity: deliveredSeverity(queue.delivered_today),
    },
  ]
})

function providerSeverity(state: SyncProviderState): Severity {
  if (state === 'online') return 'good'
  if (state === 'degraded' || state === 'not_configured') return 'warn'
  return 'bad'
}

function providerLabel(state: SyncProviderState): string {
  if (state === 'online') return 'Online'
  if (state === 'degraded') return 'Degraded'
  if (state === 'not_configured') return 'Not configured'
  return 'Offline'
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('de-DE', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function formatDuration(value: number | null): string {
  if (value == null) return '-'
  return `${value} ms`
}

function previewError(text: string, max = 120): string {
  if (text.length <= max) return text
  return `${text.slice(0, max)}...`
}

onMounted(() => {
  void loadStatus()
  pollHandle = globalThis.setInterval(() => {
    void loadStatus()
  }, 30000)
})

onUnmounted(() => {
  if (pollHandle) {
    globalThis.clearInterval(pollHandle)
    pollHandle = null
  }
})
</script>

<template>
  <section class="sync-status-panel">
    <header class="panel-header">
      <div>
        <h2 class="panel-title">Sync Status</h2>
        <p class="panel-subtitle">Queue metrics, provider health, and recent sync events.</p>
      </div>
      <button class="refresh-btn" :disabled="loading || refreshing" @click="loadStatus(true)">
        {{ refreshing ? 'Aktualisiere...' : 'Aktualisieren' }}
      </button>
    </header>

    <p v-if="error" class="error-text">{{ error }}</p>
    <p v-if="loading && !status" class="loading-text">Sync status is loading...</p>

    <template v-if="status">
      <div class="queue-grid">
        <article v-for="card in queueCards" :key="card.key" class="queue-card">
          <div class="queue-card__meta">
            <span class="hud-dot" :class="`hud-dot--${card.severity}`" />
            <span class="queue-card__label">{{ card.label }}</span>
          </div>
          <strong class="queue-card__value">{{ card.value }}</strong>
        </article>
      </div>

      <div class="providers">
        <h3 class="section-title">Provider status</h3>
        <div class="provider-grid">
          <article class="provider-card">
            <div class="provider-row">
              <span class="provider-name">Ollama</span>
              <span
                class="provider-badge"
                :class="`provider-badge--${providerSeverity(status.providers.ollama.state)}`"
              >
                {{ providerLabel(status.providers.ollama.state) }}
              </span>
            </div>
            <p class="provider-detail">{{ status.providers.ollama.detail ?? 'No detail' }}</p>
          </article>

          <article class="provider-card">
            <div class="provider-row">
              <span class="provider-name">YouTrack</span>
              <span
                class="provider-badge"
                :class="`provider-badge--${providerSeverity(status.providers.youtrack.state)}`"
              >
                {{ providerLabel(status.providers.youtrack.state) }}
              </span>
            </div>
            <p class="provider-detail">{{ status.providers.youtrack.detail ?? 'No detail' }}</p>
          </article>
        </div>
      </div>

      <div class="lists-grid">
        <section class="list-section">
          <h3 class="section-title">Last delivered (10)</h3>
          <p v-if="status.recent_delivered.length === 0" class="empty-text">No delivered entries found.</p>
          <ul v-else class="list">
            <li v-for="item in status.recent_delivered" :key="item.id" class="list-row">
              <span class="list-time">{{ formatDateTime(item.timestamp) }}</span>
              <span class="list-type">{{ item.direction }} / {{ item.payload_type }}</span>
              <span class="list-duration">{{ formatDuration(item.duration_ms) }}</span>
            </li>
          </ul>
        </section>

        <section class="list-section">
          <h3 class="section-title">Failed or dead (5)</h3>
          <p v-if="status.recent_failed.length === 0" class="empty-text">No failed entries found.</p>
          <ul v-else class="list">
            <li v-for="item in status.recent_failed" :key="item.id" class="list-row list-row--error">
              <div class="error-row">
                <span class="list-time">{{ formatDateTime(item.timestamp) }}</span>
                <span class="list-attempts">attempts: {{ item.attempts }}</span>
                <RouterLink class="dlq-link" :to="item.dlq_url">Open DLQ</RouterLink>
              </div>
              <p class="error-preview">{{ previewError(item.last_error) }}</p>
            </li>
          </ul>
        </section>
      </div>
    </template>
  </section>
</template>

<style scoped>
.sync-status-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
}

.panel-title {
  margin: 0;
  font-family: var(--font-heading);
  color: var(--color-text);
  font-size: var(--font-size-lg);
}

.panel-subtitle {
  margin: var(--space-1) 0 0;
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.refresh-btn {
  background: color-mix(in srgb, var(--color-accent) 12%, transparent);
  border: 1px solid var(--color-accent);
  color: var(--color-accent);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
}

.refresh-btn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--color-accent) 20%, transparent);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.queue-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-3);
}

.queue-card {
  border: 1px solid var(--color-border);
  background: linear-gradient(
    145deg,
    color-mix(in srgb, var(--color-surface-alt) 78%, transparent),
    color-mix(in srgb, var(--color-bg) 90%, transparent)
  );
  border-radius: var(--radius-md);
  padding: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.queue-card__meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.queue-card__label {
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-family: var(--font-mono);
}

.queue-card__value {
  color: var(--color-text);
  font-size: var(--font-size-2xl);
  font-family: var(--font-mono);
}

.hud-dot {
  width: 10px;
  height: 10px;
  border-radius: var(--radius-full);
  box-shadow: 0 0 10px transparent;
}

.hud-dot--good {
  background: var(--color-success);
  box-shadow: 0 0 10px color-mix(in srgb, var(--color-success) 55%, transparent);
}

.hud-dot--warn {
  background: var(--color-warning);
  box-shadow: 0 0 10px color-mix(in srgb, var(--color-warning) 55%, transparent);
}

.hud-dot--bad {
  background: var(--color-danger);
  box-shadow: 0 0 10px color-mix(in srgb, var(--color-danger) 55%, transparent);
}

.providers {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.provider-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
}

.provider-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  background: var(--color-surface-alt);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.provider-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.provider-name {
  color: var(--color-text);
  font-family: var(--font-heading);
}

.provider-badge {
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  border-radius: var(--radius-full);
  border: 1px solid var(--color-border);
  padding: var(--space-0-5) var(--space-2);
  text-transform: uppercase;
}

.provider-badge--good {
  color: var(--color-success);
  border-color: color-mix(in srgb, var(--color-success) 50%, var(--color-border));
}

.provider-badge--warn {
  color: var(--color-warning);
  border-color: color-mix(in srgb, var(--color-warning) 50%, var(--color-border));
}

.provider-badge--bad {
  color: var(--color-danger);
  border-color: color-mix(in srgb, var(--color-danger) 50%, var(--color-border));
}

.provider-detail {
  margin: 0;
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  word-break: break-word;
}

.lists-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
}

.list-section {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  background: color-mix(in srgb, var(--color-surface-alt) 88%, transparent);
}

.section-title {
  margin: 0 0 var(--space-2);
  font-family: var(--font-heading);
  font-size: var(--font-size-sm);
  color: var(--color-text);
}

.list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.list-row {
  border: 1px solid color-mix(in srgb, var(--color-border) 50%, transparent);
  border-radius: var(--radius-sm);
  background: var(--color-bg);
  padding: var(--space-2);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.list-row--error {
  align-items: flex-start;
  flex-direction: column;
}

.list-time,
.list-type,
.list-duration,
.list-attempts {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
}

.list-time {
  color: var(--color-text-muted);
}

.list-type {
  color: var(--color-text);
}

.list-duration,
.list-attempts {
  color: var(--color-accent);
}

.error-row {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.error-preview {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  word-break: break-word;
}

.dlq-link {
  color: var(--color-accent);
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  text-decoration: none;
}

.dlq-link:hover {
  text-decoration: underline;
}

.empty-text,
.loading-text {
  margin: 0;
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.error-text {
  margin: 0;
  color: var(--color-danger);
  font-size: var(--font-size-sm);
}

@media (max-width: 1024px) {
  .queue-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .lists-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .panel-header {
    flex-direction: column;
    align-items: stretch;
  }

  .provider-grid,
  .queue-grid {
    grid-template-columns: 1fr;
  }
}
</style>
