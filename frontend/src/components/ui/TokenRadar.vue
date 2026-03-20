<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  current: number
  max: number
  size?: number
  minified?: number | null
}>(), {
  size: 120,
  minified: null,
})

const savings = computed(() => {
  if (!props.minified || props.minified >= props.current) return null
  return props.current - props.minified
})

const percentage = computed(() => Math.min((props.current / props.max) * 100, 100))

const color = computed(() => {
  if (percentage.value > 85) return 'var(--color-danger, #ff4d6d)'
  if (percentage.value > 60) return 'var(--color-warning, #ffb020)'
  return 'var(--color-accent, #20e3ff)'
})

const radius = computed(() => (props.size - 12) / 2)
const circumference = computed(() => 2 * Math.PI * radius.value)
const dashOffset = computed(() => circumference.value * (1 - percentage.value / 100))

const ariaLabel = computed(() =>
  `Token usage: ${props.current} of ${props.max} (${Math.round(percentage.value)}%)`
)
</script>

<template>
  <div
    class="token-radar"
    :style="{ width: `${size}px`, height: `${size}px` }"
    role="meter"
    :aria-label="ariaLabel"
    :aria-valuenow="current"
    :aria-valuemin="0"
    :aria-valuemax="max"
  >
    <svg :width="size" :height="size" :viewBox="`0 0 ${size} ${size}`">
      <!-- Background ring -->
      <circle
        :cx="size / 2"
        :cy="size / 2"
        :r="radius"
        fill="none"
        stroke="var(--color-surface-alt, #162238)"
        stroke-width="8"
      />
      <!-- Progress ring -->
      <circle
        class="progress-ring"
        :cx="size / 2"
        :cy="size / 2"
        :r="radius"
        fill="none"
        :stroke="color"
        stroke-width="8"
        stroke-linecap="round"
        :stroke-dasharray="circumference"
        :stroke-dashoffset="dashOffset"
        :transform="`rotate(-90 ${size / 2} ${size / 2})`"
      />
    </svg>
    <div class="token-label">
      <span class="token-current" :style="{ color }">{{ current.toLocaleString() }}</span>
      <span class="token-separator">/</span>
      <span class="token-max">{{ max.toLocaleString() }}</span>
      <span v-if="savings" class="token-minified" :title="`Minified: ${minified!.toLocaleString()} tokens (-${savings.toLocaleString()})`">
        -{{ savings.toLocaleString() }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.token-radar {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.progress-ring {
  transition: stroke-dashoffset 300ms ease, stroke 300ms ease;
}

.token-label {
  position: absolute;
  display: flex;
  flex-direction: column;
  align-items: center;
  line-height: 1.2;
}

.token-current {
  font-size: var(--font-size-lg);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.token-separator {
  font-size: var(--font-size-2xs);
  color: var(--color-text-muted);
}

.token-max {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-variant-numeric: tabular-nums;
}

.token-minified {
  font-size: var(--font-size-2xs);
  color: var(--color-success, #34d399);
  font-variant-numeric: tabular-nums;
  opacity: 0.85;
}
</style>
