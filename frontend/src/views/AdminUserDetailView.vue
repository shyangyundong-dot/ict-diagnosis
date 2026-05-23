<template>
  <div class="page">
    <div class="page-header">
      <router-link to="/admin/users" class="back-link">← 账号管理</router-link>
    </div>

    <div v-if="loading" class="empty">加载中...</div>
    <div v-else-if="error" class="error">{{ error }}</div>

    <template v-else-if="user">
      <div class="user-card">
        <div class="user-card-header">
          <h1>{{ user.display_name }}</h1>
          <span class="badge" :class="`badge-role-${user.role}`">{{ roleLabel(user.role) }}</span>
          <span v-if="!user.is_active" class="badge badge-inactive">已禁用</span>
          <span v-if="user.must_change_password" class="badge badge-warn">待改密</span>
        </div>
        <div class="user-card-body">
          <div><label>用户名：</label>{{ user.username }}</div>
          <div><label>邮箱：</label>{{ user.email || '—' }}</div>
          <div><label>所属线条：</label>{{ user.line_name || (user.role === 'admin' ? '—' : '未分配') }}</div>
          <div><label>创建时间：</label>{{ user.created_at }}</div>
          <div><label>上次登录：</label>{{ user.last_login_at || '从未' }}</div>
          <div><label>上次失败登录：</label>{{ user.last_failed_login_at || '—' }}（累计失败 {{ user.failed_login_count }} 次）</div>
        </div>
      </div>

      <div class="tabs">
        <button v-for="t in tabs" :key="t.key"
          class="tab-btn" :class="{ active: activeTab === t.key }"
          @click="activeTab = t.key">
          {{ t.label }} ({{ counts[t.key] }})
        </button>
      </div>

      <!-- 诊断 tab -->
      <table v-if="activeTab === 'diagnoses'" class="data-table">
        <thead>
          <tr><th>ID</th><th>BPM</th><th>项目类型</th><th>风险</th><th>线条</th><th>规则版本</th><th>时间</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-if="!activity.diagnoses.items.length"><td colspan="8" class="empty-row">无</td></tr>
          <tr v-for="d in activity.diagnoses.items" :key="d.diagnosis_id">
            <td class="muted">#{{ d.diagnosis_id }}</td>
            <td>{{ d.bpm_id }}</td>
            <td class="muted">{{ d.project_type }}</td>
            <td><span class="risk-badge" :class="`risk-${d.overall_risk}`">{{ d.overall_risk_label || d.overall_risk }}</span></td>
            <td class="muted">{{ d.line_id || '—' }}</td>
            <td class="muted">{{ d.rule_version }}</td>
            <td class="muted">{{ d.created_at }}</td>
            <td><router-link :to="`/report/${d.diagnosis_id}`" class="btn-link">报告</router-link></td>
          </tr>
        </tbody>
      </table>

      <!-- 复核 tab -->
      <table v-if="activeTab === 'reviews'" class="data-table">
        <thead>
          <tr><th>复核ID</th><th>诊断ID</th><th>BPM</th><th>结论</th><th>说明</th><th>时间</th></tr>
        </thead>
        <tbody>
          <tr v-if="!activity.reviews.items.length"><td colspan="6" class="empty-row">无</td></tr>
          <tr v-for="r in activity.reviews.items" :key="r.dissent_id">
            <td class="muted">#{{ r.dissent_id }}</td>
            <td><router-link :to="`/report/${r.diagnosis_id}`" class="btn-link">#{{ r.diagnosis_id }}</router-link></td>
            <td>{{ r.bpm_id }}</td>
            <td><span class="result-badge">{{ resultLabel(r.review_result) }}</span></td>
            <td class="muted truncate">{{ r.manual_conclusion || r.override_reason || '—' }}</td>
            <td class="muted">{{ r.created_at }}</td>
          </tr>
        </tbody>
      </table>

      <!-- 对话 tab -->
      <table v-if="activeTab === 'chat_sessions'" class="data-table">
        <thead>
          <tr><th>会话 ID</th><th>状态</th><th>创建</th><th>最后更新</th></tr>
        </thead>
        <tbody>
          <tr v-if="!activity.chat_sessions.items.length"><td colspan="4" class="empty-row">无</td></tr>
          <tr v-for="s in activity.chat_sessions.items" :key="s.session_id">
            <td class="muted truncate">{{ s.session_id }}</td>
            <td>{{ s.status === 'confirmed' ? '已确认' : '收集中' }}</td>
            <td class="muted">{{ s.created_at }}</td>
            <td class="muted">{{ s.updated_at }}</td>
          </tr>
        </tbody>
      </table>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getUser, getUserActivity } from '../api/admin.js'

const route = useRoute()
const userId = Number(route.params.id)

const user = ref(null)
const activity = ref({ diagnoses: { count: 0, items: [] }, reviews: { count: 0, items: [] }, chat_sessions: { count: 0, items: [] } })
const loading = ref(true)
const error = ref('')

const tabs = [
  { key: 'diagnoses', label: '创建的诊断' },
  { key: 'reviews', label: '写过的复核' },
  { key: 'chat_sessions', label: '未完成对话' },
]
const activeTab = ref('diagnoses')

const counts = computed(() => ({
  diagnoses: activity.value.diagnoses.count,
  reviews: activity.value.reviews.count,
  chat_sessions: activity.value.chat_sessions.count,
}))

function roleLabel(r) { return { admin: '管理员', reviewer: '主管', user: '员工' }[r] || r }
function resultLabel(r) { return { confirmed: '一致', partial: '部分采纳', overridden: '推翻' }[r] || r }

onMounted(async () => {
  try {
    const [u, a] = await Promise.all([getUser(userId), getUserActivity(userId)])
    user.value = u.data
    activity.value = a.data
  } catch (e) {
    error.value = e.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.page { max-width: 1100px; margin: 0 auto; padding: 24px 20px; }
.page-header { margin-bottom: 12px; }
.back-link { color: var(--slate-600); text-decoration: none; font-size: 13px; }
.back-link:hover { color: var(--blue-600); }

.empty { padding: 60px 0; text-align: center; color: var(--slate-500); }
.error { background: var(--red-50); color: var(--red-600); padding: 10px 14px; border-radius: var(--radius-sm); }

.user-card {
  background: white; border-radius: var(--radius-md); box-shadow: var(--shadow-sm);
  padding: 18px 20px; margin-bottom: 16px;
}
.user-card-header { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.user-card-header h1 { font-size: 18px; font-weight: 600; }
.user-card-body {
  display: grid; grid-template-columns: 1fr 1fr; gap: 6px 24px; font-size: 13px; color: var(--slate-700);
}
.user-card-body label { color: var(--slate-500); }

.badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; }
.badge-inactive { background: var(--slate-100); color: var(--slate-500); border: 1px solid var(--slate-200); }
.badge-warn { background: var(--yellow-50); color: var(--yellow-600); border: 1px solid var(--yellow-200); }
.badge-role-admin { background: #f5f3ff; color: #7c3aed; border: 1px solid #ddd6fe; }
.badge-role-reviewer { background: var(--blue-50); color: var(--blue-700); border: 1px solid var(--blue-200); }
.badge-role-user { background: var(--slate-50); color: var(--slate-600); border: 1px solid var(--slate-200); }

.tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--slate-200); margin-bottom: 12px; }
.tab-btn {
  background: none; border: none; padding: 8px 14px; cursor: pointer;
  font-size: 13px; color: var(--slate-600); border-bottom: 2px solid transparent;
  font-family: inherit;
}
.tab-btn.active { color: var(--blue-700); border-bottom-color: var(--blue-600); font-weight: 500; }

.data-table { width: 100%; background: white; border-radius: var(--radius-md); border-collapse: separate; border-spacing: 0; overflow: hidden; box-shadow: var(--shadow-sm); }
.data-table th, .data-table td { padding: 9px 12px; text-align: left; font-size: 12px; border-bottom: 1px solid var(--slate-100); }
.data-table thead th { background: var(--slate-50); color: var(--slate-600); font-weight: 500; font-size: 11px; }
.muted { color: var(--slate-500); }
.truncate { max-width: 280px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.empty-row { text-align: center; color: var(--slate-400); padding: 18px 0; }

.risk-badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; }
.risk-high { background: var(--red-50); color: var(--red-600); border: 1px solid var(--red-200); }
.risk-medium { background: var(--yellow-50); color: var(--yellow-600); border: 1px solid var(--yellow-200); }
.risk-low { background: var(--green-50); color: var(--green-600); border: 1px solid var(--green-200); }
.result-badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; background: var(--slate-50); color: var(--slate-600); border: 1px solid var(--slate-200); }

.btn-link { background: none; border: none; color: var(--blue-600); cursor: pointer; padding: 0 6px; font-size: 12px; text-decoration: none; }
.btn-link:hover { text-decoration: underline; }
</style>
