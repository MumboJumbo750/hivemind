import { createApp } from 'vue'
import { createPinia } from 'pinia'
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

createApp(App).use(router).use(pinia).mount('#app')
