import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import ChatView from './views/ChatView.vue'
import ReportView from './views/ReportView.vue'
import BpmLookupView from './views/BpmLookupView.vue'
import TraceabilityView from './views/TraceabilityView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: ChatView },
    { path: '/lookup', component: BpmLookupView },
    { path: '/trace', component: TraceabilityView },
    { path: '/trace/:id', component: TraceabilityView },
    { path: '/report/:id', component: ReportView },
  ]
})

createApp(App).use(router).mount('#app')
