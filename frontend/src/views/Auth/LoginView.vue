<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/authStore'

const router = useRouter()
const authStore = useAuthStore()

const username = ref('')
const password = ref('')
const error = ref<string | null>(null)
const loading = ref(false)

async function handleLogin() {
  error.value = null
  loading.value = true
  try {
    await authStore.login(username.value, password.value)
    router.push('/')
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Login fehlgeschlagen'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-screen">
    <div class="login-panel">
      <div class="login-panel__header">
        <span class="login-panel__logo">⬡ HIVEMIND</span>
        <p class="login-panel__subtitle">Commander Authentication</p>
      </div>

      <form class="login-form" @submit.prevent="handleLogin">
        <div class="login-form__field">
          <label class="login-form__label" for="username">IDENTIFIER</label>
          <input
            id="username"
            v-model="username"
            class="login-form__input"
            type="text"
            autocomplete="username"
            placeholder="commander_id"
            required
          />
        </div>

        <div class="login-form__field">
          <label class="login-form__label" for="password">ACCESS CODE</label>
          <input
            id="password"
            v-model="password"
            class="login-form__input"
            type="password"
            autocomplete="current-password"
            placeholder="••••••••"
            required
          />
        </div>

        <div v-if="error" class="login-form__error">
          ⚠ {{ error }}
        </div>

        <button
          class="login-form__submit"
          type="submit"
          :disabled="loading"
        >
          <span v-if="loading">AUTHENTICATING…</span>
          <span v-else>[ AUTHENTICATE ▶ ]</span>
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.login-screen {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg);
}

.login-panel {
  width: 360px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  padding: var(--space-8) var(--space-6);
  box-shadow: 0 0 40px rgba(0, 255, 200, 0.06);
}

.login-panel__header {
  text-align: center;
  margin-bottom: var(--space-7);
}

.login-panel__logo {
  font-family: var(--font-heading);
  font-size: var(--font-size-xl);
  letter-spacing: 0.2em;
  color: var(--color-accent);
}

.login-panel__subtitle {
  margin-top: var(--space-1);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  letter-spacing: 0.15em;
  text-transform: uppercase;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.login-form__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.login-form__label {
  font-size: var(--font-size-xs);
  letter-spacing: 0.12em;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.login-form__input {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
  color: var(--color-text);
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  outline: none;
  transition: border-color var(--transition-duration) ease;
}

.login-form__input:focus {
  border-color: var(--color-accent);
}

.login-form__error {
  font-size: var(--font-size-sm);
  color: var(--color-danger);
  font-family: var(--font-mono);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-danger);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--color-danger) 10%, transparent);
}

.login-form__submit {
  margin-top: var(--space-2);
  padding: var(--space-3) var(--space-4);
  background: transparent;
  border: 1px solid var(--color-accent);
  border-radius: var(--radius-sm);
  color: var(--color-accent);
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  letter-spacing: 0.08em;
  cursor: pointer;
  transition: background var(--transition-duration) ease;
}

.login-form__submit:hover:not(:disabled) {
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
}

.login-form__submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
