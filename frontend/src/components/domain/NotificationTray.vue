<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api } from '../../api'
import type { HivemindNotification } from '../../api/types'

const panelOpen = ref(false)
const notifications = ref<HivemindNotification[]>([])
const unreadCount = ref(0)
const loading = ref(false)
let pollInterval: ReturnType<typeof setInterval> | null = null

// ── Priority grouping ────────────────────────────────────────────────────
const groups = computed(() => {
  const action_now: HivemindNotification[] = []
  const soon: HivemindNotification[] = []
  const fyi: HivemindNotification[] = []
  for (const n of notifications.value) {
    if (n.priority === 'action_now') action_now.push(n)
    else if (n.priority === 'soon') soon.push(n)
    else fyi.push(n)
  }
  return [
    { key: 'action_now', label: 'ACTION NOW', items: action_now, color: 'danger' },
    { key: 'soon', label: 'SOON', items: soon, color: 'warning' },
    { key: 'fyi', label: 'FYI', items: fyi, color: 'muted' },
  ].filter(g => g.items.length > 0)
})

// ── Loaders ──────────────────────────────────────────────────────────────
async function loadNotifications() {
  try {
    notifications.value = await api.getNotifications({ limit: 50 })
  } catch {
    /* fallback: keep previous */
  }
}

async function loadUnreadCount() {
  try {
    const res = await api.getUnreadCount()
    unreadCount.value = res.count
  } catch {
    /* ignore */
  }
}

async function refresh() {
  await Promise.all([loadNotifications(), loadUnreadCount()])
}

async function markRead(n: HivemindNotification) {
  if (n.read) return
  try {
    await api.markNotificationRead(n.id)
    n.read = true
    unreadCount.value = Math.max(0, unreadCount.value - 1)
  } catch {
    /* ignore */
  }
}

async function markAllRead() {
  const unread = notifications.value.filter(n => !n.read)
  await Promise.all(unread.map(n => markRead(n)))
}

function iconForType(type: string): string {
  switch (type) {
    case 'sla_warning': return '⏰'
    case 'sla_breach': return '🚨'
    case 'sla_admin_fallback': return '🛡️'
    case 'decision_request': return '❓'
    case 'decision_escalated_backup': return '⚠️'
    case 'decision_escalated_admin': return '⛔'
    case 'escalation': return '🔺'
    case 'skill_proposal': return '💡'
    case 'skill_merged': return '✅'
    case 'task_done': return '🏁'
    case 'dead_letter': return '💀'
    case 'guard_failed': return '❌'
    case 'task_assigned': return '📋'
    case 'review_requested': return '🔍'
    default: return '📌'
  }
}

function nextActionForType(type: string): string {
  switch (type) {
    case 'sla_warning': return 'Epic prüfen und Blockaden beseitigen'
    case 'sla_breach': return 'Sofort eingreifen – SLA überschritten'
    case 'sla_admin_fallback': return 'Admin-Eingriff: Epic manuell priorisieren'
    case 'decision_request': return 'Entscheidung treffen in Decision Request'
    case 'decision_escalated_backup': return 'Überfällige Entscheidung übernehmen'
    case 'decision_escalated_admin': return 'Admin: Eskalierte Entscheidung auflösen'
    case 'escalation': return 'Eskalation prüfen und de-eskalieren'
    case 'skill_proposal': return 'Skill-Vorschlag begutachten'
    case 'skill_merged': return 'Keine Aktion nötig'
    case 'task_done': return 'Keine Aktion nötig'
    case 'dead_letter': return 'DLQ-Eintrag prüfen und manuell beheben'
    case 'guard_failed': return 'Guard-Fehler beheben und erneut einreichen'
    case 'task_assigned': return 'Task beginnen'
    case 'review_requested': return 'Review durchführen'
    default: return ''
  }
}

function formatTime(ts: string): string {
  try {
    const d = new Date(ts)
    const now = Date.now()
    const diff = now - d.getTime()
    if (diff < 60_000) return 'jetzt'
    if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m`
    if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h`
    return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })
  } catch {
    return ''
  }
}

// ── SSE Live Updates ─────────────────────────────────────────────────────
let eventSource: EventSource | null = null

function connectSSE() {
  const baseUrl = (import.meta.env.VITE_API_URL as string) ?? 'http://localhost:8000'
  try {
    eventSource = new EventSource(`${baseUrl}/api/events/notifications`)
    eventSource.addEventListener('notification', () => {
      refresh()
    })
    eventSource.onerror = () => {
      eventSource?.close()
      eventSource = null
    }
  } catch {
    /* SSE not available — fallback to polling */
  }
}

onMounted(() => {
  refresh()
  connectSSE()
  pollInterval = setInterval(refresh, 30_000)
})

onUnmounted(() => {
  if (pollInterval) clearInterval(pollInterval)
  eventSource?.close()
})
</script>

<template>
  <div class="notif-tray">
    <button
      class="notif-tray__bell"
      :class="{ 'notif-tray__bell--active': unreadCount > 0 }"
      @click="panelOpen = !panelOpen"
      title="Notifications"
    >
      🔔
      <span v-if="unreadCount > 0" class="notif-tray__count">
        {{ unreadCount > 99 ? '99+' : unreadCount }}
      </span>
    </button>

    <div v-if="panelOpen" class="notif-tray__panel">
      <div class="notif-tray__header">
        <span class="notif-tray__title">Notifications</span>
        <div class="notif-tray__actions">
          <button
            v-if="unreadCount > 0"
            class="notif-tray__mark-all"
            @click="markAllRead"
            title="Alle als gelesen markieren"
          >✓ Alle</button>
          <button class="notif-tray__close" @click="panelOpen = false">✕</button>
        </div>
      </div>

      <div v-if="notifications.length === 0" class="notif-tray__empty">
        Keine Notifications
      </div>

      <div v-else class="notif-tray__groups">
        <div v-for="group in groups" :key="group.key" class="notif-group">
          <div :class="['notif-group__label', `notif-group__label--${group.color}`]">
            {{ group.label }}
            <span class="notif-group__count">{{ group.items.length }}</span>
          </div>
          <ul class="notif-tray__list">
            <li
              v-for="n in group.items"
              :key="n.id"
              class="notif-tray__item"
              :class="[
                `notif-tray__item--${group.color}`,
                { 'notif-tray__item--unread': !n.read }
              ]"
              @click="markRead(n)"
            >
              <span class="notif-item__icon">{{ iconForType(n.type) }}</span>
              <div class="notif-item__body">
                <span class="notif-item__title">{{ n.title }}</span>
                <span v-if="n.body" class="notif-item__desc">{{ n.body }}</span>
                <span v-if="nextActionForType(n.type)" class="notif-item__action">→ {{ nextActionForType(n.type) }}</span>
                <div class="notif-item__meta">
                  <span class="notif-item__type">{{ n.type }}</span>
                  <span class="notif-item__time">{{ formatTime(n.created_at) }}</span>
                </div>
              </div>
              <span v-if="!n.read" class="notif-item__dot"></span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.notif-tray {
  position: relative;
}

.notif-tray__bell {
  position: relative;
  background: none;
  border: none;
  cursor: pointer;
  font-size: var(--font-size-base);
  padding: var(--space-1);
  border-radius: var(--radius-sm);
  transition: background var(--transition-duration) ease;
  line-height: 1;
}
.notif-tray__bell:hover { background: var(--color-surface-alt); }
.notif-tray__bell--active { animation: bell-ring 0.3s ease; }

@keyframes bell-ring {
  0%, 100% { transform: rotate(0); }
  25% { transform: rotate(8deg); }
  75% { transform: rotate(-8deg); }
}

.notif-tray__count {
  position: absolute;
  top: -2px;
  right: -2px;
  background: var(--color-danger);
  color: white;
  font-size: var(--font-size-2xs);
  font-family: var(--font-mono);
  font-weight: 700;
  min-width: 14px;
  height: 14px;
  border-radius: var(--radius-full);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 var(--space-0-5);
}

.notif-tray__panel {
  position: absolute;
  top: calc(100% + var(--space-2));
  right: 0;
  width: 340px;
  max-height: 480px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  box-shadow: 0 8px 24px rgba(0,0,0,0.5);
  z-index: var(--z-modal);
  display: flex;
  flex-direction: column;
}

.notif-tray__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-3) var(--space-3) var(--space-2);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}

.notif-tray__title {
  font-size: var(--font-size-xs);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.notif-tray__actions {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}

.notif-tray__mark-all {
  background: none;
  border: none;
  color: var(--color-accent);
  cursor: pointer;
  font-size: var(--font-size-2xs);
  font-family: var(--font-mono);
  padding: var(--space-0-5) var(--space-1-5);
  border-radius: var(--radius-xs);
}
.notif-tray__mark-all:hover { background: var(--color-surface-alt); }

.notif-tray__close {
  background: none;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: var(--font-size-xs);
  padding: 0;
}

.notif-tray__empty {
  padding: var(--space-4) var(--space-3);
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  text-align: center;
}

.notif-tray__groups {
  overflow-y: auto;
  flex: 1;
}

.notif-group__label {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  font-size: var(--font-size-2xs);
  font-family: var(--font-mono);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  border-bottom: 1px solid var(--color-border);
}
.notif-group__label--danger  { color: var(--color-danger); }
.notif-group__label--warning { color: var(--color-warning); }
.notif-group__label--muted   { color: var(--color-text-muted); }

.notif-group__count {
  font-size: var(--font-size-2xs);
  background: var(--color-surface-alt);
  padding: 0 var(--space-1-5);
  border-radius: var(--radius-md);
}

.notif-tray__list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.notif-tray__item {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-left: 3px solid transparent;
  cursor: pointer;
  transition: background 0.15s ease;
}
.notif-tray__item:hover { background: var(--color-surface-alt); }
.notif-tray__item--unread { background: color-mix(in srgb, var(--color-accent) 5%, transparent); }
.notif-tray__item--danger  { border-left-color: var(--color-danger); }
.notif-tray__item--warning { border-left-color: var(--color-warning); }
.notif-tray__item--muted   { border-left-color: var(--color-border); }

.notif-item__icon {
  font-size: var(--font-size-sm);
  flex-shrink: 0;
  margin-top: 1px;
}

.notif-item__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-0-5);
  min-width: 0;
  flex: 1;
}

.notif-item__title {
  font-size: var(--font-size-xs);
  color: var(--color-text);
  line-height: 1.4;
}

.notif-item__desc {
  font-size: var(--font-size-2xs);
  color: var(--color-text-muted);
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.notif-item__action {
  font-size: var(--font-size-2xs);
  color: var(--color-accent);
  font-style: italic;
  line-height: 1.3;
}

.notif-item__meta {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}

.notif-item__type {
  font-size: var(--font-size-2xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  background: var(--color-surface-alt);
  padding: 0 var(--space-1);
  border-radius: var(--radius-xs);
}

.notif-item__time {
  font-size: var(--font-size-2xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.notif-item__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-accent);
  flex-shrink: 0;
  margin-top: 4px;
}
</style>
