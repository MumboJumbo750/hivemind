<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../../api'
import type { Epic, Task } from '../../api/types'

const router = useRouter()
const open = ref(false)
const query = ref('')
const loading = ref(false)
const resultEpics = ref<Epic[]>([])
const resultTasks = ref<Task[]>([])
const selectedIndex = ref(0)
let debounceTimer: ReturnType<typeof setTimeout> | null = null
const inputRef = ref<HTMLInputElement | null>(null)

const allResults = computed(() => [
  ...resultEpics.value.map(e => ({ type: 'epic' as const, id: e.id, title: e.epic_key + ' ' + e.title, sub: e.state })),
  ...resultTasks.value.map(t => ({ type: 'task' as const, id: t.id, title: t.task_key + ' ' + t.title, sub: t.state })),
])

function openSpotlight() {
  open.value = true
  query.value = ''
  resultEpics.value = []
  resultTasks.value = []
  selectedIndex.value = 0
  nextTick(() => inputRef.value?.focus())
}

function close() {
  open.value = false
  query.value = ''
}

async function _search(q: string) {
  if (!q.trim()) { resultEpics.value = []; resultTasks.value = []; return }
  loading.value = true
  try {
    const res = await api.search(q)
    resultEpics.value = (res.epics ?? []) as Epic[]
    resultTasks.value = (res.tasks ?? []) as Task[]
    selectedIndex.value = 0
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
}

watch(query, (q) => {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => _search(q), 300)
})

function selectResult(idx: number) {
  const item = allResults.value[idx]
  if (!item) return
  close()
  router.push('/command-deck')
}

function _onKeydown(e: KeyboardEvent) {
  if (!open.value) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') { e.preventDefault(); openSpotlight() }
    return
  }
  if (e.key === 'Escape') { close(); return }
  if (e.key === 'ArrowDown') { e.preventDefault(); selectedIndex.value = Math.min(selectedIndex.value + 1, allResults.value.length - 1) }
  if (e.key === 'ArrowUp') { e.preventDefault(); selectedIndex.value = Math.max(selectedIndex.value - 1, 0) }
  if (e.key === 'Enter') { selectResult(selectedIndex.value) }
}

onMounted(() => window.addEventListener('keydown', _onKeydown))
onUnmounted(() => window.removeEventListener('keydown', _onKeydown))
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="spotlight-overlay" @click.self="close">
      <div class="spotlight-modal" role="dialog" aria-label="Spotlight-Suche">
        <div class="spotlight-input-row">
          <span class="spotlight-icon">⌕</span>
          <input
            ref="inputRef"
            v-model="query"
            class="spotlight-input"
            placeholder="Suche Tasks, Epics..."
            autocomplete="off"
          />
          <span v-if="loading" class="spotlight-loading">…</span>
        </div>

        <div v-if="query && !loading && allResults.length === 0" class="spotlight-empty">
          Keine Ergebnisse
        </div>

        <ul v-if="allResults.length > 0" class="spotlight-results">
          <li
            v-if="resultEpics.length > 0"
            class="spotlight-group-label"
          >EPICS</li>
          <li
            v-for="(item, i) in allResults.filter(r => r.type === 'epic')"
            :key="item.id"
            class="spotlight-item"
            :class="{ 'spotlight-item--selected': selectedIndex === i }"
            @click="selectResult(i)"
            @mouseover="selectedIndex = i"
          >
            <span class="spotlight-item__title">{{ item.title }}</span>
            <span class="spotlight-item__sub">{{ item.sub }}</span>
          </li>

          <li
            v-if="resultTasks.length > 0"
            class="spotlight-group-label"
          >TASKS</li>
          <li
            v-for="(item, i) in allResults.filter(r => r.type === 'task')"
            :key="item.id"
            class="spotlight-item"
            :class="{ 'spotlight-item--selected': selectedIndex === (resultEpics.length + i) }"
            @click="selectResult(resultEpics.length + i)"
            @mouseover="selectedIndex = resultEpics.length + i"
          >
            <span class="spotlight-item__title">{{ item.title }}</span>
            <span class="spotlight-item__sub">{{ item.sub }}</span>
          </li>
        </ul>

        <div class="spotlight-footer">
          <span>↑↓ navigieren</span>
          <span>↵ öffnen</span>
          <span>ESC schließen</span>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.spotlight-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 15vh;
  z-index: 1000;
}

.spotlight-modal {
  width: 560px;
  max-width: calc(100vw - var(--space-8));
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.7);
  overflow: hidden;
}

.spotlight-input-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--color-border);
}

.spotlight-icon {
  font-size: 18px;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.spotlight-input {
  flex: 1;
  background: none;
  border: none;
  outline: none;
  color: var(--color-text);
  font-family: var(--font-body);
  font-size: var(--font-size-base);
}
.spotlight-input::placeholder { color: var(--color-text-muted); }

.spotlight-loading {
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
}

.spotlight-empty {
  padding: var(--space-6) var(--space-4);
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  text-align: center;
}

.spotlight-results {
  list-style: none;
  margin: 0;
  padding: var(--space-1) 0;
  max-height: 360px;
  overflow-y: auto;
}

.spotlight-group-label {
  padding: var(--space-2) var(--space-4) var(--space-1);
  font-size: 10px;
  letter-spacing: 0.1em;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.spotlight-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-2) var(--space-4);
  cursor: pointer;
  transition: background var(--transition-duration) ease;
}
.spotlight-item--selected { background: var(--color-surface-alt); }

.spotlight-item__title {
  font-size: var(--font-size-sm);
  color: var(--color-text);
  font-family: var(--font-mono);
}

.spotlight-item__sub {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.spotlight-footer {
  display: flex;
  gap: var(--space-4);
  padding: var(--space-2) var(--space-4);
  border-top: 1px solid var(--color-border);
  font-size: 10px;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}
</style>
