<script setup lang="ts">
import { ref } from 'vue'
import { useAuthStore } from '../../stores/authStore'
import { useRouter } from 'vue-router'

const auth = useAuthStore()
const router = useRouter()
const dropdownOpen = ref(false)

function initials(name: string): string {
  return name.slice(0, 2).toUpperCase()
}

async function handleLogout() {
  dropdownOpen.value = false
  await auth.logout()
  router.push('/login')
}
</script>

<template>
  <div v-if="auth.user" class="actor-badge" @click="dropdownOpen = !dropdownOpen">
    <div class="actor-badge__avatar">{{ initials(auth.user.username) }}</div>
    <div class="actor-badge__info">
      <span class="actor-badge__username">{{ auth.user.username }}</span>
      <span class="actor-badge__role" :class="`actor-badge__role--${auth.user.role}`">
        {{ auth.user.role }}
      </span>
    </div>

    <div v-if="dropdownOpen" class="actor-badge__dropdown">
      <button class="actor-badge__logout" @click.stop="handleLogout">
        [ LOGOUT ]
      </button>
    </div>
  </div>
</template>

<style scoped>
.actor-badge {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  max-width: 200px;
  cursor: pointer;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  transition: background var(--transition-duration) ease;
}

.actor-badge:hover {
  background: var(--color-surface-alt);
}

.actor-badge__avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--color-accent);
  color: var(--color-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  font-weight: 700;
  flex-shrink: 0;
}

.actor-badge__info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.actor-badge__username {
  font-size: var(--font-size-xs);
  color: var(--color-text);
  font-family: var(--font-mono);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.actor-badge__role {
  font-size: var(--font-size-2xs);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-family: var(--font-mono);
}

.actor-badge__role--admin    { color: var(--color-accent); }
.actor-badge__role--developer { color: var(--color-text-muted); }
.actor-badge__role--service  { color: var(--color-warning); }
.actor-badge__role--kartograph { color: var(--color-warning); }

.actor-badge__dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  min-width: 120px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  box-shadow: 0 4px 12px rgba(0,0,0,0.4);
  z-index: var(--z-tooltip);
  margin-top: var(--space-1);
}

.actor-badge__logout {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: none;
  border: none;
  color: var(--color-danger);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  cursor: pointer;
  text-align: left;
  transition: background var(--transition-duration) ease;
}

.actor-badge__logout:hover {
  background: var(--color-surface-alt);
}
</style>
