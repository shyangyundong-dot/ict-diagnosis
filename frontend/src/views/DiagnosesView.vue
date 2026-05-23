<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h1>诊断列表</h1>
        <div class="hint">{{ scopeHint }}</div>
      </div>
      <button v-if="canCreate" class="btn-primary" @click="goNew">+ 发起新诊断</button>
    </div>

    <div v-if="loading" class="empty">加载中...</div>
    <div v-else-if="!items.length" class="empty">
      {{ state.user?.role === 'user' ? '你还没有提交过诊断。' : '当前可见范围内没有诊断记录。' }}
    </div>

    <table v-else class="data-table">
      <thead>
        <tr>
          <th>ID</th>
          <th>BPM 编号</th>
          <th>项目类型</th>
          <th>整体风险</th>
          <th>提交人</th>
          <th>提交时间</th>
          <th>规则版本</th>
          <th class="actions-col">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="d in items" :key="d.diagnosis_id">
          <td class="muted">#{{ d.diagnosis_id }}</td>
          <td>{{ d.bpm_id }}</td>
          <td class="muted">{{ d.project_type }}</td>
          <td>
            <span class="risk-badge" :class="`risk-${d.overall_risk}`">
              {{ d.overall_risk_label || d.overall_risk }}
            </span>
          </td>
          <td>{{ d.creator_display_name }}</td>
          <td class="muted">{{ d.created_at }}</td>
          <td class="muted">{{ d.rule_version }}</td>
          <td class="actions-col">
            <router-link :to="`/report/${d.diagnosis_id}`" class="btn-link">报告</router-link>
            <router-link :to="`/trace/${d.diagnosis_id}`" class="btn-link">溯源</router-link>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-if="items.length && total > items.length" class="footer-note">
      共 {{ total }} 条，已加载 {{ items.length }} 条
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api/diagnosis.js'
import { useAuth } from '../composables/useAuth.js'

const router = useRouter()
const { state } = useAuth()

const items = ref([])
const total = ref(0)
const loading = ref(false)

const canCreate = computed(() => state.user && state.user.role !== 'admin')

const scopeHint = computed(() => {
  const role = state.user?.role
  if (role === 'admin') return '管理员视图：全部诊断记录（含存量数据）'
  if (role === 'reviewer') return '主管视图：本线条内所有员工的诊断 + 自己创建的'
  return '员工视图：仅显示你自己创建的诊断'
})

async function refresh() {
  loading.value = true
  try {
    const { data } = await api.get('/diagnoses', { params: { limit: 100, offset: 0 } })
    items.value = data.items || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

function goNew() {
  router.push('/')
}

onMounted(refresh)
</script>

<style scoped>
.page { max-width: 1200px; margin: 0 auto; padding: 24px 20px; }

.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.page-header h1 { font-size: 18px; font-weight: 600; }
.hint { color: var(--slate-500); font-size: 12px; margin-top: 4px; }

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
.actions-col { width: 1%; white-space: nowrap; }
.muted { color: var(--slate-500); }

.risk-badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 500; }
.risk-high { background: var(--red-50); color: var(--red-600); border: 1px solid var(--red-200); }
.risk-medium { background: var(--yellow-50); color: var(--yellow-600); border: 1px solid var(--yellow-200); }
.risk-low { background: var(--green-50); color: var(--green-600); border: 1px solid var(--green-200); }

.btn-link { background: none; border: none; color: var(--blue-600); cursor: pointer; padding: 0 6px; font-size: 13px; text-decoration: none; }
.btn-link:hover { text-decoration: underline; }

.btn-primary {
  height: 34px; padding: 0 16px; border-radius: var(--radius-sm); font-size: 13px; cursor: pointer; border: none; font-family: inherit;
  background: var(--blue-600); color: white;
}
.btn-primary:hover { background: var(--blue-700); }

.footer-note { color: var(--slate-500); font-size: 12px; text-align: center; margin-top: 12px; }
</style>
