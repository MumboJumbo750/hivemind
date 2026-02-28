import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('../views/Auth/LoginView.vue'), meta: { public: true } },
    { path: '/',              component: () => import('../views/PromptStation/PromptStationView.vue') },
    { path: '/command-deck',  component: () => import('../views/CommandDeck/CommandDeckView.vue') },
    { path: '/skill-lab',     component: () => import('../views/SkillLab/SkillLabView.vue') },
    { path: '/wiki',          component: () => import('../views/Wiki/WikiView.vue') },
    { path: '/guild',         component: () => import('../views/Guild/GuildView.vue') },
    { path: '/settings',      component: () => import('../views/Settings/SettingsView.vue') },
    { path: '/notifications', component: () => import('../views/NotificationTray/NotificationTrayView.vue') },
    { path: '/triage',        component: () => import('../views/Triage/TriageStationView.vue') },
    { path: '/kartograph-bootstrap', component: () => import('../views/KartographBootstrap/KartographBootstrapView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

// Auth Guard: unauthentifizierte User → /login (im Solo-Modus: auto-login als solo)
router.beforeEach(async (to) => {
  if (to.meta.public) return true

  const { useAuthStore } = await import('../stores/authStore')
  const { getActivePinia } = await import('pinia')
  if (!getActivePinia()) return true

  const authStore = useAuthStore()
  if (authStore.isAuthenticated) return true

  // Im Solo-Modus: Settings prüfen und ggf. synthetischen Actor setzen
  try {
    const { api } = await import('../api')
    const settings = await api.getSettings()
    if (settings.mode === 'solo') {
      authStore.setSoloMode()
      return true
    }
  } catch {
    // API nicht erreichbar — auf Login weiterleiten
  }

  return { path: '/login', query: { redirect: to.fullPath } }
})

export default router
