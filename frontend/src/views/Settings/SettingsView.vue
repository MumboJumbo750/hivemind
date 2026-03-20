<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useTheme } from '../../composables/useTheme'
import { useSettingsStore } from '../../stores/settingsStore'
import { useAuthStore } from '../../stores/authStore'
import FederationSettings from '../../components/domain/FederationSettings.vue'
import ProjectIntegrationsPanel from '../../components/domain/ProjectIntegrationsPanel.vue'
import SyncStatusPanel from '../../components/SyncStatusPanel.vue'
import AiProviderConfigPanel from '../../components/domain/AiProviderConfigPanel.vue'
import GovernanceConfigPanel from '../../components/domain/GovernanceConfigPanel.vue'
import McpBridgeConfigPanel from '../../components/domain/McpBridgeConfigPanel.vue'
import DispatchPoliciesPanel from '../../components/domain/DispatchPoliciesPanel.vue'
import { api } from '../../api'
import type { AuditEntry } from '../../api/types'

const { currentTheme, availableThemes, setTheme } = useTheme()
const settingsStore = useSettingsStore()
const authStore = useAuthStore()

const activeTab = ref<'settings' | 'integrations' | 'sync' | 'audit' | 'ai-providers' | 'governance' | 'mcp-bridges' | 'dispatch-policies'>('settings')
const isAdmin = computed(() => authStore.user?.role === 'admin')

// ── Audit Log state ──────────────────────────────────────────────────────────
const auditEntries = ref<AuditEntry[]>([])
const auditLoading = ref(false)
const auditPage = ref(1)
const auditPageSize = 50
const auditTotalCount = ref(0)
const auditHasMore = ref(false)
const auditError = ref('')

// Filters
const filterAction = ref('')
const filterEntityType = ref('')
const filterFrom = ref('')
const filterTo = ref('')

// Expand state for snapshot lazy-load
const expandedRows = ref<Set<string>>(new Set())

// Known actions / entity types for dropdowns
const actionOptions = ref<string[]>([])
const entityTypeOptions = ['epic', 'task', 'skill', 'proposal', 'triage', 'context', 'prompt']

async function loadAudit() {
  auditLoading.value = true
  auditError.value = ''
  try {
    const res = await api.getAuditEntries({
      tool_name: filterAction.value || undefined,
      entity_type: filterEntityType.value || undefined,
      from: filterFrom.value || undefined,
      to: filterTo.value || undefined,
      page: auditPage.value,
      page_size: auditPageSize,
    })
    auditEntries.value = res.data
    auditTotalCount.value = res.total_count
    auditHasMore.value = res.has_more

    // Collect unique action names for filter dropdown
    const actions = new Set(actionOptions.value)
    res.data.forEach((e: AuditEntry) => actions.add(e.tool_name))
    actionOptions.value = [...actions].sort()
  } catch {
    auditError.value = 'Fehler beim Laden der Audit-Einträge'
  } finally {
    auditLoading.value = false
  }
}

function toggleExpand(id: string) {
  if (expandedRows.value.has(id)) {
    expandedRows.value.delete(id)
  } else {
    expandedRows.value.add(id)
  }
}

function truncate(val: unknown, max = 80): string {
  const s = typeof val === 'string' ? val : JSON.stringify(val) ?? ''
  return s.length > max ? s.slice(0, max) + '…' : s
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'gerade eben'
  if (mins < 60) return `vor ${mins}m`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `vor ${hrs}h`
  const days = Math.floor(hrs / 24)
  return `vor ${days}d`
}

function absoluteTime(iso: string): string {
  return new Date(iso).toLocaleString('de-DE', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

function entityFromTool(toolName: string): string {
  // Extract entity type from tool name like "hivemind-create_task" → "task"
  const name = toolName.replace('hivemind-', '').replace('hivemind/', '')
  const parts = name.split('_')
  return parts.length > 1 ? parts.slice(1).join('_') : parts[0]
}

const totalPages = computed(() => Math.max(1, Math.ceil(auditTotalCount.value / auditPageSize)))

function prevPage() {
  if (auditPage.value > 1) { auditPage.value--; loadAudit() }
}
function nextPage() {
  if (auditHasMore.value) { auditPage.value++; loadAudit() }
}
function goToPage(p: number) {
  auditPage.value = p
  loadAudit()
}

function applyFilters() {
  auditPage.value = 1
  expandedRows.value.clear()
  loadAudit()
}

function clearFilters() {
  filterAction.value = ''
  filterEntityType.value = ''
  filterFrom.value = ''
  filterTo.value = ''
  applyFilters()
}

function exportCsv() {
  if (!auditEntries.value.length) return
  const headers = ['Timestamp', 'Action', 'Actor', 'Role', 'Entity', 'Target ID', 'Status', 'Duration (ms)']
  const rows = auditEntries.value.map(e => [
    absoluteTime(e.created_at),
    e.tool_name,
    e.actor_username ?? e.actor_id,
    e.actor_role,
    entityFromTool(e.tool_name),
    e.target_id ?? '',
    e.status,
    e.duration_ms ?? '',
  ])
  const csv = [headers, ...rows].map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n')
  const blob = new globalThis.Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = globalThis.URL.createObjectURL(blob)
  const a = globalThis.document.createElement('a')
  a.href = url
  a.download = `audit-log-${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  globalThis.URL.revokeObjectURL(url)
}

watch(activeTab, (tab) => {
  if (tab === 'audit' && auditEntries.value.length === 0) {
    loadAudit()
  }
})

onMounted(() => {
  settingsStore.fetchSettings()
})
</script>

<template>
  <div class="settings-view">
    <h1 class="settings-title">Settings</h1>

    <!-- Tab Navigation -->
    <nav class="settings-tabs">
      <button
        class="settings-tab"
        :class="{ 'settings-tab--active': activeTab === 'settings' }"
        @click="activeTab = 'settings'"
      >Allgemein</button>
      <button
        class="settings-tab"
        :class="{ 'settings-tab--active': activeTab === 'integrations' }"
        @click="activeTab = 'integrations'"
      >Integrationen</button>
      <button
        v-if="isAdmin"
        class="settings-tab"
        :class="{ 'settings-tab--active': activeTab === 'sync' }"
        @click="activeTab = 'sync'"
      >Sync Status</button>
      <button
        class="settings-tab"
        :class="{ 'settings-tab--active': activeTab === 'audit' }"
        @click="activeTab = 'audit'"
      >Audit Log</button>
      <button
        class="settings-tab"
        :class="{ 'settings-tab--active': activeTab === 'ai-providers' }"
        @click="activeTab = 'ai-providers'"
      >KI-Provider</button>
      <button
        class="settings-tab"
        :class="{ 'settings-tab--active': activeTab === 'governance' }"
        @click="activeTab = 'governance'"
      >Governance</button>
      <button
        class="settings-tab"
        :class="{ 'settings-tab--active': activeTab === 'dispatch-policies' }"
        @click="activeTab = 'dispatch-policies'"
      >Dispatch Policies</button>
      <button
        v-if="isAdmin"
        class="settings-tab"
        :class="{ 'settings-tab--active': activeTab === 'mcp-bridges' }"
        @click="activeTab = 'mcp-bridges'"
      >MCP Bridges</button>
    </nav>

    <!-- ═══ General Settings Tab ═══ -->
    <template v-if="activeTab === 'settings'">
      <!-- Theme-Auswahl -->
      <section class="settings-section">
        <h2 class="section-title">Theme</h2>
        <div class="theme-picker">
          <button
            v-for="theme in availableThemes"
            :key="theme"
            class="theme-card"
            :class="{ 'theme-card--active': currentTheme === theme }"
            @click="setTheme(theme)"
          >
            <div class="theme-preview" :data-preview-theme="theme">
              <span class="theme-name">{{ theme }}</span>
            </div>
          </button>
        </div>
      </section>

      <!-- Solo/Team-Toggle -->
      <section class="settings-section">
        <h2 class="section-title">Modus</h2>
        <p class="section-desc">Solo: Du bist der einzige Nutzer. Team: Mehrere Nutzer, RBAC aktiv.</p>

        <div class="mode-toggle-row">
          <button
            class="mode-btn"
            :class="{ 'mode-btn--active': settingsStore.mode === 'solo' }"
            :disabled="settingsStore.loading"
            @click="settingsStore.updateMode('solo')"
          >
            <span class="mode-btn__icon">👤</span>
            <span class="mode-btn__label">Solo</span>
          </button>
          <button
            class="mode-btn"
            :class="{ 'mode-btn--active': settingsStore.mode === 'team' }"
            :disabled="settingsStore.loading"
            @click="settingsStore.updateMode('team')"
          >
            <span class="mode-btn__icon">🕸</span>
            <span class="mode-btn__label">Team</span>
          </button>
        </div>

        <p v-if="settingsStore.error" class="error-text">{{ settingsStore.error }}</p>

        <!-- Notification Mode (read-only) -->
        <div class="info-row">
          <span class="info-label">Notification-Modus:</span>
          <span class="info-value">{{ settingsStore.notification_mode }}</span>
        </div>
      </section>

      <!-- MCP-Protokoll -->
      <section class="settings-section">
        <h2 class="section-title">MCP-Protokoll</h2>
        <p class="section-desc">MCP 1.0 Standard — SSE/JSON-RPC 2.0. Externe Clients verbinden via <code>/api/mcp/sse</code>.</p>
        <div class="info-row">
          <span class="info-label">Transport:</span>
          <span class="info-value">{{ settingsStore.mcpTransport === 'sse' ? 'MCP 1.0 (SSE/JSON-RPC 2.0)' : 'stdio (lokal)' }}</span>
        </div>
      </section>

      <!-- Federation -->
      <section class="settings-section">
        <h2 class="section-title">Federation</h2>
        <p class="section-desc">Verbindung zu anderen Hivemind-Nodes konfigurieren.</p>
        <FederationSettings />
      </section>
    </template>

    <template v-if="activeTab === 'integrations'">
      <section class="settings-section">
        <ProjectIntegrationsPanel />
      </section>
    </template>

    <!-- ═══ Audit Log Tab ═══ -->
    <template v-if="activeTab === 'sync' && isAdmin">
      <section class="settings-section">
        <SyncStatusPanel />
      </section>
    </template>

    <template v-if="activeTab === 'audit'">
      <section class="audit-section">
        <!-- Filter Bar -->
        <div class="audit-filters">
          <div class="audit-filter-group">
            <label class="audit-filter-label">Aktion</label>
            <select v-model="filterAction" class="audit-select" @change="applyFilters">
              <option value="">Alle</option>
              <option v-for="a in actionOptions" :key="a" :value="a">{{ a }}</option>
            </select>
          </div>
          <div class="audit-filter-group">
            <label class="audit-filter-label">Entity-Typ</label>
            <select v-model="filterEntityType" class="audit-select" @change="applyFilters">
              <option value="">Alle</option>
              <option v-for="et in entityTypeOptions" :key="et" :value="et">{{ et }}</option>
            </select>
          </div>
          <div class="audit-filter-group">
            <label class="audit-filter-label">Von</label>
            <input type="datetime-local" v-model="filterFrom" class="audit-input" @change="applyFilters" />
          </div>
          <div class="audit-filter-group">
            <label class="audit-filter-label">Bis</label>
            <input type="datetime-local" v-model="filterTo" class="audit-input" @change="applyFilters" />
          </div>
          <button class="btn-filter-clear" @click="clearFilters">✕ Reset</button>
          <button v-if="isAdmin" class="btn-export" @click="exportCsv">⬇ CSV Export</button>
        </div>

        <!-- Loading / Error -->
        <div v-if="auditLoading" class="audit-loading">Lade Audit-Einträge…</div>
        <p v-if="auditError" class="error-text">{{ auditError }}</p>

        <!-- Empty -->
        <div v-if="!auditLoading && auditEntries.length === 0 && !auditError" class="audit-empty">
          <svg viewBox="0 0 24 24" class="audit-empty__icon" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M9 12h6m-3-3v6m-7 4h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
          <p>Noch keine Audit-Einträge</p>
        </div>

        <!-- Table -->
        <div v-if="!auditLoading && auditEntries.length > 0" class="audit-table-wrap">
          <table class="audit-table">
            <thead>
              <tr>
                <th>Zeitpunkt</th>
                <th>Aktion</th>
                <th>Akteur</th>
                <th>Entity</th>
                <th>Input</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="entry in auditEntries" :key="entry.id">
                <tr class="audit-row" @click="toggleExpand(entry.id)">
                  <td class="audit-cell audit-cell--time" :title="absoluteTime(entry.created_at)">
                    {{ relativeTime(entry.created_at) }}
                  </td>
                  <td class="audit-cell">
                    <span class="audit-action-badge">{{ entry.tool_name }}</span>
                  </td>
                  <td class="audit-cell audit-cell--actor">
                    {{ entry.actor_username ?? entry.actor_id.slice(0, 8) }}
                  </td>
                  <td class="audit-cell">
                    <span class="audit-entity-type">{{ entityFromTool(entry.tool_name) }}</span>
                    <span v-if="entry.target_id" class="audit-entity-key">{{ entry.target_id }}</span>
                  </td>
                  <td class="audit-cell audit-cell--input">
                    <template v-if="entry.input_snapshot">
                      {{ truncate(entry.input_snapshot) }}
                    </template>
                    <span v-else class="text-muted">—</span>
                  </td>
                  <td class="audit-cell">
                    <span class="audit-status" :class="'audit-status--' + entry.status">{{ entry.status }}</span>
                  </td>
                </tr>
                <!-- Expanded detail row -->
                <tr v-if="expandedRows.has(entry.id)" class="audit-expand-row">
                  <td colspan="6">
                    <div class="audit-expand">
                      <div class="audit-expand__meta">
                        <span><strong>ID:</strong> {{ entry.id }}</span>
                        <span><strong>Zeitpunkt:</strong> {{ absoluteTime(entry.created_at) }}</span>
                        <span v-if="entry.duration_ms != null"><strong>Dauer:</strong> {{ entry.duration_ms }}ms</span>
                        <span><strong>Rolle:</strong> {{ entry.actor_role }}</span>
                      </div>
                      <div v-if="entry.input_snapshot" class="audit-expand__section">
                        <h4>Input Snapshot{{ entry.input_truncated ? ' (gekürzt)' : '' }}</h4>
                        <pre class="audit-expand__pre">{{ JSON.stringify(entry.input_snapshot, null, 2) }}</pre>
                      </div>
                      <div v-if="entry.output_snapshot" class="audit-expand__section">
                        <h4>Output Snapshot{{ entry.output_truncated ? ' (gekürzt)' : '' }}</h4>
                        <pre class="audit-expand__pre">{{ JSON.stringify(entry.output_snapshot, null, 2) }}</pre>
                      </div>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>

        <!-- Pagination -->
        <div v-if="auditTotalCount > 0" class="audit-pagination">
          <span class="audit-pagination__info">{{ auditTotalCount }} Einträge · Seite {{ auditPage }} / {{ totalPages }}</span>
          <div class="audit-pagination__btns">
            <button class="btn-page" :disabled="auditPage <= 1" @click="prevPage">◀</button>
            <template v-for="p in Math.min(totalPages, 7)" :key="p">
              <button
                class="btn-page"
                :class="{ 'btn-page--active': p === auditPage }"
                @click="goToPage(p)"
              >{{ p }}</button>
            </template>
            <button class="btn-page" :disabled="!auditHasMore" @click="nextPage">▶</button>
          </div>
        </div>
      </section>
    </template>

    <!-- ═══ KI-Provider Tab ═══ -->
    <template v-if="activeTab === 'ai-providers'">
      <section class="settings-section">
        <h2 class="section-title">KI-Provider</h2>
        <p class="section-desc">Konfiguriere AI-Provider und Modelle pro Agenten-Rolle. Rollenspezifische Einstellungen haben Vorrang vor dem globalen Fallback.</p>
        <AiProviderConfigPanel />
      </section>
    </template>

    <!-- ═══ Governance Tab ═══ -->
    <template v-if="activeTab === 'governance'">
      <section class="settings-section">
        <h2 class="section-title">Governance</h2>
        <p class="section-desc">Lege fest, wie autonom Hivemind für jeden Governance-Typ entscheiden darf.</p>
        <GovernanceConfigPanel />
      </section>
    </template>

    <!-- ═══ Dispatch Policies Tab ═══ -->
    <template v-if="activeTab === 'dispatch-policies'">
      <section class="settings-section">
        <h2 class="section-title">Dispatch Policies</h2>
        <p class="section-desc">Konfiguriere Rate Limits, Token-Budgets und Parallelitäts-Grenzen pro Agenten-Rolle.</p>
        <DispatchPoliciesPanel />
      </section>
    </template>

    <!-- ═══ MCP Bridges Tab (Admin only) ═══ -->
    <template v-if="activeTab === 'mcp-bridges' && isAdmin">
      <section class="settings-section">
        <h2 class="section-title">MCP Bridges</h2>
        <p class="section-desc">Verwalte externe MCP Tool-Server, die Hivemind als zusätzliche Tool-Quellen nutzt.</p>
        <McpBridgeConfigPanel />
      </section>
    </template>
  </div>
</template>

<style scoped>
.settings-view {
  padding: var(--space-6);
  max-width: 960px;
  display: flex;
  flex-direction: column;
  gap: var(--space-8);
}

.settings-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-3xl);
  color: var(--color-text);
  margin: 0;
}

.settings-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.section-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-lg);
  color: var(--color-text);
  margin: 0;
  border-bottom: 1px solid var(--color-border);
  padding-bottom: var(--space-2);
}

.section-desc {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  margin: 0;
}

/* Theme Cards */
.theme-picker {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.theme-card {
  background: transparent;
  border: 2px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  cursor: pointer;
  transition: border-color var(--transition-duration) ease;
  min-width: 140px;
}
.theme-card:hover { border-color: var(--color-text-muted); }
.theme-card--active { border-color: var(--color-accent); }

.theme-preview {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.theme-name {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--color-text);
}

.theme-preview[data-preview-theme="space-neon"] .theme-name    { color: #20e3ff; }
.theme-preview[data-preview-theme="industrial-amber"] .theme-name { color: #ffaa00; }
.theme-preview[data-preview-theme="operator-mono"] .theme-name { color: #ffffff; }

/* Mode Toggle */
.mode-toggle-row {
  display: flex;
  gap: var(--space-3);
}

.mode-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-3) var(--space-6);
  background: var(--color-surface-alt);
  border: 2px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: border-color var(--transition-duration) ease;
  min-width: 100px;
}
.mode-btn:hover:not(:disabled) { border-color: var(--color-text-muted); }
.mode-btn--active { border-color: var(--color-accent); }
.mode-btn:disabled { opacity: 0.6; cursor: not-allowed; }

.mode-btn__icon { font-size: var(--font-size-2xl); }
.mode-btn__label { font-size: var(--font-size-sm); color: var(--color-text); font-family: var(--font-mono); }

/* Info row */
.info-row {
  display: flex;
  gap: var(--space-3);
  align-items: center;
}

.info-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.info-value {
  font-size: var(--font-size-xs);
  color: var(--color-accent);
  font-family: var(--font-mono);
}

.error-text {
  color: var(--color-danger);
  font-size: var(--font-size-sm);
  margin: 0;
}

/* Button */
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
.btn-secondary:hover { border-color: var(--color-accent); color: var(--color-accent); }

/* ── Tab Navigation ─────────────────────────────────────────────────────── */
.settings-tabs {
  display: flex;
  gap: var(--space-1);
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 0;
  margin: calc(-1 * var(--space-4)) 0 0;
}

.settings-tab {
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--color-text-muted);
  font-family: var(--font-heading);
  font-size: var(--font-size-sm);
  padding: var(--space-2) var(--space-4);
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}
.settings-tab:hover { color: var(--color-text); }
.settings-tab--active {
  color: var(--color-accent);
  border-bottom-color: var(--color-accent);
}

/* ── Audit Section ──────────────────────────────────────────────────────── */
.audit-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.audit-filters {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  align-items: flex-end;
}

.audit-filter-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-0-5);
}

.audit-filter-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.audit-select, .audit-input {
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  font-family: var(--font-body);
  font-size: var(--font-size-xs);
  padding: var(--space-1) var(--space-2);
  min-width: 130px;
}
.audit-select:focus, .audit-input:focus {
  outline: none;
  border-color: var(--color-accent);
}

.btn-filter-clear {
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
  padding: var(--space-1) var(--space-3);
  cursor: pointer;
}
.btn-filter-clear:hover { color: var(--color-danger); border-color: var(--color-danger); }

.btn-export {
  background: var(--color-accent-10);
  border: 1px solid var(--color-accent);
  border-radius: var(--radius-sm);
  color: var(--color-accent);
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  padding: var(--space-1) var(--space-3);
  cursor: pointer;
}
.btn-export:hover { background: var(--color-accent-20); }

.audit-loading {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  text-align: center;
  padding: var(--space-6);
}

.audit-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-8);
  color: var(--color-text-muted);
}
.audit-empty__icon {
  width: 48px;
  height: 48px;
  opacity: 0.4;
}

/* Table */
.audit-table-wrap {
  overflow-x: auto;
  max-width: 100%;
}

.audit-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-xs);
}

.audit-table th {
  text-align: left;
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  text-transform: uppercase;
  color: var(--color-text-muted);
  padding: var(--space-2) var(--space-2);
  border-bottom: 1px solid var(--color-border);
  white-space: nowrap;
}

.audit-row {
  cursor: pointer;
  transition: background 0.1s;
}
.audit-row:hover { background: var(--color-surface-alt); }

.audit-cell {
  padding: var(--space-2);
  border-bottom: 1px solid color-mix(in srgb, var(--color-border) 40%, transparent);
  vertical-align: top;
  color: var(--color-text);
}

.audit-cell--time {
  white-space: nowrap;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.audit-cell--actor {
  font-family: var(--font-mono);
  color: var(--color-accent);
}

.audit-cell--input {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  color: var(--color-text-muted);
}

.audit-action-badge {
  background: color-mix(in srgb, var(--color-accent-2) 15%, transparent);
  color: var(--color-accent-2);
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  padding: 1px var(--space-1-5);
  border-radius: var(--radius-xs);
  white-space: nowrap;
}

.audit-entity-type {
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
}

.audit-entity-key {
  display: block;
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  color: var(--color-accent);
  cursor: pointer;
}

.audit-status {
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  padding: 1px var(--space-1-5);
  border-radius: var(--radius-xs);
}
.audit-status--success { background: var(--color-success-20); color: var(--color-success); }
.audit-status--error { background: var(--color-danger-20); color: var(--color-danger); }
.audit-status--pending { background: var(--color-warning-20); color: var(--color-warning); }

/* Expand row */
.audit-expand-row td {
  padding: 0;
  border-bottom: 1px solid var(--color-border);
}

.audit-expand {
  background: var(--color-surface-alt);
  padding: var(--space-3) var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.audit-expand__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}
.audit-expand__meta strong { color: var(--color-text); }

.audit-expand__section h4 {
  font-family: var(--font-heading);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  margin: 0 0 var(--space-1);
}

.audit-expand__pre {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  color: var(--color-text);
  overflow-x: auto;
  max-height: 200px;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

/* Pagination */
.audit-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding-top: var(--space-2);
  border-top: 1px solid var(--color-border);
}

.audit-pagination__info {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.audit-pagination__btns {
  display: flex;
  gap: var(--space-0-5);
}

.btn-page {
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  padding: var(--space-1) var(--space-2);
  cursor: pointer;
  min-width: 28px;
  text-align: center;
}
.btn-page:hover:not(:disabled) { border-color: var(--color-accent); color: var(--color-accent); }
.btn-page--active { background: var(--color-accent); color: var(--color-bg); border-color: var(--color-accent); }
.btn-page:disabled { opacity: 0.3; cursor: not-allowed; }

.text-muted { color: var(--color-text-muted); }

@media (max-width: 768px) {
  .settings-view { max-width: 100%; }
  .audit-filters { flex-direction: column; }
  .audit-table-wrap { font-size: var(--font-size-2xs); }
}
</style>
