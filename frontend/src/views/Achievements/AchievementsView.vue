<script setup lang="ts">
/**
 * AchievementsView — Full achievements page with badges, level history, EXP log.
 * TASK-5-022: Gamification Frontend.
 */
import { ref, computed, onMounted } from 'vue'
import { HivemindCard } from '../../components/ui'

interface AchievementData {
  user_id: string
  exp: number
  level: number
  level_title: string
  next_level_exp: number
  exp_to_next: number
  badges: string[]
  recent_exp: { trigger: string; entity: string; amount: number; at: string }[]
}

// Badge display metadata
const BADGE_INFO: Record<string, { icon: string; title: string; description: string }> = {
  first_task: { icon: '🩸', title: 'First Blood', description: 'Ersten Task abgeschlossen' },
  ten_tasks: { icon: '🏅', title: 'Decathlon', description: '10 Tasks abgeschlossen' },
  guard_master: { icon: '🛡️', title: 'Guard Master', description: '5 Guards gemerged' },
  skill_gardener: { icon: '🌱', title: 'Skill Gardener', description: '3 Skills akzeptiert' },
  wiki_author: { icon: '📖', title: 'Wiki Author', description: '5 Wiki-Artikel erstellt' },
  level_5: { icon: '⭐', title: 'Mid-Game', description: 'Level 5 erreicht' },
  level_10: { icon: '👑', title: 'Endgame', description: 'Level 10 erreicht' },
}

// Level titles for display
const LEVEL_TITLES: Record<number, string> = {
  1: 'Drone', 2: 'Worker Bee', 3: 'Scout', 4: 'Builder', 5: 'Engineer',
  6: 'Architect', 7: 'Strategist', 8: "Queen's Guard", 9: 'Hive Master', 10: 'Overmind',
}

const data = ref<AchievementData | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

const progressPercent = computed(() => {
  if (!data.value) return 0
  const levelStartExp = (data.value.level - 1) * 100
  const progressInLevel = data.value.exp - levelStartExp
  return Math.min(100, Math.round((progressInLevel / 100) * 100))
})

const allBadges = computed(() =>
  Object.entries(BADGE_INFO).map(([key, info]) => ({
    key,
    ...info,
    earned: data.value?.badges.includes(key) ?? false,
  }))
)

const triggerLabels: Record<string, string> = {
  task_done: 'Task abgeschlossen',
  guard_merged: 'Guard gemerged',
  skill_accepted: 'Skill akzeptiert',
  decision_resolved: 'Decision gelöst',
  wiki_article_created: 'Wiki-Artikel erstellt',
}

async function loadAchievements() {
  loading.value = true
  error.value = null
  try {
    const base = (import.meta.env.VITE_API_URL as string) ?? 'http://localhost:8000'
    const res = await fetch(`${base}/api/users/me/achievements`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    data.value = await res.json()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

onMounted(() => loadAchievements())
</script>

<template>
  <div class="achievements-page">
    <h1 class="page-title">Achievements</h1>

    <div v-if="loading" class="loading-text">Lade...</div>
    <div v-else-if="error" class="error-text">Fehler: {{ error }}</div>

    <template v-else-if="data">
      <!-- Level Card -->
      <HivemindCard class="level-card">
        <div class="level-hero">
          <div class="level-circle">
            <span class="level-num">{{ data.level }}</span>
          </div>
          <div class="level-info">
            <h2 class="level-title">{{ data.level_title }}</h2>
            <div class="level-progress">
              <div class="progress-track">
                <div class="progress-fill" :style="{ width: progressPercent + '%' }" />
              </div>
              <span class="progress-label">{{ data.exp }} / {{ data.next_level_exp }} XP</span>
            </div>
            <p class="level-hint">{{ data.exp_to_next }} XP bis Level {{ data.level + 1 }}</p>
          </div>
        </div>

        <!-- Level Ladder -->
        <div class="level-ladder">
          <div
            v-for="lvl in 10"
            :key="lvl"
            class="ladder-step"
            :class="{ 'ladder-step--reached': lvl <= data.level, 'ladder-step--current': lvl === data.level }"
          >
            <span class="ladder-num">{{ lvl }}</span>
            <span class="ladder-title">{{ LEVEL_TITLES[lvl] || `Level ${lvl}` }}</span>
          </div>
        </div>
      </HivemindCard>

      <!-- Badges Section -->
      <HivemindCard class="badges-card">
        <h3 class="section-title">Badges</h3>
        <div class="badge-grid">
          <div
            v-for="badge in allBadges"
            :key="badge.key"
            class="badge-item"
            :class="{ 'badge-item--earned': badge.earned }"
          >
            <span class="badge-icon">{{ badge.icon }}</span>
            <span class="badge-title">{{ badge.title }}</span>
            <span class="badge-desc">{{ badge.description }}</span>
            <span v-if="!badge.earned" class="badge-locked">🔒</span>
          </div>
        </div>
      </HivemindCard>

      <!-- Recent EXP Log -->
      <HivemindCard v-if="data.recent_exp.length" class="exp-log-card">
        <h3 class="section-title">Letzte EXP-Einträge</h3>
        <ul class="exp-log">
          <li v-for="(entry, i) in data.recent_exp" :key="i" class="exp-entry">
            <span class="exp-trigger">{{ triggerLabels[entry.trigger] || entry.trigger }}</span>
            <span class="exp-entity">{{ entry.entity }}</span>
            <span class="exp-amount">+{{ entry.amount }} XP</span>
            <span class="exp-date">{{ new Date(entry.at).toLocaleDateString('de-DE') }}</span>
          </li>
        </ul>
      </HivemindCard>
    </template>
  </div>
</template>

<style scoped>
.achievements-page {
  padding: var(--space-6);
  max-width: 800px;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.page-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-2xl);
  color: var(--color-text);
  margin: 0;
}

.loading-text,
.error-text {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}
.error-text { color: var(--color-danger); }

/* Level Card */
.level-hero {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
}

.level-circle {
  width: 72px;
  height: 72px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--color-accent), color-mix(in srgb, var(--color-accent) 60%, var(--color-bg)));
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.level-num {
  font-family: var(--font-heading);
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--color-bg);
}

.level-info { flex: 1; }

.level-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-xl);
  color: var(--color-text);
  margin: 0 0 var(--space-2);
}

.level-progress {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.progress-track {
  flex: 1;
  height: 10px;
  background: var(--color-surface-raised);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--color-accent);
  border-radius: var(--radius-sm);
  transition: width 0.8s ease;
}

.progress-label {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
}

.level-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  margin: var(--space-1) 0 0;
}

/* Level Ladder */
.level-ladder {
  display: flex;
  gap: var(--space-1);
  flex-wrap: wrap;
}

.ladder-step {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: 2px var(--space-2);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  background: var(--color-surface-raised);
  color: var(--color-text-muted);
  opacity: 0.5;
  transition: all 0.2s;
}
.ladder-step--reached {
  opacity: 1;
  color: var(--color-text);
}
.ladder-step--current {
  background: var(--color-accent);
  color: var(--color-bg);
  font-weight: 600;
}
.ladder-num { font-family: var(--font-mono); font-weight: 700; }
.ladder-title { font-family: var(--font-body); }

/* Badges */
.section-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-base);
  color: var(--color-text);
  margin: 0 0 var(--space-3);
}

.badge-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: var(--space-3);
}

.badge-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  text-align: center;
  position: relative;
  transition: all 0.2s;
  opacity: 0.4;
}
.badge-item--earned {
  opacity: 1;
  border-color: var(--color-accent);
}

.badge-icon {
  font-size: var(--font-size-2xl);
}

.badge-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--color-text);
}

.badge-desc {
  font-size: var(--font-size-2xs);
  color: var(--color-text-muted);
}

.badge-locked {
  position: absolute;
  top: var(--space-1);
  right: var(--space-1);
  font-size: var(--font-size-xs);
}

/* EXP Log */
.exp-log {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.exp-entry {
  display: flex;
  gap: var(--space-3);
  padding: var(--space-1) 0;
  border-bottom: 1px solid var(--color-border);
  font-size: var(--font-size-xs);
  align-items: center;
}

.exp-trigger {
  color: var(--color-text);
  flex-shrink: 0;
}

.exp-entity {
  font-family: var(--font-mono);
  color: var(--color-text-muted);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.exp-amount {
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--color-accent);
  flex-shrink: 0;
}

.exp-date {
  color: var(--color-text-muted);
  flex-shrink: 0;
}
</style>
