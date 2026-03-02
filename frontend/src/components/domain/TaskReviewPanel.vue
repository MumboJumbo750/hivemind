<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
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
const reviewPromptLoading = ref(false)
const reviewPromptCopied = ref(false)

// ─── Guard Provenance (TASK-5-020) ─────────────────────────────────────────
interface GuardInfo {
  name: string
  type: string
  status: string
  source: 'self-reported' | 'system-executed'
  checked_at: string | null
  output: string | null
  skippable: boolean
}

const guards = ref<GuardInfo[]>([])
const guardsLoading = ref(false)

async function loadGuards() {
  guardsLoading.value = true
  try {
    const result = await api.callMcpTool('hivemind/get_task', { task_key: props.task.task_key })
    const parsed = JSON.parse(result[0]?.text || '{}')
    const taskData = parsed.data
    if (taskData?.guards) {
      guards.value = taskData.guards.map((g: Record<string, unknown>) => ({
        name: g.guard_name || g.name || 'Guard',
        type: String(g.type || 'manual'),
        status: String(g.status || 'pending'),
        source: deriveSource(String(g.type || '')),
        checked_at: g.checked_at ? String(g.checked_at) : null,
        output: g.result ? String(g.result) : null,
        skippable: !!g.skippable,
      }))
    }
  } catch {
    // Guards loading is non-critical
  } finally {
    guardsLoading.value = false
  }
}

function deriveSource(guardType: string): 'self-reported' | 'system-executed' {
  const systemTypes = ['ci', 'test', 'lint', 'typecheck', 'build', 'command']
  return systemTypes.some(t => guardType.toLowerCase().includes(t))
    ? 'system-executed'
    : 'self-reported'
}

const guardsSummary = computed(() => {
  const total = guards.value.length
  const passed = guards.value.filter(g => g.status === 'passed').length
  const failed = guards.value.filter(g => g.status === 'failed').length
  const pending = guards.value.filter(g => g.status === 'pending').length
  return { total, passed, failed, pending }
})

const emptySelfReported = computed(() =>
  guards.value.filter(g => g.source === 'self-reported' && g.status === 'passed' && !g.output)
)

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

async function copyReviewPrompt() {
  reviewPromptLoading.value = true
  error.value = null
  try {
    const result = await api.getPrompt('review', props.task.task_key)
    const parsed = JSON.parse(result[0]?.text || '{}')
    if (parsed.error) {
      throw new Error(parsed.error.message || 'Review-Prompt konnte nicht geladen werden.')
    }

    const prompt: string | undefined = parsed.data?.prompt ?? parsed.prompt
    if (!prompt) {
      throw new Error('Review-Prompt ist leer.')
    }

    await navigator.clipboard.writeText(prompt)
    reviewPromptCopied.value = true
    setTimeout(() => { reviewPromptCopied.value = false }, 2000)
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    reviewPromptLoading.value = false
  }
}

onMounted(() => loadGuards())
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

    <!-- Guard Provenance (TASK-5-020) -->
    <section v-if="guards.length || guardsLoading" class="review-section">
      <h4 class="review-section__title">
        Guard Provenance
        <span v-if="guardsSummary.total" class="guard-summary">
          {{ guardsSummary.passed }}/{{ guardsSummary.total }} passed
        </span>
      </h4>

      <div v-if="guardsLoading" class="review-empty">Lade Guards...</div>

      <!-- Warning: empty self-reported output -->
      <div v-if="emptySelfReported.length" class="guard-warning">
        ⚠ {{ emptySelfReported.length }} self-reported Guard(s) ohne Ausgabe — Ergebnis nicht verifizierbar.
      </div>

      <ul class="guard-list">
        <li
          v-for="guard in guards"
          :key="guard.name"
          class="guard-item"
          :class="`guard-item--${guard.status}`"
        >
          <div class="guard-item__header">
            <span class="guard-icon">
              {{ guard.status === 'passed' ? '✓' : guard.status === 'failed' ? '✗' : '○' }}
            </span>
            <span class="guard-name">{{ guard.name }}</span>
            <span class="source-badge" :class="`source-badge--${guard.source}`">
              {{ guard.source === 'system-executed' ? '⚙ System' : '✋ Self' }}
            </span>
            <span class="guard-status-badge" :class="`guard-status-badge--${guard.status}`">
              {{ guard.status }}
            </span>
          </div>
          <div class="guard-item__meta">
            <span v-if="guard.checked_at" class="guard-time">
              {{ new Date(guard.checked_at).toLocaleString('de-DE') }}
            </span>
            <span v-if="guard.skippable" class="guard-skippable">überspringbar</span>
          </div>
          <!-- Warning for self-reported without output -->
          <div v-if="guard.source === 'self-reported' && guard.status === 'passed' && !guard.output" class="guard-output-warning">
            ⚠ Kein Output — Self-Reported-Ergebnis nicht validiert
          </div>
          <pre v-if="guard.output" class="guard-output">{{ guard.output }}</pre>
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
        class="btn-secondary"
        @click="copyReviewPrompt"
        :disabled="loading || reviewPromptLoading"
      >
        {{
          reviewPromptCopied
            ? '✓ REVIEW-PROMPT KOPIERT'
            : reviewPromptLoading
              ? 'PROMPT...'
              : 'REVIEW-PROMPT KOPIEREN'
        }}
      </button>
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

.btn-secondary {
  background: var(--color-surface-alt);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
  font-family: var(--font-heading);
  font-size: var(--font-size-sm);
  cursor: pointer;
}
.btn-secondary:hover { border-color: var(--color-accent); color: var(--color-accent); }
.btn-secondary:disabled { opacity: 0.5; cursor: not-allowed; }

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

/* Guard Provenance (TASK-5-020) */
.guard-summary {
  font-weight: 400;
  color: var(--color-text-muted);
  font-size: 9px;
  margin-left: var(--space-2);
}

.guard-warning {
  background: rgba(249, 168, 37, 0.12);
  border: 1px solid rgba(249, 168, 37, 0.3);
  color: var(--color-warning, #f9a825);
  font-size: var(--font-size-xs);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
}

.guard-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.guard-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-2);
  border-radius: var(--radius-sm);
  background: var(--color-surface-alt);
  border-left: 3px solid transparent;
}
.guard-item--passed { border-left-color: var(--color-success); }
.guard-item--failed { border-left-color: var(--color-danger); }
.guard-item--pending { border-left-color: var(--color-text-muted); }
.guard-item--skipped { border-left-color: var(--color-warning, #f9a825); }

.guard-item__header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.guard-icon { font-size: var(--font-size-sm); flex-shrink: 0; }
.guard-item--passed .guard-icon { color: var(--color-success); }
.guard-item--failed .guard-icon { color: var(--color-danger); }
.guard-item--pending .guard-icon { color: var(--color-text-muted); }

.guard-name {
  flex: 1;
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  color: var(--color-text);
}

.source-badge {
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 3px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  flex-shrink: 0;
}
.source-badge--system-executed {
  background: var(--color-accent);
  color: var(--color-bg);
}
.source-badge--self-reported {
  background: var(--color-warning, #f9a825);
  color: #1a1a1a;
}

.guard-status-badge {
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 3px;
  text-transform: uppercase;
}
.guard-status-badge--passed { background: var(--color-success); color: var(--color-bg); }
.guard-status-badge--failed { background: var(--color-danger); color: white; }
.guard-status-badge--pending { background: var(--color-text-muted); color: var(--color-bg); }
.guard-status-badge--skipped { background: var(--color-warning, #f9a825); color: #1a1a1a; }

.guard-item__meta {
  display: flex;
  gap: var(--space-2);
  font-size: 10px;
  color: var(--color-text-muted);
  padding-left: var(--space-4);
}

.guard-skippable {
  font-style: italic;
}

.guard-output-warning {
  font-size: 10px;
  color: var(--color-warning, #f9a825);
  padding-left: var(--space-4);
}

.guard-output {
  font-family: var(--font-mono);
  font-size: 10px;
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-1) var(--space-2);
  margin: 0;
  white-space: pre-wrap;
  max-height: 80px;
  overflow-y: auto;
  margin-left: var(--space-4);
}
</style>
