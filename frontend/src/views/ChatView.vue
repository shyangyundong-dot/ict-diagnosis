<template>
  <div class="layout">

    <!-- 左侧：对话区 -->
    <div class="chat-panel">
      <div class="chat-header">
        <div class="header-logo">
          <div class="logo-icon">🛡</div>
          <div>
            <div class="logo-title">ICT项目合规诊断</div>
            <div class="logo-sub">广州电信云中台</div>
          </div>
        </div>
        <div class="header-actions">
          <router-link to="/lookup" class="lookup-link">按 BPM 查历史</router-link>
          <router-link to="/trace" class="lookup-link">填报溯源</router-link>
          <button class="new-chat-btn" @click="resetChat">＋ 新建诊断</button>
        </div>
      </div>

      <!-- 消息列表 -->
      <div class="chat-messages" ref="messagesRef">
        <!-- 欢迎消息 -->
        <div v-if="messages.length === 0" class="welcome-card">
          <div class="welcome-icon">👋</div>
          <h2>你好！我是合规诊断助手</h2>
          <p>请用<strong>自然语言</strong>描述你的项目，我会逐步引导你完成信息收集，然后生成合规风险诊断报告。</p>
          <p class="welcome-example">例如："我有一个给番禺某国企做的系统集成项目，预算500万，后向供应商还没定，毛利大概4%左右..."</p>
        </div>

        <template v-for="(msg, idx) in messages" :key="idx">
          <!-- 用户消息 -->
          <div v-if="msg.role === 'user'" class="msg-row user-row">
            <div class="msg-bubble user-bubble">{{ msg.content }}</div>
            <div class="avatar user-avatar">我</div>
          </div>
          <!-- AI消息 -->
          <div v-else class="msg-row ai-row">
            <div class="avatar ai-avatar">🛡</div>
            <div class="msg-bubble ai-bubble" v-html="formatAiMsg(msg.content)"></div>
          </div>
        </template>

        <!-- 加载中 -->
        <div v-if="loading" class="msg-row ai-row">
          <div class="avatar ai-avatar">🛡</div>
          <div class="msg-bubble ai-bubble loading-bubble">
            <span class="dot"></span><span class="dot"></span><span class="dot"></span>
          </div>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="chat-input-area">
        <div v-if="isComplete" class="complete-hint">
          ✅ 信息已收集完整，请在右侧核对字段后提交；修改字段后可再次提交以生成新报告。
        </div>
        <div class="input-row">
          <textarea
            ref="inputRef"
            v-model="inputText"
            :placeholder="isComplete ? '可以继续补充说明，或直接在右侧修改字段后再次提交...' : '描述你的项目...'"
            @keydown.enter.exact.prevent="sendMessage"
            @input="adjustTextareaHeight"
            rows="1"
            class="chat-textarea"
            :disabled="loading"
          ></textarea>
          <button class="send-btn" @click="sendMessage" :disabled="loading || !inputText.trim()">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </button>
        </div>
        <div class="input-hint">Enter 发送 · Shift+Enter 换行</div>
      </div>
    </div>

    <!-- 右侧：先展示已解析确认项，再展示待补充项 -->
    <div class="fields-panel">
      <div class="fields-header">
        <div class="fields-header-text">
          <span class="fields-header-title">信息解析</span>
          <span class="fields-header-desc">发送后自动解析，请核对已确认项与待补充项</span>
        </div>
        <span class="fields-count" :class="isComplete ? 'count-done' : 'count-pending'">
          {{ isComplete ? '✅ 可提交诊断' : `待补充 ${missingFields.length} 项` }}
        </span>
      </div>

      <!-- 实时预警气泡（规格 §12.1） -->
      <div v-if="realtimeWarnings.length > 0" class="warning-panel">
        <div v-for="(w, i) in realtimeWarnings" :key="i"
             class="warning-bubble"
             :class="w.level === 'high' ? 'warning-high' : 'warning-medium'">
          {{ w.message }}
        </div>
      </div>

      <div class="fields-body">
        <div v-if="!sessionId" class="fields-empty">
          <div class="empty-icon">💬</div>
          <p>开始对话并发送后，已解析的字段会出现在下方「已解析并确认的信息」中。</p>
        </div>

        <template v-else>
          <!-- ① 已解析并确认的信息 -->
          <section class="fields-section">
            <div class="section-head">
              <span class="section-head-title">已解析并确认的信息</span>
              <span v-if="!loading && parsedFieldKeys.length > 0" class="section-head-meta">{{ parsedFieldKeys.length }} 项</span>
            </div>
            <div v-if="loading" class="section-parsing">
              <span class="parsing-dot"></span>
              正在解析本段内容…
            </div>
            <div v-if="!loading && parsedFieldKeys.length === 0 && sessionId" class="section-empty">
              尚未解析出结构化字段。请继续描述，并尽量包含
              <strong>项目类型、BPM 编号、前向客户类型、后向采购方式</strong> 等关键信息；也可在下方待补充区直接选择。
            </div>
            <div v-if="parsedFieldKeys.length > 0" class="field-list">
              <div v-for="key in parsedFieldKeys" :key="key" class="field-item"
                   :class="aiExtractedKeys.has(key) ? 'field-item-ai' : ''">
                <div class="field-label">
                  {{ getFieldLabel(key) }}
                  <span v-if="aiExtractedKeys.has(key)" class="ai-src-tag">AI 提取</span>
                </div>
                <FieldControl
                  :field-key="key"
                  :model-value="currentFields[key]"
                  :definitions="fieldDefinitions"
                  @update:model-value="(v) => onFieldUpdate(key, v)"
                />
              </div>
            </div>
          </section>

          <!-- ② 待补充信息 -->
          <section class="fields-section section-pending-block">
            <div class="section-head">
              <span class="section-head-title">待补充信息</span>
              <span
                v-if="!isComplete"
                class="section-head-meta section-head-warn"
              >{{ missingFields.length }} 项</span>
              <span v-else class="section-head-meta section-head-ok">已齐</span>
            </div>
            <div v-if="isComplete" class="pending-all-clear">
              必填项已全部收集，请核对左侧对话与上方已解析字段后，点击下方提交诊断。
            </div>
            <div v-else-if="missingFields.length > 0" class="pending-list">
              <p class="pending-intro">
                可在下方直接选择或修改；也可在左侧对话中说明，系统将自动解析。
              </p>
              <div class="pending-edit-list">
                <div v-for="f in missingFields" :key="'p-' + f" class="pending-field-row">
                  <div class="pending-label-row">{{ getFieldLabel(f) }}</div>
                  <FieldControl
                    :field-key="f"
                    :model-value="currentFields[f]"
                    :definitions="fieldDefinitions"
                    @update:model-value="(v) => onFieldUpdate(f, v)"
                  />
                </div>
              </div>
            </div>
            <div v-else-if="loading" class="section-empty subtle">
              正在根据最新对话计算待补充项…
            </div>
            <div v-else class="section-empty subtle">
              暂无待补充清单，请再发送一条消息或检查网络与 API 配置。
            </div>
          </section>
        </template>
      </div>

      <!-- 提交按钮 -->
      <div class="fields-footer">
        <button
          class="submit-btn"
          :class="{
            'submit-ready': isComplete && !submitting,
            'submit-again': isComplete && !submitting && diagnosisId,
          }"
          :disabled="!isComplete || submitting"
          @click="submitDiagnosis"
        >
          <span v-if="submitting">⏳ 诊断中...</span>
          <span v-else-if="isComplete && diagnosisId">🔄 再次提交并生成报告</span>
          <span v-else-if="isComplete">🚀 提交诊断</span>
          <span v-else>请先完成信息收集</span>
        </button>

        <div v-if="diagnosisId" class="report-actions">
          <a :href="`/report/${diagnosisId}`" target="_blank" class="report-link">
            📄 在新窗口查看报告
          </a>
          <a :href="`/api/report/${diagnosisId}/pdf`" class="report-link pdf-link">
            ⬇️ 下载报告
          </a>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, nextTick, computed, watch, onMounted } from 'vue'
import FieldControl from '../components/FieldControl.vue'
import { sendChat, confirmDiagnosis, patchSessionFields, fetchFieldDefinitions } from '../api/diagnosis.js'

const FIELD_LABELS = {
  bpm_id: 'BPM商机编号', project_type: '项目类型', customer_type: '前向客户类型',
  supplier_confirmed: '后向供应商是否已确定', procurement_method: '后向采购方式',
  related_party: '前后向关联关系', gross_margin: '毛利率估算',
  revenue_recognition: '收入确认方式', is_end_user: '客户是否为最终用户',
  has_telecom_capability: '是否有电信自有能力融入', capability_ratio: '自有能力占比',
  contract_content_same: '前后向合同内容是否一致', project_location: '项目实施地点',
  scheme_reviewed: '方案是否经过中台评审', hardware_construction: '是否含硬件/施工内容',
  logistics_control: '物流是否由电信主控',
  service_delivery_mode: '服务交付是否由电信自有团队执行',
  service_period: '服务周期',
  has_prepayment: '我方采购是否含预付款', has_advance_funding: '我方是否存在垫资',
  related_party_checked: '三方关联关系是否已核查',
}

const messages = ref([])
const inputText = ref('')
const loading = ref(false)
const submitting = ref(false)
const sessionId = ref(null)
const missingFields = ref([])
const diagnosisId = ref(null)
const fieldDefinitions = ref({})
// 实时预警（规格 §12.1）
const realtimeWarnings = ref([])
// AI 提取的字段键集合（本轮累计，用于标注来源）
const aiExtractedKeys = ref(new Set())

const isComplete = computed(
  () => sessionId.value != null && missingFields.value.length === 0
)
const currentFields = ref({})
const messagesRef = ref(null)
const inputRef = ref(null)

const parsedFieldKeys = computed(() => {
  const missing = new Set(missingFields.value)
  const defKeys = Object.keys(fieldDefinitions.value)
  const cur = Object.keys(currentFields.value)
  const ordered = []
  for (const k of defKeys) {
    if (cur.includes(k) && !missing.has(k)) ordered.push(k)
  }
  for (const k of cur) {
    if (!ordered.includes(k) && !missing.has(k)) ordered.push(k)
  }
  return ordered
})

function normalizeFieldsFromServer(f) {
  const out = { ...(f || {}) }
  if (typeof out.project_type === 'string' && out.project_type.trim()) {
    out.project_type = [out.project_type.trim()]
  }
  if (out.project_type == null || !Array.isArray(out.project_type)) {
    out.project_type = []
  }
  return out
}

const getFieldLabel = (key) => fieldDefinitions.value[key]?.label || FIELD_LABELS[key] || key

function formatApiError(e) {
  const d = e?.response?.data
  if (d == null) {
    if (e?.code === 'ECONNABORTED' || e?.message?.includes?.('timeout')) return '请求超时，请稍后重试'
    if (e?.message?.includes?.('Network Error')) return '无法连接后端（请确认本机已启动 API 服务，且 Vite 代理指向正确端口）'
    return e?.message || '未知错误'
  }
  if (typeof d.detail === 'string') return d.detail
  if (Array.isArray(d.detail)) {
    return d.detail
      .map((x) => (typeof x === 'string' ? x : x?.msg || JSON.stringify(x)))
      .join('；')
  }
  return typeof d === 'object' ? JSON.stringify(d) : String(d)
}

async function commitFieldPatch(partial) {
  Object.assign(currentFields.value, partial)
  if (!sessionId.value) return
  try {
    const res = await patchSessionFields(sessionId.value, partial)
    currentFields.value = normalizeFieldsFromServer(res.data.extracted_fields)
    missingFields.value = res.data.missing_fields || []
    // 实时预警：手动修改字段时更新
    if (res.data.realtime_warnings?.length) {
      const newWarnings = res.data.realtime_warnings
      // 合并（同字段去重，保留最新）
      const map = new Map(realtimeWarnings.value.map(w => [w.field, w]))
      for (const w of newWarnings) map.set(w.field, w)
      realtimeWarnings.value = Array.from(map.values())
    }
    // 手动修改的字段不标 AI 来源，从集合中移除
    for (const k of Object.keys(partial)) {
      const newSet = new Set(aiExtractedKeys.value)
      newSet.delete(k)
      aiExtractedKeys.value = newSet
    }
  } catch (e) {
    alert(`保存失败：${formatApiError(e)}`)
  }
}

async function onFieldUpdate(key, value) {
  await commitFieldPatch({ [key]: value })
}

function adjustTextareaHeight() {
  nextTick(() => {
    const el = inputRef.value
    if (!el) return
    el.style.height = 'auto'
    const max = 280
    el.style.height = `${Math.min(el.scrollHeight, max)}px`
  })
}

watch(inputText, () => adjustTextareaHeight())

onMounted(async () => {
  adjustTextareaHeight()
  try {
    const res = await fetchFieldDefinitions()
    fieldDefinitions.value = res.data || {}
  } catch {
    fieldDefinitions.value = {}
  }
})

function formatAiMsg(text) {
  return text
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/^/, '<p>')
    .replace(/$/, '</p>')
}

async function scrollToBottom() {
  await nextTick()
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || loading.value) return

  messages.value.push({ role: 'user', content: text })
  inputText.value = ''
  loading.value = true
  await scrollToBottom()

  try {
    const res = await sendChat(sessionId.value, text, currentFields.value)
    const data = res.data

    sessionId.value = data.session_id
    currentFields.value = normalizeFieldsFromServer(data.extracted_fields || {})
    missingFields.value = data.missing_fields || []

    // 实时预警：合并本轮新预警
    if (data.realtime_warnings?.length) {
      const map = new Map(realtimeWarnings.value.map(w => [w.field, w]))
      for (const w of data.realtime_warnings) map.set(w.field, w)
      realtimeWarnings.value = Array.from(map.values())
    }
    // 累计 AI 提取键
    if (data.ai_extracted_keys?.length) {
      const newSet = new Set(aiExtractedKeys.value)
      for (const k of data.ai_extracted_keys) newSet.add(k)
      aiExtractedKeys.value = newSet
    }

    let replyText = data.reply != null ? String(data.reply).trim() : ''
    if (!replyText) {
      replyText =
        '已收到你的描述。若此处无文字，请查看右侧「已解析并确认的信息」与「待补充信息」。'
    }
    messages.value.push({ role: 'assistant', content: replyText })
  } catch (e) {
    messages.value.push({
      role: 'assistant',
      content:
        '抱歉，请求失败或超时（长文本可能需要更久）。请稍后重试，或拆成较短几条发送。'
    })
  } finally {
    loading.value = false
    await scrollToBottom()
    adjustTextareaHeight()
  }
}

async function submitDiagnosis() {
  if (!isComplete.value || submitting.value) return
  submitting.value = true
  try {
    const res = await confirmDiagnosis(sessionId.value, currentFields.value)
    diagnosisId.value = res.data.diagnosis_id
    window.open(`/report/${diagnosisId.value}`, '_blank')
  } catch (e) {
    alert(`提交失败：${formatApiError(e)}`)
  } finally {
    submitting.value = false
  }
}

function resetChat() {
  messages.value = []
  inputText.value = ''
  loading.value = false
  submitting.value = false
  sessionId.value = null
  missingFields.value = []
  diagnosisId.value = null
  currentFields.value = {}
  realtimeWarnings.value = []
  aiExtractedKeys.value = new Set()
}
</script>

<style scoped>
.layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

/* ── 左侧对话区 ── */
.chat-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-right: 1px solid var(--slate-200);
  min-width: 0;
}

.chat-header {
  padding: 16px 20px;
  border-bottom: 1px solid var(--slate-200);
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  flex-shrink: 0;
}

.header-logo { display: flex; align-items: center; gap: 12px; }
.logo-icon { font-size: 28px; }
.logo-title { font-size: 16px; font-weight: 700; color: var(--slate-800); }
.logo-sub { font-size: 12px; color: var(--slate-400); }

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.lookup-link {
  padding: 7px 14px;
  border-radius: 20px;
  font-size: 13px;
  color: var(--blue-600);
  text-decoration: none;
  border: 1px solid var(--blue-100);
  background: var(--blue-50);
  transition: all 0.15s;
}
.lookup-link:hover {
  background: var(--blue-100);
  border-color: var(--blue-300);
}

.new-chat-btn {
  padding: 7px 16px;
  border: 1px solid var(--slate-200);
  border-radius: 20px;
  background: #fff;
  color: var(--slate-600);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}
.new-chat-btn:hover { background: var(--slate-50); border-color: var(--blue-500); color: var(--blue-600); }

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 欢迎卡 */
.welcome-card {
  background: linear-gradient(135deg, var(--blue-50) 0%, #fff 100%);
  border: 1px solid var(--blue-100);
  border-radius: var(--radius-lg);
  padding: 28px 24px;
  text-align: center;
  max-width: 500px;
  margin: 40px auto;
}
.welcome-icon { font-size: 40px; margin-bottom: 12px; }
.welcome-card h2 { font-size: 18px; font-weight: 700; color: var(--slate-800); margin-bottom: 10px; }
.welcome-card p { color: var(--slate-600); font-size: 14px; margin-bottom: 8px; }
.welcome-example {
  background: var(--slate-50);
  border-left: 3px solid var(--blue-500);
  padding: 10px 14px;
  border-radius: 0 8px 8px 0;
  text-align: left;
  font-size: 13px;
  color: var(--slate-500);
  margin-top: 12px;
}

/* 消息气泡 */
.msg-row { display: flex; align-items: flex-end; gap: 10px; }
.user-row { flex-direction: row-reverse; }
.ai-row { flex-direction: row; }

.avatar {
  width: 34px; height: 34px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; font-weight: 600;
  flex-shrink: 0;
}
.user-avatar { background: var(--blue-600); color: #fff; }
.ai-avatar { background: var(--slate-100); font-size: 18px; }

.msg-bubble {
  max-width: 75%;
  padding: 12px 16px;
  border-radius: 16px;
  font-size: 14px;
  line-height: 1.7;
}
.user-bubble {
  background: var(--blue-600);
  color: #fff;
  border-bottom-right-radius: 4px;
}
.ai-bubble {
  background: var(--slate-50);
  color: var(--slate-700);
  border: 1px solid var(--slate-200);
  border-bottom-left-radius: 4px;
}
.ai-bubble :deep(p) { margin-bottom: 6px; }
.ai-bubble :deep(p:last-child) { margin-bottom: 0; }
.ai-bubble :deep(strong) { color: var(--slate-800); }

/* 加载动画 */
.loading-bubble { padding: 14px 20px; }
.dot {
  display: inline-block;
  width: 7px; height: 7px;
  background: var(--slate-400);
  border-radius: 50%;
  margin: 0 2px;
  animation: bounce 1.2s infinite;
}
.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-6px); }
}

/* 输入区 */
.chat-input-area {
  padding: 12px 20px 16px;
  border-top: 1px solid var(--slate-200);
  background: #fff;
  flex-shrink: 0;
}
.complete-hint {
  background: var(--green-50);
  border: 1px solid var(--green-200);
  border-radius: 8px;
  padding: 8px 14px;
  font-size: 13px;
  color: var(--green-600);
  margin-bottom: 10px;
}
.input-row {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  background: var(--slate-50);
  border: 1.5px solid var(--slate-200);
  border-radius: var(--radius-md);
  padding: 10px 12px;
  transition: border-color 0.15s;
}
.input-row:focus-within { border-color: var(--blue-500); background: #fff; }

.chat-textarea {
  flex: 1;
  border: none;
  background: transparent;
  font-size: 14px;
  color: var(--slate-800);
  resize: vertical;
  min-height: 44px;
  outline: none;
  font-family: inherit;
  line-height: 1.6;
  max-height: 280px;
  overflow-y: auto;
}
.chat-textarea::placeholder { color: var(--slate-400); }

.send-btn {
  width: 36px; height: 36px;
  border-radius: 8px;
  border: none;
  background: var(--blue-600);
  color: #fff;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  transition: background 0.15s;
}
.send-btn:hover:not(:disabled) { background: var(--blue-700); }
.send-btn:disabled { background: var(--slate-300); cursor: not-allowed; }

.input-hint { font-size: 11px; color: var(--slate-400); margin-top: 6px; text-align: right; }

/* ── 右侧字段面板 ── */
.fields-panel {
  width: 400px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--slate-50);
  border-left: 1px solid var(--slate-200);
}

.fields-header {
  padding: 14px 16px;
  border-bottom: 1px solid var(--slate-200);
  background: #fff;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-shrink: 0;
}
.fields-header-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.fields-header-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--slate-800);
}
.fields-header-desc {
  font-size: 11px;
  font-weight: 400;
  color: var(--slate-500);
  line-height: 1.35;
}

.fields-count {
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 20px;
  font-weight: 500;
}
.count-done { background: var(--green-50); color: var(--green-600); border: 1px solid var(--green-200); }
.count-pending { background: var(--yellow-50); color: var(--yellow-600); border: 1px solid var(--yellow-200); }

.fields-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.fields-empty {
  text-align: center;
  padding: 40px 20px;
  color: var(--slate-400);
}
.empty-icon { font-size: 36px; margin-bottom: 12px; }
.fields-empty p { font-size: 13px; }

.fields-section {
  background: #fff;
  border: 1px solid var(--slate-200);
  border-radius: var(--radius-md);
  padding: 12px 12px 14px;
}
.section-pending-block {
  background: var(--slate-50);
}
.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--slate-100);
}
.section-head-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--slate-800);
}
.section-head-meta {
  font-size: 11px;
  color: var(--slate-500);
  font-weight: 500;
}
.section-head-warn {
  color: var(--yellow-700);
  background: var(--yellow-50);
  padding: 2px 8px;
  border-radius: 10px;
  border: 1px solid var(--yellow-200);
}
.section-head-ok {
  color: var(--green-700);
  background: var(--green-50);
  padding: 2px 8px;
  border-radius: 10px;
  border: 1px solid var(--green-200);
}

.section-parsing {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--blue-600);
  padding: 8px 10px;
  background: var(--blue-50);
  border-radius: var(--radius-sm);
  margin-bottom: 8px;
}
.parsing-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--blue-500);
  animation: pulse-dot 1s ease-in-out infinite;
}
@keyframes pulse-dot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.85); }
}

.section-empty {
  font-size: 13px;
  color: var(--slate-600);
  line-height: 1.65;
  padding: 4px 2px;
}
.section-empty strong { color: var(--slate-900); }
.section-empty.subtle { color: var(--slate-500); font-size: 12px; }

.field-list {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.pending-all-clear {
  font-size: 13px;
  color: var(--green-800);
  line-height: 1.6;
  padding: 8px 10px;
  background: var(--green-50);
  border: 1px solid var(--green-200);
  border-radius: var(--radius-sm);
}
.pending-intro {
  font-size: 12px;
  color: var(--slate-600);
  margin-bottom: 8px;
}
.pending-ul {
  margin: 0;
  padding: 0 0 0 4px;
  list-style: none;
}
.pending-li {
  position: relative;
  padding: 6px 0 6px 18px;
  font-size: 13px;
  color: var(--slate-800);
  border-bottom: 1px dashed var(--slate-200);
}
.pending-li:last-child { border-bottom: none; }
.pending-li::before {
  content: '○';
  position: absolute;
  left: 0;
  color: var(--amber-500);
  font-size: 12px;
  top: 6px;
}
.pending-label { font-weight: 500; }

.pending-edit-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.pending-field-row {
  padding: 10px 12px;
  background: #fff;
  border: 1px solid var(--slate-200);
  border-radius: var(--radius-sm);
}
.pending-label-row {
  font-size: 12px;
  font-weight: 600;
  color: var(--slate-700);
  margin-bottom: 8px;
}

.field-item {
  background: var(--slate-50);
  border: 1px solid var(--slate-200);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
  margin-bottom: 8px;
}
.field-item:last-child { margin-bottom: 0; }
.field-item-ai {
  border-color: #bfdbfe;
  background: #eff6ff;
}
.field-label {
  font-size: 11px;
  color: var(--slate-400);
  margin-bottom: 3px;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 6px;
}
.field-value { font-size: 14px; color: var(--slate-800); font-weight: 500; }

/* AI 来源标注（规格 §12.1） */
.ai-src-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  background: #dbeafe;
  color: #1d4ed8;
  font-weight: 500;
  white-space: nowrap;
}

/* 实时预警气泡（规格 §12.1） */
.warning-panel {
  padding: 8px 14px;
  border-bottom: 1px solid var(--slate-200);
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: #fff;
  flex-shrink: 0;
}
.warning-bubble {
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 12px;
  line-height: 1.6;
}
.warning-high {
  background: #fef2f2;
  border: 1px solid #fca5a5;
  color: #991b1b;
}
.warning-medium {
  background: #fffbeb;
  border: 1px solid #fcd34d;
  color: #92400e;
}

/* 提交区 */
.fields-footer {
  padding: 16px;
  border-top: 1px solid var(--slate-200);
  background: #fff;
  flex-shrink: 0;
}

.submit-btn {
  width: 100%;
  padding: 13px;
  border-radius: var(--radius-md);
  border: none;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  background: var(--slate-200);
  color: var(--slate-400);
}
.submit-ready {
  background: linear-gradient(135deg, var(--blue-600), var(--blue-700));
  color: #fff;
  box-shadow: 0 4px 12px rgba(37,99,235,0.3);
}
.submit-ready:hover { transform: translateY(-1px); box-shadow: 0 6px 16px rgba(37,99,235,0.35); }
.submit-again {
  background: linear-gradient(135deg, #0d9488, #0f766e);
  color: #fff;
  box-shadow: 0 4px 12px rgba(13,148,136,0.28);
}
.submit-again:hover { transform: translateY(-1px); box-shadow: 0 6px 16px rgba(13,148,136,0.35); }

.report-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}
.report-link {
  display: block;
  text-align: center;
  padding: 9px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  text-decoration: none;
  border: 1px solid var(--slate-200);
  color: var(--blue-600);
  background: var(--blue-50);
  transition: background 0.15s;
}
.report-link:hover { background: var(--blue-100); }
.pdf-link { color: var(--slate-600); background: var(--slate-50); }
</style>
