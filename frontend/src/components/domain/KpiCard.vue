<script setup lang="ts">
import type { KpiStatus } from '../../api/types'

const props = defineProps<{
  kpi: string
  value: number
  target: number
  status: KpiStatus
}>()

const KPI_META: Record<string, { label: string; format: (v: number, t: number) => string }> = {
  routing_precision: { label: 'Routing Precision', format: (v) => `${v.toFixed(1)} %` },
  median_time_to_scoped_hours: { label: 'Median Time to Scoped', format: (v) => `${v.toFixed(1)} h` },
  tasks_no_reopen_pct: { label: 'Tasks Without Reopen', format: (v) => `${v.toFixed(1)} %` },
  decision_requests_in_sla_pct: { label: 'Decision Requests in SLA', format: (v) => `${v.toFixed(1)} %` },
  skill_proposals_72h_pct: { label: 'Skill Proposals <= 72h', format: (v) => `${v.toFixed(1)} %` },
  unauthorized_writes_count: { label: 'Unauthorized Writes', format: (v) => String(Math.round(v)) },
}

function meta(kpi: string) {
  return KPI_META[kpi] ?? { label: kpi, format: (v: number) => String(Math.round(v)) }
}

function formatTarget(kpi: string, target: number): string {
  return meta(kpi).format(target, target)
}

function statusClass(status: KpiStatus): string {
  if (status === 'ok') return 'kpi-card--good'
  if (status === 'warn') return 'kpi-card--warn'
  return 'kpi-card--bad'
}

function dotClass(status: KpiStatus): string {
  if (status === 'ok') return 'dot--good'
  if (status === 'warn') return 'dot--warn'
  return 'dot--bad'
}
</script>

<template>
  <article :class="['kpi-card', statusClass(props.status)]">
    <div class="kpi-card__header">
      <span :class="['kpi-dot', dotClass(props.status)]" />
      <span class="kpi-card__label">{{ meta(props.kpi).label }}</span>
      <span class="kpi-card__status">{{ props.status.toUpperCase() }}</span>
    </div>
    <strong class="kpi-card__value">{{ meta(props.kpi).format(props.value, props.target) }}</strong>
    <div class="kpi-card__target">
      Target: {{ formatTarget(props.kpi, props.target) }}
    </div>
  </article>
</template>

<style scoped>
.kpi-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  background: linear-gradient(
    145deg,
    color-mix(in srgb, var(--color-surface-alt) 80%, transparent),
    color-mix(in srgb, var(--color-bg) 90%, transparent)
  );
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.kpi-card--good { border-color: color-mix(in srgb, var(--color-success) 40%, var(--color-border)); }
.kpi-card--warn { border-color: color-mix(in srgb, var(--color-warning) 40%, var(--color-border)); }
.kpi-card--bad  { border-color: color-mix(in srgb, var(--color-danger) 40%, var(--color-border)); }

.kpi-card__header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.kpi-card__label {
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
}

.kpi-card__status {
  margin-left: auto;
  font-size: 10px;
  font-family: var(--font-mono);
  letter-spacing: 0.06em;
  color: var(--color-text-muted);
}

.kpi-card__value {
  font-size: var(--font-size-2xl);
  font-family: var(--font-mono);
  color: var(--color-text);
}

.kpi-card__target {
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  color: var(--color-text-muted);
  border-top: 1px solid var(--color-border);
  padding-top: var(--space-1);
}

.kpi-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dot--good {
  background: var(--color-success);
  box-shadow: 0 0 8px color-mix(in srgb, var(--color-success) 60%, transparent);
}

.dot--warn {
  background: var(--color-warning);
  box-shadow: 0 0 8px color-mix(in srgb, var(--color-warning) 60%, transparent);
}

.dot--bad {
  background: var(--color-danger);
  box-shadow: 0 0 8px color-mix(in srgb, var(--color-danger) 60%, transparent);
}
</style>
