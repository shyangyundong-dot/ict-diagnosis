<template>
  <div class="admin-page">
    <div class="page-header">
      <h1>账号管理</h1>
      <button class="btn-primary" @click="openCreate">+ 新建账号</button>
    </div>

    <div v-if="loading" class="empty">加载中...</div>
    <div v-else-if="!items.length" class="empty">还没有账号。</div>

    <table v-else class="data-table">
      <thead>
        <tr>
          <th>用户名</th>
          <th>姓名</th>
          <th>角色</th>
          <th>所属线条</th>
          <th>状态</th>
          <th>上次登录</th>
          <th class="actions-col">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="u in items" :key="u.id" :class="{ inactive: !u.is_active }">
          <td>{{ u.username }}</td>
          <td>{{ u.display_name }}</td>
          <td>
            <span class="badge" :class="`badge-role-${u.role}`">{{ roleLabel(u.role) }}</span>
          </td>
          <td>{{ u.line_name || (u.role === 'admin' ? '—' : '未分配') }}</td>
          <td>
            <span v-if="u.is_active" class="badge badge-active">启用</span>
            <span v-else class="badge badge-inactive">禁用</span>
            <span v-if="u.must_change_password" class="badge badge-warn">待改密</span>
          </td>
          <td class="muted">{{ u.last_login_at || '从未' }}</td>
          <td class="actions-col">
            <button class="btn-link" @click="openEdit(u)">编辑</button>
            <button class="btn-link" @click="openResetPassword(u)">重置密码</button>
            <button class="btn-link" @click="toggleActive(u)" :disabled="u.id === me?.id">
              {{ u.is_active ? '禁用' : '启用' }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- 创建 / 编辑 -->
    <div v-if="modal" class="modal-mask" @click.self="closeModal">
      <div class="modal-box">
        <div class="modal-header">
          <span class="modal-title">{{ form.id ? '编辑账号' : '新建账号' }}</span>
          <button class="modal-close" @click="closeModal">✕</button>
        </div>
        <form class="modal-body" @submit.prevent="submitForm">
          <div class="form-row">
            <label>用户名（登录用，唯一，建议工号或英文短名）</label>
            <input v-model="form.username" maxlength="50" required :disabled="!!form.id || saving" />
          </div>
          <div class="form-row">
            <label>姓名</label>
            <input v-model="form.display_name" maxlength="100" required :disabled="saving" />
          </div>
          <div class="form-row">
            <label>邮箱（选填）</label>
            <input v-model="form.email" type="email" maxlength="255" :disabled="saving" />
          </div>
          <div class="form-row">
            <label>角色</label>
            <select v-model="form.role" required :disabled="saving || form.id === me?.id">
              <option value="user">员工 (user)</option>
              <option value="reviewer">主管 (reviewer)</option>
              <option value="admin">管理员 (admin)</option>
            </select>
            <small v-if="form.id === me?.id" class="hint">不能修改自己的角色</small>
          </div>
          <div v-if="form.role !== 'admin'" class="form-row">
            <label>所属线条</label>
            <select v-model.number="form.line_id" required :disabled="saving">
              <option :value="null" disabled>请选择</option>
              <option v-for="l in activeLines" :key="l.id" :value="l.id">
                {{ l.name }}{{ form.role === 'reviewer' && l.reviewer && l.reviewer.id !== form.id ? `（已有主管：${l.reviewer.display_name}）` : '' }}
              </option>
            </select>
          </div>
          <div v-if="!form.id" class="form-row">
            <label>临时密码（用户首次登录强制改）</label>
            <input v-model="form.password" type="text" minlength="8" required :disabled="saving" />
            <small class="hint">至少 8 位</small>
          </div>

          <div v-if="error" class="error">{{ error }}</div>
          <div class="form-actions">
            <button type="button" class="btn-secondary" @click="closeModal">取消</button>
            <button type="submit" class="btn-primary" :disabled="saving">
              {{ saving ? '保存中...' : '保存' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- 重置密码 -->
    <div v-if="resetModal" class="modal-mask" @click.self="closeResetModal">
      <div class="modal-box">
        <div class="modal-header">
          <span class="modal-title">重置密码 · {{ resetTarget?.display_name }}</span>
          <button class="modal-close" @click="closeResetModal">✕</button>
        </div>
        <form class="modal-body" @submit.prevent="submitReset">
          <div class="hint-box">
            管理员为该账号设置一个临时密码，TA 下次登录会被强制修改。
          </div>
          <div class="form-row">
            <label>新密码</label>
            <input v-model="resetPwd" type="text" minlength="8" required :disabled="saving" />
            <small class="hint">至少 8 位</small>
          </div>
          <div v-if="error" class="error">{{ error }}</div>
          <div class="form-actions">
            <button type="button" class="btn-secondary" @click="closeResetModal">取消</button>
            <button type="submit" class="btn-primary" :disabled="saving">
              {{ saving ? '提交中...' : '重置' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { listLines, listUsers, createUser, updateUser, resetPassword } from '../api/admin.js'
import { useAuth } from '../composables/useAuth.js'

const { state } = useAuth()
const me = computed(() => state.user)

const items = ref([])
const lines = ref([])
const loading = ref(false)

const modal = ref(false)
const saving = ref(false)
const error = ref('')
const form = reactive({ id: null, username: '', display_name: '', email: '', role: 'user', line_id: null, password: '' })

const resetModal = ref(false)
const resetTarget = ref(null)
const resetPwd = ref('')

const activeLines = computed(() => lines.value.filter((l) => l.is_active))

function roleLabel(role) {
  return { admin: '管理员', reviewer: '主管', user: '员工' }[role] || role
}

async function refresh() {
  loading.value = true
  try {
    const [u, l] = await Promise.all([listUsers(true), listLines(true)])
    items.value = u.data.items || []
    lines.value = l.data.items || []
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(form, { id: null, username: '', display_name: '', email: '', role: 'user', line_id: null, password: '' })
  error.value = ''
  modal.value = true
}

function openEdit(u) {
  Object.assign(form, {
    id: u.id,
    username: u.username,
    display_name: u.display_name,
    email: u.email || '',
    role: u.role,
    line_id: u.line_id,
    password: '',
  })
  error.value = ''
  modal.value = true
}

function closeModal() {
  if (saving.value) return
  modal.value = false
}

async function submitForm() {
  error.value = ''
  saving.value = true
  try {
    if (form.id) {
      const payload = {
        display_name: form.display_name.trim(),
        email: form.email.trim() || null,
        role: form.role,
        line_id: form.role === 'admin' ? null : form.line_id,
      }
      await updateUser(form.id, payload)
    } else {
      const payload = {
        username: form.username.trim(),
        display_name: form.display_name.trim(),
        email: form.email.trim() || null,
        role: form.role,
        line_id: form.role === 'admin' ? null : form.line_id,
        password: form.password,
      }
      await createUser(payload)
    }
    modal.value = false
    await refresh()
  } catch (e) {
    error.value = e.response?.data?.detail || '保存失败'
  } finally {
    saving.value = false
  }
}

function openResetPassword(u) {
  resetTarget.value = u
  resetPwd.value = ''
  error.value = ''
  resetModal.value = true
}

function closeResetModal() {
  if (saving.value) return
  resetModal.value = false
}

async function submitReset() {
  error.value = ''
  saving.value = true
  try {
    await resetPassword(resetTarget.value.id, resetPwd.value)
    resetModal.value = false
    await refresh()
  } catch (e) {
    error.value = e.response?.data?.detail || '重置失败'
  } finally {
    saving.value = false
  }
}

async function toggleActive(u) {
  if (u.id === me.value?.id) return
  if (!confirm(`确认${u.is_active ? '禁用' : '启用'}账号「${u.display_name}」？`)) return
  try {
    await updateUser(u.id, { is_active: !u.is_active })
    await refresh()
  } catch (e) {
    alert(e.response?.data?.detail || '操作失败')
  }
}

onMounted(refresh)
</script>

<style scoped>
.admin-page { max-width: 1100px; margin: 0 auto; padding: 24px 20px; }

.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h1 { font-size: 18px; font-weight: 600; }

.empty { padding: 60px 0; text-align: center; color: var(--slate-500); }

.data-table {
  width: 100%;
  background: white;
  border-radius: var(--radius-md);
  border-collapse: separate;
  border-spacing: 0;
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}
.data-table th,
.data-table td { padding: 10px 14px; text-align: left; font-size: 13px; border-bottom: 1px solid var(--slate-100); }
.data-table thead th { background: var(--slate-50); color: var(--slate-600); font-weight: 500; font-size: 12px; }
.data-table tbody tr.inactive { color: var(--slate-400); }
.actions-col { width: 1%; white-space: nowrap; }
.muted { color: var(--slate-500); }

.badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; margin-right: 4px; }
.badge-active { background: var(--green-50); color: var(--green-600); border: 1px solid var(--green-200); }
.badge-inactive { background: var(--slate-100); color: var(--slate-500); border: 1px solid var(--slate-200); }
.badge-warn { background: var(--yellow-50); color: var(--yellow-600); border: 1px solid var(--yellow-200); }
.badge-role-admin { background: #f5f3ff; color: #7c3aed; border: 1px solid #ddd6fe; }
.badge-role-reviewer { background: var(--blue-50); color: var(--blue-700); border: 1px solid var(--blue-200); }
.badge-role-user { background: var(--slate-50); color: var(--slate-600); border: 1px solid var(--slate-200); }

.btn-link { background: none; border: none; color: var(--blue-600); cursor: pointer; padding: 0 6px; font-size: 13px; }
.btn-link:hover { text-decoration: underline; }
.btn-link:disabled { color: var(--slate-300); cursor: not-allowed; text-decoration: none; }

/* 弹窗 */
.modal-mask { position: fixed; inset: 0; background: rgba(15,23,42,0.45); display: flex; align-items: center; justify-content: center; z-index: 50; }
.modal-box { width: 100%; max-width: 480px; background: white; border-radius: var(--radius-lg); box-shadow: var(--shadow-md); overflow: hidden; }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 14px 18px; border-bottom: 1px solid var(--slate-100); }
.modal-title { font-weight: 600; font-size: 15px; }
.modal-close { background: none; border: none; font-size: 16px; color: var(--slate-500); cursor: pointer; }
.modal-body { display: flex; flex-direction: column; gap: 12px; padding: 18px; max-height: 70vh; overflow-y: auto; }

.form-row { display: flex; flex-direction: column; gap: 4px; }
.form-row label { font-size: 13px; color: var(--slate-600); font-weight: 500; }
.form-row input, .form-row select {
  height: 36px; padding: 0 10px; border: 1px solid var(--slate-300); border-radius: var(--radius-sm); font-size: 13px; font-family: inherit;
}
.form-row input:focus, .form-row select:focus { outline: none; border-color: var(--blue-500); }
.form-row input:disabled, .form-row select:disabled { background: var(--slate-50); }
.hint { color: var(--slate-500); font-size: 11px; }

.hint-box { background: var(--blue-50); color: var(--blue-700); border: 1px solid var(--blue-200); padding: 8px 10px; border-radius: var(--radius-sm); font-size: 12px; }

.error { background: var(--red-50); color: var(--red-600); border: 1px solid var(--red-200); border-radius: var(--radius-sm); padding: 8px 10px; font-size: 12px; }

.form-actions { display: flex; gap: 8px; justify-content: flex-end; }
.btn-primary, .btn-secondary {
  height: 34px; padding: 0 16px; border-radius: var(--radius-sm); font-size: 13px; cursor: pointer; border: none; font-family: inherit;
}
.btn-primary { background: var(--blue-600); color: white; }
.btn-primary:hover:not(:disabled) { background: var(--blue-700); }
.btn-primary:disabled { background: var(--slate-300); cursor: not-allowed; }
.btn-secondary { background: var(--slate-100); color: var(--slate-700); border: 1px solid var(--slate-300); }
.btn-secondary:hover { background: var(--slate-200); }
</style>
