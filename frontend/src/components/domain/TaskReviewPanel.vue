<script setup lang="ts">
import { ref, computed } from 'vue'
import { api } from '../../api'
import type { Task } from '../../api/types'

const props = defineProps<{
  task: Task
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'done'): void
}>()

const checkedCriteria = ref<boolean[]>([])
const reviewComment = ref('')
const showRejectComment = ref(false)
const loading = ref(false)
const error = ref<string | null>(null)

// Hard Gates (informative only in Phase 2)
const hardGates = computed(() => [
  {
    label: 'Artifact vorhanden',
    passed: !!props.task.description,
    status: props.task.description ? 'passed' : 'failed',
  },
  {
    label: 'State-Transition gültig (in_review → done)',
    passed: props.task.state === 'in_review',
    status: props.task.state === 'in_review' ? 'passed' : 'failed',
  },
  {
    label: 'Review-Gate aktiv',
    passed: true,
    status: 'passed',
  },
])

async function handleApprove() {
  loading.value = true
  error.value = null
  try {
    await api.approveTask(props.task.task_key)
    emit('done')
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

async function handleReject() {
  if (!reviewComment.value.trim()) {
    showRejectComment.value = true
    return
  }
  loading.value = true
  error.value = null
  try {
    await api.rejectTask(props.task.task_key, reviewComment.value)
    emit('done')
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="review-panel">
    <div class="review-panel__header">
      <div>
        <span class="review-panel__key">{{ task.task_key }}</span>
        <h3 class="review-panel__title">{{ task.title }}</h3>
      </div>
      <button class="review-panel__close" @click="emit('close')">✕</button>
    </div>

    <!-- Hard Gates -->
    <section class="review-section">
      <h4 class="review-section__title">Hard Gates</h4>
      <ul class="gate-list">
        <li
          v-for="gate in hardGates"
          :key="gate.label"
          class="gate-item"
          :class="`gate-item--${gate.status}`"
        >
          <span class="gate-icon">{{ gate.status === 'passed' ? '✓' : '✗' }}</span>
          <span class="gate-label">{{ gate.label }}</span>
          <span class="gate-badge" :class="`gate-badge--${gate.status}`">
            {{ gate.status }}
          </span>
        </li>
      </ul>
    </section>

    <!-- Owner Judgment / DoD Checklist -->
    <section class="review-section">
      <h4 class="review-section__title">Owner Judgment</h4>
      <div v-if="!task.definition_of_done?.criteria?.length" class="review-empty">
        Keine DoD-Kriterien definiert.
      </div>
      <ul v-else class="dod-list">
        <li
          v-for="(criterion, i) in task.definition_of_done?.criteria ?? []"
          :key="i"
          class="dod-item"
        >
          <label class="dod-item__label">
            <input type="checkbox" v-model="checkedCriteria[i]" class="dod-checkbox" />
            <span>{{ criterion }}</span>
          </label>
        </li>
      </ul>
    </section>

    <!-- Reject Comment -->
    <div v-if="showRejectComment" class="review-section">
      <label class="field-label">Ablehnungsgrund <span class="required">*</span></label>
      <textarea
        v-model="reviewComment"
        class="hm-textarea"
        placeholder="Begründung für Ablehnung (Pflichtfeld)"
        rows="3"
        autofocus
      />
    </div>

    <p v-if="error" class="error-text">{{ error }}</p>

    <!-- Actions -->
    <div class="review-actions">
      <button
        class="btn-danger"
        @click="handleReject"
        :disabled="loading"
      >
        ✗ ABLEHNEN
      </button>
      <button
        class="btn-success"
        @click="handleApprove"
        :disabled="loading"
      >
        ✓ GENEHMIGEN
      </button>
    </div>
  </div>
</template>

<style scoped>
.review-panel {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.review-panel__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.review-panel__key {
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  color: var(--color-text-muted);
}

.review-panel__title {
  font-family: var(--font-heading);
  font-size: var(--font-size-base);
  color: var(--color-text);
  margin: var(--space-1) 0 0;
}

.review-panel__close {
  background: none;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: var(--font-size-sm);
  flex-shrink: 0;
}

.review-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.review-section__title {
  font-size: var(--font-size-xs);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  margin: 0;
}

/* Hard Gates */
.gate-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.gate-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  background: var(--color-surface-alt);
}

.gate-icon { flex-shrink: 0; }
.gate-item--passed .gate-icon { color: var(--color-success); }
.gate-item--failed .gate-icon { color: var(--color-danger); }

.gate-label { flex: 1; color: var(--color-text); }

.gate-badge {
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: 1px 5px;
  border-radius: 3px;
}
.gate-badge--passed { background: var(--color-success); color: var(--color-bg); }
.gate-badge--failed { background: var(--color-danger); color: white; }

/* DoD */
.review-empty {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.dod-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.dod-item__label {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  font-size: var(--font-size-sm);
  color: var(--color-text);
  cursor: pointer;
  line-height: 1.4;
}

.dod-checkbox { flex-shrink: 0; margin-top: 2px; }

/* Comment */
.field-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-family: var(--font-mono);
}

.required { color: var(--color-danger); }

.hm-textarea {
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
  padding: var(--space-2) var(--space-3);
  box-sizing: border-box;
  width: 100%;
  resize: vertical;
}
.hm-textarea:focus { border-color: var(--input-focus-border); outline: none; }

.error-text {
  color: var(--color-danger);
  font-size: var(--font-size-sm);
  margin: 0;
}

/* Actions */
.review-actions {
  display: flex;
  gap: var(--space-3);
  justify-content: flex-end;
}

.btn-success {
  background: var(--color-success);
  color: var(--color-bg);
  border: none;
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-4);
  font-family: var(--font-heading);
  font-size: var(--font-size-sm);
  cursor: pointer;
  font-weight: 600;
}
.btn-success:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-danger {
  background: var(--button-danger-bg);
  color: white;
  border: none;
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-4);
  font-family: var(--font-heading);
  font-size: var(--font-size-sm);
  cursor: pointer;
  font-weight: 600;
}
.btn-danger:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
