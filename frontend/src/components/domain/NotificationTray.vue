<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '../../api'
import { useClientNotifications } from '../../composables/useClientNotifications'

const notificationMode = ref<string>('client')
const panelOpen = ref(false)

onMounted(async () => {
  try {
    const settings = await api.getSettings()
    notificationMode.value = settings.notification_mode
  } catch {
    // fallback to client mode
  }
})

const { notifications } = useClientNotifications()

function iconForType(type: string): string {
  if (type === 'sla_warning') return '⚠'
  if (type === 'review_requested') return '🔍'
  return '📌'
}

function formatTime(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}
</script>

<template>
  <div v-if="notificationMode === 'client'" class="notif-tray">
    <button
      class="notif-tray__bell"
      :class="{ 'notif-tray__bell--active': notifications.length > 0 }"
      @click="panelOpen = !panelOpen"
      title="Notifications"
    >
      🔔
      <span v-if="notifications.length > 0" class="notif-tray__count">
        {{ notifications.length > 9 ? '9+' : notifications.length }}
      </span>
    </button>

    <div v-if="panelOpen" class="notif-tray__panel">
      <div class="notif-tray__header">
        <span class="notif-tray__title">Notifications</span>
        <button class="notif-tray__close" @click="panelOpen = false">✕</button>
      </div>

      <div v-if="notifications.length === 0" class="notif-tray__empty">
        Keine Notifications
      </div>

      <ul v-else class="notif-tray__list">
        <li
          v-for="n in notifications"
          :key="n.id"
          class="notif-tray__item"
          :class="`notif-tray__item--${n.level} notification--${n.level}`"
        >
          <span class="notif-item__icon">{{ iconForType(n.type) }}</span>
          <div class="notif-item__body">
            <span class="notif-item__title">{{ n.title }}</span>
            <span class="notif-item__time">{{ formatTime(n.timestamp) }}</span>
          </div>
        </li>
      </ul>
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
  font-size: 16px;
  padding: var(--space-1);
  border-radius: var(--radius-sm);
  transition: background var(--transition-duration) ease;
  line-height: 1;
}
.notif-tray__bell:hover { background: var(--color-surface-alt); }

.notif-tray__count {
  position: absolute;
  top: -2px;
  right: -2px;
  background: var(--color-danger);
  color: white;
  font-size: 9px;
  font-family: var(--font-mono);
  font-weight: 700;
  min-width: 14px;
  height: 14px;
  border-radius: 7px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 2px;
}

.notif-tray__panel {
  position: absolute;
  top: calc(100% + var(--space-2));
  right: 0;
  width: 280px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  box-shadow: 0 8px 24px rgba(0,0,0,0.5);
  z-index: 200;
}

.notif-tray__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-3) var(--space-3) var(--space-2);
  border-bottom: 1px solid var(--color-border);
}

.notif-tray__title {
  font-size: var(--font-size-xs);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

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

.notif-tray__list {
  list-style: none;
  margin: 0;
  padding: var(--space-1) 0;
  max-height: 320px;
  overflow-y: auto;
}

.notif-tray__item {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-left: 3px solid transparent;
}
.notif-tray__item--danger  { border-left-color: var(--color-danger); }
.notif-tray__item--warning { border-left-color: var(--color-warning); }
.notif-tray__item--info    { border-left-color: var(--color-accent); }

.notif-item__icon {
  font-size: 14px;
  flex-shrink: 0;
  margin-top: 1px;
}

.notif-item__body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.notif-item__title {
  font-size: var(--font-size-xs);
  color: var(--color-text);
  line-height: 1.4;
}

.notif-item__time {
  font-size: 10px;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}
</style>
