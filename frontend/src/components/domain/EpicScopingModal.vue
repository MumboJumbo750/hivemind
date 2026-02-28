<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '../../api'
import type { Epic } from '../../api/types'

const props = defineProps<{
  epic: Epic
  projectId: string
}>()

const emit = defineEmits<{
  (e: 'done'): void
  (e: 'cancel'): void
}>()

// Form state
const ownerId = ref<string>('')
const priority = ref<string>(props.epic.priority ?? 'medium')
const slaDeadline = ref<string>(props.epic.sla_due_at ? props.epic.sla_due_at.split('T')[0] : '')
const dodLines = ref<string[]>(props.epic.dod_framework?.criteria ?? [''])
const loading = ref(false)
const error = ref<string | null>(null)

// Members for owner dropdown
interface Member { project_id: string; user_id: string; role: string; username?: string }
const members = ref<Member[]>([])

onMounted(async () => {
  try {
    members.value = await api.getMembers(props.projectId) as Member[]
  } catch {
    // ignore
  }
})

function addDodLine() {
  dodLines.value.push('')
}

function removeDodLine(i: number) {
  dodLines.value.splice(i, 1)
}

async function handleSubmit() {
  if (!ownerId.value || !priority.value) {
    error.value = 'Owner und Priority sind Pflichtfelder.'
    return
  }
  error.value = null
  loading.value = true
  try {
    await api.patchEpic(props.epic.epic_key, {
      state: 'scoped',
      owner_id: ownerId.value,
      priority: priority.value as Epic['priority'],
      sla_due_at: slaDeadline.value ? new Date(slaDeadline.value).toISOString() : undefined,
      dod_framework: dodLines.value.filter(Boolean).length > 0
        ? { criteria: dodLines.value.filter(Boolean) }
        : undefined,
      expected_version: props.epic.version,
    } as Parameters<typeof api.patchEpic>[1])
    emit('done')
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div class="modal-overlay" @click.self="emit('cancel')">
      <div class="modal" role="dialog" :aria-label="`Epic scopen: ${epic.title}`">
        <div class="modal__header">
          <h2 class="modal__title">Epic scopen</h2>
          <button class="modal__close" @click="emit('cancel')">✕</button>
        </div>

        <div class="modal__body">
          <p class="modal__epic-key">{{ epic.epic_key }} — {{ epic.title }}</p>

          <!-- Owner -->
          <div class="field">
            <label class="field__label">Owner <span class="required">*</span></label>
            <select v-model="ownerId" class="hm-select">
              <option value="">— Owner wählen —</option>
              <option
                v-for="m in members"
                :key="m.user_id"
                :value="m.user_id"
              >
                {{ m.username ?? m.user_id }} ({{ m.role }})
              </option>
            </select>
          </div>

          <!-- Priority -->
          <div class="field">
            <label class="field__label">Priority <span class="required">*</span></label>
            <select v-model="priority" class="hm-select">
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
              <option value="critical">critical</option>
            </select>
          </div>

          <!-- SLA Deadline -->
          <div class="field">
            <label class="field__label">SLA-Deadline</label>
            <input type="date" v-model="slaDeadline" class="hm-input" />
          </div>

          <!-- DoD -->
          <div class="field">
            <label class="field__label">Definition of Done</label>
            <div
              v-for="(line, i) in dodLines"
              :key="i"
              class="dod-row"
            >
              <input
                v-model="dodLines[i]"
                class="hm-input"
                :placeholder="`Kriterium ${i + 1}`"
              />
              <button class="btn-icon" @click="removeDodLine(i)" title="Entfernen">✕</button>
            </div>
            <button class="btn-add-dod" @click="addDodLine">+ Kriterium</button>
          </div>

          <p v-if="error" class="error-text">{{ error }}</p>
        </div>

        <div class="modal__footer">
          <button class="btn-secondary" @click="emit('cancel')" :disabled="loading">
            Abbrechen
          </button>
          <button class="btn-primary" @click="handleSubmit" :disabled="loading">
            {{ loading ? '...' : 'SCOPEN →' }}
          </button>
        </div>
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
  z-index: 500;
}

.modal {
  width: 480px;
  max-width: calc(100vw - var(--space-8));
  max-height: 85vh;
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

.modal__epic-key {
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  margin: 0;
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

.required { color: var(--color-danger); }

.hm-input, .hm-select {
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
.hm-input:focus, .hm-select:focus {
  border-color: var(--input-focus-border);
  outline: none;
}

.dod-row {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  margin-bottom: var(--space-1);
}

.btn-icon {
  background: none;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: var(--font-size-xs);
  flex-shrink: 0;
}
.btn-icon:hover { color: var(--color-danger); }

.btn-add-dod {
  background: none;
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  padding: var(--space-1) var(--space-3);
  cursor: pointer;
  align-self: flex-start;
  transition: border-color var(--transition-duration) ease, color var(--transition-duration) ease;
}
.btn-add-dod:hover { border-color: var(--color-accent); color: var(--color-accent); }

.error-text {
  color: var(--color-danger);
  font-size: var(--font-size-sm);
  margin: 0;
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
.btn-secondary:disabled { opacity: 0.5; cursor: not-allowed; }

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
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
