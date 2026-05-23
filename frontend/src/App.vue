<template>
  <div class="app-shell">
    <header v-if="showHeader" class="app-header">
      <div class="app-header-left">
        <router-link to="/" class="brand">🛡 ICT 合规诊断</router-link>
        <router-link to="/lookup" class="nav-link">BPM 查询</router-link>
        <router-link to="/trace" class="nav-link">填报溯源</router-link>
      </div>
      <div class="app-header-right" v-if="state.user">
        <span class="user-chip">
          <span class="user-name">{{ state.user.display_name || state.user.username }}</span>
          <span class="user-role">{{ roleLabel }}</span>
        </span>
        <router-link to="/profile/password" class="header-action">修改密码</router-link>
        <button class="header-action danger" @click="onLogout">登出</button>
      </div>
    </header>

    <router-view />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from './composables/useAuth'

const route = useRoute()
const router = useRouter()
const { state, logout } = useAuth()

const showHeader = computed(() => {
  // 登录页和强制改密页不显示顶栏
  if (route.path === '/login') return false
  if (route.path === '/profile/password' && state.user?.must_change_password) return false
  return !!state.user
})

const roleLabel = computed(() => {
  if (!state.user) return ''
  return { admin: '管理员', reviewer: '主管', user: '员工' }[state.user.role] || state.user.role
})

function onLogout() {
  logout()
  router.replace('/login')
}
</script>

<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --blue-50: #eff6ff;
  --blue-100: #dbeafe;
  --blue-200: #bfdbfe;
  --blue-500: #3b82f6;
  --blue-600: #2563eb;
  --blue-700: #1d4ed8;
  --blue-800: #1e40af;
  --slate-50: #f8fafc;
  --slate-100: #f1f5f9;
  --slate-200: #e2e8f0;
  --slate-300: #cbd5e1;
  --slate-400: #94a3b8;
  --slate-500: #64748b;
  --slate-600: #475569;
  --slate-700: #334155;
  --slate-800: #1e293b;
  --red-50: #fef2f2;
  --red-200: #fecaca;
  --red-500: #ef4444;
  --red-600: #dc2626;
  --yellow-50: #fffbeb;
  --yellow-200: #fde68a;
  --yellow-600: #d97706;
  --green-50: #f0fdf4;
  --green-200: #bbf7d0;
  --green-600: #16a34a;
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.08);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.10);
}

html { font-size: 15px; }

body {
  font-family: -apple-system, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  background: var(--slate-100);
  color: var(--slate-800);
  line-height: 1.7;
  min-height: 100vh;
}

::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--slate-300); border-radius: 3px; }
</style>

<style scoped>
.app-shell { min-height: 100vh; display: flex; flex-direction: column; }

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 20px;
  height: 48px;
  background: white;
  border-bottom: 1px solid var(--slate-200);
  flex-shrink: 0;
}
.app-header-left { display: flex; align-items: center; gap: 18px; }
.brand { font-weight: 600; color: var(--slate-800); text-decoration: none; font-size: 15px; }
.nav-link {
  color: var(--slate-600);
  text-decoration: none;
  font-size: 13px;
  padding: 4px 8px;
  border-radius: 6px;
}
.nav-link:hover { background: var(--slate-100); color: var(--slate-800); }
.nav-link.router-link-active { color: var(--blue-700); background: var(--blue-50); }

.app-header-right { display: flex; align-items: center; gap: 10px; }
.user-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  background: var(--slate-50);
  border: 1px solid var(--slate-200);
  border-radius: 999px;
  font-size: 12px;
  color: var(--slate-700);
}
.user-name { font-weight: 500; }
.user-role { color: var(--slate-500); font-size: 11px; }

.header-action {
  background: none;
  border: none;
  color: var(--slate-600);
  font-size: 13px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  text-decoration: none;
}
.header-action:hover { background: var(--slate-100); color: var(--slate-800); }
.header-action.danger:hover { background: var(--red-50); color: var(--red-600); }
</style>
