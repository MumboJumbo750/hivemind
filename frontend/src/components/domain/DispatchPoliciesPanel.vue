<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../../api'
import type { DispatchPolicy } from '../../api/types'

const policies = ref<DispatchPolicy[]>([])
const loading = ref(true)
const error = ref('')
const saving = ref<string | null>(null)
const toast = ref('')

const executionModes = ['local', 'ide', 'github_actions', 'byoai']

// Editing state per role
const editing = ref<Record<string, Partial<DispatchPolicy>>>({})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.getDispatchPolicies()
    policies.value = res.policies
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Fehler beim Laden'
  } finally {
    loading.value = false
  }
}

function startEdit(p: DispatchPolicy) {
  editing.value[p.agent_role] = {
    preferred_execution_mode: p.preferred_execution_mode,
    rpm_limit: p.rpm_limit,
    token_budget: p.token_budget,
    max_parallel: p.max_parallel,
    cooldown_seconds: p.cooldown_seconds,
    enabled: p.enabled,
  }
}

function cancelEdit(role: string) {
  delete editing.value[role]
}

function isEditing(role: string): boolean {
  return role in editing.value
}

async function save(role: string) {
  const draft = editing.value[role]
  if (!draft) return
  saving.value = role
  try {
    await api.updateDispatchPolicy(role, {
      preferred_execution_mode: draft.preferred_execution_mode,
      rpm_limit: draft.rpm_limit,
      token_budget: draft.token_budget,
      max_parallel: draft.max_parallel,
      cooldown_seconds: draft.cooldown_seconds,
      enabled: draft.enabled,
    })
    delete editing.value[role]
    showToast('Gespeichert')
    await load()
  } catch (e: unknown) {
    showToast(e instanceof Error ? e.message : 'Fehler beim Speichern')
  } finally {
    saving.value = null
  }
}

async function resetPolicy(role: string) {
  saving.value = role
  try {
    await api.resetDispatchPolicy(role)
    delete editing.value[role]
    showToast(`${role} auf Defaults zurückgesetzt`)
    await load()
  } catch (e: unknown) {
    showToast(e instanceof Error ? e.message : 'Fehler beim Reset')
  } finally {
    saving.value = null
  }
}

function showToast(msg: string) {
  toast.value = msg
  setTimeout(() => { toast.value = '' }, 3000)
}

onMounted(() => void load())
</script>

<template>
  <div class="dp-panel">
    <!-- Error -->
    <p v-if="error" class="dp-error">{{ error }}</p>

    <!-- Loading -->
    <div v-if="loading" class="dp-loading">Lade Dispatch Policies…</div>

    <!-- Policies Table -->
    <div v-else-if="policies.length > 0" class="dp-table-wrap">
      <table class="dp-table">
        <thead>
          <tr>
            <th>Rolle</th>
            <th>Exec Mode</th>
            <th>RPM</th>
            <th>Token Budget</th>
            <th>Max Parallel</th>
            <th>Cooldown (s)</th>
            <th>Enabled</th>
            <th>Status</th>
            <th>Quelle</th>
            <th>Aktionen</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in policies" :key="p.agent_role" class="dp-row">
            <td class="dp-role">{{ p.agent_role }}</td>

            <!-- Exec Mode -->
            <td>
              <select
                v-if="isEditing(p.agent_role)"
                v-model="editing[p.agent_role].preferred_execution_mode"
                class="dp-input dp-input--select"
              >
                <option v-for="m in executionModes" :key="m" :value="m">{{ m }}</option>
              </select>
              <span v-else class="dp-value">{{ p.preferred_execution_mode }}</span>
            </td>

            <!-- RPM Limit -->
            <td>
              <input
                v-if="isEditing(p.agent_role)"
                v-model.number="editing[p.agent_role].rpm_limit"
                type="number" min="1" class="dp-input dp-input--num"
              />
              <span v-else class="dp-value">{{ p.rpm_limit }}</span>
            </td>

            <!-- Token Budget -->
            <td>
              <input
                v-if="isEditing(p.agent_role)"
                v-model.number="editing[p.agent_role].token_budget"
                type="number" min="100" class="dp-input dp-input--num"
              />
              <span v-else class="dp-value">{{ p.token_budget.toLocaleString() }}</span>
            </td>

            <!-- Max Parallel -->
            <td>
              <input
                v-if="isEditing(p.agent_role)"
                v-model.number="editing[p.agent_role].max_parallel"
                type="number" min="1" class="dp-input dp-input--num"
              />
              <span v-else class="dp-value">{{ p.max_parallel }}</span>
            </td>

            <!-- Cooldown -->
            <td>
              <input
                v-if="isEditing(p.agent_role)"
                v-model.number="editing[p.agent_role].cooldown_seconds"
                type="number" min="0" class="dp-input dp-input--num"
              />
              <span v-else class="dp-value">{{ p.cooldown_seconds }}s</span>
            </td>

            <!-- Enabled -->
            <td>
              <label v-if="isEditing(p.agent_role)" class="dp-toggle">
                <input type="checkbox" v-model="editing[p.agent_role].enabled" />
                <span class="dp-toggle__track" />
              </label>
              <span v-else class="dp-enabled" :class="p.enabled ? 'dp-enabled--on' : 'dp-enabled--off'">
                {{ p.enabled ? 'ON' : 'OFF' }}
              </span>
            </td>

            <!-- Live Status -->
            <td>
              <span v-if="p.active_dispatches !== null" class="dp-status" :class="{ 'dp-status--limit': p.at_limit }">
                {{ p.active_dispatches }} aktiv
              </span>
              <span v-else class="dp-muted">–</span>
            </td>

            <!-- Source -->
            <td>
              <span class="dp-source" :class="'dp-source--' + p.source">{{ p.source }}</span>
            </td>

            <!-- Actions -->
            <td class="dp-actions">
              <template v-if="isEditing(p.agent_role)">
                <button class="dp-btn dp-btn--save" @click="save(p.agent_role)" :disabled="saving === p.agent_role">
                  {{ saving === p.agent_role ? '…' : 'Speichern' }}
                </button>
                <button class="dp-btn dp-btn--cancel" @click="cancelEdit(p.agent_role)">Abbrechen</button>
              </template>
              <template v-else>
                <button class="dp-btn" @click="startEdit(p)">Bearbeiten</button>
                <button
                  v-if="p.source === 'db'"
                  class="dp-btn dp-btn--reset"
                  @click="resetPolicy(p.agent_role)"
                  :disabled="saving === p.agent_role"
                >Reset</button>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Empty -->
    <p v-else class="dp-empty">Keine Dispatch Policies gefunden.</p>

    <!-- Toast -->
    <Transition name="toast">
      <div v-if="toast" class="dp-toast">{{ toast }}</div>
    </Transition>
  </div>
</template>

<style scoped>
.dp-panel {
  position: relative;
}

.dp-error {
  color: var(--color-danger);
  padding: var(--space-3);
  background: var(--color-danger-10);
  border-radius: var(--radius-sm);
}

.dp-loading {
  color: var(--color-text-muted);
  text-align: center;
  padding: var(--space-6);
}

.dp-empty {
  color: var(--color-text-muted);
  text-align: center;
  padding: var(--space-6);
}

/* ── Table ─────────────────────────────────────────────────────────────── */
.dp-table-wrap { overflow-x: auto; }

.dp-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-xs);
}

.dp-table th {
  text-align: left;
  padding: var(--space-2);
  color: var(--color-text-muted);
  font-weight: 600;
  border-bottom: 1px solid var(--color-border);
  font-size: var(--font-size-2xs);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  white-space: nowrap;
}

.dp-table td {
  padding: var(--space-2);
  border-bottom: 1px solid var(--color-border);
  vertical-align: middle;
}

.dp-row:hover { background: var(--color-surface-alt); }

.dp-role {
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--color-accent);
  white-space: nowrap;
}

.dp-value {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
}

.dp-muted { color: var(--color-text-muted); }

/* ── Inline Editing ────────────────────────────────────────────────────── */
.dp-input {
  background: var(--color-surface);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xs);
  padding: var(--space-1) var(--space-2);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
}
.dp-input:focus { outline: none; border-color: var(--color-accent); }

.dp-input--num { width: 70px; }
.dp-input--select { min-width: 100px; }

/* ── Toggle ────────────────────────────────────────────────────────────── */
.dp-toggle {
  display: inline-flex;
  align-items: center;
  cursor: pointer;
}
.dp-toggle input { display: none; }

.dp-toggle__track {
  width: 32px;
  height: 18px;
  background: var(--color-border);
  border-radius: var(--radius-full);
  position: relative;
  transition: background 0.2s;
}
.dp-toggle__track::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 14px;
  height: 14px;
  background: var(--color-text-muted);
  border-radius: var(--radius-full);
  transition: transform 0.2s;
}
.dp-toggle input:checked + .dp-toggle__track { background: var(--color-success); }
.dp-toggle input:checked + .dp-toggle__track::after { transform: translateX(14px); background: white; }

.dp-enabled {
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  font-weight: 600;
  padding: 1px var(--space-2);
  border-radius: var(--radius-full);
}
.dp-enabled--on { background: var(--color-success-10); color: var(--color-success); }
.dp-enabled--off { background: var(--color-danger-10); color: var(--color-danger); }

/* ── Status ────────────────────────────────────────────────────────────── */
.dp-status {
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  padding: 1px var(--space-2);
  border-radius: var(--radius-full);
  background: var(--color-surface-alt);
  color: var(--color-text-muted);
}
.dp-status--limit { background: var(--color-warning-10); color: var(--color-warning); }

.dp-source {
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  padding: 1px var(--space-2);
  border-radius: var(--radius-full);
}
.dp-source--db { background: var(--color-accent-10); color: var(--color-accent); }
.dp-source--default { background: var(--color-surface-alt); color: var(--color-text-muted); }

/* ── Actions ───────────────────────────────────────────────────────────── */
.dp-actions {
  display: flex;
  gap: var(--space-1);
  white-space: nowrap;
}

.dp-btn {
  background: var(--color-surface-alt);
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--font-size-2xs);
  transition: background 0.15s;
}
.dp-btn:hover:not(:disabled) { background: var(--color-border); color: var(--color-text); }
.dp-btn:disabled { opacity: 0.4; cursor: default; }

.dp-btn--save { background: var(--color-accent-10); color: var(--color-accent); border-color: var(--color-accent); }
.dp-btn--save:hover:not(:disabled) { background: var(--color-accent-20); }

.dp-btn--cancel { border-color: transparent; }

.dp-btn--reset { color: var(--color-warning); }
.dp-btn--reset:hover:not(:disabled) { border-color: var(--color-warning); background: var(--color-warning-10); }

/* ── Toast ─────────────────────────────────────────────────────────────── */
.dp-toast {
  position: fixed;
  bottom: var(--space-6);
  right: var(--space-6);
  background: var(--color-surface);
  border: 1px solid var(--color-accent);
  color: var(--color-text);
  padding: var(--space-3) var(--space-5);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  z-index: 200;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
}

.toast-enter-active,
.toast-leave-active { transition: opacity 0.3s, transform 0.3s; }
.toast-enter-from,
.toast-leave-to { opacity: 0; transform: translateY(10px); }
</style>
