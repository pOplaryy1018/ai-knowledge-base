import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { VueQueryPlugin } from '@tanstack/vue-query'
import App from './App.vue'
import { queryClient } from './queryClient'
import router from './router'
import ArcoVue from '@arco-design/web-vue'
import '@arco-design/web-vue/dist/arco.css'
import './styles/global.css'
import './styles/transition.css'

const app = createApp(App)
app.use(ArcoVue)
app.use(createPinia())
app.use(router)
app.use(VueQueryPlugin, { queryClient })
app.mount('#app')
