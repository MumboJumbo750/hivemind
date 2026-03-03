<script setup lang="ts">
/**
 * GovernanceConfigPanel.vue — TASK-8-022
 * Configuration panel for per-governance-type automation levels.
 */
import { ref, onMounted } from 'vue'
import type { GovernanceConfig, GovernanceLevel } from '../../api/types'

interface GovernanceTypeEntry {
  key: string
  label: string
  description: string
}

const GOVERNANCE_TYPES: GovernanceTypeEntry[] = [
  {
    key: 'review',
    label: 'Review',
    description: 'Review-Gate für Tasks: Wann darf ein Review automatisch akzeptiert werden?',
  },
  {
    key: 'epic_proposal',
    label: 'Epic-Vorschlag',
    description: 'Neue Epic-Proposals: Wann werden sie automatisch angenommen?',
  },
  {
    key: 'epic_scoping',
    label: 'Epic-Scoping',
    description: 'DoD-Generierung und Epic-Scoping: Wann greift der Planer automatisch?',
  },
  {
    key: 'skill_merge',
    label: 'Skill-Merge',
    description: 'Skill-Merge-Requests: Wann werden Skills automatisch gemergt?',
  },
  {
    key: 'guard_merge',
    label: 'Guard-Merge',
    description: 'Guard-Merge aus Feedback-Schleife: Wann automatisch akzeptieren?',
  },
  {
    key: 'decision_request',
    label: 'Entscheidungsanfragen',
    description: 'Decision Requests: Wann löst Hivemind automatisch auf?',
  },
  {
    key: 'escalation',
    label: 'Eskalation',
    description: 'Eskalationen: Wann werden diese automatisch weitergeleitet oder archiviert?',
  },
]

const LEVEL_OPTIONS: { value: GovernanceLevel; label: string; color: string }[] = [
  { value: 'manual', label: 'Manuell', color: 'var(--color-text-muted)' },
  { value: 'assisted', label: 'Unterstützt', color: 'var(--color-warning)' },
  { value: 'auto', label: 'Automatisch', color: 'var(--color-success)' },
]

const levels = ref<Record<string, GovernanceLevel>>({})
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const saved = ref(false)

function levelColor(level: GovernanceLevel): string {
  return LEVEL_OPTIONS.find(o => o.value === level)?.color ?? 'var(--color-text-muted)'
}

function levelLabel(level: GovernanceLevel): string {
  return LEVEL_OPTIONS.find(o => o.value === level)?.label ?? level
}

async function loadGovernance() {
  loading.value = true
  error.value = ''
  try {
    const { api } = await import('../../api')
    const cfg: GovernanceConfig = await api.getGovernance()
    levels.value = { ...cfg }
  } catch (e: any) {
    error.value = e.message
    // Initialize defaults so the panel is still usable
    const defaults: Record<string, GovernanceLevel> = {}
    for (const t of GOVERNANCE_TYPES) defaults[t.key] = 'manual'
    levels.value = defaults
  } finally {
    loading.value = false
  }
}

async function saveGovernance() {
  saving.value = true
  error.value = ''
  saved.value = false
  try {
    const { api } = await import('../../api')
    await api.updateGovernance(levels.value as GovernanceConfig)
    saved.value = true
    setTimeout(() => { saved.value = false }, 3000)
  } catch (e: any) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

onMounted(loadGovernance)
</script>

<template>
  <div class="governance-panel">
    <p v-if="error" class="error-text">{{ error }}</p>

    <!-- Safeguard notice -->
    <div class="safeguard-box">
      <span class="safeguard-box__icon">!</span>
      <div>
        <strong>Sicherheitshinweis:</strong> Automatisches <em>Ablehnen</em> ist in keinem Modus
        vorgesehen. Hivemind kann Aktionen automatisch <em>annehmen</em> oder <em>weiterleiten</em>,
        lehnt aber nie eigenständig ab.
      </div>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="loading-text">Lade Governance-Konfiguration…</div>

    <!-- Governance grid -->
    <div v-else class="governance-grid">
      <div
        v-for="entry in GOVERNANCE_TYPES"
        :key="entry.key"
        class="governance-card"
      >
        <div class="card-header">
          <div class="card-meta">
            <span class="card-label">{{ entry.label }}</span>
            <span
              class="level-badge"
              :style="{ color: levelColor(levels[entry.key] ?? 'manual'), borderColor: levelColor(levels[entry.key] ?? 'manual') }"
            >
              {{ levelLabel(levels[entry.key] ?? 'manual') }}
            </span>
          </div>
          <p class="card-desc">{{ entry.description }}</p>
        </div>

        <!-- Level selector -->
        <div class="level-selector">
          <label
            v-for="opt in LEVEL_OPTIONS"
            :key="opt.value"
            class="level-option"
            :class="{ 'level-option--active': levels[entry.key] === opt.value }"
            :style="levels[entry.key] === opt.value ? { borderColor: opt.color } : {}"
          >
            <input
              type="radio"
              :name="'gov-' + entry.key"
              :value="opt.value"
              v-model="levels[entry.key]"
              style="display: none"
            />
            <span class="level-dot" :style="{ background: opt.color }"></span>
            <span class="level-option-label">{{ opt.label }}</span>
          </label>
        </div>
      </div>
    </div>

    <!-- Save row -->
    <div class="save-row">
      <span v-if="saved" class="saved-note">Gespeichert.</span>
      <button
        class="btn-primary"
        :disabled="saving || loading"
        @click="saveGovernance"
      >
        {{ saving ? 'Speichern…' : 'Governance speichern' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.governance-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

/* Safeguard box */
.safeguard-box {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  background: color-mix(in srgb, var(--color-warning) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-warning) 35%, transparent);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
  font-size: var(--font-size-sm);
  color: var(--color-text);
}

.safeguard-box__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 1px solid var(--color-warning);
  color: var(--color-warning);
  font-size: 11px;
  font-weight: bold;
  flex-shrink: 0;
  margin-top: 1px;
}

.loading-text {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

/* Grid */
.governance-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
}

@media (max-width: 768px) {
  .governance-grid { grid-template-columns: 1fr; }
}

/* Cards */
.governance-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  background: var(--color-surface-alt);
  transition: border-color 0.15s;
}

.governance-card:hover { border-color: var(--color-text-muted); }

.card-header {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.card-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.card-label {
  font-family: var(--font-heading);
  font-size: var(--font-size-sm);
  color: var(--color-text);
  font-weight: 600;
}

.level-badge {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  border: 1px solid;
  border-radius: 10px;
  padding: 1px 8px;
  flex-shrink: 0;
}

.card-desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  margin: 0;
  line-height: 1.5;
}

/* Level selector */
.level-selector {
  display: flex;
  gap: var(--space-2);
}

.level-option {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  transition: border-color 0.15s, color 0.15s;
  flex: 1;
  justify-content: center;
}

.level-option:hover { border-color: var(--color-text-muted); color: var(--color-text); }

.level-option--active {
  color: var(--color-text);
  font-weight: 600;
}

.level-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.level-option-label {
  font-family: var(--font-mono);
}

/* Save row */
.save-row {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-3);
  padding-top: var(--space-2);
  border-top: 1px solid var(--color-border);
}

.saved-note {
  font-size: var(--font-size-sm);
  color: var(--color-success);
  font-family: var(--font-mono);
}

/* Buttons */
.btn-primary {
  background: var(--color-accent);
  color: var(--color-bg);
  border: none;
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-5);
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
  cursor: pointer;
  font-weight: 600;
}
.btn-primary:hover { opacity: 0.9; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

/* Utility */
.error-text {
  color: var(--color-danger);
  font-size: var(--font-size-sm);
  margin: 0;
}
</style>
