<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '../../api'
import type { ReviewRecommendation, ReviewVerdict } from '../../api/types'

// ─── Props ──────────────────────────────────────────────────────────────────

const props = withDefaults(defineProps<{
  taskKey: string
  governanceLevel?: 'manual' | 'assisted' | 'auto'
}>(), {
  governanceLevel: 'manual',
})

const emit = defineEmits<{
  (e: 'approve'): void
  (e: 'reject'): void
}>()

// ─── State ──────────────────────────────────────────────────────────────────

const recommendation = ref<ReviewRecommendation | null>(null)
const loading = ref(false)
const actionLoading = ref(false)
const actionError = ref<string | null>(null)

// Grace-period countdown
const graceSecondsLeft = ref(0)
let countdownTimer: ReturnType<typeof setInterval> | null = null

// ─── Computed ───────────────────────────────────────────────────────────────

const visible = computed(() =>
  !loading.value
  && recommendation.value !== null
  && props.governanceLevel !== 'manual'
)

const verdictLabel = computed((): string => {
  const map: Record<ReviewVerdict, string> = {
    approve: 'APPROVE',
    reject: 'REJECT',
    needs_review: 'NEEDS REVIEW',
  }
  return recommendation.value ? (map[recommendation.value.verdict] ?? recommendation.value.verdict) : ''
})

const confidencePct = computed(() =>
  Math.min(100, Math.max(0, recommendation.value?.confidence ?? 0))
)

const graceActive = computed(() =>
  props.governanceLevel === 'auto'
  && !recommendation.value?.auto_approved
  && graceSecondsLeft.value > 0
)

// ─── Fetch ──────────────────────────────────────────────────────────────────

async function load() {
  if (props.governanceLevel === 'manual') return
  loading.value = true
  recommendation.value = null
  try {
    recommendation.value = await api.getReviewRecommendations(props.taskKey)
    startGraceCountdown()
  } finally {
    loading.value = false
  }
}

function startGraceCountdown() {
  if (countdownTimer) clearInterval(countdownTimer)
  const endsAt = recommendation.value?.grace_period_ends_at
  if (!endsAt) return

  const update = () => {
    const diff = Math.max(0, Math.floor((new Date(endsAt).getTime() - Date.now()) / 1000))
    graceSecondsLeft.value = diff
    if (diff === 0 && countdownTimer) {
      clearInterval(countdownTimer)
      countdownTimer = null
    }
  }
  update()
  countdownTimer = setInterval(update, 1000)
}

// ─── Actions ────────────────────────────────────────────────────────────────

async function handleApprove() {
  actionLoading.value = true
  actionError.value = null
  try {
    await api.approveTask(props.taskKey)
    emit('approve')
  } catch (e: unknown) {
    actionError.value = e instanceof Error ? e.message : String(e)
  } finally {
    actionLoading.value = false
  }
}

async function handleReject() {
  actionLoading.value = true
  actionError.value = null
  try {
    await api.rejectTask(props.taskKey)
    emit('reject')
  } catch (e: unknown) {
    actionError.value = e instanceof Error ? e.message : String(e)
  } finally {
    actionLoading.value = false
  }
}

async function handleVeto() {
  actionLoading.value = true
  actionError.value = null
  try {
    await api.vetoAutoReview(props.taskKey)
    graceSecondsLeft.value = 0
    if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null }
  } catch (e: unknown) {
    actionError.value = e instanceof Error ? e.message : String(e)
  } finally {
    actionLoading.value = false
  }
}

// ─── Lifecycle ──────────────────────────────────────────────────────────────

onMounted(() => void load())

watch(() => props.taskKey, () => void load())

// cleanup
import { onUnmounted } from 'vue'
onUnmounted(() => {
  if (countdownTimer) clearInterval(countdownTimer)
})
</script>

<template>
  <div v-if="visible" class="ai-review-panel">

    <!-- Auto-Approved Badge -->
    <div v-if="recommendation?.auto_approved" class="auto-approved-badge">
      AUTO-APPROVED
    </div>

    <!-- Recommendation Card (assisted or auto before grace ends) -->
    <template v-else-if="governanceLevel === 'assisted' || (governanceLevel === 'auto' && !recommendation?.auto_approved)">

      <!-- Verdict Header -->
      <div class="ai-review-header">
        <span
          class="verdict-badge"
          :class="`verdict-badge--${recommendation?.verdict ?? 'needs_review'}`"
        >
          {{ verdictLabel }}
        </span>
        <span class="ai-label">KI-EMPFEHLUNG</span>
      </div>

      <!-- Confidence Bar -->
      <div class="confidence-row">
        <span class="confidence-label">Konfidenz</span>
        <div class="confidence-bar-track">
          <div
            class="confidence-bar-fill"
            :class="`confidence-bar-fill--${recommendation?.verdict ?? 'needs_review'}`"
            :style="{ width: `${confidencePct}%` }"
          />
        </div>
        <span class="confidence-pct mono">{{ confidencePct }}%</span>
      </div>

      <!-- Reasoning -->
      <p v-if="recommendation?.reasoning" class="ai-reasoning">
        {{ recommendation.reasoning }}
      </p>

      <!-- Checklist -->
      <ul v-if="recommendation?.checklist?.length" class="ai-checklist">
        <li
          v-for="(item, i) in recommendation.checklist"
          :key="i"
          class="ai-checklist-item"
          :class="item.passed ? 'ai-checklist-item--pass' : 'ai-checklist-item--fail'"
        >
          <span class="ai-checklist-icon">{{ item.passed ? '✓' : '✗' }}</span>
          <span class="ai-checklist-label">{{ item.label }}</span>
        </li>
      </ul>

      <!-- Auto-Mode Grace Period Countdown -->
      <div v-if="governanceLevel === 'auto' && graceActive" class="grace-period">
        <div class="grace-countdown">
          <span class="grace-countdown__label">Automatische Genehmigung in</span>
          <span class="grace-countdown__value mono">{{ graceSecondsLeft }}s</span>
        </div>
        <button
          class="btn-warning"
          @click="handleVeto"
          :disabled="actionLoading"
        >
          Eingreifen
        </button>
      </div>

      <!-- 1-Click Actions (assisted mode only) -->
      <div v-if="governanceLevel === 'assisted'" class="ai-actions">
        <p v-if="actionError" class="ai-error">{{ actionError }}</p>
        <button
          class="btn-danger"
          @click="handleReject"
          :disabled="actionLoading"
        >
          ✗ Ablehnen
        </button>
        <button
          class="btn-success"
          @click="handleApprove"
          :disabled="actionLoading"
        >
          ✓ Bestätigen
        </button>
      </div>

      <p v-if="actionError && governanceLevel === 'auto'" class="ai-error">{{ actionError }}</p>

    </template>
  </div>
</template>

<style scoped>
.ai-review-panel {
  border: 1px solid color-mix(in srgb, var(--color-accent) 30%, transparent);
  border-left: 3px solid var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 4%, var(--color-surface));
  border-radius: var(--radius-md);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

/* ── Auto-approved ── */
.auto-approved-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  background: var(--color-success);
  color: var(--color-bg);
  font-family: var(--font-heading);
  font-size: var(--font-size-xs);
  letter-spacing: 0.1em;
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-sm);
  align-self: flex-start;
}

/* ── Header ── */
.ai-review-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.ai-label {
  font-family: var(--font-mono);
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--color-text-muted);
}

/* ── Verdict Badge ── */
.verdict-badge {
  font-family: var(--font-heading);
  font-size: var(--font-size-xs);
  letter-spacing: 0.08em;
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-sm);
  font-weight: 700;
}
.verdict-badge--approve {
  background: var(--color-success);
  color: var(--color-bg);
}
.verdict-badge--reject {
  background: var(--color-danger);
  color: white;
}
.verdict-badge--needs_review {
  background: var(--color-warning, #f9a825);
  color: #1a1a1a;
}

/* ── Confidence Bar ── */
.confidence-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.confidence-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
  flex-shrink: 0;
}

.confidence-bar-track {
  flex: 1;
  height: 6px;
  background: var(--color-surface-alt);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.confidence-bar-fill {
  height: 100%;
  border-radius: var(--radius-full);
  transition: width 0.5s ease;
}
.confidence-bar-fill--approve { background: var(--color-success); }
.confidence-bar-fill--reject { background: var(--color-danger); }
.confidence-bar-fill--needs_review { background: var(--color-warning, #f9a825); }

.confidence-pct {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
  flex-shrink: 0;
  min-width: 32px;
  text-align: right;
}

/* ── Reasoning ── */
.ai-reasoning {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  line-height: 1.5;
  margin: 0;
  padding: var(--space-2) var(--space-3);
  background: var(--color-surface-alt);
  border-radius: var(--radius-sm);
  border-left: 2px solid var(--color-border);
  font-style: italic;
}

/* ── Checklist ── */
.ai-checklist {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.ai-checklist-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-xs);
  padding: 2px 0;
}

.ai-checklist-icon {
  flex-shrink: 0;
  font-size: var(--font-size-sm);
}
.ai-checklist-item--pass .ai-checklist-icon { color: var(--color-success); }
.ai-checklist-item--fail .ai-checklist-icon { color: var(--color-danger); }

.ai-checklist-label { color: var(--color-text); }

/* ── Grace Period ── */
.grace-period {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  background: color-mix(in srgb, var(--color-warning, #f9a825) 10%, var(--color-surface));
  border: 1px solid color-mix(in srgb, var(--color-warning, #f9a825) 30%, transparent);
  border-radius: var(--radius-sm);
}

.grace-countdown {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.grace-countdown__label {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.grace-countdown__value {
  font-size: var(--font-size-lg);
  color: var(--color-warning, #f9a825);
  font-weight: 700;
}

/* ── Actions ── */
.ai-actions {
  display: flex;
  gap: var(--space-3);
  justify-content: flex-end;
  flex-wrap: wrap;
}

.ai-error {
  color: var(--color-danger);
  font-size: var(--font-size-xs);
  margin: 0;
  width: 100%;
}

/* ── Buttons ── */
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

.btn-warning {
  background: var(--color-warning, #f9a825);
  color: #1a1a1a;
  border: none;
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-4);
  font-family: var(--font-heading);
  font-size: var(--font-size-sm);
  cursor: pointer;
  font-weight: 600;
}
.btn-warning:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
