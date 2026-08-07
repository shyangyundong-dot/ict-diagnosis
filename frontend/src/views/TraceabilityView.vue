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

        <section v-if="hasGuidedSnapshot" class="section">
          <h2 class="section-title">六块引导式项目说明</h2>
          <p class="section-hint">保留用户提交的原文、AI 整理摘要和提交时覆盖状态，便于复核事实来源。</p>
          <div class="guided-trace-grid">
            <article v-for="(item, key) in data.guided_input.sections" :key="key" class="guided-trace-card">
              <div class="guided-trace-head">
                <strong>{{ data.guided_section_definitions?.[key]?.title || key }}</strong>
                <span :class="data.coverage?.sections?.[key]?.status || 'missing'">
                  {{ coverageStatusLabel(data.coverage?.sections?.[key]?.status) }}
                </span>
              </div>
              <div class="trace-block-label">用户原文</div>
              <p class="trace-original">{{ item.text || (item.explicit_unknown ? '暂不清楚' : '未填写') }}</p>
              <template v-if="data.coverage?.sections?.[key]?.summary">
                <div class="trace-block-label">AI 整理摘要</div>
                <p class="trace-summary">{{ data.coverage.sections[key].summary }}</p>
              </template>
            </article>
          </div>
        </section>

        <section class="section">
          <h2 class="section-title">确认的结构化字段</h2>
          <p class="section-hint">与提交诊断时右侧「项目事实表」中确认的值一致；同时保留填写来源，便于复核。</p>
          <div v-if="!data.fields_display?.length" class="empty-block">无结构化字段记录</div>
          <table v-else class="fields-table">
            <thead>
              <tr>
                <th>字段</th>
                <th>值</th>
                <th>来源</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in data.fields_display" :key="row.key">
                <td class="field-label">{{ row.label }}</td>
                <td class="field-val">{{ row.value }}</td>
                <td><span class="source-tag" :class="fieldSource(row.key).tone">{{ fieldSource(row.key).label }}</span></td>
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

const hasGuidedSnapshot = computed(() => Object.values(data.value?.guided_input?.sections || {})
  .some((item) => item?.text || item?.explicit_unknown))

function coverageStatusLabel(status) {
  return ({
    covered: '已覆盖', partial: '部分覆盖', missing: '缺失',
    not_applicable: '不适用', unknown_confirmed: '已明确未知',
  })[status] || '未记录'
}

function fieldSource(key) {
  const entry = data.value?.field_review?.fields?.[key]
  if (entry?.source === 'ai_bulk') return { label: 'AI 整段预填 · 已核对', tone: 'ai' }
  if (entry?.source === 'ai_field_help') return { label: 'AI 字段助填 · 已核对', tone: 'ai' }
  if (entry?.source === 'manual') return { label: '人工填写', tone: 'manual' }
  return { label: '历史记录', tone: 'legacy' }
}

function formatAiMsg(text) {
  // 先转义 HTML 特殊字符再叠加安全格式，避免 v-html 渲染注入（与 ChatView 一致）
  const escaped = (text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  return escaped
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

.guided-trace-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}
.guided-trace-card {
  padding: 0.9rem;
  border: 1px solid var(--slate-200);
  border-radius: var(--radius-md);
  background: #fff;
}
.guided-trace-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
}
.guided-trace-head strong { color: var(--slate-800); font-size: 0.92rem; }
.guided-trace-head span {
  padding: 0.18rem 0.45rem;
  border-radius: 999px;
  background: var(--slate-100);
  color: var(--slate-500);
  font-size: 0.72rem;
  white-space: nowrap;
}
.guided-trace-head span.covered { color: var(--green-700); background: var(--green-50); }
.guided-trace-head span.partial,
.guided-trace-head span.unknown_confirmed { color: #816b35; background: #fff5cc; }
.trace-block-label {
  margin-top: 0.65rem;
  color: var(--slate-400);
  font-size: 0.72rem;
  font-weight: 600;
}
.trace-original,
.trace-summary {
  margin: 0.25rem 0 0;
  color: var(--slate-700);
  font-size: 0.85rem;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}
.trace-summary {
  color: var(--slate-600);
  background: var(--blue-50);
  border-radius: var(--radius-sm);
  padding: 0.55rem;
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

.source-tag {
  display: inline-block;
  white-space: nowrap;
  padding: 0.18rem 0.45rem;
  border-radius: 999px;
  font-size: 0.78rem;
  line-height: 1.3;
}
.source-tag.manual { background: var(--slate-100); color: var(--slate-600); }
.source-tag.ai { background: var(--blue-50); color: var(--blue-700); }
.source-tag.legacy { background: #f7f2e7; color: #816b35; }

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

@media (max-width: 680px) {
  .guided-trace-grid { grid-template-columns: 1fr; }
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
