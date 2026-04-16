<template>
  <div class="trace-page">
    <header class="trace-header">
      <router-link to="/" class="back-link">← 返回诊断</router-link>
      <router-link to="/lookup" class="back-link secondary">按 BPM 查询</router-link>
      <h1>填报溯源查询</h1>
      <p class="trace-desc">
        根据<strong>诊断编号</strong>查看该次提交时保存的「右侧确认字段」与「对话快照」。本页内容不展示在合规诊断报告中。
      </p>
    </header>

    <div v-if="invalidIdParam" class="trace-card">
      <p class="state err">诊断编号无效，请使用数字编号。</p>
      <router-link to="/trace" class="report-link">重新输入</router-link>
    </div>

    <div class="trace-card search-card" v-else-if="!routeId">
      <label class="search-label">诊断编号</label>
      <div class="search-row">
        <input
          v-model.trim="idInput"
          type="text"
          inputmode="numeric"
          class="id-input"
          placeholder="例如：12"
          @keydown.enter.prevent="goTrace"
        />
        <button type="button" class="go-btn" :disabled="!idInput" @click="goTrace">查询</button>
      </div>
    </div>

    <template v-else>
      <p v-if="loading" class="state">加载中…</p>
      <p v-else-if="error" class="state err">{{ error }}</p>

      <template v-else-if="data">
        <div class="meta-bar">
          <span>诊断编号 <strong class="mono">#{{ data.diagnosis_id }}</strong></span>
          <span>商机编号 <strong>{{ data.bpm_id }}</strong></span>
          <span>生成时间 {{ data.created_at }}</span>
          <span>规则版本 <code>{{ data.rule_version }}</code></span>
        </div>

        <section class="section">
          <h2 class="section-title">确认的结构化字段</h2>
          <p class="section-hint">与提交诊断时右侧「信息解析」中确认的值一致（input_json）。</p>
          <div v-if="!data.fields_display?.length" class="empty-block">无结构化字段记录</div>
          <table v-else class="fields-table">
            <thead>
              <tr>
                <th>字段</th>
                <th>值</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in data.fields_display" :key="row.key">
                <td class="field-label">{{ row.label }}</td>
                <td class="field-val">{{ row.value }}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section class="section">
          <h2 class="section-title">对话快照</h2>
          <p v-if="!data.has_chat_snapshot" class="section-hint muted">
            该条记录无对话快照（例如规则上线前的历史数据，或数据异常）。
          </p>
          <div v-else class="chat-replay">
            <div
              v-for="(msg, idx) in data.chat_messages"
              :key="idx"
              class="replay-row"
              :class="msg.role === 'user' ? 'is-user' : 'is-ai'"
            >
              <div class="replay-avatar">{{ msg.role === 'user' ? '我' : '🛡' }}</div>
              <div
                class="replay-bubble"
                v-if="msg.role === 'user'"
              >{{ msg.content }}</div>
              <div
                class="replay-bubble ai"
                v-else
                v-html="formatAiMsg(msg.content || '')"
              ></div>
            </div>
          </div>
        </section>

        <div class="footer-actions">
          <router-link :to="'/report/' + data.diagnosis_id" class="report-link" target="_blank">打开合规报告</router-link>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getDiagnosisTraceability } from '../api/diagnosis.js'

const route = useRoute()
const router = useRouter()

const routeId = computed(() => {
  const p = route.params.id
  if (p === undefined || p === '') return null
  const n = parseInt(String(p), 10)
  return Number.isFinite(n) && n > 0 ? n : null
})

const invalidIdParam = computed(() => {
  const p = route.params.id
  if (p === undefined || p === '') return false
  return routeId.value === null
})

const idInput = ref('')
const loading = ref(false)
const error = ref('')
const data = ref(null)

function formatAiMsg(text) {
  const t = text || ''
  return t
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/^/, '<p>')
    .replace(/$/, '</p>')
}

function goTrace() {
  const n = parseInt(idInput.value, 10)
  if (!Number.isFinite(n) || n < 1) return
  router.push(`/trace/${n}`)
}

async function load(id) {
  loading.value = true
  error.value = ''
  data.value = null
  try {
    const { data: body } = await getDiagnosisTraceability(id)
    data.value = body
  } catch (e) {
    const msg = e.response?.data?.detail
    error.value = typeof msg === 'string' ? msg : (e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

watch(
  routeId,
  (id) => {
    if (id) load(id)
    else {
      data.value = null
      error.value = ''
      loading.value = false
    }
  },
  { immediate: true }
)
</script>

<style scoped>
.trace-page {
  max-width: 880px;
  margin: 0 auto;
  padding: 2rem 1.25rem 3rem;
}

.trace-header {
  margin-bottom: 1.5rem;
}

.back-link {
  display: inline-block;
  margin-right: 1rem;
  margin-bottom: 0.5rem;
  color: var(--blue-600);
  text-decoration: none;
  font-size: 0.95rem;
}
.back-link.secondary { color: var(--slate-600); }
.back-link:hover { text-decoration: underline; }

.trace-header h1 {
  font-size: 1.35rem;
  font-weight: 700;
  color: var(--slate-800);
  margin: 0.5rem 0;
}

.trace-desc {
  font-size: 0.95rem;
  color: var(--slate-600);
  line-height: 1.6;
}

.trace-card {
  background: #fff;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  padding: 1.5rem 1.25rem;
  border: 1px solid var(--slate-200);
}

.search-label {
  display: block;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--slate-600);
  margin-bottom: 0.5rem;
}

.search-row {
  display: flex;
  gap: 0.75rem;
}

.id-input {
  flex: 1;
  padding: 0.65rem 0.85rem;
  border: 1px solid var(--slate-300);
  border-radius: var(--radius-sm);
  font-size: 1rem;
}

.go-btn {
  padding: 0.65rem 1.25rem;
  background: var(--blue-600);
  color: #fff;
  border: none;
  border-radius: var(--radius-sm);
  font-weight: 600;
  cursor: pointer;
}

.go-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.state {
  padding: 1rem;
  color: var(--slate-600);
}
.state.err {
  color: var(--red-600);
}

.meta-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem 1.25rem;
  padding: 1rem 1.1rem;
  background: var(--slate-50);
  border: 1px solid var(--slate-200);
  border-radius: var(--radius-md);
  font-size: 0.9rem;
  color: var(--slate-700);
  margin-bottom: 1.5rem;
}

.mono {
  font-family: ui-monospace, monospace;
}

.section {
  margin-bottom: 2rem;
}

.section-title {
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--slate-800);
  margin-bottom: 0.35rem;
}

.section-hint {
  font-size: 0.88rem;
  color: var(--slate-500);
  margin-bottom: 0.75rem;
}
.section-hint.muted {
  color: var(--slate-400);
}

.empty-block {
  padding: 1rem;
  background: var(--slate-50);
  border-radius: var(--radius-sm);
  color: var(--slate-500);
  font-size: 0.9rem;
}

.fields-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
  background: #fff;
  border: 1px solid var(--slate-200);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.fields-table th,
.fields-table td {
  text-align: left;
  padding: 0.55rem 0.75rem;
  border-bottom: 1px solid var(--slate-100);
  vertical-align: top;
}

.fields-table th {
  width: 28%;
  background: var(--slate-50);
  color: var(--slate-600);
  font-weight: 600;
  font-size: 0.82rem;
}

.field-label {
  color: var(--slate-700);
}

.field-val {
  color: var(--slate-800);
  word-break: break-word;
}

.chat-replay {
  border: 1px solid var(--slate-200);
  border-radius: var(--radius-md);
  padding: 1rem;
  background: #fafafa;
  max-height: 520px;
  overflow-y: auto;
}

.replay-row {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
  align-items: flex-start;
}

.replay-row:last-child {
  margin-bottom: 0;
}

.replay-row.is-user {
  flex-direction: row-reverse;
}

.replay-avatar {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--slate-200);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: var(--slate-600);
}

.is-ai .replay-avatar {
  background: var(--blue-100);
}

.replay-bubble {
  max-width: 85%;
  padding: 10px 12px;
  border-radius: 12px;
  font-size: 0.9rem;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--blue-50);
  border: 1px solid var(--blue-100);
}

.replay-bubble.ai {
  background: #fff;
  border-color: var(--slate-200);
}

.replay-bubble.ai :deep(p) {
  margin: 0 0 0.5em;
}
.replay-bubble.ai :deep(p:last-child) {
  margin-bottom: 0;
}

.footer-actions {
  padding-top: 0.5rem;
}

.report-link {
  color: var(--blue-600);
  font-weight: 600;
  text-decoration: none;
}
.report-link:hover {
  text-decoration: underline;
}
</style>
