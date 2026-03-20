<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { api } from '../../api'
import type { Project, ProjectIntegration, ProjectIntegrationProvider } from '../../api/types'

const projects = ref<Project[]>([])
const integrations = ref<ProjectIntegration[]>([])
const selectedProjectId = ref('')
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const editingId = ref<string | null>(null)

const form = ref({
  provider: 'youtrack' as ProjectIntegrationProvider,
  display_name: '',
  integration_key: '',
  base_url: '',
  external_project_key: '',
  project_selector_text: '',
  status_mapping_text: '',
  routing_hints_text: '',
  webhook_secret: '',
  access_token: '',
  sync_enabled: true,
  sync_direction: 'bidirectional',
})

const selectedProject = computed(() => projects.value.find(project => project.id === selectedProjectId.value) ?? null)

function formatDate(value?: string | null): string {
  if (!value) return '—'
  return new Date(value).toLocaleString('de-DE', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function badgeClass(status: string): string {
  switch (status) {
    case 'active': return 'badge--active'
    case 'incomplete': return 'badge--incomplete'
    case 'error': return 'badge--error'
    default: return 'badge--disabled'
  }
}

function parseJson(text: string): Record<string, unknown> | undefined {
  const trimmed = text.trim()
  if (!trimmed) return undefined
  return JSON.parse(trimmed) as Record<string, unknown>
}

function stringifyJson(value?: Record<string, unknown> | null): string {
  return value ? JSON.stringify(value, null, 2) : ''
}

function resetForm(): void {
  editingId.value = null
  form.value = {
    provider: 'youtrack',
    display_name: '',
    integration_key: '',
    base_url: '',
    external_project_key: '',
    project_selector_text: '',
    status_mapping_text: '',
    routing_hints_text: '',
    webhook_secret: '',
    access_token: '',
    sync_enabled: true,
    sync_direction: 'bidirectional',
  }
}

function editIntegration(integration: ProjectIntegration): void {
  editingId.value = integration.id
  form.value = {
    provider: integration.provider,
    display_name: integration.display_name ?? '',
    integration_key: integration.integration_key ?? '',
    base_url: integration.base_url ?? '',
    external_project_key: integration.external_project_key ?? '',
    project_selector_text: stringifyJson(integration.project_selector),
    status_mapping_text: stringifyJson(integration.status_mapping),
    routing_hints_text: stringifyJson(integration.routing_hints),
    webhook_secret: '',
    access_token: '',
    sync_enabled: integration.sync_enabled,
    sync_direction: integration.sync_direction,
  }
}

async function loadProjects(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    projects.value = await api.getProjects()
    if (!selectedProjectId.value && projects.value.length > 0) {
      selectedProjectId.value = projects.value[0].id
    }
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Projekte konnten nicht geladen werden'
  } finally {
    loading.value = false
  }
}

async function loadIntegrations(): Promise<void> {
  if (!selectedProjectId.value) {
    integrations.value = []
    return
  }
  loading.value = true
  error.value = ''
  try {
    integrations.value = await api.getProjectIntegrations(selectedProjectId.value)
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Integrationen konnten nicht geladen werden'
  } finally {
    loading.value = false
  }
}

async function saveIntegration(): Promise<void> {
  if (!selectedProjectId.value) return
  saving.value = true
  error.value = ''
  try {
    const payload = {
      provider: form.value.provider,
      display_name: form.value.display_name || undefined,
      integration_key: form.value.integration_key || undefined,
      base_url: form.value.base_url || undefined,
      external_project_key: form.value.external_project_key || undefined,
      project_selector: parseJson(form.value.project_selector_text),
      status_mapping: parseJson(form.value.status_mapping_text),
      routing_hints: parseJson(form.value.routing_hints_text),
      webhook_secret: form.value.webhook_secret || undefined,
      access_token: form.value.access_token || undefined,
      sync_enabled: form.value.sync_enabled,
      sync_direction: form.value.sync_direction,
    }

    if (editingId.value) {
      await api.updateProjectIntegration(selectedProjectId.value, editingId.value, payload)
    } else {
      await api.createProjectIntegration(selectedProjectId.value, payload)
    }
    resetForm()
    await loadIntegrations()
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Integration konnte nicht gespeichert werden'
  } finally {
    saving.value = false
  }
}

async function checkIntegration(integrationId: string): Promise<void> {
  if (!selectedProjectId.value) return
  error.value = ''
  try {
    await api.checkProjectIntegration(selectedProjectId.value, integrationId)
    await loadIntegrations()
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Healthcheck fehlgeschlagen'
  }
}

watch(selectedProjectId, () => {
  resetForm()
  void loadIntegrations()
})

onMounted(async () => {
  await loadProjects()
  await loadIntegrations()
})
</script>

<template>
  <section class="project-integrations">
    <header class="panel-header">
      <div>
        <h2 class="panel-title">Projekt-Integrationen</h2>
        <p class="panel-subtitle">YouTrack, Sentry und In-App-Mappings pro Projekt konfigurieren und prüfen.</p>
      </div>
      <select v-model="selectedProjectId" class="project-select">
        <option value="" disabled>Projekt wählen</option>
        <option v-for="project in projects" :key="project.id" :value="project.id">
          {{ project.name }}
        </option>
      </select>
    </header>

    <p v-if="error" class="error-text">{{ error }}</p>
    <p v-if="loading && !integrations.length" class="loading-text">Lade Integrationen…</p>

    <div v-if="selectedProject" class="grid">
      <div class="card-list">
        <article v-for="integration in integrations" :key="integration.id" class="integration-card">
          <div class="card-head">
            <div>
              <strong class="card-title">{{ integration.display_name || integration.provider }}</strong>
              <p class="card-key">{{ integration.integration_key || 'kein integration_key' }}</p>
            </div>
            <span class="badge" :class="badgeClass(integration.status)">{{ integration.status }}</span>
          </div>
          <p class="card-detail">{{ integration.status_detail }}</p>
          <div class="meta">
            <span>Projekt-Key: {{ integration.external_project_key || '—' }}</span>
            <span>Letzter Check: {{ formatDate(integration.health_checked_at) }}</span>
            <span>Letztes Event: {{ formatDate(integration.last_event_at) }}</span>
          </div>
          <div class="actions">
            <button class="btn" @click="editIntegration(integration)">Bearbeiten</button>
            <button class="btn btn-primary" @click="checkIntegration(integration.id)">Prüfen</button>
          </div>
        </article>

        <div v-if="!loading && integrations.length === 0" class="empty">
          Für dieses Projekt sind noch keine Integrationen konfiguriert.
        </div>
      </div>

      <form class="editor" @submit.prevent="saveIntegration">
        <h3>{{ editingId ? 'Integration bearbeiten' : 'Neue Integration' }}</h3>
        <label>
          Provider
          <select v-model="form.provider">
            <option value="youtrack">YouTrack</option>
            <option value="sentry">Sentry</option>
            <option value="in_app">In-App</option>
            <option value="github_projects">GitHub Projects</option>
          </select>
        </label>
        <label>
          Anzeigename
          <input v-model="form.display_name" type="text" placeholder="z. B. Core API Sentry" />
        </label>
        <label>
          Integration-Key
          <input v-model="form.integration_key" type="text" placeholder="core-api-sentry" />
        </label>
        <label>
          Base URL
          <input v-model="form.base_url" type="text" placeholder="https://youtrack.example.com" />
        </label>
        <label>
          Externer Projekt-Key / Slug
          <input v-model="form.external_project_key" type="text" placeholder="CORE / core-api" />
        </label>
        <label>
          Project Selector (JSON)
          <textarea v-model="form.project_selector_text" rows="4" placeholder='{"aliases":["core-api","CORE"]}' />
        </label>
        <label>
          Status-Mapping (JSON)
          <textarea v-model="form.status_mapping_text" rows="4" placeholder='{"in_progress":"Doing"}' />
        </label>
        <label>
          Routing-Hints (JSON)
          <textarea v-model="form.routing_hints_text" rows="4" placeholder='{"epic_hint":"backend-stability"}' />
        </label>
        <label>
          Webhook Secret
          <input v-model="form.webhook_secret" type="password" placeholder="nur setzen wenn ändern" />
        </label>
        <label>
          Access Token
          <input v-model="form.access_token" type="password" placeholder="nur setzen wenn ändern" />
        </label>
        <label class="toggle">
          <input v-model="form.sync_enabled" type="checkbox" />
          Aktiv
        </label>
        <div class="editor-actions">
          <button type="button" class="btn" @click="resetForm">Zurücksetzen</button>
          <button type="submit" class="btn btn-primary" :disabled="saving">
            {{ saving ? 'Speichere…' : (editingId ? 'Aktualisieren' : 'Anlegen') }}
          </button>
        </div>
      </form>
    </div>
  </section>
</template>

<style scoped>
.project-integrations {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.panel-header,
.card-head,
.actions,
.editor-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.panel-title,
.editor h3 {
  margin: 0;
  color: var(--color-text);
  font-family: var(--font-heading);
}

.panel-subtitle,
.loading-text,
.empty,
.card-detail,
.meta,
.card-key {
  margin: 0;
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.project-select,
.editor input,
.editor select,
.editor textarea {
  width: 100%;
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  padding: var(--space-2);
}

.grid {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: var(--space-4);
}

.card-list,
.editor {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.integration-card,
.editor {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-alt);
  padding: var(--space-4);
}

.card-title {
  color: var(--color-text);
}

.meta {
  display: flex;
  flex-direction: column;
  gap: var(--space-0-5);
}

.badge {
  border-radius: var(--radius-full);
  padding: var(--space-0-5) var(--space-2);
  font-size: var(--font-size-2xs);
  font-family: var(--font-mono);
  text-transform: uppercase;
}

.badge--active { color: var(--color-success); border: 1px solid var(--color-success); }
.badge--incomplete { color: var(--color-warning); border: 1px solid var(--color-warning); }
.badge--error { color: var(--color-danger); border: 1px solid var(--color-danger); }
.badge--disabled { color: var(--color-text-muted); border: 1px solid var(--color-border); }

.editor label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: var(--color-text);
  font-size: var(--font-size-sm);
}

.toggle {
  flex-direction: row !important;
  align-items: center;
}

.toggle input {
  width: auto;
}

.btn {
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
}

.btn-primary {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.error-text {
  margin: 0;
  color: var(--color-danger);
}

@media (max-width: 960px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
