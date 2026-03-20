<script setup lang="ts">
/**
 * ToastContainer — global toast notification overlay.
 * Place once in App.vue.
 */
import { useToast } from '../../composables/useToast'

const { toasts, dismiss } = useToast()
</script>

<template>
  <Teleport to="body">
    <div class="toast-container" v-if="toasts.length">
      <div
        v-for="t in toasts"
        :key="t.id"
        class="toast-item"
        :class="`toast-item--${t.level}`"
        @click="dismiss(t.id)"
      >
        {{ t.message }}
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-container {
  position: fixed;
  top: var(--space-4);
  right: var(--space-4);
  z-index: var(--z-toast);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  max-width: 400px;
}

.toast-item {
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-family: var(--font-body);
  cursor: pointer;
  animation: slideIn 0.2s ease;
  border: 1px solid;
}

.toast-item--success {
  background: var(--color-surface);
  color: var(--color-success);
  border-color: var(--color-success);
}

.toast-item--warning {
  background: var(--color-surface);
  color: var(--color-warning);
  border-color: var(--color-warning);
}

.toast-item--danger {
  background: var(--color-surface);
  color: var(--color-danger);
  border-color: var(--color-danger);
}

.toast-item--info {
  background: var(--color-surface);
  color: var(--color-accent);
  border-color: var(--color-accent);
}

@keyframes slideIn {
  from { transform: translateX(100%); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}
</style>
