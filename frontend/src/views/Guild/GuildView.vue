<script setup lang="ts">
/**
 * GuildView — TASK-F-013
 * Shows all federated skills as read-only cards with a fork/adopt button.
 */
import { ref, computed, onMounted } from 'vue'
import { api } from '../../api'
import type { Skill } from '../../api/types'
import { useToast } from '../../composables/useToast'

const toast = useToast()

const skills = ref<Skill[]>([])
const loading = ref(false)
const searchQuery = ref('')
const nodeFilter = ref('')
const forkedIds = ref<Set<string>>(new Set())

// Unique origin nodes for the filter dropdown
const originNodes = computed(() => {
  const map = new Map<string, string>()
  for (const s of skills.value) {
    if (s.origin_node_id && s.origin_node_name) {
      map.set(s.origin_node_id, s.origin_node_name)
    }
  }
  return Array.from(map.entries()).map(([id, name]) => ({ id, name }))
})

const filteredSkills = computed(() => {
  let result = skills.value
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    result = result.filter(s => s.title.toLowerCase().includes(q))
  }
  if (nodeFilter.value) {
    result = result.filter(s => s.origin_node_id === nodeFilter.value)
  }
  return result
})

async function loadSkills() {
  loading.value = true
  try {
    const res = await api.getSkills({ lifecycle: 'active' })
    skills.value = res.data.filter(s => s.federation_scope === 'federated')
  } catch {
    toast.danger('Federated Skills konnten nicht geladen werden.')
  } finally {
    loading.value = false
  }
}

async function forkSkill(skill: Skill) {
  try {
    await api.forkSkill(skill.id)
    forkedIds.value.add(skill.id)
    toast.success('Draft erstellt — im Skill Lab bearbeitbar ab Phase 4.')
  } catch (e: any) {
    if (e?.message?.includes('409') || e?.status === 409) {
      toast.warning('Skill bereits als lokaler Draft vorhanden.')
    } else {
      toast.danger('Fork fehlgeschlagen.')
    }
  }
}

function truncate(text: string, max = 120): string {
  if (text.length <= max) return text
  return text.slice(0, max) + '…'
}

onMounted(loadSkills)
</script>

<template>
  <div class="guild-view">
    <h1 class="guild-title">Gilde</h1>
    <p class="guild-desc">Federierte Skills aus dem Netzwerk. Übernimm Skills als lokalen Draft.</p>

    <!-- Filters -->
    <div class="guild-filters">
      <input
        v-model="searchQuery"
        type="text"
        class="guild-search"
        placeholder="Skill suchen…"
      />
      <select v-model="nodeFilter" class="guild-node-filter">
        <option value="">Alle Nodes</option>
        <option v-for="node in originNodes" :key="node.id" :value="node.id">
          {{ node.name }}
        </option>
      </select>
    </div>

    <!-- Loading -->
    <p v-if="loading" class="guild-loading">Lade Skills…</p>

    <!-- Empty state -->
    <p v-else-if="!filteredSkills.length" class="guild-empty">
      Keine federierten Skills gefunden.
    </p>

    <!-- Skill Grid -->
    <div v-else class="guild-grid">
      <div
        v-for="skill in filteredSkills"
        :key="skill.id"
        class="skill-card"
      >
        <div class="skill-card__header">
          <h3 class="skill-card__title">{{ skill.title }}</h3>
          <span class="skill-card__type">{{ skill.skill_type }}</span>
        </div>

        <p class="skill-card__content">{{ truncate(skill.content) }}</p>

        <div class="skill-card__tags" v-if="skill.stack.length || skill.service_scope.length">
          <span v-for="tag in [...skill.stack, ...skill.service_scope].slice(0, 5)" :key="tag" class="skill-card__tag">
            {{ tag }}
          </span>
        </div>

        <div class="skill-card__meta">
          <span class="skill-card__badge skill-card__badge--lifecycle">{{ skill.lifecycle }}</span>
          <span v-if="skill.origin_node_name" class="skill-card__badge skill-card__badge--node">
            von: {{ skill.origin_node_name }}
          </span>
        </div>

        <button
          class="skill-card__fork-btn"
          :class="{ 'skill-card__fork-btn--done': forkedIds.has(skill.id) }"
          :disabled="forkedIds.has(skill.id)"
          @click="forkSkill(skill)"
        >
          {{ forkedIds.has(skill.id) ? 'ÜBERNOMMEN ✓' : 'ÜBERNEHMEN' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.guild-view {
  padding: var(--space-6);
  max-width: 1200px;
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.guild-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-3xl);
  color: var(--color-text);
  margin: 0;
}

.guild-desc {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  margin: 0;
}

.guild-filters {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.guild-search {
  flex: 1;
  min-width: 200px;
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
  color: var(--color-text);
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
}
.guild-search:focus { outline: none; border-color: var(--color-accent); }

.guild-node-filter {
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
  color: var(--color-text);
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  min-width: 160px;
}

.guild-loading,
.guild-empty {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  margin: 0;
}

/* Grid */
.guild-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-4);
}

@media (max-width: 900px) {
  .guild-grid { grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 600px) {
  .guild-grid { grid-template-columns: 1fr; }
}

/* Card */
.skill-card {
  background: var(--card-bg);
  border: var(--card-border);
  border-radius: var(--card-radius);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  transition: border-color var(--transition-duration) ease;
}
.skill-card:hover { border-color: var(--color-text-muted); }

.skill-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.skill-card__title {
  font-family: var(--font-heading);
  font-size: var(--font-size-base);
  color: var(--color-text);
  margin: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.skill-card__type {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
}

.skill-card__content {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  margin: 0;
  line-height: 1.5;
}

.skill-card__tags {
  display: flex;
  gap: var(--space-1);
  flex-wrap: wrap;
}

.skill-card__tag {
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  padding: var(--space-1) var(--space-2);
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
}

.skill-card__meta {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.skill-card__badge {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
}

.skill-card__badge--lifecycle {
  background: var(--color-surface-alt);
  color: var(--color-accent);
  border: 1px solid var(--color-accent);
}

.skill-card__badge--node {
  background: var(--color-surface-alt);
  color: var(--color-warning);
  border: 1px solid var(--color-warning);
}

.skill-card__fork-btn {
  margin-top: auto;
  background: var(--color-accent);
  color: var(--color-bg);
  border: none;
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-4);
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  transition: opacity var(--transition-duration) ease;
}
.skill-card__fork-btn:hover:not(:disabled) { opacity: 0.9; }
.skill-card__fork-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.skill-card__fork-btn--done {
  background: var(--color-success);
}
</style>
