<script setup lang="ts">
/**
 * McpBridgeConfigPanel.vue — TASK-8-021
 * Admin-only panel for managing external MCP bridge configurations.
 */
import { ref, computed, onMounted } from 'vue'
import type { McpBridge, McpBridgeTool } from '../../api/types'

const TRANSPORT_OPTIONS = [
  { value: 'http', label: 'HTTP' },
  { value: 'sse', label: 'SSE (Server-Sent Events)' },
  { value: 'stdio', label: 'stdio (lokal)' },
]

const bridges = ref<McpBridge[]>([])
const loading = ref(false)
const error = ref('')

// Add/edit form state
const showAddForm = ref(false)
const savingBridge = ref(false)
const form = ref({
  name: '',
  namespace: '',
  transport: 'http' as 'http' | 'sse' | 'stdio',
  url_or_command: '',
  enabled: true,
  blocklist: '',
})

// Per-bridge state
const testingId = ref<string | null>(null)
const testResults = ref<Record<string, { ok: boolean; message: string }>>({})
const viewingToolsId = ref<string | null>(null)
const bridgeTools = ref<Record<string, McpBridgeTool[]>>({})
const loadingTools = ref<string | null>(null)
const deletingId = ref<string | null>(null)

const urlLabel = computed(() => {
  return form.value.transport === 'stdio' ? 'Befehl (command)' : 'Endpoint-URL'
})

const urlPlaceholder = computed(() => {
  if (form.value.transport === 'stdio') return 'python /path/to/mcp_server.py'
  if (form.value.transport === 'sse') return 'http://localhost:9000/sse'
  return 'http://localhost:9000'
})

async function loadBridges() {
  loading.value = true
  error.value = ''
  try {
    const { api } = await import('../../api')
    bridges.value = await api.getMcpBridges()
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function openAddForm() {
  form.value = {
    name: '',
    namespace: '',
    transport: 'http',
    url_or_command: '',
    enabled: true,
    blocklist: '',
  }
  showAddForm.value = true
}

function cancelAdd() {
  showAddForm.value = false
}

async function createBridge() {
  savingBridge.value = true
  error.value = ''
  try {
    const { api } = await import('../../api')
    const blocklist = form.value.blocklist
      ? form.value.blocklist.split(',').map(s => s.trim()).filter(Boolean)
      : []
    const created = await api.createMcpBridge({
      name: form.value.name,
      namespace: form.value.namespace,
      transport: form.value.transport,
      url_or_command: form.value.url_or_command,
      enabled: form.value.enabled,
      blocklist,
    })
    bridges.value.push(created)
    showAddForm.value = false
  } catch (e: any) {
    error.value = e.message
  } finally {
    savingBridge.value = false
  }
}

async function testBridge(id: string) {
  testingId.value = id
  try {
    const { api } = await import('../../api')
    const res = await api.testMcpBridge(id)
    testResults.value = { ...testResults.value, [id]: { ok: true, message: res.message ?? 'Verbindung erfolgreich' } }
  } catch (e: any) {
    testResults.value = { ...testResults.value, [id]: { ok: false, message: e.message } }
  } finally {
    testingId.value = null
  }
}

async function viewTools(id: string) {
  if (viewingToolsId.value === id) {
    viewingToolsId.value = null
    return
  }
  viewingToolsId.value = id
  if (!bridgeTools.value[id]) {
    loadingTools.value = id
    try {
      const { api } = await import('../../api')
      const tools = await api.getMcpBridgeTools(id)
      bridgeTools.value = { ...bridgeTools.value, [id]: tools }
    } catch (e: any) {
      bridgeTools.value = { ...bridgeTools.value, [id]: [] }
    } finally {
      loadingTools.value = null
    }
  }
}

async function deleteBridge(id: string) {
  deletingId.value = id
  try {
    const { api } = await import('../../api')
    await api.deleteMcpBridge(id)
    bridges.value = bridges.value.filter(b => b.id !== id)
    if (viewingToolsId.value === id) viewingToolsId.value = null
    delete testResults.value[id]
    delete bridgeTools.value[id]
  } catch (e: any) {
    error.value = e.message
  } finally {
    deletingId.value = null
  }
}

function statusColor(status: string): string {
  switch (status) {
    case 'connected': return 'var(--color-success)'
    case 'disconnected': return 'var(--color-danger)'
    default: return 'var(--color-text-muted)'
  }
}

onMounted(loadBridges)
</script>

<template>
  <div class="mcp-panel">
    <p v-if="error" class="error-text">{{ error }}</p>

    <!-- Header row -->
    <div class="panel-header">
      <p class="panel-desc">
        MCP Bridges ermöglichen die Anbindung externer Tool-Server an Hivemind.
        Werkzeuge werden auto-discovered und im Blocklist-Mechanismus gefiltert.
      </p>
      <button class="btn-primary" @click="openAddForm">+ Bridge hinzufügen</button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading-text">Lade MCP Bridges…</div>

    <!-- Bridge list -->
    <div v-else-if="bridges.length === 0 && !showAddForm" class="empty-state">
      <div class="empty-state__icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="40" height="40">
          <path d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
        </svg>
      </div>
      <p>Noch keine MCP Bridges konfiguriert.</p>
    </div>

    <div v-else class="bridge-list">
      <div v-for="bridge in bridges" :key="bridge.id" class="bridge-card">
        <!-- Bridge header row -->
        <div class="bridge-row">
          <div class="bridge-info">
            <span class="bridge-name">{{ bridge.name }}</span>
            <span class="bridge-namespace mono">{{ bridge.namespace }}</span>
          </div>

          <div class="bridge-meta">
            <span class="transport-badge mono">{{ bridge.transport }}</span>

            <span class="status-dot" :style="{ color: statusColor(bridge.status) }">●</span>
            <span class="status-label" :style="{ color: statusColor(bridge.status) }">
              {{ bridge.status === 'connected' ? 'Verbunden' : 'Getrennt' }}
            </span>

            <span class="tool-count mono">{{ bridge.tool_count ?? 0 }} Tools</span>
          </div>

          <div class="bridge-actions">
            <button
              class="btn-sm btn-outline"
              :disabled="testingId === bridge.id"
              @click="testBridge(bridge.id)"
            >
              {{ testingId === bridge.id ? '…' : 'Test' }}
            </button>
            <button class="btn-sm btn-outline" @click="viewTools(bridge.id)">
              {{ viewingToolsId === bridge.id ? 'Tools ausblenden' : 'Tools anzeigen' }}
            </button>
            <button
              class="btn-sm btn-danger"
              :disabled="deletingId === bridge.id"
              @click="deleteBridge(bridge.id)"
            >
              {{ deletingId === bridge.id ? '…' : 'Entfernen' }}
            </button>
          </div>
        </div>

        <!-- Test result -->
        <div v-if="testResults[bridge.id]" class="test-result" :class="testResults[bridge.id].ok ? 'test-result--ok' : 'test-result--fail'">
          {{ testResults[bridge.id].ok ? 'OK' : 'Fehler' }}: {{ testResults[bridge.id].message }}
        </div>

        <!-- Tools panel -->
        <div v-if="viewingToolsId === bridge.id" class="tools-panel">
          <div v-if="loadingTools === bridge.id" class="tools-loading">Lade Tools…</div>
          <div v-else-if="bridgeTools[bridge.id]?.length === 0" class="tools-empty">
            Keine Tools gefunden.
          </div>
          <div v-else class="tools-list">
            <div v-for="tool in bridgeTools[bridge.id]" :key="tool.name" class="tool-item">
              <span class="tool-name mono">{{ tool.name }}</span>
              <span class="tool-desc">{{ tool.description }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Add Bridge Form -->
    <div v-if="showAddForm" class="add-form">
      <h4 class="form-title">Neue Bridge</h4>

      <div class="form-grid">
        <div class="form-group">
          <label class="form-label">Name *</label>
          <input
            v-model="form.name"
            type="text"
            class="input"
            placeholder="github-mcp"
          />
        </div>

        <div class="form-group">
          <label class="form-label">Namespace *</label>
          <input
            v-model="form.namespace"
            type="text"
            class="input"
            placeholder="github"
          />
        </div>

        <div class="form-group">
          <label class="form-label">Transport</label>
          <select v-model="form.transport" class="input select-input">
            <option v-for="opt in TRANSPORT_OPTIONS" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>
        </div>

        <div class="form-group">
          <label class="form-label">{{ urlLabel }} *</label>
          <input
            v-model="form.url_or_command"
            type="text"
            class="input"
            :placeholder="urlPlaceholder"
          />
        </div>

        <div class="form-group form-group--full">
          <label class="form-label">
            Tool-Blocklist
            <span class="form-label-hint">(kommagetrennte Tool-Namen, die gesperrt werden)</span>
          </label>
          <textarea
            v-model="form.blocklist"
            class="input textarea-input"
            rows="2"
            placeholder="tool_name_1, tool_name_2"
          ></textarea>
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
        <button class="btn-secondary" @click="cancelAdd">Abbrechen</button>
        <button
          class="btn-primary"
          :disabled="savingBridge || !form.name || !form.namespace || !form.url_or_command"
          @click="createBridge"
        >
          {{ savingBridge ? 'Erstellen…' : 'Bridge erstellen' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mcp-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
}

.panel-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  margin: 0;
  max-width: 560px;
  line-height: 1.6;
}

.loading-text {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

/* Empty state */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-8);
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.empty-state__icon {
  opacity: 0.4;
}

/* Bridge list */
.bridge-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.bridge-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.bridge-row {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-4);
  background: var(--color-surface-alt);
  flex-wrap: wrap;
}

.bridge-info {
  display: flex;
  flex-direction: column;
  gap: var(--space-0-5);
  flex: 1;
  min-width: 120px;
}

.bridge-name {
  font-family: var(--font-heading);
  font-size: var(--font-size-sm);
  color: var(--color-text);
  font-weight: 600;
}

.bridge-namespace {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.bridge-meta {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.transport-badge {
  font-size: var(--font-size-xs);
  background: color-mix(in srgb, var(--color-accent-2) 15%, transparent);
  color: var(--color-accent-2);
  padding: var(--space-0-5) var(--space-2);
  border-radius: var(--radius-full);
}

.status-dot { font-size: var(--font-size-2xs); }

.status-label {
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
}

.tool-count {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.bridge-actions {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

/* Test result */
.test-result {
  padding: var(--space-2) var(--space-4);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  border-top: 1px solid var(--color-border);
}

.test-result--ok { color: var(--color-success); background: color-mix(in srgb, var(--color-success) 8%, transparent); }
.test-result--fail { color: var(--color-danger); background: color-mix(in srgb, var(--color-danger) 8%, transparent); }

/* Tools panel */
.tools-panel {
  border-top: 1px solid var(--color-border);
  padding: var(--space-3) var(--space-4);
  background: var(--color-bg);
}

.tools-loading, .tools-empty {
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
}

.tools-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  max-height: 240px;
  overflow-y: auto;
}

.tool-item {
  display: flex;
  gap: var(--space-3);
  align-items: baseline;
}

.tool-name {
  font-size: var(--font-size-xs);
  color: var(--color-accent);
  white-space: nowrap;
  min-width: 140px;
}

.tool-desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  line-height: 1.4;
}

/* Add form */
.add-form {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-4) var(--space-5);
  background: var(--color-surface-alt);
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

.form-group--full { grid-column: 1 / -1; }

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
  background: var(--color-bg);
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

.textarea-input {
  resize: vertical;
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  line-height: 1.5;
}

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

.error-text {
  color: var(--color-danger);
  font-size: var(--font-size-sm);
  margin: 0;
}

@media (max-width: 768px) {
  .panel-header { flex-direction: column; }
  .bridge-row { flex-direction: column; align-items: flex-start; }
  .form-grid { grid-template-columns: 1fr; }
  .form-group--full { grid-column: 1; }
}
</style>
