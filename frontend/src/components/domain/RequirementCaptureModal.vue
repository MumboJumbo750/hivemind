<script setup lang="ts">
import { ref, watch } from 'vue'
import { api } from '../../api'
import type { RequirementDraftResponse } from '../../api/types'

const props = defineProps<{
  modelValue: boolean
  projectId: string | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'proposal-saved': []
}>()

// ── Step 1: Input ────────────────────────────────────────────────────────────
const requirementText = ref('')
const priorityHint = ref<'' | 'critical' | 'high' | 'medium' | 'low'>('')
const generating = ref(false)
const generateError = ref<string | null>(null)

// ── Step 2: Result ───────────────────────────────────────────────────────────
const draft = ref<RequirementDraftResponse | null>(null)
const copySuccess = ref(false)
const enrichmentOpen = ref(false)

// ── Step 2b: AI Execute ──────────────────────────────────────────────────────
const executing = ref(false)
const executeError = ref<string | null>(null)

// ── Step 3: Submit ───────────────────────────────────────────────────────────
const proposalText = ref('')
const saving = ref(false)
const saveError = ref<string | null>(null)
const saved = ref(false)

function close() {
  emit('update:modelValue', false)
}

watch(() => props.modelValue, (open) => {
  if (!open) {
    requirementText.value = ''
    priorityHint.value = ''
    generating.value = false
    generateError.value = null
    draft.value = null
    copySuccess.value = false
    enrichmentOpen.value = false
    executing.value = false
    executeError.value = null
    proposalText.value = ''
    saving.value = false
    saveError.value = null
    saved.value = false
  }
})

async function generate() {
  if (!requirementText.value.trim() || !props.projectId) return
  generating.value = true
  generateError.value = null
  try {
    draft.value = await api.draftRequirement({
      project_id: props.projectId,
      text: requirementText.value.trim(),
      priority_hint: priorityHint.value || undefined,
    })
  } catch (e: unknown) {
    generateError.value = e instanceof Error ? e.message : String(e)
  } finally {
    generating.value = false
  }
}

async function copyPrompt() {
  if (!draft.value?.prompt) return
  try {
    await navigator.clipboard.writeText(draft.value.prompt)
  } catch {
    const ta = document.createElement('textarea')
    ta.value = draft.value.prompt
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
  }
  copySuccess.value = true
  setTimeout(() => { copySuccess.value = false }, 2000)
}

async function executeAndSubmit() {
  if (!draft.value?.prompt || !props.projectId) return
  executing.value = true
  executeError.value = null
  try {
    const result = await api.executePrompt('stratege', draft.value.prompt)
    if (result.status === 'no_provider') {
      executeError.value = result.message ?? 'Kein AI-Provider für Stratege konfiguriert.'
      return
    }
    if (result.status === 'error') {
      executeError.value = result.message ?? 'Fehler bei der Ausführung.'
      return
    }
    // Success — fill proposal text and auto-submit
    const aiOutput = result.content ?? ''
    proposalText.value = aiOutput
    // Auto-submit the proposal
    const lines = aiOutput.trim().split('\n')
    const titleLine = lines.find(l => l.startsWith('#')) ?? lines[0] ?? ''
    const title = titleLine.replace(/^#+\s*/, '').replace(/\*\*/g, '').trim().slice(0, 120)
    await fetch(`${import.meta.env.VITE_API_URL ?? 'http://localhost:8000'}/api/epic-proposals`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${await _getToken()}`,
      },
      body: JSON.stringify({
        project_id: props.projectId,
        title: title || requirementText.value.slice(0, 80),
        description: aiOutput.trim(),
        rationale: `Abgeleitet aus Anforderung: ${requirementText.value.trim().slice(0, 300)}`,
      }),
    })
    saved.value = true
    emit('proposal-saved')
    setTimeout(() => close(), 2000)
  } catch (e: unknown) {
    executeError.value = e instanceof Error ? e.message : String(e)
  } finally {
    executing.value = false
  }
}

async function submitProposal() {
  if (!proposalText.value.trim() || !props.projectId || !draft.value) return
  saving.value = true
  saveError.value = null
  try {
    const lines = proposalText.value.trim().split('\n')
    const titleLine = lines.find(l => l.startsWith('#')) ?? lines[0] ?? ''
    const title = titleLine.replace(/^#+\s*/, '').replace(/\*\*/g, '').trim().slice(0, 120)

    await fetch(`${import.meta.env.VITE_API_URL ?? 'http://localhost:8000'}/api/epic-proposals`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${await _getToken()}`,
      },
      body: JSON.stringify({
        project_id: props.projectId,
        title: title || requirementText.value.slice(0, 80),
        description: proposalText.value.trim(),
        rationale: `Abgeleitet aus Anforderung: ${requirementText.value.trim().slice(0, 300)}`,
      }),
    })

    saved.value = true
    emit('proposal-saved')
    setTimeout(() => close(), 1500)
  } catch (e: unknown) {
    saveError.value = e instanceof Error ? e.message : String(e)
  } finally {
    saving.value = false
  }
}

async function _getToken(): Promise<string | null> {
  const { useAuthStore } = await import('../../stores/authStore')
  const { getActivePinia } = await import('pinia')
  if (!getActivePinia()) return null
  return useAuthStore().accessToken
}
</script>

<template>
  <Teleport to="body">
    <div v-if="modelValue" class="modal-overlay" @click.self="close">
      <div class="modal" role="dialog" aria-label="Neue Anforderung erfassen">

        <div class="modal__header">
          <h2 class="modal__title">Neue Anforderung</h2>
          <button class="modal__close" @click="close">✕</button>
        </div>

        <!-- Step 1: Input -->
        <template v-if="!draft && !saved">
          <div class="modal__body">
            <div class="field">
              <label class="field__label">Beschreibe deine Anforderung</label>
              <textarea
                v-model="requirementText"
                class="hm-input hm-textarea"
                rows="5"
                placeholder="Was soll das System können? Welches Problem wird gelöst?"
                :disabled="generating"
              />
            </div>

            <div class="field">
              <label class="field__label">Prioritäts-Hint (optional)</label>
              <select v-model="priorityHint" class="hm-select" :disabled="generating">
                <option value="">— keine Angabe —</option>
                <option value="critical">critical</option>
                <option value="high">high</option>
                <option value="medium">medium</option>
                <option value="low">low</option>
              </select>
            </div>

            <p v-if="generateError" class="error-text">{{ generateError }}</p>
          </div>

          <div class="modal__footer">
            <button class="btn-secondary" @click="close">Abbrechen</button>
            <button
              class="btn-primary"
              :disabled="!requirementText.trim() || generating || !projectId"
              @click="generate"
            >
              {{ generating ? 'Generiere…' : 'STRATEGE-PROMPT GENERIEREN →' }}
            </button>
          </div>
        </template>

        <!-- Step 2: Prompt Result + Proposal Input -->
        <template v-else-if="draft && !saved">
          <div class="modal__body">
            <div class="prompt-header">
              <span class="prompt-label">Stratege-Prompt</span>
              <span class="token-count">{{ draft.token_count }} Tokens</span>
              <button class="btn-copy" @click="copyPrompt">
                {{ copySuccess ? '✓ Kopiert' : 'Kopieren' }}
              </button>
            </div>

            <pre class="prompt-block">{{ draft.prompt }}</pre>

            <button class="btn-toggle" @click="enrichmentOpen = !enrichmentOpen">
              {{ enrichmentOpen ? '▲' : '▼' }} Enrichment-Details
            </button>

            <div v-if="enrichmentOpen" class="enrichment-panel">
              <div v-if="draft.enrichment.priority_hint" class="enrichment-row">
                <span class="field__label">Prioritäts-Hint</span>
                <span class="badge">{{ draft.enrichment.priority_hint }}</span>
              </div>
              <div v-if="draft.enrichment.tags.length" class="enrichment-row">
                <span class="field__label">Tags</span>
                <span class="enrichment-value">{{ draft.enrichment.tags.join(', ') }}</span>
              </div>
              <div class="enrichment-row">
                <span class="field__label">Draft-ID</span>
                <span class="enrichment-value mono-xs">{{ draft.draft_id }}</span>
              </div>
            </div>

            <!-- AI Execute Section -->
            <div class="execute-section">
              <button
                class="btn-execute"
                :disabled="executing"
                @click="executeAndSubmit"
              >
                {{ executing ? '⏳ Stratege arbeitet…' : '▶ AUSFÜHREN & EINREICHEN' }}
              </button>
              <span class="execute-hint">Sendet den Prompt an den konfigurierten Stratege-Provider und reicht das Ergebnis direkt als Proposal ein.</span>
            </div>

            <p v-if="executeError" class="error-text">{{ executeError }}</p>

            <div class="divider-or"><span>oder manuell</span></div>

            <div class="hint-banner">
              Kopiere den Prompt in deinen AI-Client. Füge den generierten Epic-Proposal unten ein.
            </div>

            <div class="field">
              <label class="field__label">Epic-Proposal vom AI-Client einfügen</label>
              <textarea
                v-model="proposalText"
                class="hm-input hm-textarea"
                rows="6"
                placeholder="Füge hier den Markdown-Output des Strategen ein…"
                :disabled="saving"
              />
            </div>

            <p v-if="saveError" class="error-text">{{ saveError }}</p>
          </div>

          <div class="modal__footer">
            <button class="btn-secondary" @click="draft = null">← Zurück</button>
            <button
              class="btn-primary"
              :disabled="!proposalText.trim() || saving"
              @click="submitProposal"
            >
              {{ saving ? 'Speichere…' : 'PROPOSAL EINREICHEN →' }}
            </button>
          </div>
        </template>

        <!-- Step 3: Success -->
        <template v-else>
          <div class="modal__body modal__body--center">
            <div class="success-icon">✓</div>
            <p class="success-text">Proposal eingereicht — landet in der Triage Station.</p>
          </div>
        </template>

      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-overlay);
}

.modal {
  width: min(680px, calc(100vw - var(--space-8)));
  max-height: 88vh;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.7);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-4) var(--space-5);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}

.modal__title {
  font-family: var(--font-heading);
  font-size: var(--font-size-lg);
  color: var(--color-text);
  margin: 0;
}

.modal__close {
  background: none;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: var(--font-size-sm);
}

.modal__body {
  padding: var(--space-5);
  overflow-y: auto;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.modal__body--center {
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: var(--space-12);
}

.modal__footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-5);
  border-top: 1px solid var(--color-border);
  flex-shrink: 0;
}

.field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.field__label {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-family: var(--font-mono);
}

.hm-input,
.hm-select {
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
  padding: var(--space-2) var(--space-3);
  box-sizing: border-box;
  width: 100%;
}

.hm-input:focus,
.hm-select:focus {
  border-color: var(--input-focus-border);
  outline: none;
}

.hm-textarea {
  min-height: 100px;
  resize: vertical;
}

/* Prompt result section */
.prompt-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.prompt-label {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--color-accent);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 600;
  flex: 1;
}

.token-count {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.prompt-block {
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-3);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--color-text);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 220px;
  overflow-y: auto;
  margin: 0;
}

.btn-toggle {
  background: none;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  text-align: left;
  padding: 0;
  align-self: flex-start;
}

.btn-toggle:hover {
  color: var(--color-text);
}

.enrichment-panel {
  background: var(--color-surface-alt);
  border-radius: var(--radius-sm);
  padding: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.enrichment-row {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  font-size: var(--font-size-xs);
}

.enrichment-value {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.mono-xs {
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
}

.badge {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-accent) 30%, transparent);
  border-radius: var(--radius-sm);
  padding: 1px var(--space-2);
}

.hint-banner {
  background: color-mix(in srgb, var(--color-accent) 6%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-accent) 20%, transparent);
  border-radius: var(--radius-sm);
  padding: var(--space-3);
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.error-text {
  color: var(--color-danger);
  font-size: var(--font-size-sm);
  margin: 0;
}

/* Success */
.success-icon {
  font-size: 3rem;
  color: var(--color-success);
}

.success-text {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  margin: var(--space-2) 0 0;
}

/* Buttons */
.btn-primary {
  background: var(--button-primary-bg);
  color: var(--button-primary-text);
  border: none;
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-4);
  font-family: var(--font-heading);
  font-size: var(--font-size-sm);
  cursor: pointer;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--color-surface-alt);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-4);
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
  cursor: pointer;
}

.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-copy {
  background: color-mix(in srgb, var(--color-accent) 12%, transparent);
  color: var(--color-accent);
  border: 1px solid color-mix(in srgb, var(--color-accent) 35%, transparent);
  border-radius: var(--radius-sm);
  padding: var(--space-1) var(--space-3);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  cursor: pointer;
  white-space: nowrap;
}

.btn-copy:hover {
  filter: brightness(1.15);
}

/* Execute section */
.execute-section {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  background: color-mix(in srgb, var(--color-success) 6%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-success) 20%, transparent);
  border-radius: var(--radius-sm);
}

.btn-execute {
  background: var(--color-success);
  color: var(--color-bg);
  border: none;
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-4);
  font-family: var(--font-heading);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
}

.btn-execute:hover {
  filter: brightness(1.1);
}

.btn-execute:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.execute-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  line-height: 1.4;
}

.divider-or {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.divider-or::before,
.divider-or::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--color-border);
}
</style>
