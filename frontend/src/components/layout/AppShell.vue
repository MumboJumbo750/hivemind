<script setup lang="ts">
const props = withDefaults(defineProps<{
  navCollapsed?: boolean
  contextCollapsed?: boolean
}>(), { navCollapsed: false, contextCollapsed: true })
</script>

<template>
  <div
    class="app-shell"
    :class="{
      'app-shell--nav-collapsed': props.navCollapsed,
      'app-shell--context-collapsed': props.contextCollapsed,
    }"
  >
    <header class="app-shell__system-bar">
      <slot name="system-bar" />
    </header>
    <nav class="app-shell__nav-sidebar">
      <slot name="nav-sidebar" />
    </nav>
    <main class="app-shell__main-canvas">
      <slot name="main-canvas" />
    </main>
    <aside class="app-shell__context-panel">
      <slot name="context-panel" />
    </aside>
    <footer class="app-shell__status-bar">
      <slot name="status-bar" />
    </footer>
  </div>
</template>

<style scoped>
.app-shell {
  display: grid;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  grid-template-areas:
    "system-bar   system-bar    system-bar"
    "nav-sidebar  main-canvas   context-panel"
    "status-bar   status-bar    status-bar";
  grid-template-rows: var(--systembar-height) 1fr var(--statusbar-height);
  grid-template-columns:
    var(--sidebar-width)
    1fr
    320px;
  transition:
    grid-template-columns var(--transition-duration) ease;
}

.app-shell--nav-collapsed {
  grid-template-columns:
    var(--sidebar-collapsed-width)
    1fr
    320px;
}

.app-shell--context-collapsed {
  grid-template-columns:
    var(--sidebar-width)
    1fr
    0;
}

.app-shell--nav-collapsed.app-shell--context-collapsed {
  grid-template-columns:
    var(--sidebar-collapsed-width)
    1fr
    0;
}

.app-shell__system-bar {
  grid-area: system-bar;
  background: var(--systembar-bg);
  overflow: hidden;
}

.app-shell__nav-sidebar {
  grid-area: nav-sidebar;
  background: var(--sidebar-bg);
  overflow: hidden;
  transition: width var(--transition-duration) ease;
}

.app-shell__main-canvas {
  grid-area: main-canvas;
  overflow-y: auto;
  background: var(--color-bg);
}

.app-shell__context-panel {
  grid-area: context-panel;
  background: var(--sidebar-bg);
  overflow: hidden;
}

.app-shell__status-bar {
  grid-area: status-bar;
  background: var(--statusbar-bg);
  overflow: hidden;
}
</style>
