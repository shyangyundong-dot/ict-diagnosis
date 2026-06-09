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

    <!-- 右侧：先展示已解析确认项，再展示待补充项（移动端为底部抽屉，DOM 共用） -->
    <div class="fields-panel" :class="{ 'drawer-open': drawerOpen }">
      <div class="drawer-handle-bar">
        <div class="drawer-handle"></div>
        <button type="button" class="drawer-close" @click="closeDrawer">✕</button>
      </div>
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

          <!-- 核算单元（#7）-->
          <section class="fields-section units-section">
            <div class="section-head">
              <span class="section-head-title">核算单元</span>
              <button class="units-segment-btn" :disabled="unitsLoading" @click="doSegmentUnits">
                {{ unitsLoading ? '切分中…' : (accountingUnits.length ? '重新切分' : 'AI 切分') }}
              </button>
            </div>
            <div class="units-hint">
              <p>把项目切分成不同的核算单元：</p>
              <ol class="units-hint-list">
                <li>设备/施工不列收</li>
                <li>重点关注「服务」单元</li>
              </ol>
              <p>AI 切分为草稿，请确认或微调。</p>
            </div>
            <div v-if="unitsLoading" class="section-parsing"><span class="parsing-dot"></span>AI 正在切分核算单元…</div>
            <div v-else-if="accountingUnits.length === 0" class="section-empty">
              尚未切分。点「AI 切分」按对话拆分核算单元，或手动添加。
            </div>
            <div v-else class="units-list">
              <div v-for="(u, idx) in accountingUnits" :key="idx" class="unit-card">
                <div class="unit-row-top">
                  <input class="unit-name" v-model="u.name" placeholder="单元名称" @change="persistUnits" />
                  <span class="unit-listed-badge" :class="listedClass(u.listed)">{{ listedLabel(u.listed) }}</span>
                  <button class="unit-del" @click="removeUnit(idx)" title="删除该单元">✕</button>
                </div>
                <div class="unit-row-fields">
                  <label>类型
                    <select v-model="u.declared_type" @change="onUnitTypeChange(u)">
                      <option v-for="t in UNIT_TYPES" :key="t" :value="t">{{ t }}</option>
                    </select>
                  </label>
                  <label>金额
                    <input v-model="u.amount" placeholder="元" @change="persistUnits" />
                  </label>
                  <label>列收
                    <select v-model="u.listed" @change="persistUnits"
                            :disabled="u.declared_type === '设备' || u.declared_type === '施工'">
                      <option :value="true">列收候选</option>
                      <option :value="false">不列收</option>
                      <option value="uncertain">待定</option>
                    </select>
                  </label>
                </div>
                <!-- 硬转服务举证字段：仅服务单元相关（引擎据 gross/logistics/has_self_capability 判嫌疑） -->
                <div v-if="u.declared_type === '服务'" class="unit-row-fields unit-row-evidence">
                  <label>毛利
                    <input v-model="u.gross" placeholder="如 8% 或 平进平出" @change="persistUnits" />
                  </label>
                  <label>物流
                    <select v-model="u.logistics" @change="persistUnits">
                      <option value="self">电信主控</option>
                      <option value="supplier_direct">供应商直发</option>
                      <option value="unknown">未知</option>
                    </select>
                  </label>
                  <label>自有能力
                    <select v-model="u.has_self_capability" @change="persistUnits">
                      <option :value="true">有</option>
                      <option :value="false">无</option>
                      <option value="unknown">未知</option>
                    </select>
                  </label>
                </div>
                <div v-if="u.reason" class="unit-reason">{{ u.reason }}</div>
              </div>
            </div>
            <button v-if="accountingUnits.length > 0 || sessionId" class="units-add-btn" @click="addUnit">＋ 添加核算单元</button>
            <p v-if="unitsSaveError" class="units-save-error">⚠ {{ unitsSaveError }}</p>
          </section>

          <!-- 控制权角色自查（总额法资格，项目级，见 docs/adr/0003）-->
          <section class="fields-section ctrl-roles-section">
            <div class="section-head">
              <span class="section-head-title">控制权角色</span>
              <span class="section-head-meta ctrl-roles-meta">总额法资格 · 自查</span>
            </div>
            <div class="ctrl-roles-hint">
              <p>电信在本项目占据哪些<strong>关键角色</strong>（决策/主导/责任）？</p>
              <p class="ctrl-roles-hint-sub">勾选标准：<strong>必选项每项都要 + 三组二选一每组至少占一个</strong> = 总额法资格成立。AI 解析不出的多需手动确认。</p>
            </div>
            <div v-for="grp in ROLE_GROUPS" :key="grp.title"
                 v-show="grp.kind !== 'mandatory_hw' || hasHardware"
                 class="ctrl-role-group" :class="`ctrl-grp-${grp.kind}`">
              <div class="ctrl-grp-title">{{ grp.title }}</div>
              <label v-for="r in grp.items" :key="r.id" class="ctrl-role-line">
                <input type="checkbox"
                       :checked="isRoleChecked(r.id)"
                       @change="toggleControlRole(r.id, $event.target.checked)" />
                <span class="ctrl-role-id">{{ r.id }}</span>
                <span class="ctrl-role-name">{{ r.name }}</span>
              </label>
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

        <div v-if="submitting && submittingHint" class="submitting-hint">{{ submittingHint }}</div>

        <div v-if="diagnosisId" class="report-actions">
          <a :href="`/report/${diagnosisId}`" target="_blank" class="report-link">
            📄 在新窗口查看报告
          </a>
          <button class="report-link pdf-link" type="button" :disabled="downloadingPdf" @click="onDownloadPdf">
            {{ downloadingPdf ? '下载中...' : '⬇️ 下载报告' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="drawerOpen" class="drawer-mask" @click="closeDrawer"></div>
    <button
      type="button"
      class="drawer-trigger"
      :class="isComplete ? 'drawer-trigger--complete' : 'drawer-trigger--incomplete'"
      @click="openDrawer"
    >
      <span v-if="isComplete">✅ 可提交诊断</span>
      <span v-else>📋 字段信息 · 待补充 {{ missingFields.length }} 项</span>
    </button>

  </div>
</template>

<script setup>
import { ref, nextTick, computed, watch, onMounted } from 'vue'
import FieldControl from '../components/FieldControl.vue'
import { sendChat, confirmDiagnosis, patchSessionFields, fetchFieldDefinitions, downloadReportPdf, segmentUnits, saveUnits } from '../api/diagnosis.js'

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
  service_capability_level: '电信自有服务能力等级（六必要，系统依据交付模式推导）',
  service_period: '服务周期',
  has_prepayment: '我方采购是否含预付款', has_advance_funding: '我方是否存在垫资',
  related_party_checked: '三方关联关系是否已核查',
}

const messages = ref([])
const inputText = ref('')
const loading = ref(false)
const submitting = ref(false)
const submittingHint = ref('')
const sessionId = ref(null)
const missingFields = ref([])
const diagnosisId = ref(null)
const downloadingPdf = ref(false)

async function onDownloadPdf() {
  if (!diagnosisId.value || downloadingPdf.value) return
  downloadingPdf.value = true
  try {
    await downloadReportPdf(diagnosisId.value)
  } catch (e) {
    alert(e.response?.data?.detail || '下载失败，请重试')
  } finally {
    downloadingPdf.value = false
  }
}
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
const drawerOpen = ref(false)

function openDrawer() { drawerOpen.value = true }
function closeDrawer() { drawerOpen.value = false }

// ── 核算单元（#7，见 docs/adr/0002）──
const accountingUnits = ref([])
const unitsLoading = ref(false)
const unitsSaveError = ref('')
const UNIT_TYPES = ['设备', '施工', '服务', '标品', '其他']

function listedLabel(v) {
  if (v === true) return '列收候选'
  if (v === false) return '不列收'
  return '待定'
}
function listedClass(v) {
  if (v === true) return 'unit-listed-yes'
  if (v === false) return 'unit-listed-no'
  return 'unit-listed-uncertain'
}

async function doSegmentUnits() {
  if (!sessionId.value || unitsLoading.value) return
  unitsLoading.value = true
  try {
    const res = await segmentUnits(sessionId.value)
    accountingUnits.value = res.data.accounting_units || []
  } catch (e) {
    alert('核算单元切分失败：' + formatApiError(e))
  } finally {
    unitsLoading.value = false
  }
}

function onUnitTypeChange(u) {
  // 硬件/施工 铁律不列收（与后端一致）
  if (u.declared_type === '设备' || u.declared_type === '施工') u.listed = false
  persistUnits()
}

function addUnit() {
  accountingUnits.value.push({
    name: '', declared_type: '服务', amount: null, tax_rate: null,
    gross: null, logistics: 'unknown', has_self_capability: 'unknown',
    listed: 'uncertain', reason: '',
  })
  persistUnits()
}

function removeUnit(idx) {
  accountingUnits.value.splice(idx, 1)
  persistUnits()
}

async function persistUnits() {
  if (!sessionId.value) return
  try {
    await saveUnits(sessionId.value, accountingUnits.value)
    unitsSaveError.value = ''
  } catch (e) {
    // 保存失败不打断填报，但要让用户看见——否则误以为已确认（编辑任意字段会再尝试）
    unitsSaveError.value = '核算单元未能保存，请检查网络后重试'
  }
}

// 独立段已经管的字段，不在「已解析」/「待补充」段重复渲染
const DEDICATED_FIELDS = new Set(['control_roles'])

const parsedFieldKeys = computed(() => {
  const missing = new Set(missingFields.value)
  const defKeys = Object.keys(fieldDefinitions.value)
  const cur = Object.keys(currentFields.value)
  const ordered = []
  for (const k of defKeys) {
    if (cur.includes(k) && !missing.has(k) && !DEDICATED_FIELDS.has(k)) ordered.push(k)
  }
  for (const k of cur) {
    if (!ordered.includes(k) && !missing.has(k) && !DEDICATED_FIELDS.has(k)) ordered.push(k)
  }
  return ordered
})

// ── 控制权角色自查（总额法资格，见 docs/adr/0003）──
const ROLE_GROUPS = [
  { title: '必选（每项都要）', kind: 'mandatory', items: [
    { id: '6', name: '应标与签约统筹者' },
    { id: '7', name: '软硬件采购决策者' },
    { id: '9', name: '全流程交付管理与质量责任者' },
  ]},
  { title: '必选 · 涉硬件时', kind: 'mandatory_hw', items: [
    { id: '16', name: '到货验收及设备管理者' },
  ]},
  { title: '方案（二选一，至少占一个）', kind: 'either_or', items: [
    { id: '3', name: '解决方案设计者' },
    { id: '4', name: '解决方案整合确定者' },
  ]},
  { title: '交付实施方案（二选一，至少占一个）', kind: 'either_or', items: [
    { id: '10', name: '交付实施方案设计者' },
    { id: '11', name: '交付实施方案确定及责任者' },
  ]},
  { title: '实施开发（二选一，至少占一个）', kind: 'either_or', items: [
    { id: '13', name: '项目实施/技术开发/联调实施者' },
    { id: '14', name: '项目实施/技术开发主导与联调实操责任者' },
  ]},
]

const hasHardware = computed(() =>
  accountingUnits.value.some(u => u.declared_type === '设备' || u.declared_type === '施工')
  || currentFields.value.hardware_construction === 'yes'
)

const controlRolesList = computed(() => {
  const v = currentFields.value.control_roles
  return Array.isArray(v) ? v.map(String) : []
})

function isRoleChecked(id) {
  return controlRolesList.value.includes(id)
}

// debounce 提交：连续勾选 N 个角色合并成 1 次 PATCH，避免并发响应乱序覆盖（review 问题 #4）
let _ctrlCommitTimer = null
function toggleControlRole(id, checked) {
  const arr = [...controlRolesList.value]
  if (checked) {
    if (!arr.includes(id)) arr.push(id)
  } else {
    const j = arr.indexOf(id)
    if (j >= 0) arr.splice(j, 1)
  }
  // 立刻更新本地（UI 即时反应），延迟 300ms 提交（连续点击只发一次 PATCH）
  currentFields.value.control_roles = arr
  if (_ctrlCommitTimer) clearTimeout(_ctrlCommitTimer)
  _ctrlCommitTimer = setTimeout(() => {
    _ctrlCommitTimer = null
    onFieldUpdate('control_roles', controlRolesList.value)
  }, 300)
}

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
  // 先转义 HTML 特殊字符，杜绝 AI 文本里的标签被 v-html 当真渲染（XSS）；
  // 再叠加我们自己的安全格式（段落 / 换行 / 加粗）。* 不转义，故 **加粗** 仍生效。
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
  submittingHint.value = 'AI 正在逐条分析风险规则，生成个性化报告…'
  const hints = [
    '正在结合项目情况生成整改建议…',
    '正在生成模式优化方向…',
    '即将完成，请稍候…',
  ]
  let hintIdx = 0
  const hintTimer = setInterval(() => {
    if (hintIdx < hints.length) {
      submittingHint.value = hints[hintIdx++]
    }
  }, 12000)
  try {
    const res = await confirmDiagnosis(sessionId.value, currentFields.value)
    diagnosisId.value = res.data.diagnosis_id
    window.open(`/report/${diagnosisId.value}`, '_blank')
  } catch (e) {
    alert(`提交失败：${formatApiError(e)}`)
  } finally {
    clearInterval(hintTimer)
    submitting.value = false
    submittingHint.value = ''
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
  drawerOpen.value = false
}
</script>

<style scoped>
.layout {
  display: flex;
  flex: 1;
  min-height: 0;
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

/* ── 核算单元（#7）── */
.units-segment-btn {
  padding: 4px 12px; border: 1px solid var(--blue-300); border-radius: 14px;
  background: var(--blue-50); color: var(--blue-700); font-size: 12px; cursor: pointer;
}
.units-segment-btn:disabled { opacity: .6; cursor: default; }
.units-hint { font-size: 12px; color: var(--slate-500); line-height: 1.55; margin: 4px 0 8px; }
.units-hint p { margin: 0; }
.units-hint-list { margin: 2px 0; padding-left: 18px; }
.units-hint-list li { margin: 1px 0; }
.units-list { display: flex; flex-direction: column; gap: 8px; }
.unit-card {
  border: 1px solid var(--slate-200); border-radius: 10px; padding: 10px 12px; background: #fff;
}
.unit-row-top { display: flex; align-items: center; gap: 8px; }
.unit-name {
  flex: 1; min-width: 0; border: none; border-bottom: 1px solid var(--slate-200);
  font-size: 13px; font-weight: 600; color: var(--slate-800); padding: 2px 0; background: transparent;
}
.unit-name:focus { outline: none; border-bottom-color: var(--blue-500); }
.unit-listed-badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; white-space: nowrap; }
.unit-listed-yes { background: #dcfce7; color: #15803d; }
.unit-listed-no { background: var(--slate-100); color: var(--slate-500); }
.unit-listed-uncertain { background: #fef3c7; color: #b45309; }
.unit-del { border: none; background: transparent; color: var(--slate-400); cursor: pointer; font-size: 13px; }
.unit-del:hover { color: #dc2626; }
.unit-row-fields { display: flex; gap: 10px; margin-top: 8px; }
.unit-row-fields label { flex: 1; display: flex; flex-direction: column; gap: 3px; font-size: 11px; color: var(--slate-500); }
.unit-row-fields select, .unit-row-fields input {
  font-size: 12px; padding: 4px 6px; border: 1px solid var(--slate-200); border-radius: 6px; color: var(--slate-800);
}
.unit-row-fields select:disabled { background: var(--slate-50); color: var(--slate-400); }
.unit-row-evidence { margin-top: 6px; padding-top: 6px; border-top: 1px dashed var(--slate-200); }
.unit-reason { font-size: 11px; color: var(--slate-500); margin-top: 6px; line-height: 1.5; }
.units-save-error { margin-top: 8px; font-size: 12px; color: var(--red-600, #dc2626); }
.units-add-btn {
  margin-top: 8px; width: 100%; padding: 6px; border: 1px dashed var(--slate-300);
  border-radius: 8px; background: transparent; color: var(--slate-500); font-size: 12px; cursor: pointer;
}
.units-add-btn:hover { border-color: var(--blue-400); color: var(--blue-600); }

/* ── 控制权角色自查（总额法资格，见 docs/adr/0003）── */
.ctrl-roles-section {}
.ctrl-roles-meta {
  font-size: 11px; color: var(--slate-500); background: var(--slate-50);
  padding: 2px 8px; border-radius: 8px; border: 1px solid var(--slate-200);
}
.ctrl-roles-hint {
  font-size: 12px; color: var(--slate-600); line-height: 1.6; margin-bottom: 10px;
}
.ctrl-roles-hint p { margin: 0 0 4px 0; }
.ctrl-roles-hint-sub { color: var(--slate-500); font-size: 11px; }
.ctrl-role-group {
  margin-bottom: 8px; padding: 8px 10px; border-radius: 6px;
}
.ctrl-grp-mandatory, .ctrl-grp-mandatory_hw {
  background: var(--slate-50); border: 1px solid var(--slate-200);
}
.ctrl-grp-either_or {
  background: transparent; border: 1px dashed var(--slate-300);
}
.ctrl-grp-title {
  font-size: 11px; font-weight: 600; color: var(--slate-500);
  margin-bottom: 6px; text-transform: none;
}
.ctrl-role-line {
  display: flex; align-items: center; gap: 8px;
  padding: 3px 0; font-size: 12px; color: var(--slate-800);
  cursor: pointer;
}
.ctrl-role-line input { accent-color: var(--blue-600); }
.ctrl-role-id {
  display: inline-block; min-width: 22px; padding: 1px 6px;
  background: var(--slate-100); color: var(--slate-700);
  border-radius: 4px; font-size: 11px; font-weight: 600; text-align: center;
}
.ctrl-role-name { flex: 1; }

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

.submitting-hint {
  font-size: 12px;
  color: var(--slate-500);
  text-align: center;
  padding: 6px 0 2px;
  line-height: 1.5;
}

.report-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}
.report-link {
  display: block;
  width: 100%;
  text-align: center;
  padding: 9px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  font-family: inherit;
  text-decoration: none;
  border: 1px solid var(--slate-200);
  color: var(--blue-600);
  background: var(--blue-50);
  transition: background 0.15s;
  cursor: pointer;
}
.report-link:disabled { opacity: 0.6; cursor: not-allowed; }
.report-link:hover { background: var(--blue-100); }
.pdf-link { color: var(--slate-600); background: var(--slate-50); }

/* ── 移动端底部抽屉（仅新增规则，不改动上方既有样式） ── */
.drawer-handle-bar {
  display: none;
}

.drawer-mask {
  display: none;
}

.drawer-trigger {
  display: none;
}

@media (max-width: 768px) {
  .layout {
    flex-direction: column;
  }

  .chat-panel {
    width: 100%;
    flex: 1;
    min-height: 0;
    border-right: none;
  }

  .fields-panel {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    width: 100% !important;
    height: 75vh;
    border-radius: 16px 16px 0 0;
    transform: translateY(100%);
    transition: transform 0.3s ease;
    z-index: 200;
    background: #fff;
    box-shadow: 0 -4px 24px rgba(0, 0, 0, 0.15);
    display: flex;
    flex-direction: column;
  }

  .fields-panel.drawer-open {
    transform: translateY(0);
  }

  .drawer-handle-bar {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 10px 16px 4px;
    flex-shrink: 0;
    position: relative;
  }

  .drawer-handle {
    width: 40px;
    height: 4px;
    background: #cbd5e1;
    border-radius: 2px;
  }

  .drawer-close {
    position: absolute;
    right: 16px;
    top: 8px;
    background: none;
    border: none;
    font-size: 18px;
    color: #94a3b8;
    cursor: pointer;
    padding: 4px 8px;
    border-radius: 6px;
  }

  .drawer-mask {
    display: block;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.4);
    z-index: 190;
  }

  .drawer-trigger {
    position: fixed;
    right: 16px;
    bottom: 90px;
    z-index: 150;
    display: block;
    border: 1.5px solid;
    border-radius: 20px;
    padding: 10px 16px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  }

  .drawer-trigger--incomplete {
    background: #fffbeb;
    border-color: #fcd34d;
    color: #92400e;
  }

  .drawer-trigger--complete {
    background: #f0fdf4;
    border-color: #86efac;
    color: #166534;
  }
}
</style>
