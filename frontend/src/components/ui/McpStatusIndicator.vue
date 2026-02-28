<script setup lang="ts">
import { useMcpStore } from '../../stores/mcpStore'

const mcpStore = useMcpStore()

function formatLastCheck(iso: string | null) {
  if (!iso) return 'Never'
  return new Date(iso).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div
    class="mcp-status"
    :title="`Transport: ${mcpStore.transport}\nTools: ${mcpStore.toolsCount}\nLast check: ${formatLastCheck(mcpStore.lastCheck)}`"
  >
    <span :class="['status-dot', mcpStore.connected ? 'connected' : 'disconnected']">
      {{ mcpStore.connected ? '●' : '◌' }}
    </span>
    <span class="status-text">
      {{ mcpStore.connected ? 'verbunden' : 'getrennt' }}
    </span>
    <span v-if="mcpStore.connected" class="status-tools">{{ mcpStore.toolsCount }} tools</span>
  </div>
</template>

<style scoped>
.mcp-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 4px;
  background: var(--color-surface-alt, #162238);
  font-size: 0.75rem;
  cursor: default;
}

.status-dot {
  font-size: 0.9rem;
}

.connected {
  color: var(--color-success, #3cff9a);
}

.disconnected {
  color: var(--color-danger, #ff4d6d);
}

.status-text {
  color: var(--color-text-muted);
}

.status-tools {
  color: var(--color-text-muted);
  opacity: 0.7;
  font-size: 0.65rem;
}
</style>
