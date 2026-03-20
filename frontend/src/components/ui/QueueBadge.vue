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
  padding: var(--space-0-5) var(--space-2);
  border-radius: var(--radius-xs);
  font-size: var(--font-size-2xs);
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
  background: var(--color-warning-20);
  color: var(--color-warning);
}

.badge-decision {
  background: var(--color-warning-20);
  color: var(--primitive-yellow-400);
}

.badge-sla {
  background: var(--color-danger-20);
  color: var(--color-danger);
}

.badge-followup {
  background: var(--color-info-20);
  color: var(--primitive-blue-400);
}
</style>
