<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h1>存量诊断认领</h1>
        <div class="hint">上线前的 {{ items.length }} 条匿名诊断（created_by 为空）。选中后归到指定账号；归属后 reviewer 就能看到了。</div>
      </div>
    </div>

    <div v-if="loading" class="empty">加载中...</div>
    <div v-else-if="!items.length" class="empty">所有存量数据已认领完毕 🎉</div>

    <template v-else>
      <div class="action-bar">
        <label>认领到：</label>
        <select v-model.number="targetUserId">
          <option :value="null" disabled>请选择账号</option>
          <optgroup v-for="line in linesWithUsers" :key="line.id" :label="line.name">
            <option v-for="u in line.users" :key="u.id" :value="u.id">
              {{ u.display_name }}（{{ u.username }} · {{ roleLabel(u.role) }}）
            </option>
          </optgroup>
          <optgroup v-if="adminUsers.length" label="管理员（认领后仍仅 admin 可见）">
            <option v-for="u in adminUsers" :key="u.id" :value="u.id">
              {{ u.display_name }}（{{ u.username }}）
            </option>
          </optgroup>
        </select>
        <span class="selected-count">已选 {{ selected.length }} 条</span>
        <button class="btn-primary" :disabled="!selected.length || !targetUserId || submitting" @click="doClaim">
          {{ submitting ? '处理中...' : '认领选中' }}
        </button>
      </div>

      <table class="data-table">
        <thead>
          <tr>
            <th class="checkbox-col">
              <input type="checkbox" :checked="allSelected" @change="toggleAll" />
            </th>
            <th>ID</th>
            <th>BPM</th>
            <th>项目类型</th>
            <th>风险</th>
            <th>规则版本</th>
            <th>时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="d in items" :key="d.diagnosis_id" :class="{ selected: selectedSet.has(d.diagnosis_id) }">
            <td class="checkbox-col">
              <input type="checkbox" :value="d.diagnosis_id" v-model="selected" />
            </td>
            <td class="muted">#{{ d.diagnosis_id }}</td>
            <td>{{ d.bpm_id }}</td>
            <td class="muted">{{ d.project_type }}</td>
            <td>
              <span class="risk-badge" :class="`risk-${d.overall_risk}`">{{ d.overall_risk_label || d.overall_risk }}</span>
            </td>
            <td class="muted">{{ d.rule_version }}</td>
            <td class="muted">{{ d.created_at }}</td>
          </tr>
        </tbody>
      </table>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { claimLegacy, listLegacy, listLines, listUsers } from '../api/admin.js'

const items = ref([])
const users = ref([])
const lines = ref([])
const selected = ref([])
const targetUserId = ref(null)
const loading = ref(false)
const submitting = ref(false)

const selectedSet = computed(() => new Set(selected.value))
const allSelected = computed(() => items.value.length > 0 && selected.value.length === items.value.length)

const adminUsers = computed(() => users.value.filter((u) => u.role === 'admin' && u.is_active))
const linesWithUsers = computed(() => {
  return lines.value
    .filter((l) => l.is_active)
    .map((l) => ({
      ...l,
      users: users.value.filter((u) => u.line_id === l.id && u.is_active),
    }))
    .filter((l) => l.users.length > 0)
})

function roleLabel(r) { return { admin: '管理员', reviewer: '主管', user: '员工' }[r] || r }

function toggleAll(e) {
  selected.value = e.target.checked ? items.value.map((d) => d.diagnosis_id) : []
}

async function refresh() {
  loading.value = true
  try {
    const [l, u, leg] = await Promise.all([listLines(true), listUsers(true), listLegacy()])
    lines.value = l.data.items || []
    users.value = u.data.items || []
    items.value = leg.data.items || []
    selected.value = []
  } finally {
    loading.value = false
  }
}

async function doClaim() {
  if (!selected.value.length || !targetUserId.value) return
  const target = users.value.find((u) => u.id === targetUserId.value)
  if (!confirm(`确认把选中的 ${selected.value.length} 条诊断认领到「${target?.display_name}」？此操作不可逆。`)) return
  submitting.value = true
  try {
    const { data } = await claimLegacy(selected.value, targetUserId.value)
    alert(`已认领 ${data.claimed_count} 条${data.skipped_ids.length ? `（${data.skipped_ids.length} 条跳过：${data.skipped_reason}）` : ''}`)
    await refresh()
  } catch (e) {
    alert(e.response?.data?.detail || '认领失败')
  } finally {
    submitting.value = false
  }
}

onMounted(refresh)
</script>

<style scoped>
.page { max-width: 1200px; margin: 0 auto; padding: 24px 20px; }

.page-header { margin-bottom: 14px; }
.page-header h1 { font-size: 18px; font-weight: 600; }
.hint { color: var(--slate-500); font-size: 12px; margin-top: 4px; }

.empty { padding: 60px 0; text-align: center; color: var(--slate-500); }

.action-bar {
  display: flex; align-items: center; gap: 10px;
  background: white; padding: 12px 14px; border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm); margin-bottom: 12px;
}
.action-bar label { font-size: 13px; color: var(--slate-600); }
.action-bar select {
  height: 34px; padding: 0 10px; border: 1px solid var(--slate-300); border-radius: var(--radius-sm);
  font-size: 13px; font-family: inherit; min-width: 240px;
}
.selected-count { color: var(--slate-500); font-size: 12px; margin-left: auto; }

.btn-primary {
  height: 34px; padding: 0 16px; border-radius: var(--radius-sm); font-size: 13px; cursor: pointer; border: none;
  font-family: inherit; background: var(--blue-600); color: white;
}
.btn-primary:hover:not(:disabled) { background: var(--blue-700); }
.btn-primary:disabled { background: var(--slate-300); cursor: not-allowed; }

.data-table { width: 100%; background: white; border-radius: var(--radius-md); border-collapse: separate; border-spacing: 0; overflow: hidden; box-shadow: var(--shadow-sm); }
.data-table th, .data-table td { padding: 9px 12px; text-align: left; font-size: 13px; border-bottom: 1px solid var(--slate-100); }
.data-table thead th { background: var(--slate-50); color: var(--slate-600); font-weight: 500; font-size: 12px; }
.data-table tbody tr.selected { background: var(--blue-50); }
.checkbox-col { width: 32px; }
.muted { color: var(--slate-500); }

.risk-badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; }
.risk-high { background: var(--red-50); color: var(--red-600); border: 1px solid var(--red-200); }
.risk-medium { background: var(--yellow-50); color: var(--yellow-600); border: 1px solid var(--yellow-200); }
.risk-low { background: var(--green-50); color: var(--green-600); border: 1px solid var(--green-200); }
</style>
