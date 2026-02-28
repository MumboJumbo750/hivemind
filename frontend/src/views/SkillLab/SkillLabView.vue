<template>
  <div class="lock-teaser">
    <span class="lock-icon">🔒</span>
    <h2>Skill Lab</h2>
    <p>Verfügbar in Phase 2</p>
    <RouterLink to="/">← Zurück zur Prompt Station</RouterLink>
  </div>
</template>

<style scoped>
.lock-teaser {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: var(--space-4);
  color: var(--color-text-muted);
  font-family: var(--font-body);
}
.lock-icon { font-size: var(--font-size-4xl); }
h2 { font-family: var(--font-heading); color: var(--color-text); margin: 0; }
a { color: var(--color-accent); font-size: var(--font-size-sm); }
</style>
