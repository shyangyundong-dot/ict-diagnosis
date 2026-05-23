<template>
  <div class="page">
    <div class="page-header">
      <h1>审计日志</h1>
    </div>

    <div class="filter-bar">
      <select v-model="filters.action" @change="refresh">
        <option value="">全部操作</option>
        <option value="create_user">创建账号</option>
        <option value="update_user">修改账号</option>
        <option value="reset_password">重置密码</option>
        <option value="create_line">创建线条</option>
        <option value="update_line">修改线条</option>
        <option value="claim_legacy">认领存量</option>
      </select>
      <select v-model.number="filters.admin_user_id" @change="refresh">
        <option :value="null">全部管理员</option>
        <option v-for="a in admins" :key="a.id" :value="a.id">{{ a.display_name }}（{{ a.username }}）</option>
      </select>
      <label class="date-label">从
        <input type="date" v-model="filters.start" @change="refresh" />
      </label>
      <label class="date-label">到
        <input type="date" v-model="filters.end" @change="refresh" />
      </label>
      <button class="btn-secondary" @click="resetFilters">清空筛选</button>
      <div class="spacer"></div>
      <div class="total-hint">共 {{ total }} 条</div>
    </div>

    <div v-if="loading" class="empty">加载中...</div>
    <div v-else-if="!items.length" class="empty">没有匹配的记录</div>

    <table v-else class="data-table">
      <thead>
        <tr>
          <th>时间</th>
          <th>管理员</th>
          <th>操作</th>
          <th>对象</th>
          <th>详情</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in items" :key="r.id">
          <td class="muted">{{ r.created_at }}</td>
          <td>{{ r.admin_display_name }}</td>
          <td><span class="action-badge" :class="`action-${r.action}`">{{ actionLabel(r.action) }}</span></td>
          <td class="muted">
            <span v-if="r.target_type">{{ r.target_type }} #{{ r.target_id }}</span>
            <span v-else>—</span>
          </td>
          <td><pre class="details">{{ formatDetails(r.details) }}</pre></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { listAudit, listUsers } from '../api/admin.js'

const items = ref([])
const total = ref(0)
const loading = ref(false)
const admins = ref([])

const filters = reactive({ action: '', admin_user_id: null, start: '', end: '' })

const ACTION_LABEL = {
  create_user: '创建账号',
  update_user: '修改账号',
  reset_password: '重置密码',
  create_line: '创建线条',
  update_line: '修改线条',
  claim_legacy: '认领存量',
}
function actionLabel(a) { return ACTION_LABEL[a] || a }

function formatDetails(d) {
  if (!d) return '—'
  try { return JSON.stringify(d, null, 2) } catch { return String(d) }
}

async function refresh() {
  loading.value = true
  try {
    const params = {}
    if (filters.action) params.action = filters.action
    if (filters.admin_user_id) params.admin_user_id = filters.admin_user_id
    if (filters.start) params.start = filters.start
    if (filters.end) params.end = filters.end
    const { data } = await listAudit(params)
    items.value = data.items || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  filters.action = ''
  filters.admin_user_id = null
  filters.start = ''
  filters.end = ''
  refresh()
}

onMounted(async () => {
  const u = await listUsers(true)
  admins.value = (u.data.items || []).filter((x) => x.role === 'admin')
  await refresh()
})
</script>

<style scoped>
.page { max-width: 1200px; margin: 0 auto; padding: 24px 20px; }
.page-header h1 { font-size: 18px; font-weight: 600; margin-bottom: 14px; }

.filter-bar {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  background: white; padding: 12px 14px; border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm); margin-bottom: 12px;
}
.filter-bar select, .filter-bar input[type=date] {
  height: 32px; padding: 0 10px; border: 1px solid var(--slate-300); border-radius: var(--radius-sm); font-size: 13px; font-family: inherit;
}
.date-label { font-size: 12px; color: var(--slate-600); display: flex; align-items: center; gap: 4px; }
.spacer { flex: 1; }
.total-hint { color: var(--slate-500); font-size: 12px; }

.btn-secondary {
  height: 32px; padding: 0 12px; border-radius: var(--radius-sm); font-size: 12px; cursor: pointer; font-family: inherit;
  background: var(--slate-100); color: var(--slate-700); border: 1px solid var(--slate-300);
}
.btn-secondary:hover { background: var(--slate-200); }

.empty { padding: 60px 0; text-align: center; color: var(--slate-500); }

.data-table { width: 100%; background: white; border-radius: var(--radius-md); border-collapse: separate; border-spacing: 0; overflow: hidden; box-shadow: var(--shadow-sm); }
.data-table th, .data-table td { padding: 9px 12px; text-align: left; font-size: 12px; border-bottom: 1px solid var(--slate-100); vertical-align: top; }
.data-table thead th { background: var(--slate-50); color: var(--slate-600); font-weight: 500; font-size: 11px; }
.muted { color: var(--slate-500); }

.action-badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; background: var(--blue-50); color: var(--blue-700); border: 1px solid var(--blue-200); }
.action-reset_password { background: #f5f3ff; color: #7c3aed; border-color: #ddd6fe; }
.action-claim_legacy { background: var(--yellow-50); color: var(--yellow-600); border-color: var(--yellow-200); }

.details {
  margin: 0; font-family: ui-monospace, "SF Mono", monospace; font-size: 11px;
  color: var(--slate-600); background: var(--slate-50); padding: 6px 8px; border-radius: 4px;
  max-width: 480px; max-height: 200px; overflow: auto; white-space: pre-wrap;
}
</style>
