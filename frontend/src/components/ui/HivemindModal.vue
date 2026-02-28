<script setup lang="ts">
import {
  DialogRoot,
  DialogPortal,
  DialogOverlay,
  DialogContent,
  DialogTitle,
  DialogClose,
} from 'reka-ui'

const props = withDefaults(defineProps<{
  modelValue: boolean
  title?: string
  size?: 'sm' | 'md' | 'lg'
}>(), { size: 'md' })

const emit = defineEmits<{ 'update:modelValue': [boolean] }>()

const maxWidthMap = {
  sm: '400px',
  md: '560px',
  lg: '760px',
}
</script>

<template>
  <DialogRoot :open="props.modelValue" @update:open="emit('update:modelValue', $event)">
    <DialogPortal>
      <DialogOverlay class="hm-modal-overlay" />
      <DialogContent
        class="hm-modal-content"
        :style="{ maxWidth: maxWidthMap[props.size ?? 'md'] }"
      >
        <DialogTitle v-if="props.title" class="hm-modal-title">
          {{ props.title }}
        </DialogTitle>
        <div class="hm-modal-body">
          <slot />
        </div>
        <div v-if="$slots.footer" class="hm-modal-footer">
          <slot name="footer" />
        </div>
        <DialogClose class="hm-modal-close" aria-label="Schließen">✕</DialogClose>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style scoped>
.hm-modal-overlay {
  position: fixed;
  inset: 0;
  background: var(--modal-backdrop);
  z-index: var(--z-modal);
}

.hm-modal-content {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: calc(100% - var(--space-8));
  background: var(--modal-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  z-index: calc(var(--z-modal) + 1);
}

.hm-modal-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-xl);
  color: var(--color-text);
  margin: 0 0 var(--space-4);
}

.hm-modal-body {
  color: var(--color-text);
}

.hm-modal-footer {
  display: flex;
  gap: var(--space-3);
  justify-content: flex-end;
  margin-top: var(--space-4);
}

.hm-modal-close {
  position: absolute;
  top: var(--space-4);
  right: var(--space-4);
  background: transparent;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: var(--font-size-base);
  padding: var(--space-1);
  border-radius: var(--radius-sm);
}
.hm-modal-close:hover {
  color: var(--color-text);
  background: var(--color-surface-alt);
}
</style>
