import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export interface CurrentActor {
  id: string
  username: string
  role: 'developer' | 'admin' | 'service' | 'kartograph'
}

const TOKEN_KEY = 'hivemind-access-token'
const ACTOR_KEY = 'hivemind-actor'

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const user = ref<CurrentActor | null>(
    (() => {
      try { return JSON.parse(localStorage.getItem(ACTOR_KEY) ?? 'null') } catch { return null }
    })()
  )

  const isAuthenticated = computed(() => !!accessToken.value && !!user.value)

  function _persist() {
    if (accessToken.value) localStorage.setItem(TOKEN_KEY, accessToken.value)
    else localStorage.removeItem(TOKEN_KEY)
    if (user.value) localStorage.setItem(ACTOR_KEY, JSON.stringify(user.value))
    else localStorage.removeItem(ACTOR_KEY)
  }

  function _parseJwt(token: string): Record<string, unknown> {
    try {
      return JSON.parse(atob(token.split('.')[1]))
    } catch {
      return {}
    }
  }

  async function login(username: string, password: string): Promise<void> {
    const { api } = await import('../api')
    const res = await api.login(username, password)
    accessToken.value = res.access_token
    const claims = _parseJwt(res.access_token)
    user.value = {
      id: claims.sub as string,
      username,
      role: claims.role as CurrentActor['role'],
    }
    _persist()
  }

  async function logout(): Promise<void> {
    try {
      const { api } = await import('../api')
      await api.logout()
    } catch {
      // Ignore errors on logout
    }
    accessToken.value = null
    user.value = null
    _persist()
  }

  async function refreshToken(): Promise<boolean> {
    try {
      const { api } = await import('../api')
      const res = await api.refreshToken()
      accessToken.value = res.access_token
      if (user.value) {
        const claims = _parseJwt(res.access_token)
        user.value = { ...user.value, role: claims.role as CurrentActor['role'] }
      }
      _persist()
      return true
    } catch {
      accessToken.value = null
      user.value = null
      _persist()
      return false
    }
  }

  function setSoloMode() {
    accessToken.value = 'solo-mode'
    user.value = { id: '00000000-0000-0000-0000-000000000001', username: 'solo', role: 'admin' }
    _persist()
  }

  return { accessToken, user, isAuthenticated, login, logout, refreshToken, setSoloMode }
})
