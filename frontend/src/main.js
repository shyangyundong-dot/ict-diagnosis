import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import ChatView from './views/ChatView.vue'
import ReportView from './views/ReportView.vue'
import BpmLookupView from './views/BpmLookupView.vue'
import TraceabilityView from './views/TraceabilityView.vue'
import LoginView from './views/LoginView.vue'
import ChangePasswordView from './views/ChangePasswordView.vue'
import { useAuth } from './composables/useAuth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: LoginView, meta: { public: true } },
    { path: '/profile/password', component: ChangePasswordView },
    { path: '/', component: ChatView },
    { path: '/lookup', component: BpmLookupView },
    { path: '/trace', component: TraceabilityView },
    { path: '/trace/:id', component: TraceabilityView },
    { path: '/report/:id', component: ReportView },
  ],
})

const { state, loadUserFromToken } = useAuth()

router.beforeEach(async (to) => {
  await loadUserFromToken()
  if (to.meta.public) return true
  if (!state.token) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  // 强制改密：登录后第一件事是去改密页，去其他页一律跳改密页
  if (state.user?.must_change_password && to.path !== '/profile/password') {
    return { path: '/profile/password', query: { redirect: to.fullPath } }
  }
  return true
})

createApp(App).use(router).mount('#app')
