<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { api } from '../../api'
import { HivemindCard } from '../../components/ui'

// ─── Types ─────────────────────────────────────────────────────────────────
interface WikiArticle {
  id: string
  title: string
  slug: string
  content: string
  tags: string[]
  version: number
  epic_id?: string | null
  epic_key?: string | null
  created_at: string
  updated_at?: string | null
}

interface WikiVersion {
  version: number
  content: string
  changed_by?: string
  created_at: string
}

// ─── State ─────────────────────────────────────────────────────────────────
const articles = ref<WikiArticle[]>([])
const selectedArticle = ref<WikiArticle | null>(null)
const versions = ref<WikiVersion[]>([])
const searchQuery = ref('')
const selectedTags = ref<string[]>([])
const showHistory = ref(false)
const showEpicLink = ref(false)
const epicKeyInput = ref('')
const loading = ref(false)
const error = ref<string | null>(null)

// Debounced search
let searchTimer: ReturnType<typeof setTimeout> | null = null

// ─── Computed ──────────────────────────────────────────────────────────────
const allTags = computed(() => {
  const tags = new Set<string>()
  articles.value.forEach(a => a.tags?.forEach(t => tags.add(t)))
  return [...tags].sort()
})

const filteredArticles = computed(() => {
  let result = articles.value
  if (selectedTags.value.length > 0) {
    result = result.filter(a =>
      selectedTags.value.every(t => a.tags?.includes(t))
    )
  }
  return result
})

// ─── Search via MCP ────────────────────────────────────────────────────────
watch(searchQuery, (q) => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => doSearch(q), 350)
})

async function doSearch(q: string) {
  loading.value = true
  error.value = null
  try {
    const result = await api.callMcpTool('hivemind-search_wiki', {
      query: q || '',
      fulltext: !!q,
      limit: 50,
    })
    const parsed = JSON.parse(result[0]?.text || '{}')
    if (parsed.data) {
      articles.value = parsed.data
    }
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

// ─── Article selection ─────────────────────────────────────────────────────
async function selectArticle(article: WikiArticle) {
  selectedArticle.value = article
  showHistory.value = false
  versions.value = []

  // Search liefert nur Metadaten — vollen Content nachladen
  if (!article.content) {
    try {
      const result = await api.callMcpTool('hivemind-get_wiki_article', {
        id: article.slug || article.id,
      })
      const parsed = JSON.parse(result[0]?.text || '{}')
      if (parsed.data) {
        selectedArticle.value = { ...article, ...parsed.data }
      }
    } catch {
      // Content bleibt leer — Fehler wird nicht eskaliert
    }
  }
}

// ─── Version History via MCP ───────────────────────────────────────────────
async function loadHistory() {
  if (!selectedArticle.value) return
  showHistory.value = true
  try {
    const result = await api.callMcpTool('hivemind-get_wiki_article', {
      slug: selectedArticle.value.slug,
    })
    const parsed = JSON.parse(result[0]?.text || '{}')
    if (parsed.data?.versions) {
      versions.value = parsed.data.versions
    }
  } catch {
    // versions stay empty
  }
}

// ─── Epic linking via MCP ──────────────────────────────────────────────────
async function linkToEpic() {
  if (!selectedArticle.value || !epicKeyInput.value.trim()) return
  try {
    await api.callMcpTool('hivemind-link_wiki_to_epic', {
      article_slug: selectedArticle.value.slug,
      epic_key: epicKeyInput.value.trim(),
    })
    epicKeyInput.value = ''
    showEpicLink.value = false
    doSearch(searchQuery.value) // refresh
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

// ─── Tag toggle ────────────────────────────────────────────────────────────
function toggleTag(tag: string) {
  const idx = selectedTags.value.indexOf(tag)
  if (idx >= 0) {
    selectedTags.value.splice(idx, 1)
  } else {
    selectedTags.value.push(tag)
  }
}

// ─── Simple Markdown rendering ─────────────────────────────────────────────
function renderMarkdown(md: string): string {
  if (!md) return ''
  return md
    // Code blocks
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="code-block"><code class="lang-$1">$2</code></pre>')
    // Inline code
    .replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')
    // Headers
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    // Bold / italic
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // Links
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
    // Lists
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>')
    // Paragraphs
    .replace(/\n\n/g, '</p><p>')
    .replace(/^(?!<[hupol])(.+)$/gm, '<p>$1</p>')
}

// ─── Init ──────────────────────────────────────────────────────────────────
onMounted(() => doSearch(''))
</script>

<template>
  <div class="wiki-view">
    <!-- Sidebar -->
    <aside class="wiki-sidebar">
      <div class="wiki-search">
        <input
          v-model="searchQuery"
          class="hm-input"
          placeholder="Wiki durchsuchen..."
          type="search"
        />
      </div>

      <!-- Tag Filter -->
      <div v-if="allTags.length" class="wiki-tags">
        <button
          v-for="tag in allTags"
          :key="tag"
          class="tag-btn"
          :class="{ 'tag-btn--active': selectedTags.includes(tag) }"
          @click="toggleTag(tag)"
        >
          {{ tag }}
        </button>
      </div>

      <!-- Article List -->
      <div class="wiki-article-list">
        <div v-if="loading" class="wiki-loading">Suche...</div>
        <div v-else-if="filteredArticles.length === 0" class="wiki-empty">
          Keine Artikel gefunden.
        </div>
        <button
          v-for="article in filteredArticles"
          :key="article.id"
          class="article-btn"
          :class="{ 'article-btn--active': selectedArticle?.id === article.id }"
          @click="selectArticle(article)"
        >
          <span class="article-title">{{ article.title }}</span>
          <span class="article-meta">v{{ article.version }}</span>
        </button>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="wiki-main">
      <div v-if="error" class="error-banner">{{ error }}</div>

      <div v-if="!selectedArticle" class="wiki-placeholder">
        <h2>Wiki</h2>
        <p>Wähle einen Artikel aus der Seitenliste.</p>
      </div>

      <template v-else>
        <div class="wiki-article-header">
          <div>
            <h1 class="wiki-article-title">{{ selectedArticle.title }}</h1>
            <div class="wiki-article-info">
              <span class="article-slug">{{ selectedArticle.slug }}</span>
              <span v-if="selectedArticle.epic_key" class="article-epic">
                📎 {{ selectedArticle.epic_key }}
              </span>
              <span class="article-version">v{{ selectedArticle.version }}</span>
            </div>
          </div>
          <div class="wiki-article-actions">
            <button class="btn-secondary btn-sm" @click="showEpicLink = !showEpicLink">
              🔗 Epic verknüpfen
            </button>
            <button class="btn-secondary btn-sm" @click="loadHistory">
              📜 Versionen
            </button>
          </div>
        </div>

        <!-- Epic Link Dialog -->
        <HivemindCard v-if="showEpicLink" class="epic-link-dialog">
          <h4>Mit Epic verknüpfen</h4>
          <div class="epic-link-form">
            <input
              v-model="epicKeyInput"
              class="hm-input"
              placeholder="EPIC-KEY eingeben..."
            />
            <button class="btn-primary btn-sm" @click="linkToEpic">
              Verknüpfen
            </button>
          </div>
        </HivemindCard>

        <!-- Version History -->
        <HivemindCard v-if="showHistory && versions.length" class="version-history">
          <h4>Versionshistorie</h4>
          <ul class="version-list">
            <li v-for="v in versions" :key="v.version" class="version-item">
              <span class="version-num">v{{ v.version }}</span>
              <span class="version-date">{{ new Date(v.created_at).toLocaleString('de-DE') }}</span>
              <span v-if="v.changed_by" class="version-author">{{ v.changed_by }}</span>
            </li>
          </ul>
        </HivemindCard>

        <!-- Tags -->
        <div v-if="selectedArticle.tags?.length" class="wiki-article-tags">
          <span v-for="tag in selectedArticle.tags" :key="tag" class="article-tag">
            {{ tag }}
          </span>
        </div>

        <!-- Rendered Body -->
        <div class="wiki-article-body" v-html="renderMarkdown(selectedArticle.content)" />
      </template>
    </main>
  </div>
</template>

<style scoped>
.wiki-view {
  display: grid;
  grid-template-columns: 280px 1fr;
  height: 100%;
  gap: 0;
}

/* Sidebar */
.wiki-sidebar {
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--color-surface);
}

.wiki-search {
  padding: var(--space-3);
  border-bottom: 1px solid var(--color-border);
}

.wiki-search .hm-input {
  width: 100%;
}

.wiki-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--color-border);
}

.tag-btn {
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 2px var(--space-2);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  cursor: pointer;
  font-family: var(--font-body);
  transition: all 0.15s;
}
.tag-btn:hover { border-color: var(--color-accent); color: var(--color-text); }
.tag-btn--active {
  background: var(--color-accent);
  color: var(--color-bg);
  border-color: var(--color-accent);
}

.wiki-article-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-2) 0;
}

.wiki-loading,
.wiki-empty {
  padding: var(--space-4) var(--space-3);
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  text-align: center;
}

.article-btn {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: none;
  border: none;
  border-left: 3px solid transparent;
  cursor: pointer;
  text-align: left;
  transition: all 0.15s;
  font-family: var(--font-body);
  color: var(--color-text);
}
.article-btn:hover { background: var(--color-surface-raised); }
.article-btn--active {
  border-left-color: var(--color-accent);
  background: var(--color-surface-raised);
}
.article-title {
  font-size: var(--font-size-sm);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.article-meta {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  flex-shrink: 0;
  margin-left: var(--space-2);
}

/* Main Content */
.wiki-main {
  padding: var(--space-5);
  overflow-y: auto;
}

.wiki-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--color-text-muted);
}
.wiki-placeholder h2 {
  font-family: var(--font-heading);
  color: var(--color-text);
}

.error-banner {
  background: var(--color-danger-bg, rgba(255,0,0,0.1));
  color: var(--color-danger);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-3);
  font-size: var(--font-size-sm);
}

.wiki-article-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--space-4);
}

.wiki-article-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-xl);
  color: var(--color-text);
  margin: 0;
}

.wiki-article-info {
  display: flex;
  gap: var(--space-3);
  margin-top: var(--space-1);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.article-epic { color: var(--color-accent); }

.wiki-article-actions {
  display: flex;
  gap: var(--space-2);
  flex-shrink: 0;
}

.btn-sm {
  font-size: var(--font-size-xs);
  padding: var(--space-1) var(--space-2);
}

.epic-link-dialog {
  margin-bottom: var(--space-3);
}
.epic-link-dialog h4 {
  font-family: var(--font-heading);
  font-size: var(--font-size-sm);
  margin: 0 0 var(--space-2);
}
.epic-link-form {
  display: flex;
  gap: var(--space-2);
}
.epic-link-form .hm-input { flex: 1; }

.version-history {
  margin-bottom: var(--space-3);
}
.version-history h4 {
  font-family: var(--font-heading);
  font-size: var(--font-size-sm);
  margin: 0 0 var(--space-2);
}
.version-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.version-item {
  display: flex;
  gap: var(--space-3);
  padding: var(--space-1) 0;
  font-size: var(--font-size-xs);
  border-bottom: 1px solid var(--color-border);
}
.version-num { font-family: var(--font-mono); font-weight: 600; }
.version-date { color: var(--color-text-muted); }
.version-author { color: var(--color-accent); }

.wiki-article-tags {
  display: flex;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}
.article-tag {
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 2px var(--space-2);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

/* Markdown Body */
.wiki-article-body {
  font-family: var(--font-body);
  font-size: var(--font-size-base);
  line-height: 1.7;
  color: var(--color-text);
}
.wiki-article-body :deep(h1) { font-family: var(--font-heading); font-size: var(--font-size-xl); margin: var(--space-5) 0 var(--space-2); }
.wiki-article-body :deep(h2) { font-family: var(--font-heading); font-size: var(--font-size-lg); margin: var(--space-4) 0 var(--space-2); }
.wiki-article-body :deep(h3) { font-family: var(--font-heading); font-size: var(--font-size-base); margin: var(--space-3) 0 var(--space-1); }
.wiki-article-body :deep(p) { margin: 0 0 var(--space-3); }
.wiki-article-body :deep(ul) { padding-left: var(--space-4); margin: 0 0 var(--space-3); }
.wiki-article-body :deep(li) { margin-bottom: var(--space-1); }
.wiki-article-body :deep(a) { color: var(--color-accent); text-decoration: none; }
.wiki-article-body :deep(a:hover) { text-decoration: underline; }
.wiki-article-body :deep(strong) { color: var(--color-text); }
.wiki-article-body :deep(.code-block) {
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  overflow-x: auto;
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  margin: 0 0 var(--space-3);
}
.wiki-article-body :deep(.inline-code) {
  background: var(--color-surface-raised);
  padding: 1px var(--space-1);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: 0.9em;
}

/* Responsive */
@media (max-width: 768px) {
  .wiki-view { grid-template-columns: 1fr; grid-template-rows: auto 1fr; }
  .wiki-sidebar { border-right: none; border-bottom: 1px solid var(--color-border); max-height: 40vh; }
}
</style>
