<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../../api'
import type { MemoryEntry, MemorySearchResult, MemorySession, MemorySummary } from '../../api/types'

const tab = ref<'sessions' | 'entries' | 'summaries' | 'search'>('sessions')
const loading = ref(false)
const error = ref('')
const page = ref(1)
const pageSize = 25
const role = ref('')
const scope = ref('')
const scopeId = ref('')
const uncoveredOnly = ref(false)
const graduatedFilter = ref<'all' | 'only_graduated' | 'only_active'>('all')
const searchQuery = ref('')
const searchLevel = ref<'L0' | 'L1' | 'L2' | 'all'>('all')
const searchTags = ref('')
const searchLimit = ref(20)

const sessions = ref<MemorySession[]>([])
const entries = ref<MemoryEntry[]>([])
const summaries = ref<MemorySummary[]>([])
const searchResults = ref<MemorySearchResult[]>([])
const totalCount = ref(0)
const hasMore = ref(false)
const searchCount = ref(0)
const selectedRecord = ref<{ title: string; subtitle: string; payload: Record<string, unknown> } | null>(null)

const roleOptions = ['worker', 'reviewer', 'gaertner', 'triage', 'stratege', 'architekt', 'admin']
const scopeOptions = ['global', 'project', 'epic', 'task']
const levelOptions: Array<'L0' | 'L1' | 'L2' | 'all'> = ['all', 'L0', 'L1', 'L2']

async function load() {
  if (tab.value === 'search') return

  loading.value = true
  error.value = ''
  try {
    if (tab.value === 'sessions') {
      const result = await api.getMemorySessions({
        agent_role: role.value || undefined,
        scope: scope.value || undefined,
        scope_id: scopeId.value || undefined,
        page: page.value,
        page_size: pageSize,
      })
      sessions.value = result.data
      totalCount.value = result.total_count
      hasMore.value = result.has_more
      return
    }

    if (tab.value === 'entries') {
      const result = await api.getMemoryEntries({
        agent_role: role.value || undefined,
        scope: scope.value || undefined,
        scope_id: scopeId.value || undefined,
        uncovered_only: uncoveredOnly.value || undefined,
        page: page.value,
        page_size: pageSize,
      })
      entries.value = result.data
      totalCount.value = result.total_count
      hasMore.value = result.has_more
      return
    }

    const result = await api.getMemorySummaries({
      agent_role: role.value || undefined,
      scope: scope.value || undefined,
      scope_id: scopeId.value || undefined,
      graduated: graduatedFilter.value === 'all' ? undefined : graduatedFilter.value === 'only_graduated',
      page: page.value,
      page_size: pageSize,
    })
    summaries.value = result.data
    totalCount.value = result.total_count
    hasMore.value = result.has_more
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Fehler beim Laden des Memory Ledgers'
  } finally {
    loading.value = false
  }
}

async function runSearch() {
  if (!searchQuery.value.trim()) {
    searchResults.value = []
    searchCount.value = 0
    selectedRecord.value = null
    return
  }

  loading.value = true
  error.value = ''
  try {
    const result = await api.searchMemories({
      query: searchQuery.value.trim(),
      scope: scope.value || undefined,
      scope_id: scopeId.value || undefined,
      level: searchLevel.value,
      tags: normalizeTagInput(searchTags.value),
      limit: searchLimit.value,
    })
    searchResults.value = result.results
    searchCount.value = result.count
    selectedRecord.value = result.results[0] ? buildSearchSelection(result.results[0]) : null
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Fehler bei der Memory-Suche'
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  role.value = ''
  scope.value = ''
  scopeId.value = ''
  uncoveredOnly.value = false
  graduatedFilter.value = 'all'
  searchQuery.value = ''
  searchLevel.value = 'all'
  searchTags.value = ''
  searchLimit.value = 20
  searchResults.value = []
  searchCount.value = 0
  selectedRecord.value = null
  page.value = 1
  void load()
}

watch([tab, page], () => {
  selectedRecord.value = null
  void load()
})

onMounted(() => void load())

const totalPages = computed(() => Math.max(1, Math.ceil(totalCount.value / pageSize)))
const activeCount = computed(() => (tab.value === 'search' ? searchCount.value : totalCount.value))
const selectedJson = computed(() => (selectedRecord.value ? JSON.stringify(selectedRecord.value.payload, null, 2) : ''))

function formatDate(iso: string) {
  return new Date(iso).toLocaleString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function normalizeTagInput(raw: string): string[] | undefined {
  const tags = raw.split(',').map((item) => item.trim()).filter(Boolean)
  return tags.length > 0 ? tags : undefined
}

function selectSession(item: MemorySession) {
  selectedRecord.value = {
    title: `Session ${item.id}`,
    subtitle: `${item.agent_role} · ${item.scope}`,
    payload: item as unknown as Record<string, unknown>,
  }
}

function selectEntry(item: MemoryEntry) {
  selectedRecord.value = {
    title: `Entry ${item.id}`,
    subtitle: `${item.agent_role} · ${item.scope}`,
    payload: item as unknown as Record<string, unknown>,
  }
}

function selectSummary(item: MemorySummary) {
  selectedRecord.value = {
    title: `Summary ${item.id}`,
    subtitle: `${item.agent_role} · ${item.scope}`,
    payload: item as unknown as Record<string, unknown>,
  }
}

function buildSearchSelection(item: MemorySearchResult) {
  return {
    title: `${item.level} Treffer ${item.id}`,
    subtitle: `${item.search_mode}${item.similarity !== undefined ? ` · sim ${item.similarity.toFixed(2)}` : ''}`,
    payload: item as unknown as Record<string, unknown>,
  }
}

function selectSearchResult(item: MemorySearchResult) {
  selectedRecord.value = buildSearchSelection(item)
}

function formatSearchMeta(item: MemorySearchResult): string {
  if (item.level === 'L1') {
    return [item.entity, item.key, item.confidence !== undefined ? `conf ${item.confidence}` : ''].filter(Boolean).join(' · ')
  }
  return [item.scope, item.search_mode, item.similarity !== undefined ? `sim ${item.similarity.toFixed(2)}` : ''].filter(Boolean).join(' · ')
}
</script>

<template>
  <div class="memory-view">
    <header class="memory-header">
      <div>
        <h1>Memory Ledger</h1>
        <p>Debug- und Operator-Sicht auf Sessions, Roh-Einträge, Verdichtungen und Hybrid-Suche.</p>
      </div>
      <button class="memory-btn" :disabled="loading" @click="tab === 'search' ? runSearch() : load()">{{ loading ? 'Lade…' : 'Aktualisieren' }}</button>
    </header>

    <section class="memory-controls">
      <div class="memory-tabs">
        <button class="memory-tab" :class="{ 'memory-tab--active': tab === 'sessions' }" @click="tab = 'sessions'; page = 1">Sessions</button>
        <button class="memory-tab" :class="{ 'memory-tab--active': tab === 'entries' }" @click="tab = 'entries'; page = 1">Entries</button>
        <button class="memory-tab" :class="{ 'memory-tab--active': tab === 'summaries' }" @click="tab = 'summaries'; page = 1">Summaries</button>
        <button class="memory-tab" :class="{ 'memory-tab--active': tab === 'search' }" @click="tab = 'search'; page = 1">Search</button>
      </div>

      <div class="memory-filters">
        <select v-model="role" class="memory-select" @change="page = 1; load()">
          <option value="">Alle Rollen</option>
          <option v-for="item in roleOptions" :key="item" :value="item">{{ item }}</option>
        </select>
        <select v-model="scope" class="memory-select" @change="page = 1; load()">
          <option value="">Alle Scopes</option>
          <option v-for="item in scopeOptions" :key="item" :value="item">{{ item }}</option>
        </select>
        <input v-model="scopeId" class="memory-input memory-input--wide" placeholder="Scope-ID oder Key" @change="page = 1; load()" />
        <label v-if="tab === 'entries'" class="memory-checkbox"><input v-model="uncoveredOnly" type="checkbox" @change="page = 1; load()" /> nur uncovered</label>
        <select v-if="tab === 'summaries'" v-model="graduatedFilter" class="memory-select" @change="page = 1; load()">
          <option value="all">alle Summaries</option>
          <option value="only_graduated">nur graduated</option>
          <option value="only_active">nur aktiv</option>
        </select>
        <button class="memory-btn memory-btn--ghost" @click="resetFilters">Reset</button>
      </div>
    </section>

    <p v-if="error" class="memory-error">{{ error }}</p>

    <section v-if="tab === 'search'" class="memory-search-panel">
      <input v-model="searchQuery" class="memory-input memory-input--wide memory-input--grow" placeholder="Query für Hybrid-Suche" @keyup.enter="runSearch" />
      <select v-model="searchLevel" class="memory-select">
        <option v-for="item in levelOptions" :key="item" :value="item">{{ item }}</option>
      </select>
      <input v-model="searchTags" class="memory-input memory-input--wide" placeholder="Tags, kommasepariert" @keyup.enter="runSearch" />
      <input v-model.number="searchLimit" class="memory-input" min="1" max="50" type="number" />
      <button class="memory-btn" :disabled="loading" @click="runSearch">Suchen</button>
    </section>

    <div class="memory-content-grid">
      <section v-if="tab === 'sessions'" class="memory-table-wrap">
        <table class="memory-table">
          <thead>
            <tr><th>Rolle</th><th>Scope</th><th>Einträge</th><th>Kompaktiert</th><th>Start</th><th>Ende</th></tr>
          </thead>
          <tbody>
            <tr v-for="item in sessions" :key="item.id" class="memory-row" @click="selectSession(item)">
              <td>{{ item.agent_role }}</td>
              <td class="memory-mono">{{ item.scope }}<span v-if="item.scope_id"> · {{ item.scope_id }}</span></td>
              <td>{{ item.entry_count }}</td>
              <td>{{ item.compacted ? 'ja' : 'nein' }}</td>
              <td class="memory-mono">{{ formatDate(item.started_at) }}</td>
              <td class="memory-mono">{{ item.ended_at ? formatDate(item.ended_at) : 'offen' }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section v-if="tab === 'entries'" class="memory-table-wrap">
        <table class="memory-table">
          <thead>
            <tr><th>Rolle</th><th>Scope</th><th>Inhalt</th><th>Tags</th><th>Covered</th><th>Zeit</th></tr>
          </thead>
          <tbody>
            <tr v-for="item in entries" :key="item.id" class="memory-row" @click="selectEntry(item)">
              <td>{{ item.agent_role }}</td>
              <td class="memory-mono">{{ item.scope }}<span v-if="item.scope_id"> · {{ item.scope_id }}</span></td>
              <td class="memory-content">{{ item.content }}</td>
              <td>{{ item.tags.join(', ') || '–' }}</td>
              <td class="memory-mono">{{ item.covered_by ?? '–' }}</td>
              <td class="memory-mono">{{ formatDate(item.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section v-if="tab === 'summaries'" class="memory-table-wrap">
        <table class="memory-table">
          <thead>
            <tr><th>Rolle</th><th>Scope</th><th>Summary</th><th>Quellen</th><th>Open Questions</th><th>Zeit</th></tr>
          </thead>
          <tbody>
            <tr v-for="item in summaries" :key="item.id" class="memory-row" @click="selectSummary(item)">
              <td>{{ item.agent_role }}</td>
              <td class="memory-mono">{{ item.scope }}<span v-if="item.scope_id"> · {{ item.scope_id }}</span></td>
              <td class="memory-content">{{ item.content }}</td>
              <td>{{ item.source_count }}</td>
              <td>{{ item.open_questions.join(' | ') || '–' }}</td>
              <td class="memory-mono">{{ formatDate(item.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section v-if="tab === 'search'" class="memory-search-results">
        <article v-for="item in searchResults" :key="`${item.level}-${item.id}`" class="memory-search-card" @click="selectSearchResult(item)">
          <header class="memory-search-card__header">
            <strong>{{ item.level }}</strong>
            <span class="memory-badge" :class="`memory-badge--${item.search_mode}`">{{ item.search_mode }}</span>
          </header>
          <p class="memory-search-card__meta">{{ formatSearchMeta(item) }}</p>
          <p class="memory-search-card__body">{{ item.content ?? item.value ?? 'Kein Textinhalt' }}</p>
          <p v-if="item.open_questions?.length" class="memory-search-card__extra">{{ item.open_questions.join(' | ') }}</p>
        </article>
        <p v-if="!loading && searchResults.length === 0" class="memory-empty">Keine Suchtreffer.</p>
      </section>

      <aside class="memory-inspector">
        <template v-if="selectedRecord">
          <h2>{{ selectedRecord.title }}</h2>
          <p class="memory-inspector__subtitle">{{ selectedRecord.subtitle }}</p>
          <pre class="memory-json">{{ selectedJson }}</pre>
        </template>
        <template v-else>
          <h2>Inspector</h2>
          <p class="memory-inspector__subtitle">Wähle einen Record oder Suchtreffer, um Details zu sehen.</p>
        </template>
      </aside>
    </div>

    <footer v-if="tab !== 'search'" class="memory-pagination">
      <button class="memory-btn" :disabled="page <= 1" @click="page -= 1">← Zurück</button>
      <span>Seite {{ page }} / {{ totalPages }} · {{ activeCount }} Einträge</span>
      <button class="memory-btn" :disabled="!hasMore" @click="page += 1">Weiter →</button>
    </footer>
    <footer v-else class="memory-pagination">
      <span>{{ activeCount }} Suchtreffer</span>
    </footer>
  </div>
</template>

<style scoped>
.memory-view {
  padding: var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.memory-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-4);
}

.memory-header h1 {
  margin: 0 0 var(--space-1);
  font-size: var(--font-size-2xl);
}

.memory-header p {
  margin: 0;
  color: var(--color-text-muted);
}

.memory-controls,
.memory-filters,
.memory-tabs,
.memory-pagination {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  flex-wrap: wrap;
}

.memory-tab,
.memory-btn,
.memory-select,
.memory-input {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  padding: var(--space-2) var(--space-3);
}

.memory-input--wide {
  min-width: 220px;
}

.memory-input--grow {
  flex: 1 1 320px;
}

.memory-tab--active {
  border-color: var(--color-accent);
  color: var(--color-accent);
  background: var(--color-accent-10);
}

.memory-btn--ghost {
  background: transparent;
}

.memory-checkbox {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  color: var(--color-text-muted);
}

.memory-search-panel {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
  align-items: center;
}

.memory-content-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: var(--space-4);
}

.memory-table-wrap {
  overflow: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.memory-table {
  width: 100%;
  border-collapse: collapse;
}

.memory-table th,
.memory-table td {
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--color-border);
  vertical-align: top;
}

.memory-table th {
  text-align: left;
  font-size: var(--font-size-2xs);
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.memory-row {
  cursor: pointer;
}

.memory-row:hover {
  background: var(--color-surface-alt);
}

.memory-content {
  min-width: 320px;
  max-width: 640px;
  white-space: pre-wrap;
}

.memory-mono {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
}

.memory-error {
  margin: 0;
  padding: var(--space-3);
  border: 1px solid var(--color-danger);
  background: var(--color-danger-10);
  color: var(--color-danger);
  border-radius: var(--radius-sm);
}

.memory-search-results {
  display: grid;
  gap: var(--space-3);
}

.memory-search-card,
.memory-inspector {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  padding: var(--space-4);
}

.memory-search-card {
  cursor: pointer;
}

.memory-search-card:hover {
  border-color: var(--color-accent);
}

.memory-search-card__header {
  display: flex;
  justify-content: space-between;
  gap: var(--space-2);
  align-items: center;
}

.memory-search-card__meta,
.memory-inspector__subtitle,
.memory-search-card__extra,
.memory-empty {
  color: var(--color-text-muted);
}

.memory-search-card__body {
  margin: var(--space-2) 0;
  white-space: pre-wrap;
}

.memory-badge {
  border-radius: var(--radius-full);
  padding: 1px var(--space-2);
  font-size: var(--font-size-2xs);
  text-transform: uppercase;
}

.memory-badge--text {
  background: var(--color-surface-alt);
  color: var(--color-text-muted);
}

.memory-badge--semantic {
  background: var(--color-warning-10);
  color: var(--color-warning);
}

.memory-badge--hybrid {
  background: var(--color-success-10);
  color: var(--color-success);
}

.memory-inspector {
  min-height: 240px;
}

.memory-inspector h2 {
  margin: 0 0 var(--space-1);
  font-size: var(--font-size-lg);
}

.memory-json {
  margin: var(--space-3) 0 0;
  padding: var(--space-3);
  border-radius: var(--radius-sm);
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  overflow: auto;
  max-height: 520px;
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
}

@media (max-width: 1100px) {
  .memory-content-grid {
    grid-template-columns: 1fr;
  }
}
</style>