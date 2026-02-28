<script setup lang="ts">
import { ref, watch } from 'vue'
import { HivemindModal } from '../ui'
import { api } from '../../api'
import { useProjectStore } from '../../stores/projectStore'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()

const projectStore = useProjectStore()

const name = ref('')
const slug = ref('')
const description = ref('')
const slugManuallyEdited = ref(false)
const slugError = ref<string | null>(null)
const error = ref<string | null>(null)
const loading = ref(false)

function generateSlug(val: string): string {
  return val.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '')
}

watch(name, (val) => {
  if (!slugManuallyEdited.value) {
    slug.value = generateSlug(val)
  }
})

async function handleSubmit() {
  if (!name.value || !slug.value) return
  slugError.value = null
  error.value = null
  loading.value = true
  try {
    const project = await api.createProject({
      name: name.value,
      slug: slug.value,
      description: description.value || undefined,
    })
    projectStore.projects.push(project)
    await projectStore.setActiveProject(project)
    emit('update:modelValue', false)
    name.value = ''
    slug.value = ''
    description.value = ''
    slugManuallyEdited.value = false
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e)
    if (msg.includes('409') || msg.toLowerCase().includes('conflict')) {
      slugError.value = 'Dieser Slug ist bereits vergeben.'
    } else {
      error.value = msg
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <HivemindModal
    :model-value="props.modelValue"
    @update:model-value="emit('update:modelValue', $event)"
    title="Neues Projekt anlegen"
  >
    <form class="create-form" @submit.prevent="handleSubmit">
      <div class="form-field">
        <label class="form-label">Name</label>
        <input
          v-model="name"
          class="form-input"
          required
          maxlength="100"
          placeholder="Mein Projekt"
        />
      </div>
      <div class="form-field">
        <label class="form-label">Slug</label>
        <input
          v-model="slug"
          class="form-input"
          @input="slugManuallyEdited = true"
          pattern="[a-z0-9-]+"
          placeholder="mein-projekt"
        />
        <span v-if="slugError" class="field-error">{{ slugError }}</span>
        <span v-else class="field-hint">Nur Kleinbuchstaben, Zahlen und Bindestriche</span>
      </div>
      <div class="form-field">
        <label class="form-label">Beschreibung</label>
        <textarea
          v-model="description"
          class="form-input"
          maxlength="500"
          placeholder="Projektbeschreibung (optional)"
          rows="3"
        />
      </div>
      <span v-if="error" class="form-error">{{ error }}</span>
    </form>
    <template #footer>
      <button type="button" class="btn-cancel" @click="emit('update:modelValue', false)">
        Abbrechen
      </button>
      <button
        type="submit"
        class="btn-submit"
        @click="handleSubmit"
        :disabled="loading || !name || !slug"
      >
        {{ loading ? '...' : 'PROJEKT ANLEGEN' }}
      </button>
    </template>
  </HivemindModal>
</template>

<style scoped>
.create-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.form-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.form-input {
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
  padding: var(--space-2) var(--space-3);
  resize: vertical;
}
.form-input:focus {
  border-color: var(--input-focus-border);
  outline: none;
}

.field-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.field-error {
  font-size: var(--font-size-xs);
  color: var(--color-danger);
}

.form-error {
  font-size: var(--font-size-sm);
  color: var(--color-danger);
}

.btn-cancel {
  background: transparent;
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-4);
  font-size: var(--font-size-sm);
  cursor: pointer;
}
.btn-cancel:hover { color: var(--color-text); border-color: var(--color-text-muted); }

.btn-submit {
  background: var(--button-primary-bg);
  color: var(--button-primary-text);
  border: none;
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-4);
  font-family: var(--font-heading);
  font-size: var(--font-size-sm);
  cursor: pointer;
  font-weight: 600;
}
.btn-submit:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
