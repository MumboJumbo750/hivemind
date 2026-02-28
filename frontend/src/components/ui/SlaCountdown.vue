<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'

const props = defineProps<{
  sla_due_at: string | null | undefined
}>()

const now = ref(Date.now())
let interval: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  interval = setInterval(() => { now.value = Date.now() }, 60_000)
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
  if (diff <= 0) return 'Abgelaufen'
  const h = Math.floor(diff / 3_600_000)
  const m = Math.floor((diff % 3_600_000) / 60_000)
  return `${h}h ${m}m`
})

const colorClass = computed(() => {
  const diff = diffMs.value
  if (diff === null) return ''
  if (diff <= 0) return 'sla--expired'
  if (diff < 4 * 3_600_000) return 'sla--danger'
  if (diff < 24 * 3_600_000) return 'sla--warning'
  return 'sla--muted'
})
</script>

<template>
  <span v-if="sla_due_at" class="sla-countdown" :class="colorClass">{{ label }}</span>
</template>

<style scoped>
.sla-countdown {
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  letter-spacing: 0.04em;
}

.sla--muted   { color: var(--color-text-muted); }
.sla--warning { color: var(--color-warning); }
.sla--danger  { color: var(--color-danger); }
.sla--expired { color: var(--color-danger); font-weight: 700; }
</style>
