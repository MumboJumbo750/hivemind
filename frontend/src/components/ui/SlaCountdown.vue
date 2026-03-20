<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'

const props = defineProps<{
  sla_due_at: string | null | undefined
  /** Show seconds when remaining < 1h (default: true) */
  showSeconds?: boolean
}>()

const now = ref(Date.now())
let interval: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  // Tick every second for accurate countdown with animation
  interval = setInterval(() => { now.value = Date.now() }, 1_000)
})

onUnmounted(() => {
  if (interval !== null) clearInterval(interval)
})

const diffMs = computed(() => {
  if (!props.sla_due_at) return null
  return new Date(props.sla_due_at).getTime() - now.value
})

const label = computed(() => {
  const diff = diffMs.value
  if (diff === null) return ''
  if (diff <= 0) {
    const elapsed = Math.abs(diff)
    const h = Math.floor(elapsed / 3_600_000)
    const m = Math.floor((elapsed % 3_600_000) / 60_000)
    return h > 0 ? `-${h}h ${m}m` : `-${m}m`
  }
  const h = Math.floor(diff / 3_600_000)
  const m = Math.floor((diff % 3_600_000) / 60_000)
  const s = Math.floor((diff % 60_000) / 1_000)
  const showSec = props.showSeconds !== false
  if (h === 0 && showSec) return `${m}m ${s}s`
  return `${h}h ${m}m`
})

const colorClass = computed(() => {
  const diff = diffMs.value
  if (diff === null) return ''
  if (diff <= 0) return 'sla--expired'
  if (diff < 1 * 3_600_000) return 'sla--critical'
  if (diff < 4 * 3_600_000) return 'sla--danger'
  if (diff < 24 * 3_600_000) return 'sla--warning'
  return 'sla--ok'
})

/** Progress bar ratio (1.0 = full, 0.0 = expired). Based on 48h total window. */
const progressRatio = computed(() => {
  const diff = diffMs.value
  if (diff === null) return 1
  if (diff <= 0) return 0
  return Math.min(1, diff / (48 * 3_600_000))
})
</script>

<template>
  <span v-if="sla_due_at" class="sla-countdown" :class="colorClass">
    <span class="sla-countdown__bar" :style="{ width: `${progressRatio * 100}%` }"></span>
    <span class="sla-countdown__label">{{ label }}</span>
  </span>
</template>

<style scoped>
.sla-countdown {
  position: relative;
  display: inline-flex;
  align-items: center;
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  letter-spacing: 0.04em;
  padding: var(--space-0-5) var(--space-2);
  border-radius: var(--radius-sm);
  overflow: hidden;
  transition: color 0.3s ease;
}

.sla-countdown__bar {
  position: absolute;
  left: 0;
  top: 0;
  height: 100%;
  opacity: 0.15;
  transition: width 1s linear, background-color 0.3s ease;
  border-radius: var(--radius-sm);
}

.sla-countdown__label {
  position: relative;
  z-index: 1;
}

.sla--ok              { color: var(--color-success, #3cff9a); }
.sla--ok .sla-countdown__bar { background-color: var(--color-success, #3cff9a); }

.sla--warning         { color: var(--color-warning, #ffb020); }
.sla--warning .sla-countdown__bar { background-color: var(--color-warning, #ffb020); }

.sla--danger          { color: var(--color-danger, #ff4d6d); }
.sla--danger .sla-countdown__bar { background-color: var(--color-danger, #ff4d6d); }

.sla--critical        { color: var(--color-danger, #ff4d6d); font-weight: 700; animation: sla-pulse 1s ease-in-out infinite; }
.sla--critical .sla-countdown__bar { background-color: var(--color-danger, #ff4d6d); }

.sla--expired         { color: var(--color-danger, #ff4d6d); font-weight: 700; animation: sla-pulse 0.6s ease-in-out infinite; }
.sla--expired .sla-countdown__bar { background-color: var(--color-danger, #ff4d6d); width: 100% !important; opacity: 0.25; }

@keyframes sla-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>
