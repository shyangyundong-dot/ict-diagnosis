<template>
  <div class="admin-page">
    <div class="page-header">
      <h1>线条管理</h1>
      <button class="btn-primary" @click="openCreate">+ 新建线条</button>
    </div>

    <div v-if="loading" class="empty">加载中...</div>
    <div v-else-if="!items.length" class="empty">还没有线条，点右上角新建第一个。</div>

    <table v-else class="data-table">
      <thead>
        <tr>
          <th>线条名</th>
          <th>主管</th>
          <th>员工数</th>
          <th>状态</th>
          <th>创建时间</th>
          <th class="actions-col">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="line in items" :key="line.id" :class="{ inactive: !line.is_active }">
          <td>{{ line.name }}</td>
          <td>
            <span v-if="line.reviewer">{{ line.reviewer.display_name }}</span>
            <span v-else class="warning-text">⚠️ 暂无主管</span>
          </td>
          <td>{{ line.user_count }}</td>
          <td>
            <span v-if="line.is_active" class="badge badge-active">启用</span>
            <span v-else class="badge badge-inactive">停用</span>
          </td>
          <td class="muted">{{ line.created_at }}</td>
          <td class="actions-col">
            <button class="btn-link" @click="openEdit(line)">编辑</button>
            <button class="btn-link" @click="toggleActive(line)">
              {{ line.is_active ? '停用' : '启用' }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- 编辑 / 新建弹窗 -->
    <div v-if="modal" class="modal-mask" @click.self="closeModal">
      <div class="modal-box">
        <div class="modal-header">
          <span class="modal-title">{{ form.id ? '编辑线条' : '新建线条' }}</span>
          <button class="modal-close" @click="closeModal">✕</button>
        </div>
        <form class="modal-body" @submit.prevent="submitForm">
          <div class="form-row">
            <label>线条名</label>
            <input v-model="form.name" maxlength="100" required :disabled="saving" />
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
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { listLines, createLine, updateLine } from '../api/admin.js'

const items = ref([])
const loading = ref(false)
const modal = ref(false)
const saving = ref(false)
const error = ref('')
const form = reactive({ id: null, name: '' })

async function refresh() {
  loading.value = true
  try {
    const { data } = await listLines(true)
    items.value = data.items || []
  } finally {
    loading.value = false
  }
}

function openCreate() {
  form.id = null
  form.name = ''
  error.value = ''
  modal.value = true
}

function openEdit(line) {
  form.id = line.id
  form.name = line.name
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
      await updateLine(form.id, { name: form.name.trim() })
    } else {
      await createLine(form.name.trim())
    }
    modal.value = false
    await refresh()
  } catch (e) {
    error.value = e.response?.data?.detail || '保存失败'
  } finally {
    saving.value = false
  }
}

async function toggleActive(line) {
  if (!confirm(`确认${line.is_active ? '停用' : '启用'}线条「${line.name}」？`)) return
  try {
    await updateLine(line.id, { is_active: !line.is_active })
    await refresh()
  } catch (e) {
    alert(e.response?.data?.detail || '操作失败')
  }
}

onMounted(refresh)
</script>

<style scoped>
.admin-page { max-width: 980px; margin: 0 auto; padding: 24px 20px; }

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
.warning-text { color: var(--yellow-600); font-size: 12px; }

.badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; }
.badge-active { background: var(--green-50); color: var(--green-600); border: 1px solid var(--green-200); }
.badge-inactive { background: var(--slate-100); color: var(--slate-500); border: 1px solid var(--slate-200); }

.btn-link { background: none; border: none; color: var(--blue-600); cursor: pointer; padding: 0 6px; font-size: 13px; }
.btn-link:hover { text-decoration: underline; }

/* 弹窗 */
.modal-mask { position: fixed; inset: 0; background: rgba(15,23,42,0.45); display: flex; align-items: center; justify-content: center; z-index: 50; }
.modal-box { width: 100%; max-width: 420px; background: white; border-radius: var(--radius-lg); box-shadow: var(--shadow-md); overflow: hidden; }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 14px 18px; border-bottom: 1px solid var(--slate-100); }
.modal-title { font-weight: 600; font-size: 15px; }
.modal-close { background: none; border: none; font-size: 16px; color: var(--slate-500); cursor: pointer; }
.modal-body { display: flex; flex-direction: column; gap: 14px; padding: 18px; }

.form-row { display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 13px; color: var(--slate-600); font-weight: 500; }
.form-row input, .form-row select {
  height: 36px; padding: 0 10px; border: 1px solid var(--slate-300); border-radius: var(--radius-sm); font-size: 13px; font-family: inherit;
}
.form-row input:focus, .form-row select:focus { outline: none; border-color: var(--blue-500); }

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
