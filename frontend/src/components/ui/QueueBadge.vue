<script setup lang="ts">
const props = defineProps<{
  type: 'escalated' | 'decision' | 'sla' | 'followup'
  detail?: string
}>()

const config = {
  escalated: { label: 'ESCALATED', color: 'badge-escalated' },
  decision: { label: 'DECISION OFFEN', color: 'badge-decision' },
  sla: { label: 'SLA <4h', color: 'badge-sla' },
  followup: { label: 'FOLLOW-UP', color: 'badge-followup' },
}

const badge = config[props.type]
</script>

<template>
  <span
    :class="['queue-badge', badge.color]"
    :title="detail || badge.label"
    role="status"
  >
    {{ badge.label }}
  </span>
</template>

<style scoped>
.queue-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  cursor: pointer;
  transition: opacity 150ms;
}

.queue-badge:hover {
  opacity: 0.8;
}

.badge-escalated {
  background: rgba(255, 176, 32, 0.2);
  color: var(--color-warning, #ffb020);
}

.badge-decision {
  background: rgba(250, 204, 21, 0.2);
  color: #facc15;
}

.badge-sla {
  background: rgba(255, 77, 109, 0.2);
  color: var(--color-danger, #ff4d6d);
}

.badge-followup {
  background: rgba(96, 165, 250, 0.2);
  color: #60a5fa;
}
</style>
