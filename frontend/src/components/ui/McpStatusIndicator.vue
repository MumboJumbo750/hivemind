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
  gap: var(--space-1-5);
  padding: var(--space-1) var(--space-2-5);
  border-radius: var(--radius-sm);
  background: var(--color-surface-alt);
  font-size: var(--font-size-xs);
  cursor: default;
}

.status-dot {
  font-size: var(--font-size-base);
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
  font-size: var(--font-size-2xs);
}
</style>
