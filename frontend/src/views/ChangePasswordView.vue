<template>
  <div class="page">
    <div class="card">
      <h1 class="title">{{ forced ? '请先修改密码' : '修改密码' }}</h1>
      <div v-if="forced" class="hint">
        管理员设置的初始密码不安全，请设置新密码后继续使用。
      </div>

      <form class="form" @submit.prevent="onSubmit">
        <div class="row">
          <label>原密码</label>
          <input v-model="form.old_password" type="password" autocomplete="current-password" required :disabled="loading" />
        </div>
        <div class="row">
          <label>新密码（至少 8 位）</label>
          <input v-model="form.new_password" type="password" autocomplete="new-password" minlength="8" required :disabled="loading" />
        </div>
        <div class="row">
          <label>确认新密码</label>
          <input v-model="form.confirm" type="password" autocomplete="new-password" minlength="8" required :disabled="loading" />
        </div>

        <div v-if="error" class="error">{{ error }}</div>
        <div v-if="success" class="success">{{ success }}</div>

        <div class="actions">
          <button v-if="!forced" type="button" class="btn-secondary" @click="onCancel">取消</button>
          <button type="submit" class="btn-primary" :disabled="loading">{{ loading ? '提交中...' : '提交' }}</button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import axios from 'axios'
import { useRoute, useRouter } from 'vue-router'
import { useAuth, markPasswordChanged, getToken } from '../composables/useAuth'

const route = useRoute()
const router = useRouter()
const { state } = useAuth()

const forced = computed(() => !!state.user?.must_change_password)

const form = reactive({ old_password: '', new_password: '', confirm: '' })
const loading = ref(false)
const error = ref('')
const success = ref('')

async function onSubmit() {
  error.value = ''
  success.value = ''
  if (form.new_password !== form.confirm) {
    error.value = '两次输入的新密码不一致'
    return
  }
  if (form.new_password.length < 8) {
    error.value = '新密码至少 8 位'
    return
  }
  loading.value = true
  try {
    await axios.post(
      '/api/auth/change-password',
      { old_password: form.old_password, new_password: form.new_password },
      { headers: { Authorization: `Bearer ${getToken()}` } },
    )
    markPasswordChanged()
    success.value = '密码修改成功'
    const redirect = (route.query.redirect && String(route.query.redirect)) || '/'
    setTimeout(() => router.replace(redirect), 600)
  } catch (e) {
    error.value = e.response?.data?.detail || '修改失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

function onCancel() {
  router.back()
}
</script>

<style scoped>
.page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--slate-100);
  padding: 24px;
}
.card {
  width: 100%;
  max-width: 420px;
  background: white;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  padding: 32px 28px;
}
.title { font-size: 18px; font-weight: 600; margin-bottom: 12px; }
.hint {
  background: var(--yellow-50);
  border: 1px solid var(--yellow-200);
  color: var(--yellow-600);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  font-size: 13px;
  margin-bottom: 16px;
}

.form { display: flex; flex-direction: column; gap: 14px; }
.row { display: flex; flex-direction: column; gap: 6px; }
.row label { font-size: 13px; color: var(--slate-600); font-weight: 500; }
.row input {
  height: 38px;
  padding: 0 12px;
  border: 1px solid var(--slate-300);
  border-radius: var(--radius-sm);
  font-size: 14px;
  outline: none;
}
.row input:focus { border-color: var(--blue-500); }
.row input:disabled { background: var(--slate-50); }

.error {
  background: var(--red-50);
  color: var(--red-600);
  border: 1px solid var(--red-200);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  font-size: 13px;
}
.success {
  background: var(--green-50);
  color: var(--green-600);
  border: 1px solid var(--green-200);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  font-size: 13px;
}

.actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 8px; }
.btn-primary, .btn-secondary {
  height: 38px;
  padding: 0 18px;
  border-radius: var(--radius-sm);
  font-size: 14px;
  cursor: pointer;
  border: none;
}
.btn-primary { background: var(--blue-600); color: white; }
.btn-primary:hover:not(:disabled) { background: var(--blue-700); }
.btn-primary:disabled { background: var(--slate-300); cursor: not-allowed; }
.btn-secondary { background: var(--slate-100); color: var(--slate-700); border: 1px solid var(--slate-300); }
.btn-secondary:hover { background: var(--slate-200); }
</style>
