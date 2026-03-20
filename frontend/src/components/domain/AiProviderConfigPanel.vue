<script setup lang="ts">
/**
 * AiProviderConfigPanel.vue — TASK-8-020
 * Settings panel for per-agent AI provider configuration.
 * Features: dynamic model dropdown, GitHub Copilot support, credential management.
 */
import { ref, computed, onMounted, watch } from 'vue'
import type { AiProviderConfig, AiModelInfo, AiCredential } from '../../api/types'

const AGENT_ROLES = [
  'kartograph',
  'stratege',
  'architekt',
  'worker',
  'gaertner',
  'triage',
  'reviewer',
] as const

type AgentRole = typeof AGENT_ROLES[number]

const PROVIDER_OPTIONS = [
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'github_copilot', label: 'GitHub Copilot' },
  { value: 'github_models', label: 'GitHub Models' },
  { value: 'ollama', label: 'Ollama (lokal)' },
  { value: 'custom', label: 'Custom' },
]

const PROVIDER_HINTS: Record<string, string> = {
  github_copilot: 'Token via: gh auth token --hostname github.com',
  github_models: 'GitHub PAT mit Models-Zugriff',
  ollama: 'Lokaler Ollama-Server',
}

// ── State: Credentials ──────────────────────────────────────────────────────
const credentials = ref<AiCredential[]>([])
const showCredentialPanel = ref(false)
const credentialForm = ref({
  id: null as string | null,
  name: '',
  provider_type: 'anthropic',
  api_key: '',
  endpoint: '',
  note: '',
})
const savingCredential = ref(false)

// ── State: Provider configs ─────────────────────────────────────────────────
const configs = ref<Record<string, AiProviderConfig>>({})
const loading = ref(false)
const error = ref('')
const saving = ref<string | null>(null)
const testing = ref<string | null>(null)
const testResults = ref<Record<string, { ok: boolean; message: string }>>({})
const editingRole = ref<AgentRole | null>(null)

// Model list state
const availableModels = ref<AiModelInfo[]>([])
const loadingModels = ref(false)
const modelListError = ref('')
const useCustomModel = ref(false)

// Inline form state — credential-first: credential determines provider
const form = ref({
  credential_id: null as string | null,
  provider: 'ollama' as string,  // only used in manual (no-credential) mode
  model: '',
  endpoint: '',
  rpm_limit: null as number | null,
  daily_token_budget: null as number | null,
  enabled: true,
})

// Derived state
const selectedCredential = computed(() =>
  credentials.value.find(c => c.id === form.value.credential_id) ?? null
)

const resolvedProvider = computed(() =>
  selectedCredential.value?.provider_type ?? form.value.provider
)

const isManualMode = computed(() => !form.value.credential_id)

const needsEndpoint = computed(() =>
  resolvedProvider.value === 'ollama' || resolvedProvider.value === 'custom'
)

// Watch credential selection — auto-set provider, reload models
watch(() => form.value.credential_id, () => {
  availableModels.value = []
  modelListError.value = ''
  useCustomModel.value = false
  form.value.model = ''
  loadModelList()
})

// Watch manual provider change (only relevant in manual mode)
watch(() => form.value.provider, () => {
  if (isManualMode.value) {
    availableModels.value = []
    modelListError.value = ''
    useCustomModel.value = false
    form.value.model = ''
    loadModelList()
  }
})

// ── Credential CRUD ─────────────────────────────────────────────────────────
async function loadCredentials() {
  try {
    const { api } = await import('../../api')
    credentials.value = await api.getCredentials()
  } catch (e: any) {
    error.value = e.message
  }
}

function openNewCredential() {
  credentialForm.value = { id: null, name: '', provider_type: 'anthropic', api_key: '', endpoint: '', note: '' }
  showCredentialPanel.value = true
}

function openEditCredential(cred: AiCredential) {
  credentialForm.value = {
    id: cred.id,
    name: cred.name,
    provider_type: cred.provider_type,
    api_key: '',
    endpoint: cred.endpoint ?? '',
    note: cred.note ?? '',
  }
  showCredentialPanel.value = true
}

async function saveCredential() {
  savingCredential.value = true
  error.value = ''
  try {
    const { api } = await import('../../api')
    const f = credentialForm.value
    if (f.id) {
      await api.updateCredential(f.id, {
        name: f.name || undefined,
        provider_type: f.provider_type,
        api_key: f.api_key || undefined,
        endpoint: f.endpoint || undefined,
        note: f.note || undefined,
      })
    } else {
      await api.createCredential({
        name: f.name,
        provider_type: f.provider_type,
        api_key: f.api_key || undefined,
        endpoint: f.endpoint || undefined,
        note: f.note || undefined,
      })
    }
    showCredentialPanel.value = false
    await loadCredentials()
  } catch (e: any) {
    error.value = e.message
  } finally {
    savingCredential.value = false
  }
}

async function deleteCredential(id: string) {
  try {
    const { api } = await import('../../api')
    await api.deleteCredential(id)
    await loadCredentials()
  } catch (e: any) {
    error.value = e.message
  }
}

// ── Model List ──────────────────────────────────────────────────────────────
async function loadModelList() {
  loadingModels.value = true
  modelListError.value = ''
  try {
    const { api } = await import('../../api')
    const models = await api.getAiProviderModels(
      resolvedProvider.value,
      undefined,
      form.value.endpoint || undefined,
      form.value.credential_id || undefined,
      editingRole.value || undefined,
    )
    availableModels.value = models
    if (form.value.model && !models.some(m => m.id === form.value.model)) {
      useCustomModel.value = true
    }
  } catch (e: any) {
    modelListError.value = e.message
    availableModels.value = []
  } finally {
    loadingModels.value = false
  }
}

// ── Provider Config CRUD ────────────────────────────────────────────────────
async function loadConfigs() {
  loading.value = true
  error.value = ''
  try {
    const { api } = await import('../../api')
    const list: AiProviderConfig[] = await api.getAiProviders()
    const map: Record<string, AiProviderConfig> = {}
    for (const cfg of list) map[cfg.agent_role] = cfg
    configs.value = map
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function openEdit(role: AgentRole) {
  const existing = configs.value[role]
  if (existing) {
    form.value = {
      credential_id: existing.credential_id ?? null,
      provider: existing.provider,
      model: existing.model ?? '',
      endpoint: existing.endpoint ?? '',
      rpm_limit: existing.rpm_limit ?? null,
      daily_token_budget: existing.daily_token_budget ?? null,
      enabled: existing.enabled,
    }
  } else {
    // Auto-select first credential if available
    const firstCred = credentials.value[0] ?? null
    form.value = {
      credential_id: firstCred?.id ?? null,
      provider: firstCred?.provider_type ?? 'ollama',
      model: '',
      endpoint: '',
      rpm_limit: null,
      daily_token_budget: null,
      enabled: true,
    }
  }
  useCustomModel.value = false
  editingRole.value = role
  testResults.value[role] && delete testResults.value[role]
  loadModelList()
}

function cancelEdit() {
  editingRole.value = null
  availableModels.value = []
  modelListError.value = ''
}

async function saveConfig(role: AgentRole) {
  saving.value = role
  error.value = ''
  try {
    const { api } = await import('../../api')
    const payload: any = {
      agent_role: role,
      provider: resolvedProvider.value,
      model: form.value.model || undefined,
      endpoint: form.value.endpoint || undefined,
      rpm_limit: form.value.rpm_limit ?? undefined,
      daily_token_budget: form.value.daily_token_budget ?? undefined,
      enabled: form.value.enabled,
    }
    if (form.value.credential_id) {
      payload.credential_id = form.value.credential_id
    }
    const saved = await api.upsertAiProvider(role, payload)
    configs.value[role] = saved
    editingRole.value = null
  } catch (e: any) {
    error.value = e.message
  } finally {
    saving.value = null
  }
}

async function deleteConfig(role: AgentRole) {
  try {
    const { api } = await import('../../api')
    await api.deleteAiProvider(role)
    delete configs.value[role]
    if (editingRole.value === role) editingRole.value = null
  } catch (e: any) {
    error.value = e.message
  }
}

async function testConfig(role: AgentRole) {
  testing.value = role
  try {
    const { api } = await import('../../api')
    const res = await api.testAiProvider(role)
    testResults.value = { ...testResults.value, [role]: { ok: true, message: res.message ?? 'Verbindung erfolgreich' } }
  } catch (e: any) {
    testResults.value = { ...testResults.value, [role]: { ok: false, message: e.message } }
  } finally {
    testing.value = null
  }
}

function providerLabel(provider: string): string {
  return PROVIDER_OPTIONS.find(p => p.value === provider)?.label ?? provider
}

function credentialName(id: string | null): string {
  if (!id) return '—'
  return credentials.value.find(c => c.id === id)?.name ?? id
}

function formatK(n?: number): string {
  if (!n) return '?'
  return n >= 1000 ? `${Math.round(n / 1000)}k` : `${n}`
}

onMounted(async () => {
  await Promise.all([loadConfigs(), loadCredentials()])
})
</script>

<template>
  <div class="ai-panel">
    <p v-if="error" class="error-text">{{ error }}</p>

    <!-- Workflow hint -->
    <div class="info-box">
      <span class="info-box__icon">i</span>
      <div>
        <strong>Workflow:</strong> Lege oben ein <strong>Credential</strong> an (API-Key + Provider).
        Darunter weist du jeder Rolle einfach ein Credential + Modell zu.
        Tipp: <code class="mono">gh auth token</code> liefert den GitHub-Copilot-Token.
      </div>
    </div>

    <!-- Credential Management -->
    <div class="credential-section">
      <div class="credential-header">
        <h3 class="section-title">API-Credentials</h3>
        <button class="btn-sm btn-accent" @click="openNewCredential">+ Neues Credential</button>
      </div>

      <div v-if="credentials.length === 0" class="text-muted credential-empty">
        Noch keine Credentials angelegt. Erstelle eines, um es mehreren Rollen zuzuweisen.
      </div>

      <div v-else class="credential-list">
        <div v-for="cred in credentials" :key="cred.id" class="credential-card">
          <div class="credential-card__info">
            <span class="credential-card__name mono">{{ cred.name }}</span>
            <span class="credential-card__type">{{ providerLabel(cred.provider_type) }}</span>
            <span v-if="cred.has_api_key" class="key-indicator">••••••••</span>
            <span v-else class="text-muted">Kein Key</span>
            <span class="credential-card__usage" :title="`Verwendet von ${cred.usage_count} Rolle(n)`">
              {{ cred.usage_count }}× genutzt
            </span>
          </div>
          <div class="credential-card__actions">
            <button class="btn-sm btn-outline" @click="openEditCredential(cred)">Bearbeiten</button>
            <button class="btn-sm btn-danger" @click="deleteCredential(cred.id)">Entfernen</button>
          </div>
        </div>
      </div>

      <!-- Credential Edit/Create Form -->
      <div v-if="showCredentialPanel" class="credential-form">
        <h4 class="form-title">{{ credentialForm.id ? 'Credential bearbeiten' : 'Neues Credential' }}</h4>
        <div class="form-grid">
          <div class="form-group">
            <label class="form-label">Name</label>
            <input v-model="credentialForm.name" type="text" class="input" placeholder="z. B. Mein Copilot Token" />
          </div>
          <div class="form-group">
            <label class="form-label">Provider-Typ</label>
            <select v-model="credentialForm.provider_type" class="input select-input">
              <option v-for="opt in PROVIDER_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
          </div>
          <div class="form-group form-group--full">
            <label class="form-label">API Key <span class="form-label-hint">(leer = unverändert bei Edit)</span></label>
            <input v-model="credentialForm.api_key" type="password" class="input" placeholder="Token / API Key" autocomplete="new-password" />
          </div>
          <div class="form-group form-group--full">
            <label class="form-label">Endpoint <span class="form-label-hint">(optional)</span></label>
            <input v-model="credentialForm.endpoint" type="url" class="input" placeholder="https://…" />
          </div>
          <div class="form-group form-group--full">
            <label class="form-label">Notiz <span class="form-label-hint">(optional)</span></label>
            <input v-model="credentialForm.note" type="text" class="input" placeholder="z. B. Ablauf Nov 2026" />
          </div>
        </div>
        <div class="form-actions">
          <button class="btn-secondary" @click="showCredentialPanel = false">Abbrechen</button>
          <button class="btn-primary" :disabled="savingCredential || !credentialForm.name" @click="saveCredential">
            {{ savingCredential ? 'Speichern…' : 'Speichern' }}
          </button>
        </div>
      </div>
    </div>

    <hr class="section-divider" />

    <!-- Loading -->
    <div v-if="loading" class="loading-text">Lade Provider-Konfigurationen…</div>

    <!-- Provider Table -->
    <div v-else class="table-wrap">
      <table class="provider-table">
        <thead>
          <tr>
            <th>Agent-Rolle</th>
            <th>Provider</th>
            <th>Modell</th>
            <th>Status</th>
            <th>Credential</th>
            <th>Aktionen</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="role in AGENT_ROLES" :key="role">
            <tr class="provider-row" :class="{ 'provider-row--editing': editingRole === role }">
              <td class="cell-role mono">{{ role }}</td>
              <td class="cell">
                <span v-if="configs[role]">{{ providerLabel(configs[role].provider) }}</span>
                <span v-else class="text-muted">—</span>
              </td>
              <td class="cell mono">
                <span v-if="configs[role]?.model">{{ configs[role].model }}</span>
                <span v-else class="text-muted">—</span>
              </td>
              <td class="cell">
                <span
                  v-if="configs[role]"
                  class="status-pill"
                  :class="configs[role].enabled ? 'status-pill--enabled' : 'status-pill--disabled'"
                >
                  {{ configs[role].enabled ? 'Aktiv' : 'Deaktiviert' }}
                </span>
                <span v-else class="text-muted">Nicht konfiguriert</span>
              </td>
              <td class="cell">
                <span v-if="configs[role]?.credential_name" class="credential-badge mono">
                  {{ configs[role].credential_name }}
                </span>
                <span v-else-if="configs[role]?.has_api_key" class="key-indicator">Inline ••••</span>
                <span v-else class="text-muted">—</span>
              </td>
              <td class="cell-actions">
                <button class="btn-sm btn-accent" @click="openEdit(role)">
                  {{ configs[role] ? 'Bearbeiten' : 'Konfigurieren' }}
                </button>
                <button
                  v-if="configs[role]"
                  class="btn-sm btn-outline"
                  :disabled="testing === role"
                  @click="testConfig(role)"
                >
                  {{ testing === role ? '…' : 'Test' }}
                </button>
                <button
                  v-if="configs[role]"
                  class="btn-sm btn-danger"
                  @click="deleteConfig(role)"
                >
                  Entfernen
                </button>
              </td>
            </tr>

            <!-- Test result inline -->
            <tr v-if="testResults[role]" class="test-result-row">
              <td colspan="6">
                <span class="test-result" :class="testResults[role].ok ? 'test-result--ok' : 'test-result--fail'">
                  {{ testResults[role].ok ? 'OK' : 'Fehler' }}: {{ testResults[role].message }}
                </span>
              </td>
            </tr>

            <!-- Inline edit form -->
            <tr v-if="editingRole === role" class="form-row">
              <td colspan="6">
                <div class="inline-form">
                  <h4 class="form-title">{{ role }} — Konfiguration</h4>

                  <div class="form-grid">
                    <!-- Step 1: Credential — determines Provider automatically -->
                    <div class="form-group form-group--full">
                      <label class="form-label">Credential</label>
                      <select v-model="form.credential_id" class="input select-input">
                        <option :value="null">— Ohne Credential (z. B. Ollama lokal) —</option>
                        <option
                          v-for="cred in credentials"
                          :key="cred.id"
                          :value="cred.id"
                        >
                          {{ cred.name }} · {{ providerLabel(cred.provider_type) }}
                        </option>
                      </select>
                      <span v-if="selectedCredential" class="form-hint credential-hint">
                        Provider: <strong>{{ providerLabel(selectedCredential.provider_type) }}</strong>
                        <span v-if="selectedCredential.has_api_key" class="hint-ok"> · Key ✓</span>
                        <span v-else class="text-danger"> · Kein Key hinterlegt</span>
                      </span>
                      <span v-if="!form.credential_id && credentials.length === 0" class="form-hint text-muted">
                        Noch keine Credentials vorhanden.
                        <button class="btn-inline" @click="openNewCredential">↑ Oben anlegen</button>
                      </span>
                    </div>

                    <!-- Manual provider/endpoint (only without credential) -->
                    <div v-if="isManualMode" class="form-group">
                      <label class="form-label">Provider</label>
                      <select v-model="form.provider" class="input select-input">
                        <option v-for="opt in PROVIDER_OPTIONS" :key="opt.value" :value="opt.value">
                          {{ opt.label }}
                        </option>
                      </select>
                    </div>

                    <div v-if="needsEndpoint" class="form-group" :class="{ 'form-group--full': !isManualMode }">
                      <label class="form-label">Endpoint URL</label>
                      <input
                        v-model="form.endpoint"
                        type="url"
                        class="input"
                        placeholder="http://localhost:11434"
                      />
                    </div>

                    <!-- Step 2: Model selection -->
                    <div class="form-group form-group--full">
                      <label class="form-label">
                        Modell
                        <button
                          v-if="!useCustomModel"
                          class="btn-inline"
                          :disabled="loadingModels"
                          @click="loadModelList"
                          title="Modelle neu laden"
                        >
                          {{ loadingModels ? '⟳' : '↻ Laden' }}
                        </button>
                        <button
                          class="btn-inline"
                          @click="useCustomModel = !useCustomModel"
                        >
                          {{ useCustomModel ? '↩ Liste' : '✎ Manuell' }}
                        </button>
                      </label>

                      <!-- Model picker -->
                      <template v-if="!useCustomModel">
                        <div v-if="availableModels.length > 0" class="model-picker">
                          <div
                            v-for="m in availableModels"
                            :key="m.id"
                            class="model-option"
                            :class="{ 'model-option--selected': form.model === m.id }"
                            @click="form.model = m.id"
                          >
                            <span class="model-option__name">{{ m.name || m.id }}</span>
                            <span v-if="m.vendor" class="model-option__vendor">{{ m.vendor }}</span>
                            <span v-if="m.max_context_tokens" class="model-option__ctx" :title="`Prompt: ${formatK(m.max_prompt_tokens)} / Output: ${formatK(m.max_output_tokens)}`">
                              {{ formatK(m.max_context_tokens) }} ctx
                            </span>
                            <span v-if="m.supports_vision" class="model-option__badge" title="Vision">👁</span>
                            <span v-if="m.supports_tool_calls" class="model-option__badge" title="Tool Calls">🔧</span>
                            <span
                              v-if="m.premium_multiplier != null"
                              class="model-option__multiplier"
                              :class="{
                                'multiplier--free': m.premium_multiplier < 1,
                                'multiplier--base': m.premium_multiplier === 1,
                                'multiplier--premium': m.premium_multiplier > 1 && m.premium_multiplier < 50,
                                'multiplier--ultra': m.premium_multiplier >= 50,
                              }"
                            >
                              {{ m.premium_multiplier < 1 ? `${m.premium_multiplier}×` : m.premium_multiplier === 1 ? '1×' : `${m.premium_multiplier}×` }}
                            </span>
                          </div>
                        </div>
                        <div v-else-if="loadingModels" class="model-loading">
                          Lade Modelle…
                        </div>
                        <div v-else class="model-empty">
                          <span v-if="modelListError" class="text-danger">{{ modelListError }}</span>
                          <span v-else class="text-muted">
                            <template v-if="form.credential_id">Keine Modelle geladen. ↻ klicken.</template>
                            <template v-else>Credential oben wählen oder Modell manuell eingeben.</template>
                          </span>
                        </div>
                      </template>

                      <!-- Manual mode -->
                      <input
                        v-if="useCustomModel"
                        v-model="form.model"
                        type="text"
                        class="input"
                        placeholder="z. B. gpt-4o, claude-sonnet-4-6"
                      />
                    </div>

                    <!-- Step 3: Advanced options (compact row) -->
                    <div class="form-group">
                      <label class="form-label">RPM-Limit <span class="form-label-hint">(Anfragen/Min)</span></label>
                      <input
                        v-model.number="form.rpm_limit"
                        type="number"
                        min="1"
                        class="input"
                        placeholder="60"
                      />
                    </div>

                    <div class="form-group">
                      <label class="form-label">Daily Token Budget</label>
                      <input
                        v-model.number="form.daily_token_budget"
                        type="number"
                        min="0"
                        class="input"
                        placeholder="1000000"
                      />
                    </div>

                    <div class="form-group form-group--toggle">
                      <label class="form-label">Aktiviert</label>
                      <label class="toggle">
                        <input type="checkbox" v-model="form.enabled" />
                        <span class="toggle-track"></span>
                      </label>
                    </div>
                  </div>

                  <div class="form-actions">
                    <button class="btn-secondary" @click="cancelEdit">Abbrechen</button>
                    <button
                      class="btn-primary"
                      :disabled="saving === role || (!form.credential_id && !form.model)"
                      @click="saveConfig(role)"
                    >
                      {{ saving === role ? 'Speichern…' : 'Speichern' }}
                    </button>
                  </div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.ai-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

/* Info box */
.info-box {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  background: var(--color-accent-10);
  border: 1px solid color-mix(in srgb, var(--color-accent) 30%, transparent);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
  font-size: var(--font-size-sm);
  color: var(--color-text);
}

.info-box__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 1px solid var(--color-accent);
  color: var(--color-accent);
  font-size: var(--font-size-2xs);
  font-weight: bold;
  flex-shrink: 0;
  margin-top: 1px;
}

.info-box--copilot {
  background: color-mix(in srgb, #6e40c9 10%, transparent);
  border-color: color-mix(in srgb, #6e40c9 30%, transparent);
}
.info-box--copilot .info-box__icon {
  border-color: #6e40c9;
  color: #6e40c9;
}

.loading-text {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

/* Table */
.table-wrap {
  overflow-x: auto;
}

.provider-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.provider-table th {
  text-align: left;
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--color-border);
}

.provider-row td {
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid color-mix(in srgb, var(--color-border) 50%, transparent);
  vertical-align: middle;
}

.provider-row--editing td {
  background: color-mix(in srgb, var(--color-accent) 5%, transparent);
}

.cell-role {
  color: var(--color-accent);
  font-weight: 600;
}

.cell { color: var(--color-text); }

.cell-actions {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

/* Status pills */
.status-pill {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  padding: var(--space-0-5) var(--space-2);
  border-radius: var(--radius-full);
}

.status-pill--enabled {
  background: var(--color-success-10);
  color: var(--color-success);
}

.status-pill--disabled {
  background: color-mix(in srgb, var(--color-text-muted) 15%, transparent);
  color: var(--color-text-muted);
}

.key-indicator {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  letter-spacing: 2px;
}

/* Test result row */
.test-result-row td {
  padding: var(--space-1) var(--space-3) var(--space-2);
  border-bottom: 1px solid color-mix(in srgb, var(--color-border) 50%, transparent);
}

.test-result {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
}

.test-result--ok { color: var(--color-success); }
.test-result--fail { color: var(--color-danger); }

/* Inline form row */
.form-row td {
  padding: 0;
  border-bottom: 1px solid var(--color-border);
}

.inline-form {
  background: var(--color-surface-alt);
  border-top: 1px solid color-mix(in srgb, var(--color-accent) 30%, transparent);
  padding: var(--space-4) var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.form-title {
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  color: var(--color-accent);
  margin: 0;
  font-weight: 600;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.form-group--full {
  grid-column: 1 / -1;
}

.form-group--toggle {
  flex-direction: row;
  align-items: center;
  gap: var(--space-3);
}

.form-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.form-label-hint {
  color: color-mix(in srgb, var(--color-text-muted) 70%, transparent);
  font-size: var(--font-size-2xs);
}

.form-actions {
  display: flex;
  gap: var(--space-3);
  justify-content: flex-end;
}

/* Toggle */
.toggle {
  position: relative;
  display: inline-flex;
  align-items: center;
  cursor: pointer;
}

.toggle input { display: none; }

.toggle-track {
  width: 36px;
  height: 20px;
  background: var(--color-border);
  border-radius: var(--radius-full);
  position: relative;
  transition: background 0.2s;
}

.toggle-track::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  background: var(--color-text-muted);
  border-radius: 50%;
  transition: transform 0.2s, background 0.2s;
}

.toggle input:checked + .toggle-track { background: var(--color-accent); }
.toggle input:checked + .toggle-track::after {
  transform: translateX(16px);
  background: var(--color-bg);
}

/* Shared inputs */
.input {
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
  color: var(--color-text);
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  width: 100%;
  box-sizing: border-box;
}

.input:focus {
  outline: none;
  border-color: var(--color-accent);
}

.select-input { cursor: pointer; }

/* Buttons */
.btn-primary {
  background: var(--color-accent);
  color: var(--color-bg);
  border: none;
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-4);
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
  cursor: pointer;
  font-weight: 600;
}
.btn-primary:hover { opacity: 0.9; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-secondary {
  background: transparent;
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-4);
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
  cursor: pointer;
}
.btn-secondary:hover { border-color: var(--color-accent); color: var(--color-accent); }

.btn-sm {
  font-size: var(--font-size-xs);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  border: 1px solid;
  cursor: pointer;
  font-family: var(--font-mono);
  white-space: nowrap;
}
.btn-sm:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-accent {
  border-color: var(--color-accent);
  color: var(--color-accent);
  background: transparent;
}
.btn-accent:hover { background: var(--color-accent); color: var(--color-bg); }

.btn-outline {
  border-color: var(--color-border);
  color: var(--color-text-muted);
  background: transparent;
}
.btn-outline:hover { border-color: var(--color-text-muted); color: var(--color-text); }

.btn-danger {
  border-color: var(--color-danger);
  color: var(--color-danger);
  background: transparent;
}
.btn-danger:hover { background: var(--color-danger); color: var(--color-bg); }

/* Utility */
.mono { font-family: var(--font-mono); }
.text-muted { color: var(--color-text-muted); }
.text-danger { color: var(--color-danger); }

.error-text {
  color: var(--color-danger);
  font-size: var(--font-size-sm);
  margin: 0;
}

/* Model selector helpers */
.btn-inline {
  background: none;
  border: none;
  color: var(--color-accent);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  cursor: pointer;
  padding: 0 var(--space-1);
  text-decoration: underline;
  text-decoration-style: dotted;
  text-underline-offset: 2px;
}
.btn-inline:hover { color: var(--color-text); }
.btn-inline:disabled { color: var(--color-text-muted); cursor: wait; }

.input-with-action {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}
.input-with-action .input { flex: 1; }
.btn-refresh {
  white-space: nowrap;
  font-size: var(--font-size-xs);
  padding: var(--space-1) var(--space-2);
  border: 1px solid var(--color-accent);
  border-radius: var(--radius-sm);
  text-decoration: none;
}

.form-hint {
  font-size: var(--font-size-2xs);
  color: var(--color-text-muted);
  margin-top: var(--space-0-5);
}
.form-hint code {
  background: var(--color-accent-10);
  padding: 1px var(--space-1);
  border-radius: var(--radius-xs);
}

.model-loading {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  padding: var(--space-2) 0;
}

.model-empty {
  font-size: var(--font-size-xs);
  padding: var(--space-2) 0;
}

/* Model Picker (custom list with multiplier badges) */
.model-picker {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  max-height: 240px;
  overflow-y: auto;
  background: var(--color-surface-alt);
}

.model-option {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
  font-size: var(--font-size-sm);
  border-bottom: 1px solid color-mix(in srgb, var(--color-border) 40%, transparent);
  transition: background 0.1s;
}
.model-option:last-child { border-bottom: none; }
.model-option:hover { background: color-mix(in srgb, var(--color-accent) 8%, transparent); }

.model-option--selected {
  background: var(--color-accent-10);
  font-weight: 600;
}

.model-option__name {
  font-family: var(--font-mono);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-option__vendor {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
}

.model-option__multiplier {
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  font-weight: 700;
  padding: 1px var(--space-1-5);
  border-radius: var(--radius-md);
  white-space: nowrap;
  flex-shrink: 0;
}

.multiplier--free {
  background: var(--color-success-10);
  color: var(--color-success);
}
.multiplier--base {
  background: color-mix(in srgb, var(--color-text-muted) 12%, transparent);
  color: var(--color-text-muted);
}
.multiplier--premium {
  background: color-mix(in srgb, #f59e0b 15%, transparent);
  color: #f59e0b;
}
.multiplier--ultra {
  background: var(--color-danger-10);
  color: var(--color-danger);
}

.model-option__ctx {
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  color: var(--color-text-muted);
  white-space: nowrap;
  flex-shrink: 0;
}

.model-option__badge {
  font-size: var(--font-size-xs);
  line-height: 1;
  flex-shrink: 0;
  opacity: 0.7;
  cursor: default;
}

@media (max-width: 768px) {
  .form-grid { grid-template-columns: 1fr; }
  .form-group--full { grid-column: 1; }
}

/* Credential Management Section */
.credential-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.credential-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.section-title {
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  color: var(--color-text);
  font-weight: 600;
  margin: 0;
}

.credential-empty {
  font-size: var(--font-size-sm);
  padding: var(--space-2) 0;
}

.credential-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.credential-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
}

.credential-card__info {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
  min-width: 0;
}

.credential-card__name {
  font-weight: 600;
  color: var(--color-accent);
  font-size: var(--font-size-sm);
}

.credential-card__type {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  background: color-mix(in srgb, var(--color-text-muted) 10%, transparent);
  padding: 1px var(--space-1-5);
  border-radius: var(--radius-md);
}

.credential-card__usage {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.credential-card__actions {
  display: flex;
  gap: var(--space-2);
  flex-shrink: 0;
}

.credential-badge {
  font-size: var(--font-size-xs);
  color: var(--color-accent);
  background: var(--color-accent-10);
  padding: 1px var(--space-2);
  border-radius: var(--radius-md);
}

.credential-form {
  background: var(--color-surface-alt);
  border: 1px solid color-mix(in srgb, var(--color-accent) 30%, transparent);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.section-divider {
  border: none;
  border-top: 1px solid var(--color-border);
  margin: var(--space-2) 0;
}

/* Key mode toggle — unused now, kept minimal */
.key-mode-toggle {
  display: inline-flex;
  gap: var(--space-1);
  margin-left: var(--space-2);
}

.key-mode-toggle .btn-inline.active {
  color: var(--color-accent);
  font-weight: 700;
  text-decoration-style: solid;
}

.credential-hint {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.hint-ok {
  color: var(--color-success);
  font-weight: 600;
}
</style>
