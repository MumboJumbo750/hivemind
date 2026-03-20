<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { api } from '../../api'
import { useAuthStore } from '../../stores/authStore'
import type { Skill, SkillVersion } from '../../api/types'
import { HivemindCard, HivemindModal } from '../../components/ui'

const authStore = useAuthStore()
const isAdmin = computed(() => authStore.user?.role === 'admin')
const currentUserId = computed(() => authStore.user?.id)

// ─── State ─────────────────────────────────────────────────────────────────
const skills = ref<Skill[]>([])
const totalCount = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)

// Filter & pagination
const activeTab = ref<string>('all')
const page = ref(0)
const pageSize = 20

// Detail
const selectedSkill = ref<Skill | null>(null)
const versions = ref<SkillVersion[]>([])
const selectedVersion = ref<string | null>(null)
const detailLoading = ref(false)

// Reject modal
const showRejectModal = ref(false)
const rejectRationale = ref('')
const rejectLoading = ref(false)

// Action loading
const actionLoading = ref(false)

const tabs = [
  { key: 'all', label: 'Alle' },
  { key: 'active', label: 'Aktiv' },
  { key: 'pending_merge', label: 'Pendend' },
  { key: 'draft', label: 'Draft' },
  { key: 'rejected', label: 'Abgelehnt' },
]

// ─── Computed ──────────────────────────────────────────────────────────────
const lifecycleFilter = computed(() =>
  activeTab.value === 'all' ? undefined : activeTab.value
)

// ─── Loaders ───────────────────────────────────────────────────────────────
async function loadSkills() {
  loading.value = true
  error.value = null
  try {
    const res = await api.getSkills({
      lifecycle: lifecycleFilter.value,
      limit: pageSize,
      offset: page.value * pageSize,
    })
    skills.value = res.data
    totalCount.value = res.total_count
  } catch (e: unknown) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}

async function openDetail(skill: Skill) {
  selectedSkill.value = skill
  detailLoading.value = true
  try {
    const [fresh, vers] = await Promise.all([
      api.getSkill(skill.id),
      api.getSkillVersions(skill.id),
    ])
    selectedSkill.value = fresh
    versions.value = vers
    selectedVersion.value = null
  } catch (e: unknown) {
    error.value = (e as Error).message
  } finally {
    detailLoading.value = false
  }
}

function closeDetail() {
  selectedSkill.value = null
  versions.value = []
  selectedVersion.value = null
}

// ─── Actions ───────────────────────────────────────────────────────────────
async function submitSkill(skill: Skill) {
  actionLoading.value = true
  try {
    const updated = await api.submitSkill(skill.id)
    selectedSkill.value = updated
    await loadSkills()
  } catch (e: unknown) {
    error.value = (e as Error).message
  } finally {
    actionLoading.value = false
  }
}

async function mergeSkill(skill: Skill) {
  if (!confirm(`Skill "${skill.title}" mergen?`)) return
  actionLoading.value = true
  try {
    const updated = await api.mergeSkill(skill.id)
    selectedSkill.value = updated
    await loadSkills()
  } catch (e: unknown) {
    error.value = (e as Error).message
  } finally {
    actionLoading.value = false
  }
}

function openRejectModal() {
  rejectRationale.value = ''
  showRejectModal.value = true
}

async function confirmReject(skill: Skill) {
  if (!rejectRationale.value.trim()) return
  rejectLoading.value = true
  try {
    const updated = await api.rejectSkill(skill.id, rejectRationale.value)
    selectedSkill.value = updated
    showRejectModal.value = false
    await loadSkills()
  } catch (e: unknown) {
    error.value = (e as Error).message
  } finally {
    rejectLoading.value = false
  }
}

// ─── Helpers ───────────────────────────────────────────────────────────────
function lifecycleColor(lc: string): string {
  switch (lc) {
    case 'active': return 'var(--color-success)'
    case 'pending_merge': return 'var(--color-warning)'
    case 'draft': return 'var(--color-text-muted)'
    case 'rejected': return 'var(--color-danger)'
    default: return 'var(--color-text-muted)'
  }
}

function lifecycleLabel(lc: string): string {
  switch (lc) {
    case 'active': return 'Aktiv'
    case 'pending_merge': return 'Pendend'
    case 'draft': return 'Draft'
    case 'rejected': return 'Abgelehnt'
    default: return lc
  }
}

function confidencePercent(c: number | undefined): number {
  return Math.round((c ?? 0) * 100)
}

function formatDate(d: string | null | undefined): string {
  if (!d) return '–'
  return new Date(d).toLocaleDateString('de-DE', {
    day: '2-digit', month: '2-digit', year: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

function canSubmit(skill: Skill): boolean {
  return skill.lifecycle === 'draft' && (isAdmin.value || skill.owner_id === currentUserId.value)
}

function canMergeReject(skill: Skill): boolean {
  return skill.lifecycle === 'pending_merge' && !!isAdmin.value
}

// ─── Diff computation ──────────────────────────────────────────────────────
function computeDiff(oldText: string, newText: string): { type: string; text: string }[] {
  const oldLines = oldText.split('\n')
  const newLines = newText.split('\n')
  const result: { type: string; text: string }[] = []
  const max = Math.max(oldLines.length, newLines.length)
  for (let i = 0; i < max; i++) {
    const ol = oldLines[i] ?? ''
    const nl = newLines[i] ?? ''
    if (ol === nl) {
      result.push({ type: 'same', text: nl })
    } else {
      if (ol) result.push({ type: 'removed', text: ol })
      if (nl) result.push({ type: 'added', text: nl })
    }
  }
  return result
}

const selectedVersionObj = computed(() =>
  versions.value.find(v => v.id === selectedVersion.value) ?? null
)

const diffLines = computed(() => {
  if (!selectedVersionObj.value || !selectedSkill.value) return []
  return computeDiff(selectedVersionObj.value.content, selectedSkill.value.content)
})

const showDiff = computed(() => selectedVersion.value !== null)

// ─── Watchers ──────────────────────────────────────────────────────────────
watch(activeTab, () => { page.value = 0; loadSkills() })
onMounted(() => loadSkills())
</script>

<template>
  <div class="skill-lab">
    <header class="skill-lab__header">
      <h1>Skill Lab</h1>
      <span class="skill-lab__count">{{ totalCount }} Skills</span>
    </header>

    <!-- Tab Filters -->
    <nav class="skill-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="skill-tabs__tab"
        :class="{ 'skill-tabs__tab--active': activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </button>
    </nav>

    <!-- Error -->
    <div v-if="error" class="skill-lab__error">{{ error }}</div>

    <!-- Loading -->
    <div v-if="loading" class="skill-lab__loading">Laden…</div>

    <!-- Skill Cards Grid -->
    <div v-else class="skill-grid">
      <HivemindCard
        v-for="skill in skills"
        :key="skill.id"
        class="skill-card"
        @click="openDetail(skill)"
      >
        <div class="skill-card__header">
          <h3 class="skill-card__title">{{ skill.title }}</h3>
          <span
            class="skill-card__badge"
            :style="{ backgroundColor: lifecycleColor(skill.lifecycle), color: '#070b14' }"
          >
            {{ lifecycleLabel(skill.lifecycle) }}
          </span>
        </div>

        <!-- Confidence Ring -->
        <div class="skill-card__meta">
          <svg class="confidence-ring" width="40" height="40" viewBox="0 0 40 40">
            <circle cx="20" cy="20" r="16" fill="none" stroke="var(--color-border)" stroke-width="3" />
            <circle
              cx="20" cy="20" r="16" fill="none"
              :stroke="lifecycleColor(skill.lifecycle)"
              stroke-width="3"
              stroke-linecap="round"
              :stroke-dasharray="`${confidencePercent(skill.confidence) * 1.005} 100.53`"
              transform="rotate(-90 20 20)"
              class="confidence-ring__progress"
            />
            <text x="20" y="24" text-anchor="middle" class="confidence-ring__text">
              {{ confidencePercent(skill.confidence) }}%
            </text>
          </svg>

          <div class="skill-card__tags">
            <span v-for="s in skill.service_scope" :key="s" class="tag tag--scope">{{ s }}</span>
            <span v-for="s in skill.stack" :key="s" class="tag tag--stack">{{ s }}</span>
          </div>
        </div>

        <div class="skill-card__footer">
          <span class="skill-card__author">{{ skill.proposed_by_username || '–' }}</span>
          <span class="skill-card__date">{{ formatDate(skill.created_at) }}</span>
        </div>
      </HivemindCard>
    </div>

    <!-- Pagination -->
    <div v-if="totalCount > pageSize" class="skill-pagination">
      <button :disabled="page === 0" @click="page--; loadSkills()">← Zurück</button>
      <span>Seite {{ page + 1 }} / {{ Math.ceil(totalCount / pageSize) }}</span>
      <button :disabled="(page + 1) * pageSize >= totalCount" @click="page++; loadSkills()">Weiter →</button>
    </div>

    <!-- Detail Panel (overlay) -->
    <Teleport to="body">
      <div v-if="selectedSkill" class="skill-detail-overlay" @click.self="closeDetail">
        <div class="skill-detail">
          <header class="skill-detail__header">
            <h2>{{ selectedSkill.title }}</h2>
            <span
              class="skill-card__badge"
              :style="{ backgroundColor: lifecycleColor(selectedSkill.lifecycle), color: '#070b14' }"
            >
              {{ lifecycleLabel(selectedSkill.lifecycle) }}
            </span>
            <button class="btn-close" @click="closeDetail">✕</button>
          </header>

          <div v-if="detailLoading" class="skill-lab__loading">Laden…</div>
          <template v-else>
            <!-- Version Dropdown -->
            <div v-if="versions.length > 0" class="skill-detail__versions">
              <label>Version:</label>
              <select v-model="selectedVersion">
                <option :value="null">Aktuell (v{{ selectedSkill.version }})</option>
                <option v-for="v in versions" :key="v.id" :value="v.id">
                  v{{ v.version }} — {{ formatDate(v.created_at) }}
                </option>
              </select>
            </div>

            <!-- Diff View -->
            <div v-if="showDiff && selectedVersionObj" class="skill-diff">
              <h3>Diff: v{{ selectedVersionObj.version }} → v{{ selectedSkill.version }}</h3>
              <pre class="skill-diff__code"><code><template v-for="(line, i) in diffLines" :key="i"><span :class="{ 'diff-added': line.type === 'added', 'diff-removed': line.type === 'removed' }">{{ line.text }}
</span></template></code></pre>
            </div>

            <!-- Content (preformatted) -->
            <div v-else class="skill-detail__content">
              <pre class="skill-content">{{ selectedSkill.content }}</pre>
            </div>

            <!-- Meta info -->
            <div class="skill-detail__meta">
              <span v-if="selectedSkill.token_count">Tokens: {{ selectedSkill.token_count }}</span>
              <span>Typ: {{ selectedSkill.skill_type }}</span>
              <span>Confidence: {{ confidencePercent(selectedSkill.confidence) }}%</span>
              <span v-if="selectedSkill.proposed_by_username">Von: {{ selectedSkill.proposed_by_username }}</span>
            </div>

            <!-- Actions -->
            <div class="skill-detail__actions">
              <button
                v-if="canSubmit(selectedSkill)"
                class="btn btn--accent"
                :disabled="actionLoading"
                @click="submitSkill(selectedSkill!)"
              >
                Einreichen →
              </button>
              <button
                v-if="canMergeReject(selectedSkill)"
                class="btn btn--success"
                :disabled="actionLoading"
                @click="mergeSkill(selectedSkill!)"
              >
                Merge ✓
              </button>
              <button
                v-if="canMergeReject(selectedSkill)"
                class="btn btn--danger"
                :disabled="actionLoading"
                @click="openRejectModal"
              >
                Ablehnen ✗
              </button>
            </div>

            <!-- Rejection Info -->
            <div
              v-if="selectedSkill.lifecycle === 'rejected' && selectedSkill.rejection_rationale"
              class="skill-detail__rejection"
            >
              <strong>Ablehnungsgrund:</strong> {{ selectedSkill.rejection_rationale }}
            </div>
          </template>
        </div>
      </div>
    </Teleport>

    <!-- Reject Modal -->
    <HivemindModal v-model:model-value="showRejectModal" title="Skill ablehnen">
      <p>Begründung für die Ablehnung von „{{ selectedSkill?.title }}":</p>
      <textarea
        v-model="rejectRationale"
        class="reject-textarea"
        placeholder="Begründung eingeben…"
        rows="4"
      />
      <template #footer>
        <button class="btn" @click="showRejectModal = false">Abbrechen</button>
        <button
          class="btn btn--danger"
          :disabled="!rejectRationale.trim() || rejectLoading"
          @click="selectedSkill && confirmReject(selectedSkill)"
        >
          {{ rejectLoading ? 'Wird abgelehnt…' : 'Ablehnen' }}
        </button>
      </template>
    </HivemindModal>
  </div>
</template>

<style scoped>
.skill-lab {
  padding: var(--space-6);
  height: 100%;
  overflow-y: auto;
  font-family: var(--font-body);
  color: var(--color-text);
}

.skill-lab__header {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.skill-lab__header h1 {
  font-family: var(--font-heading);
  font-size: var(--font-size-2xl);
  margin: 0;
}

.skill-lab__count {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.skill-lab__error {
  background: var(--color-danger-10);
  border: 1px solid var(--color-danger);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  margin-bottom: var(--space-4);
  color: var(--color-danger);
}

.skill-lab__loading {
  color: var(--color-text-muted);
  text-align: center;
  padding: var(--space-8);
}

/* Tabs */
.skill-tabs {
  display: flex;
  gap: var(--space-1);
  margin-bottom: var(--space-5);
  border-bottom: 1px solid var(--color-border);
  padding-bottom: var(--space-1);
}

.skill-tabs__tab {
  background: none;
  border: none;
  color: var(--color-text-muted);
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
  border-radius: var(--radius-sm) var(--radius-sm) 0 0;
  font-size: var(--font-size-sm);
  transition: all 0.15s ease;
}

.skill-tabs__tab:hover {
  color: var(--color-text);
  background: var(--color-surface-alt);
}

.skill-tabs__tab--active {
  color: var(--color-accent);
  border-bottom: 2px solid var(--color-accent);
}

/* Grid */
.skill-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: var(--space-4);
}

.skill-card {
  cursor: pointer;
  transition: border-color 0.15s ease;
}

.skill-card:hover {
  border-color: var(--color-accent);
}

.skill-card__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}

.skill-card__title {
  font-family: var(--font-heading);
  font-size: var(--font-size-base);
  margin: 0;
  flex: 1;
}

.skill-card__badge {
  font-size: var(--font-size-xs);
  padding: var(--space-0-5) var(--space-2);
  border-radius: var(--radius-lg);
  font-weight: 600;
  white-space: nowrap;
}

.skill-card__meta {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.confidence-ring__progress {
  transition: stroke-dasharray 0.6s ease;
}

.confidence-ring__text {
  fill: var(--color-text);
  font-size: var(--font-size-2xs);
  font-family: var(--font-mono);
}

.skill-card__tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.tag {
  font-size: var(--font-size-xs);
  padding: 1px var(--space-1-5);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
}

.tag--scope {
  background: var(--color-accent-10);
  color: var(--color-accent);
}

.tag--stack {
  background: rgba(255, 63, 210, 0.15);
  color: var(--color-accent-2);
}

.skill-card__footer {
  display: flex;
  justify-content: space-between;
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
}

/* Pagination */
.skill-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  margin-top: var(--space-5);
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.skill-pagination button {
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  color: var(--color-text);
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.skill-pagination button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* Detail overlay */
.skill-detail-overlay {
  position: fixed;
  inset: 0;
  background: rgba(7, 11, 20, 0.85);
  z-index: var(--z-tooltip);
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding-top: 5vh;
  overflow-y: auto;
}

.skill-detail {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  width: min(800px, 90vw);
  max-height: 85vh;
  overflow-y: auto;
  padding: var(--space-6);
}

.skill-detail__header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.skill-detail__header h2 {
  font-family: var(--font-heading);
  margin: 0;
  flex: 1;
}

.btn-close {
  background: none;
  border: none;
  color: var(--color-text-muted);
  font-size: var(--font-size-lg);
  cursor: pointer;
}

.skill-detail__versions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
  font-size: var(--font-size-sm);
}

.skill-detail__versions label {
  color: var(--color-text-muted);
}

.skill-detail__versions select {
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  color: var(--color-text);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
}

.skill-detail__content {
  margin-bottom: var(--space-4);
}

.skill-content {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-x: auto;
  color: var(--color-text);
  margin: 0;
}

.skill-detail__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.skill-detail__actions {
  display: flex;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}

.btn {
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
  cursor: pointer;
  font-size: var(--font-size-sm);
  font-weight: 600;
  transition: all 0.15s ease;
  background: var(--color-surface-alt);
  color: var(--color-text);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn--accent {
  background: var(--color-accent);
  color: var(--color-bg);
  border-color: var(--color-accent);
}

.btn--success {
  background: var(--color-success);
  color: var(--color-bg);
  border-color: var(--color-success);
}

.btn--danger {
  background: var(--color-danger);
  color: var(--color-bg);
  border-color: var(--color-danger);
}

.skill-detail__rejection {
  background: var(--color-danger-10);
  border: 1px solid var(--color-danger);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  font-size: var(--font-size-sm);
  color: var(--color-danger);
}

/* Diff */
.skill-diff {
  margin-bottom: var(--space-4);
}

.skill-diff h3 {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  margin: 0 0 var(--space-2);
}

.skill-diff__code {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  line-height: 1.5;
  overflow-x: auto;
  margin: 0;
}

.diff-added {
  background: var(--color-success-10);
  color: var(--color-success);
  display: block;
}

.diff-removed {
  background: var(--color-danger-10);
  color: var(--color-danger);
  text-decoration: line-through;
  display: block;
}

/* Reject modal */
.reject-textarea {
  width: 100%;
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  color: var(--color-text);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
  resize: vertical;
  margin: var(--space-3) 0;
}
</style>
