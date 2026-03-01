<script setup lang="ts">
/**
 * NotificationTrayView — Full-page notification view (TASK-6-015).
 *
 * Paginated list with filters by read status, priority, and type.
 * Groups by priority: ACTION NOW / SOON / FYI.
 */
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '../../api'
import type { HivemindNotification } from '../../api/types'
import SlaCountdown from '../../components/ui/SlaCountdown.vue'

const notifications = ref<HivemindNotification[]>([])
const loading = ref(false)
const unreadCount = ref(0)

// Filters
const filterRead = ref<'all' | 'unread' | 'read'>('all')
const filterPriority = ref<'all' | 'action_now' | 'soon' | 'fyi'>('all')
const filterType = ref<string>('all')
const limit = ref(100)
const offset = ref(0)

const NOTIFICATION_TYPES = [
  'sla_warning', 'sla_breach', 'sla_admin_fallback',
  'decision_request', 'decision_escalated_backup', 'decision_escalated_admin',
  'escalation', 'skill_proposal', 'skill_merged', 'task_done',
  'dead_letter', 'guard_failed', 'task_assigned', 'review_requested',
]

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

function priorityLabel(p: string): string {
  if (p === 'action_now') return 'ACTION NOW'
  if (p === 'soon') return 'SOON'
  return 'FYI'
}

function priorityColor(p: string): string {
  if (p === 'action_now') return 'danger'
  if (p === 'soon') return 'warning'
  return 'muted'
}

function formatTime(ts: string): string {
  try {
    const d = new Date(ts)
    return d.toLocaleString('de-DE', { dateStyle: 'medium', timeStyle: 'short' })
  } catch {
    return ''
  }
}

const grouped = computed(() => {
  const groups: Record<string, HivemindNotification[]> = {
    action_now: [],
    soon: [],
    fyi: [],
  }
  for (const n of notifications.value) {
    const p = n.priority || 'fyi'
    if (groups[p]) groups[p].push(n)
    else groups.fyi.push(n)
  }
  return [
    { key: 'action_now', label: 'ACTION NOW', items: groups.action_now, color: 'danger' },
    { key: 'soon', label: 'SOON', items: groups.soon, color: 'warning' },
    { key: 'fyi', label: 'FYI', items: groups.fyi, color: 'muted' },
  ].filter(g => g.items.length > 0)
})

async function loadNotifications() {
  loading.value = true
  try {
    const params: Record<string, string | number> = { limit: limit.value, offset: offset.value }
    if (filterRead.value === 'unread') params.read = 'false'
    else if (filterRead.value === 'read') params.read = 'true'
    if (filterPriority.value !== 'all') params.priority = filterPriority.value
    if (filterType.value !== 'all') params.type = filterType.value
    notifications.value = await api.getNotifications(params)
  } catch { /* keep previous */ }
  loading.value = false
}

async function loadUnreadCount() {
  try {
    const res = await api.getUnreadCount()
    unreadCount.value = res.count
  } catch { /* ignore */ }
}

async function markRead(n: HivemindNotification) {
  if (n.read) return
  try {
    await api.markNotificationRead(n.id)
    n.read = true
    unreadCount.value = Math.max(0, unreadCount.value - 1)
  } catch { /* ignore */ }
}

async function markAllRead() {
  const unread = notifications.value.filter(n => !n.read)
  await Promise.all(unread.map(n => markRead(n)))
}

watch([filterRead, filterPriority, filterType], () => {
  offset.value = 0
  loadNotifications()
})

onMounted(() => {
  loadNotifications()
  loadUnreadCount()
})
</script>

<template>
  <div class="notif-view">
    <header class="notif-view__header">
      <h1>Notifications</h1>
      <span class="notif-view__unread" v-if="unreadCount > 0">{{ unreadCount }} ungelesen</span>
      <button v-if="unreadCount > 0" class="btn btn-sm" @click="markAllRead">✓ Alle als gelesen</button>
    </header>

    <!-- Filters -->
    <div class="notif-view__filters">
      <div class="filter-group">
        <label class="filter-label">Status</label>
        <select v-model="filterRead" class="filter-select">
          <option value="all">Alle</option>
          <option value="unread">Ungelesen</option>
          <option value="read">Gelesen</option>
        </select>
      </div>
      <div class="filter-group">
        <label class="filter-label">Priorität</label>
        <select v-model="filterPriority" class="filter-select">
          <option value="all">Alle</option>
          <option value="action_now">ACTION NOW</option>
          <option value="soon">SOON</option>
          <option value="fyi">FYI</option>
        </select>
      </div>
      <div class="filter-group">
        <label class="filter-label">Typ</label>
        <select v-model="filterType" class="filter-select">
          <option value="all">Alle</option>
          <option v-for="t in NOTIFICATION_TYPES" :key="t" :value="t">{{ t }}</option>
        </select>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="notif-view__loading">Lade Notifications…</div>

    <!-- Empty -->
    <div v-else-if="notifications.length === 0" class="notif-view__empty">
      Keine Notifications gefunden.
    </div>

    <!-- Grouped list -->
    <div v-else class="notif-view__groups">
      <section v-for="group in grouped" :key="group.key" class="notif-group">
        <div :class="['notif-group__header', `notif-group__header--${group.color}`]">
          {{ group.label }}
          <span class="notif-group__count">{{ group.items.length }}</span>
        </div>
        <ul class="notif-group__list">
          <li
            v-for="n in group.items"
            :key="n.id"
            :class="['notif-item', `notif-item--${group.color}`, { 'notif-item--unread': !n.read }]"
            @click="markRead(n)"
          >
            <span class="notif-item__icon">{{ iconForType(n.type) }}</span>
            <div class="notif-item__body">
              <div class="notif-item__title-row">
                <span class="notif-item__title">{{ n.title }}</span>
                <span v-if="!n.read" class="notif-item__dot"></span>
              </div>
              <p v-if="n.body" class="notif-item__desc">{{ n.body }}</p>
              <p v-if="nextActionForType(n.type)" class="notif-item__action">→ {{ nextActionForType(n.type) }}</p>
              <div class="notif-item__meta">
                <span class="notif-item__type-badge">{{ n.type }}</span>
                <span v-if="n.entity_type" class="notif-item__entity">{{ n.entity_type }}</span>
                <span class="notif-item__time">{{ formatTime(n.created_at) }}</span>
                <a v-if="n.link" :href="n.link" class="notif-item__link" @click.stop>Öffnen →</a>
              </div>
            </div>
          </li>
        </ul>
      </section>
    </div>

    <!-- Pagination -->
    <div v-if="notifications.length >= limit" class="notif-view__pagination">
      <button class="btn" :disabled="offset === 0" @click="offset -= limit; loadNotifications()">← Zurück</button>
      <button class="btn" @click="offset += limit; loadNotifications()">Weiter →</button>
    </div>
  </div>
</template>

<style scoped>
.notif-view {
  padding: var(--space-6);
  max-width: 900px;
  margin: 0 auto;
}

.notif-view__header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.notif-view__header h1 {
  font-family: var(--font-heading);
  color: var(--color-text);
  font-size: 1.5rem;
  margin: 0;
}

.notif-view__unread {
  font-size: var(--font-size-sm);
  color: var(--color-accent);
  font-family: var(--font-mono);
}

.notif-view__filters {
  display: flex;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
  flex-wrap: wrap;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.filter-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.filter-select {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  color: var(--color-text);
  border-radius: 4px;
  padding: 4px 8px;
  font-size: var(--font-size-sm);
  min-width: 140px;
}

.notif-view__loading,
.notif-view__empty {
  padding: var(--space-6);
  text-align: center;
  color: var(--color-text-muted);
}

.notif-group {
  margin-bottom: var(--space-4);
}

.notif-group__header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  font-size: 11px;
  font-family: var(--font-mono);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  border-bottom: 1px solid var(--color-border);
  margin-bottom: var(--space-1);
}
.notif-group__header--danger  { color: var(--color-danger); }
.notif-group__header--warning { color: var(--color-warning); }
.notif-group__header--muted   { color: var(--color-text-muted); }

.notif-group__count {
  font-size: 9px;
  background: var(--color-surface-alt);
  padding: 0 5px;
  border-radius: 8px;
}

.notif-group__list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.notif-item {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-3);
  border-left: 3px solid transparent;
  cursor: pointer;
  transition: background 0.15s ease;
  border-bottom: 1px solid color-mix(in srgb, var(--color-border) 40%, transparent);
}
.notif-item:hover { background: var(--color-surface-alt); }
.notif-item--unread { background: color-mix(in srgb, var(--color-accent) 5%, transparent); }
.notif-item--danger  { border-left-color: var(--color-danger); }
.notif-item--warning { border-left-color: var(--color-warning); }
.notif-item--muted   { border-left-color: var(--color-border); }

.notif-item__icon {
  font-size: 18px;
  flex-shrink: 0;
  margin-top: 2px;
}

.notif-item__body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  flex: 1;
}

.notif-item__title-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.notif-item__title {
  font-size: var(--font-size-sm);
  color: var(--color-text);
  font-weight: 500;
}

.notif-item__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-accent);
  flex-shrink: 0;
}

.notif-item__desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  line-height: 1.4;
  margin: 0;
}

.notif-item__action {
  font-size: var(--font-size-xs);
  color: var(--color-accent);
  font-style: italic;
  margin: 0;
}

.notif-item__meta {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  flex-wrap: wrap;
}

.notif-item__type-badge {
  font-size: 9px;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  background: var(--color-surface-alt);
  padding: 1px 5px;
  border-radius: 3px;
}

.notif-item__entity {
  font-size: 9px;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.notif-item__time {
  font-size: 10px;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.notif-item__link {
  font-size: 10px;
  color: var(--color-accent);
  text-decoration: none;
  font-family: var(--font-mono);
}
.notif-item__link:hover { text-decoration: underline; }

.notif-view__pagination {
  display: flex;
  justify-content: center;
  gap: var(--space-3);
  margin-top: var(--space-4);
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
.btn-sm { font-size: 0.75rem; padding: 4px 8px; }
</style>
