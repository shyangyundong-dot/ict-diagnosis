<template>
  <div class="lookup-page">
    <header class="lookup-header">
      <router-link to="/" class="back-link">← 返回诊断</router-link>
      <h1>按 BPM 商机编码查询</h1>
      <p class="lookup-desc">
        与填报时<strong>完全一致</strong>的商机编码可查出全部历史记录；同一商机多次诊断会列出多条，请按时间与规则版本选择对应报告。
      </p>
    </header>

    <div class="lookup-card">
      <div class="search-row">
        <input
          v-model.trim="bpmInput"
          type="text"
          class="bpm-input"
          placeholder="请输入 BPM 商机编码"
          @keydown.enter.prevent="search"
        />
        <button type="button" class="search-btn" :disabled="loading || !bpmInput" @click="search">
          查询
        </button>
      </div>

      <p v-if="error" class="msg error">{{ error }}</p>
      <p v-else-if="searched && !loading && items.length === 0" class="msg empty">
        未找到该商机编码下的诊断记录。请确认编码是否与提交时一致（含空格、大小写需一致）。
      </p>

      <div v-if="loading" class="loading">查询中…</div>

      <div v-if="!loading && items.length > 0" class="result-wrap">
        <div class="result-meta">共 <strong>{{ items.length }}</strong> 条记录（按时间从新到旧）</div>
        <table class="result-table">
          <thead>
            <tr>
              <th>诊断编号</th>
              <th>生成时间</th>
              <th>风险等级</th>
              <th>规则版本</th>
              <th>项目类型</th>
              <th colspan="2">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in items" :key="row.diagnosis_id">
              <td class="mono">#{{ row.diagnosis_id }}</td>
              <td>{{ row.created_at }}</td>
              <td>
                <span class="risk-pill" :class="'r-' + row.overall_risk">{{ row.overall_risk_label || '—' }}</span>
              </td>
              <td class="mono">{{ row.rule_version }}</td>
              <td class="pt-cell">{{ row.project_type }}</td>
              <td class="actions">
                <router-link :to="'/trace/' + row.diagnosis_id" class="trace-link">填报溯源</router-link>
              </td>
              <td class="actions">
                <router-link :to="'/report/' + row.diagnosis_id" class="open-link" target="_blank">打开报告</router-link>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { listDiagnosesByBpm } from '../api/diagnosis.js'

const bpmInput = ref('')
const loading = ref(false)
const error = ref('')
const searched = ref(false)
const items = ref([])

async function search() {
  if (!bpmInput.value) return
  loading.value = true
  error.value = ''
  searched.value = true
  items.value = []
  try {
    const { data } = await listDiagnosesByBpm(bpmInput.value)
    items.value = data.items || []
  } catch (e) {
    const msg = e.response?.data?.detail
    error.value = typeof msg === 'string' ? msg : (e.message || '查询失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.lookup-page {
  max-width: 960px;
  margin: 0 auto;
  padding: 2rem 1.25rem 3rem;
}

.lookup-header {
  margin-bottom: 1.5rem;
}

.back-link {
  display: inline-block;
  margin-bottom: 0.75rem;
  color: var(--blue-600);
  text-decoration: none;
  font-size: 0.95rem;
}
.back-link:hover { text-decoration: underline; }

.lookup-header h1 {
  font-size: 1.35rem;
  font-weight: 700;
  color: var(--slate-800);
  margin-bottom: 0.5rem;
}

.lookup-desc {
  font-size: 0.95rem;
  color: var(--slate-600);
  line-height: 1.6;
}

.lookup-card {
  background: #fff;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  padding: 1.5rem 1.25rem;
  border: 1px solid var(--slate-200);
}

.search-row {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.bpm-input {
  flex: 1;
  min-width: 200px;
  padding: 0.65rem 0.85rem;
  border: 1px solid var(--slate-300);
  border-radius: var(--radius-sm);
  font-size: 1rem;
}

.bpm-input:focus {
  outline: none;
  border-color: var(--blue-500);
  box-shadow: 0 0 0 3px var(--blue-100);
}

.search-btn {
  padding: 0.65rem 1.25rem;
  background: var(--blue-600);
  color: #fff;
  border: none;
  border-radius: var(--radius-sm);
  font-weight: 600;
  cursor: pointer;
}

.search-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.search-btn:not(:disabled):hover {
  background: var(--blue-700);
}

.msg {
  margin-top: 1rem;
  font-size: 0.95rem;
}

.msg.error {
  color: var(--red-600);
}

.msg.empty {
  color: var(--slate-600);
}

.loading {
  margin-top: 1rem;
  color: var(--slate-500);
}

.result-wrap {
  margin-top: 1.25rem;
}

.result-meta {
  font-size: 0.9rem;
  color: var(--slate-600);
  margin-bottom: 0.75rem;
}

.result-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}

.result-table th,
.result-table td {
  text-align: left;
  padding: 0.6rem 0.5rem;
  border-bottom: 1px solid var(--slate-200);
  vertical-align: middle;
}

.result-table th {
  color: var(--slate-500);
  font-weight: 600;
  font-size: 0.82rem;
  text-transform: none;
}

.mono {
  font-family: ui-monospace, monospace;
  font-size: 0.85rem;
}

.pt-cell {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.risk-pill {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 6px;
  font-size: 0.82rem;
  font-weight: 600;
}

.risk-pill.r-high { background: var(--red-50); color: var(--red-600); }
.risk-pill.r-medium { background: var(--yellow-50); color: var(--yellow-600); }
.risk-pill.r-low { background: var(--green-50); color: var(--green-600); }
.risk-pill.r-tip { background: var(--slate-100); color: var(--slate-600); }

.actions {
  white-space: nowrap;
}

.open-link {
  color: var(--blue-600);
  font-weight: 600;
  text-decoration: none;
}

.open-link:hover {
  text-decoration: underline;
}

.trace-link {
  color: var(--slate-700);
  font-weight: 600;
  text-decoration: none;
  font-size: 0.88rem;
}
.trace-link:hover {
  text-decoration: underline;
  color: var(--blue-600);
}
</style>
