<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { RouterView, RouterLink } from 'vue-router'
import AppShell from './components/layout/AppShell.vue'
import ActorBadge from './components/domain/ActorBadge.vue'
import GamificationBar from './components/domain/GamificationBar.vue'
import NotificationTray from './components/domain/NotificationTray.vue'
import Spotlight from './components/domain/Spotlight.vue'
import ToastContainer from './components/ui/ToastContainer.vue'
import { toggleFocusMode, exitFocusMode } from './composables/useFocusMode'
import { useFederationSSE } from './composables/useFederationSSE'

useFederationSSE()

function _onKeydown(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement)?.tagName?.toLowerCase()
  if (e.key === 'Escape') { exitFocusMode(); return }
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return
  if (e.key === 'f' || e.key === 'F') { e.preventDefault(); toggleFocusMode() }
}

onMounted(() => window.addEventListener('keydown', _onKeydown))
onUnmounted(() => window.removeEventListener('keydown', _onKeydown))
</script>

<template>
  <AppShell>
    <template #system-bar>
      <div class="systembar-content">
        <span class="systembar-brand">HIVEMIND</span>
        <div class="systembar-right">
          <NotificationTray />
          <ActorBadge />
        </div>
      </div>
    </template>
    <template #nav-sidebar>
      <nav class="app-nav">
        <RouterLink to="/" class="app-nav__link">Prompt Station</RouterLink>
        <RouterLink to="/command-deck" class="app-nav__link">Command Deck</RouterLink>
        <RouterLink to="/triage" class="app-nav__link">Triage Station</RouterLink>
        <RouterLink to="/kartograph-bootstrap" class="app-nav__link">Kartograph</RouterLink>
        <RouterLink to="/skill-lab" class="app-nav__link">Skill Lab</RouterLink>
        <RouterLink to="/wiki" class="app-nav__link">Wiki</RouterLink>
        <RouterLink to="/nexus-grid" class="app-nav__link">Nexus Grid</RouterLink>
        <RouterLink to="/guild" class="app-nav__link">Gilde</RouterLink>
        <RouterLink to="/achievements" class="app-nav__link">Achievements</RouterLink>
        <RouterLink to="/dashboard/kpi" class="app-nav__link">KPI Dashboard</RouterLink>
        <RouterLink to="/learning-artifacts" class="app-nav__link">Learning Artifacts</RouterLink>
        <RouterLink to="/agent-sessions" class="app-nav__link">Agent Sessions</RouterLink>
        <RouterLink to="/governance-audit" class="app-nav__link">Governance Audit</RouterLink>
        <RouterLink to="/memory-ledger" class="app-nav__link">Memory Ledger</RouterLink>
        <RouterLink to="/settings" class="app-nav__link">Settings</RouterLink>
      </nav>
    </template>
    <template #main-canvas>
      <RouterView />
    </template>
    <template #context-panel>
      <div style="background: var(--sidebar-bg); height: 100%;" />
    </template>
    <template #status-bar>
      <div class="statusbar-content">
        <GamificationBar />
      </div>
    </template>
  </AppShell>

  <!-- Global Spotlight overlay (Ctrl+K) -->
  <Spotlight />

  <!-- Toast notifications -->
  <ToastContainer />
</template>

<style>
body {
  margin: 0;
  background: var(--color-bg);
  color: var(--color-text);
  font-family: var(--font-body);
}

/* Focus mode: hide nav and status bar */
body.focus-mode .app-shell__nav-sidebar { display: none; }
body.focus-mode .app-shell__status-bar  { display: none; }
/* Keep danger-level alerts visible */
body.focus-mode .notification--danger   { display: block !important; }
</style>

<style scoped>
.systembar-content {
  padding: 0 var(--space-4);
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 100%;
}

.systembar-brand {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  font-family: var(--font-heading);
  letter-spacing: 0.1em;
}

.systembar-right {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.app-nav {
  display: flex;
  flex-direction: column;
  padding: var(--space-3) var(--space-2);
  gap: var(--space-1);
}

.app-nav__link {
  display: block;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  text-decoration: none;
  font-size: var(--font-size-sm);
  transition: background var(--transition-duration) ease, color var(--transition-duration) ease;
}
.app-nav__link:hover {
  background: var(--color-surface-alt);
  color: var(--color-text);
}
.app-nav__link.router-link-active {
  background: var(--color-surface-alt);
  color: var(--color-accent);
}
.app-nav__link--locked {
  opacity: 0.5;
  cursor: default;
}

.statusbar-content {
  height: 100%;
  background: var(--statusbar-bg);
  display: flex;
  align-items: center;
  padding: 0 var(--space-3);
}
</style>
