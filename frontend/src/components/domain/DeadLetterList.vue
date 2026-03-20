<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { api } from '../../api'
import type { DeadLetterItem } from '../../api/types'

const emit = defineEmits<{
  (e: 'count-updated', value: number): void
}>()

const items = ref<DeadLetterItem[]>([])
const total = ref(0)
const badgeTotal = ref(0)
const loading = ref(false)
const error = ref('')
const nextCursor = ref<string | null>(null)
const limit = 20
const systemFilter = ref('')
const actionLoading = ref<string | null>(null)
const actionError = ref('')

let eventSource: EventSource | null = null
let refreshTimer: ReturnType<typeof setTimeout> | null = null

function setTotal(value: number): void {
  total.value = Math.max(0, value)
}

function setBadgeTotal(value: number): void {
  badgeTotal.value = Math.max(0, value)
  emit('count-updated', badgeTotal.value)
}

async function refreshBadgeTotal(): Promise<void> {
  try {
    const res = await api.getDeadLetters({ limit: 1 })
    setBadgeTotal(res.total)
  } catch {
    // Keep the last badge value if global count fetch fails.
  }
}

function scheduleRefresh(): void {
  if (refreshTimer !== null) return
  refreshTimer = setTimeout(() => {
    refreshTimer = null
    void load(true)
  }, 180)
}

async function load(reset = false): Promise<void> {
  if (reset) nextCursor.value = null
  loading.value = true
  error.value = ''
  try {
    const res = await api.getDeadLetters({
      system: systemFilter.value || undefined,
      cursor: reset ? undefined : (nextCursor.value ?? undefined),
      limit,
    })
    items.value = reset ? res.items : [...items.value, ...res.items]
    setTotal(res.total)
    nextCursor.value = res.next_cursor
    if (systemFilter.value) {
      await refreshBadgeTotal()
    } else {
      setBadgeTotal(res.total)
    }
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Ladefehler'
  } finally {
    loading.value = false
  }
}

async function requeue(id: string): Promise<void> {
  const previousItems = [...items.value]
  const previousTotal = total.value
  const previousBadgeTotal = badgeTotal.value
  const previousCursor = nextCursor.value
  const hadItem = items.value.some((item) => item.id === id)

  if (hadItem) {
    items.value = items.value.filter((item) => item.id !== id)
    setTotal(previousTotal - 1)
    setBadgeTotal(previousBadgeTotal - 1)
  }

  actionLoading.value = id
  actionError.value = ''
  try {
    await api.requeueDeadLetter(id)
    if (hadItem && items.value.length < limit && nextCursor.value) {
      void load(false)
    }
  } catch (e: unknown) {
    if (hadItem) {
      items.value = previousItems
      setTotal(previousTotal)
      setBadgeTotal(previousBadgeTotal)
      nextCursor.value = previousCursor
    }
    actionError.value = e instanceof Error ? e.message : 'Requeue fehlgeschlagen'
  } finally {
    actionLoading.value = null
  }
}

async function discard(id: string): Promise<void> {
  if (!confirm('Dead Letter verwerfen?')) return
  const previousBadgeTotal = badgeTotal.value
  actionLoading.value = id
  actionError.value = ''
  try {
    await api.discardDeadLetter(id)
    const before = items.value.length
    items.value = items.value.filter((item) => item.id !== id)
    if (items.value.length < before) {
      setTotal(total.value - 1)
      setBadgeTotal(previousBadgeTotal - 1)
    }
  } catch (e: unknown) {
    setBadgeTotal(previousBadgeTotal)
    actionError.value = e instanceof Error ? e.message : 'Discard fehlgeschlagen'
  } finally {
    actionLoading.value = null
  }
}

function connectSSE(): void {
  const baseUrl = (import.meta.env.VITE_API_URL as string) ?? 'http://localhost:8000'
  eventSource = new EventSource(`${baseUrl}/api/events/triage`)
  eventSource.addEventListener('triage_dlq_updated', () => scheduleRefresh())
  // Legacy DLQ events are still emitted by the backend and should refresh the list as well.
  eventSource.addEventListener('dlq_requeued', () => scheduleRefresh())
  eventSource.addEventListener('dlq_discarded', () => scheduleRefresh())
}

function loadMore(): void {
  if (!nextCursor.value) return
  void load(false)
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '–'
  return new Date(iso).toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' })
}

onMounted(() => {
  void load(true)
  connectSSE()
})

onUnmounted(() => {
  eventSource?.close()
  if (refreshTimer !== null) clearTimeout(refreshTimer)
})
</script>

<template>
  <div class="dlq-list">
    <div class="dlq-toolbar">
      <select
        v-model="systemFilter"
        class="dlq-select"
        @change="load(true)"
      >
        <option value="">Alle Systeme</option>
        <option value="youtrack">YouTrack</option>
        <option value="sentry">Sentry</option>
      </select>
      <span class="dlq-count">{{ total }} Einträge gesamt</span>
      <button
        class="dlq-refresh"
        :disabled="loading"
        @click="load(true)"
      >
        Aktualisieren
      </button>
    </div>

    <p v-if="actionError" class="dlq-error">{{ actionError }}</p>
    <p v-if="error" class="dlq-error">{{ error }}</p>
    <p v-if="loading && items.length === 0" class="dlq-empty">Lade Dead Letters…</p>
    <div v-else-if="!loading && items.length === 0" class="dlq-empty dlq-empty--ok">
      <span class="dlq-status-indicator" aria-hidden="true"></span>
      <span>Sektor stabil: Keine Dead Letters im Hyperraum-Kanal.</span>
    </div>

    <ul v-else class="dlq-items">
      <li
        v-for="item in items"
        :key="item.id"
        class="dlq-item"
      >
        <div class="dlq-item__header">
          <span class="dlq-system">{{ item.system }}</span>
          <span class="dlq-entity">{{ item.entity_type }}</span>
          <span class="dlq-attempts">Attempts: {{ item.attempts }}</span>
          <span class="dlq-time">{{ formatDate(item.failed_at) }}</span>
          <span v-if="item.requeued_at" class="dlq-requeued">
            Requeued: {{ formatDate(item.requeued_at) }}
          </span>
        </div>
        <p v-if="item.last_error || item.error" class="dlq-item__error">{{ item.last_error || item.error }}</p>
        <p v-if="item.payload_preview" class="dlq-item__payload">{{ item.payload_preview }}</p>
        <div class="dlq-item__actions">
          <button
            class="dlq-btn dlq-btn--primary"
            :disabled="actionLoading === item.id"
            @click="requeue(item.id)"
          >
            {{ actionLoading === item.id ? '…' : 'Requeue' }}
          </button>
          <button
            class="dlq-btn dlq-btn--danger"
            :disabled="actionLoading === item.id"
            @click="discard(item.id)"
          >
            Verwerfen
          </button>
        </div>
      </li>
    </ul>

    <button
      v-if="nextCursor && !loading"
      class="dlq-load-more"
      @click="loadMore"
    >
      Mehr laden ({{ items.length }} / {{ total }})
    </button>
  </div>
</template>

<style scoped>
.dlq-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.dlq-toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.dlq-select {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  padding: var(--space-1) var(--space-2);
}

.dlq-count {
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
}

.dlq-refresh {
  margin-left: auto;
  background: color-mix(in srgb, var(--color-accent) 12%, transparent);
  border: 1px solid var(--color-accent);
  color: var(--color-accent);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  padding: var(--space-1) var(--space-3);
  cursor: pointer;
}

.dlq-refresh:disabled { opacity: 0.5; cursor: not-allowed; }

.dlq-items {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.dlq-item {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-alt);
  padding: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.dlq-item__header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.dlq-system {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  font-weight: 700;
  padding: 1px var(--space-1-5);
  border-radius: var(--radius-xs);
  background: color-mix(in srgb, var(--color-danger) 15%, transparent);
  color: var(--color-danger);
  text-transform: uppercase;
}

.dlq-entity {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.dlq-time {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.dlq-attempts {
  font-size: var(--font-size-xs);
  color: var(--color-warning);
  font-family: var(--font-mono);
}

.dlq-requeued {
  font-size: var(--font-size-xs);
  color: var(--color-success);
  font-family: var(--font-mono);
}

.dlq-item__error {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--color-danger);
  font-family: var(--font-mono);
  word-break: break-word;
}

.dlq-item__payload {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  word-break: break-word;
  background: var(--color-bg);
  border-radius: var(--radius-sm);
  padding: var(--space-2);
}

.dlq-item__actions {
  display: flex;
  gap: var(--space-2);
}

.dlq-btn {
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  cursor: pointer;
  border: 1px solid transparent;
}

.dlq-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.dlq-btn--primary {
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.dlq-btn--danger {
  background: color-mix(in srgb, var(--color-danger) 12%, transparent);
  border-color: var(--color-danger);
  color: var(--color-danger);
}

.dlq-load-more {
  width: 100%;
  padding: var(--space-2);
  background: none;
  border: 1px dashed var(--color-border);
  color: var(--color-text-muted);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  cursor: pointer;
}

.dlq-empty {
  margin: 0;
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  text-align: center;
  padding: var(--space-6);
}

.dlq-empty--ok {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  color: var(--color-success);
}

.dlq-status-indicator {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--color-success);
  box-shadow: 0 0 10px color-mix(in srgb, var(--color-success) 70%, transparent);
}

.dlq-error {
  margin: 0;
  color: var(--color-danger);
  font-size: var(--font-size-sm);
}
</style>
