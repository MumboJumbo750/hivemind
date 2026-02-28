<script setup lang="ts">
/**
 * FederationSettings.vue — TASK-F-012
 * Federation settings section for SettingsView.
 */
import { ref, computed, onMounted } from 'vue'
import type { NodeIdentity, PeerNode, FederationSettings } from '../../api/types'

const identity = ref<NodeIdentity | null>(null)
const peers = ref<PeerNode[]>([])
const fedSettings = ref<FederationSettings | null>(null)
const loading = ref(false)
const error = ref('')
const showAddPeer = ref(false)

// Add peer form
const newPeerName = ref('')
const newPeerUrl = ref('')
const newPeerKey = ref('')

const topologyOptions = [
  { value: 'direct_mesh', label: 'Direct Mesh', desc: 'Peer-Discovery ausschließlich über peers.yaml. Transport direkt Node → Node.' },
  { value: 'hub_assisted', label: 'Hub Assisted', desc: 'Peer-Liste über Hive Station + direkter Transport.' },
  { value: 'hub_relay', label: 'Hub Relay', desc: 'Wie Hub Assisted + Store-and-Forward-Relay bei Ausfall.' },
]

const showHiveStation = computed(() =>
  fedSettings.value?.topology === 'hub_assisted' || fedSettings.value?.topology === 'hub_relay'
)

const truncatedKey = computed(() => {
  if (!identity.value?.public_key) return ''
  const pk = identity.value.public_key
  return pk.length > 40 ? pk.slice(0, 20) + '…' + pk.slice(-20) : pk
})

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const { api } = await import('../../api')
    const [id, nodes, settings] = await Promise.all([
      api.getNodeIdentity().catch(() => null),
      api.getNodes().catch(() => []),
      api.getFederationSettings().catch(() => null),
    ])
    identity.value = id
    peers.value = nodes
    fedSettings.value = settings
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function addPeer() {
  if (!newPeerName.value || !newPeerUrl.value) return
  try {
    const { api } = await import('../../api')
    const peer = await api.createNode({
      node_name: newPeerName.value,
      node_url: newPeerUrl.value,
      public_key: newPeerKey.value || undefined,
    })
    peers.value.push(peer)
    showAddPeer.value = false
    newPeerName.value = ''
    newPeerUrl.value = ''
    newPeerKey.value = ''
  } catch (e: any) {
    error.value = e.message
  }
}

async function blockPeer(peer: PeerNode) {
  try {
    const { api } = await import('../../api')
    const updated = await api.updateNode(peer.id, { status: 'blocked' })
    const idx = peers.value.findIndex(p => p.id === peer.id)
    if (idx >= 0) peers.value[idx] = updated
  } catch (e: any) {
    error.value = e.message
  }
}

async function removePeer(peer: PeerNode) {
  try {
    const { api } = await import('../../api')
    await api.deleteNode(peer.id)
    peers.value = peers.value.filter(p => p.id !== peer.id)
  } catch (e: any) {
    error.value = e.message
  }
}

async function updateTopology(topology: string) {
  if (!fedSettings.value) return
  try {
    const { api } = await import('../../api')
    fedSettings.value = await api.updateFederationSettings({ topology: topology as any })
  } catch (e: any) {
    error.value = e.message
  }
}

function relativeTime(dateStr: string | null): string {
  if (!dateStr) return '—'
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'gerade eben'
  if (mins < 60) return `vor ${mins} Min.`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `vor ${hours} Std.`
  return `vor ${Math.floor(hours / 24)} Tagen`
}

function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text)
}

function statusColor(status: string): string {
  switch (status) {
    case 'active': return 'var(--color-success)'
    case 'inactive': return 'var(--color-warning)'
    case 'blocked': return 'var(--color-danger)'
    default: return 'var(--color-text-muted)'
  }
}

onMounted(loadData)
</script>

<template>
  <div class="federation-settings">
    <p v-if="error" class="error-text">{{ error }}</p>

    <!-- Node Identity -->
    <div class="sub-section">
      <h3 class="sub-title">🔑 Eigene Node-Identität</h3>
      <div v-if="identity" class="identity-grid">
        <div class="identity-row">
          <span class="identity-label">Node-ID:</span>
          <span class="identity-value mono">{{ identity.node_id }}</span>
          <button class="copy-btn" @click="copyToClipboard(identity.node_id)" title="Kopieren">📋</button>
        </div>
        <div class="identity-row">
          <span class="identity-label">Name:</span>
          <span class="identity-value">{{ identity.node_name }}</span>
        </div>
        <div class="identity-row">
          <span class="identity-label">URL:</span>
          <span class="identity-value mono">{{ identity.node_url }}</span>
        </div>
        <div class="identity-row">
          <span class="identity-label">Public Key:</span>
          <span class="identity-value mono" :title="identity.public_key">{{ truncatedKey }}</span>
          <button class="copy-btn" @click="copyToClipboard(identity.public_key)" title="Kopieren">📋</button>
        </div>
      </div>
      <p v-else class="section-desc">Keine Node-Identität konfiguriert.</p>
    </div>

    <!-- Peer List -->
    <div class="sub-section">
      <div class="sub-title-row">
        <h3 class="sub-title">🌐 Bekannte Peers</h3>
        <button class="btn-primary" @click="showAddPeer = true">+ Peer hinzufügen</button>
      </div>

      <table v-if="peers.length" class="peer-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>URL</th>
            <th>Status</th>
            <th>Zuletzt gesehen</th>
            <th>Aktionen</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="peer in peers" :key="peer.id">
            <td>{{ peer.node_name }}</td>
            <td class="mono">{{ peer.node_url }}</td>
            <td>
              <span class="status-badge" :style="{ color: statusColor(peer.status) }">●</span>
              {{ peer.status }}
            </td>
            <td>{{ relativeTime(peer.last_seen) }}</td>
            <td class="action-cell">
              <button
                v-if="peer.status !== 'blocked'"
                class="btn-sm btn-warn"
                @click="blockPeer(peer)"
              >Blockieren</button>
              <button class="btn-sm btn-danger" @click="removePeer(peer)">Entfernen</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="section-desc">Keine Peers konfiguriert.</p>

      <!-- Add Peer Modal -->
      <div v-if="showAddPeer" class="modal-overlay" @click.self="showAddPeer = false">
        <div class="modal-content">
          <h3>Peer hinzufügen</h3>
          <div class="form-group">
            <label>Name *</label>
            <input v-model="newPeerName" type="text" placeholder="peer-alpha" class="input" />
          </div>
          <div class="form-group">
            <label>URL *</label>
            <input v-model="newPeerUrl" type="url" placeholder="http://peer:8000" class="input" />
          </div>
          <div class="form-group">
            <label>Public Key</label>
            <input v-model="newPeerKey" type="text" placeholder="ssh-ed25519 ..." class="input" />
          </div>
          <div class="modal-actions">
            <button class="btn-secondary" @click="showAddPeer = false">Abbrechen</button>
            <button class="btn-primary" @click="addPeer" :disabled="!newPeerName || !newPeerUrl">Hinzufügen</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Topology -->
    <div class="sub-section">
      <h3 class="sub-title">🔀 Topologie</h3>
      <div class="topology-options">
        <label
          v-for="opt in topologyOptions"
          :key="opt.value"
          class="topology-option"
          :class="{ 'topology-option--active': fedSettings?.topology === opt.value }"
        >
          <input
            type="radio"
            name="topology"
            :value="opt.value"
            :checked="fedSettings?.topology === opt.value"
            @change="updateTopology(opt.value)"
          />
          <div>
            <span class="topology-label">{{ opt.label }}</span>
            <p class="topology-desc">{{ opt.desc }}</p>
          </div>
        </label>
      </div>
    </div>

    <!-- Hive Station -->
    <div v-if="showHiveStation" class="sub-section">
      <h3 class="sub-title">🏠 Hive Station</h3>
      <div class="form-group">
        <label>URL</label>
        <input
          :value="fedSettings?.hive_station_url"
          type="url"
          class="input"
          placeholder="https://hub.example.com"
          readonly
        />
      </div>
      <div class="form-group">
        <label>Token</label>
        <input
          :value="fedSettings?.hive_station_token ? '••••••••' : ''"
          type="password"
          class="input"
          readonly
        />
      </div>
      <div class="info-row">
        <span class="identity-label">Relay:</span>
        <span class="identity-value">{{ fedSettings?.hive_relay_enabled ? 'Aktiviert' : 'Deaktiviert' }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.federation-settings {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.sub-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.sub-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-base);
  color: var(--color-text);
  margin: 0;
}

.sub-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.identity-grid {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.identity-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.identity-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  min-width: 80px;
}

.identity-value {
  font-size: var(--font-size-xs);
  color: var(--color-text);
}

.mono { font-family: var(--font-mono); }

.copy-btn {
  background: none;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-1);
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
}
.copy-btn:hover { border-color: var(--color-accent); }

/* Peer Table */
.peer-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.peer-table th,
.peer-table td {
  text-align: left;
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--color-border);
}

.peer-table th {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.status-badge { font-size: 10px; }

.action-cell {
  display: flex;
  gap: var(--space-2);
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
  background: var(--color-surface-alt);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-4);
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
  cursor: pointer;
}

.btn-sm {
  font-size: var(--font-size-xs);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  border: 1px solid;
  cursor: pointer;
  font-family: var(--font-mono);
}

.btn-warn {
  border-color: var(--color-warning);
  color: var(--color-warning);
  background: transparent;
}
.btn-warn:hover { background: var(--color-warning); color: var(--color-bg); }

.btn-danger {
  border-color: var(--color-danger);
  color: var(--color-danger);
  background: transparent;
}
.btn-danger:hover { background: var(--color-danger); color: var(--color-bg); }

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
}

.modal-content {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-6);
  min-width: 400px;
  max-width: 500px;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.modal-content h3 {
  font-family: var(--font-heading);
  color: var(--color-text);
  margin: 0;
}

.modal-actions {
  display: flex;
  gap: var(--space-3);
  justify-content: flex-end;
}

/* Form */
.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.form-group label {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.input {
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
  color: var(--color-text);
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
}
.input:focus {
  outline: none;
  border-color: var(--color-accent);
}

/* Topology */
.topology-options {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.topology-option {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: border-color var(--transition-duration) ease;
}
.topology-option:hover { border-color: var(--color-text-muted); }
.topology-option--active { border-color: var(--color-accent); }

.topology-option input[type="radio"] {
  margin-top: var(--space-1);
  accent-color: var(--color-accent);
}

.topology-label {
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  color: var(--color-text);
  font-weight: 600;
}

.topology-desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  margin: var(--space-1) 0 0;
}

.info-row {
  display: flex;
  gap: var(--space-3);
  align-items: center;
}

.error-text {
  color: var(--color-danger);
  font-size: var(--font-size-sm);
  margin: 0;
}

.section-desc {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  margin: 0;
}
</style>
