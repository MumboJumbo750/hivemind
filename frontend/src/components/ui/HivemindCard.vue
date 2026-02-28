<script setup lang="ts">
withDefaults(defineProps<{
  variant?: 'default' | 'elevated' | 'outlined'
}>(), { variant: 'default' })
</script>

<template>
  <div class="hm-card" :class="`hm-card--${variant}`">
    <slot />
  </div>
</template>

<style scoped>
.hm-card {
  background: var(--card-bg);
  border: var(--card-border);
  border-radius: var(--card-radius);
  padding: var(--space-4);
}
.hm-card--elevated { box-shadow: var(--shadow-md); }
.hm-card--outlined { background: transparent; }
</style>
