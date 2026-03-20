<script setup lang="ts">
/**
 * DecisionRequestDialog — TASK-6-010
 *
 * Modal dialog for resolving a DecisionRequest.
 * Shows the request context, options from payload, SLA timer,
 * and lets the user pick an option + provide rationale.
 *
 * Props:
 *   open      – v-model visibility
 *   request   – DecisionRequest object from API / MCP
 *
 * Emits:
 *   resolved  – after successful resolution
 *   close     – when dialog is dismissed
 */
import { ref, computed, watch } from 'vue'
import { api } from '../../api'
import type { DecisionRequest } from '../../api/types'
import HivemindModal from '../ui/HivemindModal.vue'
import SlaCountdown from '../ui/SlaCountdown.vue'

const props = defineProps<{
  open: boolean
  request: DecisionRequest | null
}>()

const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'resolved'): void
  (e: 'close'): void
}>()

const selectedOption = ref('')
const rationale = ref('')
const loading = ref(false)
const error = ref<string | null>(null)

// Reset form when dialog opens
watch(() => props.open, (val) => {
  if (val) {
    selectedOption.value = ''
    rationale.value = ''
    error.value = null
  }
})

const options = computed<string[]>(() => {
  const p = props.request?.payload
  if (!p) return []
  if (Array.isArray(p.options)) return p.options as string[]
  return []
})

const question = computed(() => {
  return (props.request?.payload?.question as string) || (props.request?.payload?.title as string) || 'Decision Required'
})

const context = computed(() => {
  return (props.request?.payload?.context as string) || ''
})

async function resolve() {
  if (!props.request || !selectedOption.value) return
  loading.value = true
  error.value = null
  try {
    await api.callMcpTool('hivemind-resolve_decision_request', {
      decision_request_id: props.request.id,
      decision: selectedOption.value,
      rationale: rationale.value || undefined,
    })
    emit('resolved')
    emit('update:open', false)
  } catch (e: unknown) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}

function close() {
  emit('update:open', false)
  emit('close')
}
</script>

<template>
  <HivemindModal :modelValue="open" @update:modelValue="$emit('update:open', $event)" title="Decision Request">
    <template v-if="request">
      <div class="dr-dialog">
        <!-- Status / SLA -->
        <div class="dr-dialog__meta">
          <span :class="['dr-state', `dr-state--${request.state}`]">{{ request.state }}</span>
          <SlaCountdown :sla_due_at="request.sla_due_at" />
        </div>

        <!-- Owner / Backup Owner -->
        <div class="dr-dialog__owners">
          <span v-if="request.owner_id" class="dr-owner" title="Owner">
            👤 Owner: {{ request.owner_id.slice(0, 8) }}…
          </span>
          <span v-if="request.backup_owner_id" class="dr-backup-owner" title="Backup Owner">
            👥 Backup: {{ request.backup_owner_id.slice(0, 8) }}…
          </span>
          <span v-else class="dr-no-backup">Kein Backup-Owner</span>
        </div>

        <!-- Question / Context -->
        <h3 class="dr-dialog__question">{{ question }}</h3>
        <p v-if="context" class="dr-dialog__context">{{ context }}</p>

        <!-- Options -->
        <div class="dr-dialog__options">
          <label class="dr-dialog__option-label">Optionen wählen:</label>
          <div class="dr-options-list">
            <button
              v-for="opt in options"
              :key="opt"
              :class="['dr-option', { 'dr-option--selected': selectedOption === opt }]"
              @click="selectedOption = opt"
            >
              <span class="dr-option__radio">{{ selectedOption === opt ? '●' : '○' }}</span>
              {{ opt }}
            </button>
          </div>

          <!-- Free-text fallback when no predefined options -->
          <div v-if="options.length === 0" class="dr-dialog__freetext">
            <label class="dr-dialog__option-label">Entscheidung:</label>
            <input
              v-model="selectedOption"
              type="text"
              class="field-input"
              placeholder="Entscheidung eingeben..."
            />
          </div>
        </div>

        <!-- Rationale -->
        <div class="dr-dialog__rationale">
          <label class="dr-dialog__option-label">Begründung (optional):</label>
          <textarea
            v-model="rationale"
            class="field-textarea"
            rows="3"
            placeholder="Warum diese Entscheidung?"
          ></textarea>
        </div>

        <!-- Error -->
        <div v-if="error" class="dr-dialog__error">{{ error }}</div>
      </div>
    </template>

    <template #footer>
      <button class="btn" @click="close">Abbrechen</button>
      <button
        class="btn btn-primary"
        :disabled="!selectedOption || loading"
        @click="resolve"
      >
        {{ loading ? 'Wird aufgelöst…' : 'Entscheidung treffen' }}
      </button>
    </template>
  </HivemindModal>
</template>

<style scoped>
.dr-dialog {
  display: flex;
  flex-direction: column;
  gap: var(--space-4, 1rem);
}

.dr-dialog__meta {
  display: flex;
  align-items: center;
  gap: var(--space-3, 0.75rem);
}

.dr-state {
  font-size: var(--font-size-2xs);
  font-family: var(--font-mono);
  padding: var(--space-0-5) var(--space-2);
  border-radius: var(--radius-xs);
  text-transform: uppercase;
  font-weight: 600;
}
.dr-state--open { background: var(--color-warning-20); color: var(--color-warning); }
.dr-state--resolved { background: var(--color-success-20); color: var(--color-success); }
.dr-state--expired { background: var(--color-danger-20); color: var(--color-danger); }

.dr-dialog__owners {
  display: flex;
  gap: var(--space-3, 0.75rem);
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  color: var(--color-text-muted);
}
.dr-owner, .dr-backup-owner {
  padding: var(--space-0-5) var(--space-1-5);
  background: var(--color-surface-alt);
  border-radius: var(--radius-xs);
}
.dr-no-backup {
  color: var(--color-text-muted);
  font-style: italic;
  font-size: var(--font-size-2xs);
}

.dr-dialog__question {
  font-family: var(--font-heading);
  font-size: var(--font-size-lg);
  color: var(--color-text);
  margin: 0;
}

.dr-dialog__context {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  line-height: 1.5;
  margin: 0;
}

.dr-dialog__options {
  display: flex;
  flex-direction: column;
  gap: var(--space-2, 0.5rem);
}

.dr-dialog__option-label {
  font-size: var(--font-size-sm);
  color: var(--color-text);
  font-weight: 500;
}

.dr-options-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2, 0.5rem);
}

.dr-option {
  display: flex;
  align-items: center;
  gap: var(--space-2, 0.5rem);
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
  cursor: pointer;
  color: var(--color-text);
  font-size: var(--font-size-sm);
  transition: all 0.15s ease;
  text-align: left;
  width: 100%;
}
.dr-option:hover {
  border-color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 5%, transparent);
}
.dr-option--selected {
  border-color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 10%, transparent);
}

.dr-option__radio {
  color: var(--color-accent);
  font-size: var(--font-size-sm);
}

.dr-dialog__freetext {
  display: flex;
  flex-direction: column;
  gap: var(--space-1, 0.25rem);
}

.dr-dialog__rationale {
  display: flex;
  flex-direction: column;
  gap: var(--space-1, 0.25rem);
}

.field-input {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  padding: var(--space-2);
  font-size: var(--font-size-sm);
  width: 100%;
}

.field-textarea {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  padding: var(--space-2);
  font-size: var(--font-size-sm);
  width: 100%;
  resize: vertical;
  font-family: inherit;
}

.dr-dialog__error {
  color: var(--color-danger);
  font-size: var(--font-size-sm);
  padding: var(--space-2, 0.5rem);
  background: color-mix(in srgb, var(--color-danger) 10%, transparent);
  border-radius: var(--radius-sm);
}

.btn {
  padding: var(--space-1-5) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
  font-size: var(--font-size-sm);
  transition: all 150ms;
}
.btn:hover { background: var(--color-surface-alt); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: var(--color-accent); color: var(--color-bg); border-color: var(--color-accent); }
</style>
