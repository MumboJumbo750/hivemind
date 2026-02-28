<script setup lang="ts">
import {
  DropdownMenuRoot,
  DropdownMenuTrigger,
  DropdownMenuPortal,
  DropdownMenuContent,
  DropdownMenuItem,
} from 'reka-ui'

const props = defineProps<{
  items: Array<{ label: string; value: string; icon?: string; disabled?: boolean }>
  modelValue?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [string] }>()
</script>

<template>
  <DropdownMenuRoot>
    <DropdownMenuTrigger as-child>
      <slot name="trigger" />
    </DropdownMenuTrigger>
    <DropdownMenuPortal>
      <DropdownMenuContent class="hm-dropdown-content" :side-offset="4">
        <DropdownMenuItem
          v-for="item in props.items"
          :key="item.value"
          class="hm-dropdown-item"
          :class="{ 'hm-dropdown-item--active': item.value === props.modelValue, 'hm-dropdown-item--disabled': item.disabled }"
          :disabled="item.disabled"
          @select="emit('update:modelValue', item.value)"
        >
          <span v-if="item.icon" class="hm-dropdown-item-icon">{{ item.icon }}</span>
          {{ item.label }}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenuPortal>
  </DropdownMenuRoot>
</template>

<style scoped>
.hm-dropdown-content {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-1);
  min-width: 160px;
  z-index: var(--z-tooltip);
  box-shadow: var(--shadow-md);
}

.hm-dropdown-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  font-size: var(--font-size-sm);
  cursor: pointer;
  outline: none;
}
.hm-dropdown-item:hover,
.hm-dropdown-item[data-highlighted] {
  background: var(--color-surface-alt);
  color: var(--color-accent);
}
.hm-dropdown-item--active {
  color: var(--color-accent);
}
.hm-dropdown-item--disabled {
  color: var(--color-text-muted);
  cursor: not-allowed;
}

.hm-dropdown-item-icon {
  font-size: var(--font-size-base);
}
</style>
