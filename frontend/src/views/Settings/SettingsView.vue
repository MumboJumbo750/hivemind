<script setup lang="ts">
import { onMounted } from 'vue'
import { useTheme } from '../../composables/useTheme'
import { useSettingsStore } from '../../stores/settingsStore'
import { HivemindDropdown } from '../../components/ui'
import FederationSettings from '../../components/domain/FederationSettings.vue'

const { currentTheme, availableThemes, setTheme } = useTheme()
const settingsStore = useSettingsStore()

const mcpItems = [
  { label: 'stdio (lokal)', value: 'stdio' },
  { label: 'HTTP', value: 'http' },
  { label: 'SSE', value: 'sse' },
]

onMounted(() => {
  settingsStore.fetchSettings()
})
</script>

<template>
  <div class="settings-view">
    <h1 class="settings-title">Settings</h1>

    <!-- Theme-Auswahl -->
    <section class="settings-section">
      <h2 class="section-title">Theme</h2>
      <div class="theme-picker">
        <button
          v-for="theme in availableThemes"
          :key="theme"
          class="theme-card"
          :class="{ 'theme-card--active': currentTheme === theme }"
          @click="setTheme(theme)"
        >
          <div class="theme-preview" :data-preview-theme="theme">
            <span class="theme-name">{{ theme }}</span>
          </div>
        </button>
      </div>
    </section>

    <!-- Solo/Team-Toggle -->
    <section class="settings-section">
      <h2 class="section-title">Modus</h2>
      <p class="section-desc">Solo: Du bist der einzige Nutzer. Team: Mehrere Nutzer, RBAC aktiv.</p>

      <div class="mode-toggle-row">
        <button
          class="mode-btn"
          :class="{ 'mode-btn--active': settingsStore.mode === 'solo' }"
          :disabled="settingsStore.loading"
          @click="settingsStore.updateMode('solo')"
        >
          <span class="mode-btn__icon">👤</span>
          <span class="mode-btn__label">Solo</span>
        </button>
        <button
          class="mode-btn"
          :class="{ 'mode-btn--active': settingsStore.mode === 'team' }"
          :disabled="settingsStore.loading"
          @click="settingsStore.updateMode('team')"
        >
          <span class="mode-btn__icon">🕸</span>
          <span class="mode-btn__label">Team</span>
        </button>
      </div>

      <p v-if="settingsStore.error" class="error-text">{{ settingsStore.error }}</p>

      <!-- Notification Mode (read-only) -->
      <div class="info-row">
        <span class="info-label">Notification-Modus:</span>
        <span class="info-value">{{ settingsStore.notification_mode }}</span>
      </div>
    </section>

    <!-- MCP-Transport -->
    <section class="settings-section">
      <h2 class="section-title">MCP-Transport</h2>
      <p class="section-desc settings-note">MCP-Backend-Anbindung ab Phase 3.</p>
      <HivemindDropdown
        :items="mcpItems"
        v-model="settingsStore.mcpTransport"
      >
        <template #trigger>
          <button class="btn-secondary">Transport: {{ settingsStore.mcpTransport }}</button>
        </template>
      </HivemindDropdown>
    </section>

    <!-- Federation -->
    <section class="settings-section">
      <h2 class="section-title">Federation</h2>
      <p class="section-desc">Verbindung zu anderen Hivemind-Nodes konfigurieren.</p>
      <FederationSettings />
    </section>
  </div>
</template>

<style scoped>
.settings-view {
  padding: var(--space-6);
  max-width: 640px;
  display: flex;
  flex-direction: column;
  gap: var(--space-8);
}

.settings-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-3xl);
  color: var(--color-text);
  margin: 0;
}

.settings-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.section-title {
  font-family: var(--font-heading);
  font-size: var(--font-size-lg);
  color: var(--color-text);
  margin: 0;
  border-bottom: 1px solid var(--color-border);
  padding-bottom: var(--space-2);
}

.section-desc {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  margin: 0;
}

/* Theme Cards */
.theme-picker {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.theme-card {
  background: transparent;
  border: 2px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  cursor: pointer;
  transition: border-color var(--transition-duration) ease;
  min-width: 140px;
}
.theme-card:hover { border-color: var(--color-text-muted); }
.theme-card--active { border-color: var(--color-accent); }

.theme-preview {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.theme-name {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--color-text);
}

.theme-preview[data-preview-theme="space-neon"] .theme-name    { color: #20e3ff; }
.theme-preview[data-preview-theme="industrial-amber"] .theme-name { color: #ffaa00; }
.theme-preview[data-preview-theme="operator-mono"] .theme-name { color: #ffffff; }

/* Mode Toggle */
.mode-toggle-row {
  display: flex;
  gap: var(--space-3);
}

.mode-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-3) var(--space-6);
  background: var(--color-surface-alt);
  border: 2px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: border-color var(--transition-duration) ease;
  min-width: 100px;
}
.mode-btn:hover:not(:disabled) { border-color: var(--color-text-muted); }
.mode-btn--active { border-color: var(--color-accent); }
.mode-btn:disabled { opacity: 0.6; cursor: not-allowed; }

.mode-btn__icon { font-size: 24px; }
.mode-btn__label { font-size: var(--font-size-sm); color: var(--color-text); font-family: var(--font-mono); }

/* Info row */
.info-row {
  display: flex;
  gap: var(--space-3);
  align-items: center;
}

.info-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.info-value {
  font-size: var(--font-size-xs);
  color: var(--color-accent);
  font-family: var(--font-mono);
}

.error-text {
  color: var(--color-danger);
  font-size: var(--font-size-sm);
  margin: 0;
}

/* Button */
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
.btn-secondary:hover { border-color: var(--color-accent); color: var(--color-accent); }
</style>
