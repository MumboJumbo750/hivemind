import { createApp } from 'vue'
import { createPinia } from 'pinia'
import * as Sentry from '@sentry/vue'
import App from './App.vue'
import router from './router'

import '@fontsource/inter'
import '@fontsource/space-grotesk'
import '@fontsource/jetbrains-mono'

import './design/tokens.css'
import './design/semantic.css'
import './design/components.css'
import './design/themes/space-neon.css'
import './design/themes/industrial-amber.css'
import './design/themes/operator-mono.css'

const pinia = createPinia()
const app = createApp(App)

if (import.meta.env.VITE_SENTRY_DSN) {
  Sentry.init({
    app,
    dsn: import.meta.env.VITE_SENTRY_DSN,
    integrations: [
      Sentry.browserTracingIntegration({ router }),
      Sentry.replayIntegration(),
    ],
    tracesSampleRate: 1.0,
    replaysSessionSampleRate: 0.1,
    replaysOnErrorSampleRate: 1.0,
    environment: import.meta.env.MODE,
  })
}

app.use(router).use(pinia).mount('#app')
