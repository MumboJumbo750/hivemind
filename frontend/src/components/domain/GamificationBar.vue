<script setup lang="ts">
/**
 * GamificationBar — Status bar showing EXP, level, and title.
 * TASK-5-022: Gamification Frontend.
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useToast } from '../../composables/useToast'

interface Achievements {
  exp: number
  level: number
  level_title: string
  next_level_exp: number
  exp_to_next: number
  badges: string[]
}

const data = ref<Achievements | null>(null)
const toast = useToast()

// SSE for level-up / badge notifications
let sseSource: EventSource | null = null

const progressPercent = computed(() => {
  if (!data.value) return 0
  const levelStartExp = (data.value.level - 1) * 100
  const progressInLevel = data.value.exp - levelStartExp
  return Math.min(100, Math.round((progressInLevel / 100) * 100))
})

async function loadAchievements() {
  try {
    const base = (import.meta.env.VITE_API_URL as string) ?? 'http://localhost:8000'
    const res = await fetch(`${base}/api/users/me/achievements`, {
      headers: { 'Content-Type': 'application/json' },
    })
    if (res.ok) {
      const json = await res.json()
      // Ensure badges is always an array to prevent template crash
      if (json && typeof json === 'object') {
        json.badges = Array.isArray(json.badges) ? json.badges : []
        data.value = json
      }
    }
  } catch {
    // Silently fail — gamification is non-critical
  }
}

function startSSE() {
  const base = (import.meta.env.VITE_API_URL as string) ?? 'http://localhost:8000'
  sseSource = new EventSource(`${base}/api/events`)

  sseSource.addEventListener('level_up', (evt) => {
    try {
      const d = JSON.parse(evt.data)
      toast.success(`🎉 Level Up! Level ${d.level}: ${d.title}`)
      loadAchievements()
    } catch { /* ignore */ }
  })

  sseSource.addEventListener('badge_earned', (evt) => {
    try {
      const d = JSON.parse(evt.data)
      toast.success(`🏆 Badge: ${d.title}`)
      loadAchievements()
    } catch { /* ignore */ }
  })
}

onMounted(() => {
  loadAchievements()
  startSSE()
})

onBeforeUnmount(() => {
  if (sseSource) { sseSource.close(); sseSource = null }
})
</script>

<template>
  <div v-if="data" class="gamification-bar">
    <div class="gam-level">
      <span class="gam-level-num">Lv.{{ data.level }}</span>
      <span class="gam-level-title">{{ data.level_title }}</span>
    </div>
    <div class="gam-progress">
      <div class="gam-progress-track">
        <div class="gam-progress-fill" :style="{ width: progressPercent + '%' }" />
      </div>
      <span class="gam-exp">{{ data.exp }} XP</span>
    </div>
    <div v-if="data.badges.length" class="gam-badges">
      <span v-for="b in data.badges.slice(-3)" :key="b" class="gam-badge" :title="b">🏆</span>
    </div>
  </div>
</template>

<style scoped>
.gamification-bar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-1) var(--space-3);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-xs);
}

.gam-level {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  flex-shrink: 0;
}

.gam-level-num {
  font-family: var(--font-mono);
  font-weight: 700;
  color: var(--color-accent);
}

.gam-level-title {
  color: var(--color-text-muted);
  font-family: var(--font-body);
}

.gam-progress {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex: 1;
  min-width: 80px;
}

.gam-progress-track {
  flex: 1;
  height: 6px;
  background: var(--color-surface-raised);
  border-radius: 3px;
  overflow: hidden;
}

.gam-progress-fill {
  height: 100%;
  background: var(--color-accent);
  border-radius: 3px;
  transition: width 0.5s ease;
}

.gam-exp {
  font-family: var(--font-mono);
  color: var(--color-text-muted);
  white-space: nowrap;
}

.gam-badges {
  display: flex;
  gap: 2px;
}

.gam-badge {
  font-size: 14px;
  cursor: default;
}
</style>
