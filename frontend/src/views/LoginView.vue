<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-header">
        <div class="login-icon">🛡</div>
        <h1 class="login-title">ICT 项目合规诊断工具</h1>
        <div class="login-subtitle">广州电信云中台</div>
      </div>

      <form class="login-form" @submit.prevent="onSubmit">
        <div class="form-row">
          <label class="form-label">账号</label>
          <input
            v-model="form.username"
            class="form-input"
            type="text"
            autocomplete="username"
            placeholder="请输入工号或用户名"
            :disabled="loading"
            required
          />
        </div>
        <div class="form-row">
          <label class="form-label">密码</label>
          <input
            v-model="form.password"
            class="form-input"
            type="password"
            autocomplete="current-password"
            placeholder="请输入密码"
            :disabled="loading"
            required
          />
        </div>

        <div v-if="error" class="error-banner">{{ error }}</div>

        <button class="submit-btn" type="submit" :disabled="loading || !canSubmit">
          {{ loading ? '登录中...' : '登 录' }}
        </button>
      </form>

      <div class="login-footer">如忘记密码请联系管理员重置</div>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '../composables/useAuth'

const route = useRoute()
const router = useRouter()
const { login } = useAuth()

const form = reactive({ username: '', password: '' })
const loading = ref(false)
const error = ref('')

const canSubmit = computed(() => form.username.trim() && form.password)

async function onSubmit() {
  loading.value = true
  error.value = ''
  try {
    const data = await login(form.username.trim(), form.password)
    const redirect = (route.query.redirect && String(route.query.redirect)) || '/'
    if (data.user?.must_change_password) {
      await router.replace({ path: '/profile/password', query: { redirect } })
    } else {
      await router.replace(redirect)
    }
  } catch (e) {
    error.value = e.response?.data?.detail || '登录失败，请检查账号或密码'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--blue-50) 0%, var(--slate-100) 100%);
  padding: 24px;
}
.login-card {
  width: 100%;
  max-width: 380px;
  background: white;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  padding: 36px 32px 28px;
}
.login-header { text-align: center; margin-bottom: 28px; }
.login-icon { font-size: 40px; line-height: 1; margin-bottom: 12px; }
.login-title { font-size: 18px; font-weight: 600; color: var(--slate-800); }
.login-subtitle { font-size: 13px; color: var(--slate-500); margin-top: 6px; }

.login-form { display: flex; flex-direction: column; gap: 16px; }
.form-row { display: flex; flex-direction: column; gap: 6px; }
.form-label { font-size: 13px; color: var(--slate-600); font-weight: 500; }
.form-input {
  height: 40px;
  padding: 0 12px;
  border: 1px solid var(--slate-300);
  border-radius: var(--radius-sm);
  font-size: 14px;
  outline: none;
  transition: border-color 0.15s;
}
.form-input:focus { border-color: var(--blue-500); }
.form-input:disabled { background: var(--slate-50); cursor: not-allowed; }

.error-banner {
  background: var(--red-50);
  color: var(--red-600);
  border: 1px solid var(--red-200);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  font-size: 13px;
}

.submit-btn {
  height: 42px;
  background: var(--blue-600);
  color: white;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
  margin-top: 4px;
}
.submit-btn:hover:not(:disabled) { background: var(--blue-700); }
.submit-btn:disabled { background: var(--slate-300); cursor: not-allowed; }

.login-footer {
  margin-top: 20px;
  text-align: center;
  font-size: 12px;
  color: var(--slate-400);
}
</style>
