<script setup lang="ts">
import { ref } from 'vue'
import { api } from '../../api'
import HivemindCard from '../../components/ui/HivemindCard.vue'
import HivemindModal from '../../components/ui/HivemindModal.vue'
import TokenRadar from '../../components/ui/TokenRadar.vue'

const repoUrl = ref('')
const generatedPrompt = ref('')
const tokenCount = ref(0)
const tokenMax = ref(8000)
const showPromptModal = ref(false)
const loading = ref(false)
const error = ref<string | null>(null)
const kartographOutput = ref('')
const copied = ref(false)

async function generateKartographPrompt() {
  if (!repoUrl.value) return
  loading.value = true
  error.value = null
  try {
    const result = await api.getPrompt('kartograph')
    if (result && result.length > 0) {
      const data = JSON.parse(result[0].text)
      generatedPrompt.value = data.data?.prompt ?? data.prompt ?? result[0].text
      tokenCount.value = data.data?.token_count ?? data.token_count ?? 0
    }
    showPromptModal.value = true
  } catch (e: unknown) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}

async function copyPrompt() {
  await navigator.clipboard.writeText(generatedPrompt.value)
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}
</script>

<template>
  <div class="kartograph-bootstrap">
    <header class="kb-header">
      <h1>Kartograph-Bootstrap</h1>
      <p class="kb-subtitle">Codebase-Analyse starten — Kartograph-Prompt generieren und ausführen</p>
    </header>

    <!-- Phase notice -->
    <div class="kb-banner">
      <span class="banner-icon">ℹ️</span>
      <span>Kartograph-Ergebnisse werden ab Phase 5 automatisch gespeichert. Bis dahin: Ergebnisse manuell in Wiki/Code-Graph übertragen.</span>
    </div>

    <!-- Step 1: Input -->
    <HivemindCard class="kb-step">
      <h2 class="step-title">1. Repository</h2>
      <div class="step-field">
        <label class="field-label">Repo-URL oder lokaler Pfad</label>
        <input
          v-model="repoUrl"
          class="field-input"
          type="text"
          placeholder="https://github.com/org/repo oder /path/to/local"
        />
      </div>
      <button
        class="btn btn-primary"
        :disabled="!repoUrl || loading"
        @click="generateKartographPrompt"
      >
        {{ loading ? 'Generiere...' : 'Kartograph-Analyse starten' }}
      </button>
      <p v-if="error" class="error-text">{{ error }}</p>
    </HivemindCard>

    <!-- Step 2: Generated Prompt (after generation) -->
    <HivemindCard v-if="generatedPrompt" class="kb-step">
      <div class="step-header">
        <h2 class="step-title">2. Generierter Prompt</h2>
        <TokenRadar :current="tokenCount" :max="tokenMax" :size="80" />
      </div>
      <p class="step-hint">Kopiere den Prompt und führe ihn in deinem AI-Client aus.</p>
      <div class="prompt-preview">
        <pre>{{ generatedPrompt.slice(0, 500) }}{{ generatedPrompt.length > 500 ? '...' : '' }}</pre>
      </div>
      <div class="step-actions">
        <button class="btn btn-primary" @click="showPromptModal = true">Vollständig anzeigen</button>
        <button class="btn btn-secondary" @click="copyPrompt">
          {{ copied ? '✓ Kopiert!' : '📋 In Zwischenablage' }}
        </button>
      </div>
    </HivemindCard>

    <!-- Step 3: Result input -->
    <HivemindCard v-if="generatedPrompt" class="kb-step">
      <h2 class="step-title">3. Kartograph-Ergebnis</h2>
      <p class="step-hint">Füge das Ergebnis der Kartograph-Analyse hier ein (manuelles Copy-Paste).</p>
      <textarea
        v-model="kartographOutput"
        class="field-textarea"
        rows="12"
        placeholder="Kartograph-Output hier einfügen..."
      ></textarea>
    </HivemindCard>

    <!-- Prompt Modal -->
    <HivemindModal v-model="showPromptModal" title="Kartograph-Prompt" size="lg">
      <div class="prompt-full">
        <pre>{{ generatedPrompt }}</pre>
      </div>
      <template #footer>
        <button class="btn" @click="showPromptModal = false">Schließen</button>
        <button class="btn btn-primary" @click="copyPrompt">
          {{ copied ? '✓ Kopiert!' : '📋 Kopieren' }}
        </button>
      </template>
    </HivemindModal>
  </div>
</template>

<style scoped>
.kartograph-bootstrap {
  padding: var(--space-6, 1.5rem);
  max-width: 900px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-4, 1rem);
}

.kb-header h1 {
  color: var(--color-text);
  margin: 0 0 var(--space-1, 0.25rem);
}

.kb-subtitle {
  color: var(--color-text-muted);
  font-size: 0.875rem;
  margin: 0;
}

.kb-banner {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2, 0.5rem);
  background: rgba(255, 176, 32, 0.1);
  border: 1px solid rgba(255, 176, 32, 0.3);
  border-radius: 6px;
  padding: var(--space-3, 0.75rem);
  font-size: 0.8rem;
  color: var(--color-warning, #ffb020);
}

.banner-icon {
  flex-shrink: 0;
}

.kb-step {
  padding: var(--space-4, 1rem);
}

.step-title {
  color: var(--color-text);
  font-size: 1rem;
  margin: 0 0 var(--space-3, 0.75rem);
}

.step-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3, 0.75rem);
}

.step-hint {
  color: var(--color-text-muted);
  font-size: 0.8rem;
  margin: 0 0 var(--space-3, 0.75rem);
}

.step-field {
  margin-bottom: var(--space-3, 0.75rem);
}

.field-label {
  display: block;
  color: var(--color-text);
  font-size: 0.8rem;
  font-weight: 500;
  margin-bottom: var(--space-1, 0.25rem);
}

.field-input,
.field-textarea {
  width: 100%;
  background: var(--color-bg, #070b14);
  border: 1px solid var(--color-border, #223a63);
  border-radius: 4px;
  color: var(--color-text);
  padding: 8px 12px;
  font-size: 0.875rem;
  font-family: inherit;
}

.field-textarea {
  resize: vertical;
}

.prompt-preview {
  background: var(--color-bg, #070b14);
  border-radius: 4px;
  padding: var(--space-3, 0.75rem);
  margin-bottom: var(--space-3, 0.75rem);
  max-height: 200px;
  overflow: auto;
}

.prompt-preview pre,
.prompt-full pre {
  margin: 0;
  white-space: pre-wrap;
  font-size: 0.75rem;
  color: var(--color-text-muted);
}

.prompt-full {
  max-height: 60vh;
  overflow: auto;
}

.step-actions {
  display: flex;
  gap: var(--space-2, 0.5rem);
}

.btn {
  padding: 8px 16px;
  border: 1px solid var(--color-border, #223a63);
  border-radius: 4px;
  background: var(--color-surface, #101a2b);
  color: var(--color-text);
  cursor: pointer;
  font-size: 0.8rem;
  transition: all 150ms;
}

.btn:hover { background: var(--color-surface-alt, #162238); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: var(--color-accent, #20e3ff); color: var(--color-bg, #070b14); border-color: var(--color-accent); }
.btn-secondary { border-color: var(--color-accent, #20e3ff); color: var(--color-accent); }

.error-text {
  color: var(--color-danger, #ff4d6d);
  font-size: 0.8rem;
  margin-top: var(--space-2, 0.5rem);
}

@media (max-width: 768px) {
  .step-header {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-2, 0.5rem);
  }
  .step-actions {
    flex-direction: column;
  }
}
</style>
