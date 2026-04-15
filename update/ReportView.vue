<template>
  <div class="report-page">

    <!-- 顶栏 -->
    <div class="topbar">
      <div class="topbar-left">
        <a href="/" class="back-btn">← 返回诊断</a>
        <span class="topbar-title">ICT项目合规诊断报告</span>
      </div>
      <div class="topbar-actions">
        <a :href="`/api/report/${diagnosisId}/pdf`" class="action-btn pdf-btn">⬇ 下载报告</a>
        <button class="action-btn share-btn" @click="copyLink">{{ copied ? '✅ 已复制' : '🔗 复制链接' }}</button>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="loading-screen">
      <div class="spinner"></div>
      <p>正在加载报告...</p>
    </div>

    <!-- 错误 -->
    <div v-else-if="error" class="error-screen">
      <div class="error-icon">⚠️</div>
      <p>{{ error }}</p>
      <a href="/" class="back-link">返回首页</a>
    </div>

    <!-- 报告内容 -->
    <div v-else class="report-content">

      <!-- 报告头 -->
      <div class="report-header">
        <div class="header-meta">
          <span>📋 商机编号：<strong>{{ data.bpm_id }}</strong></span>
          <span>🕐 {{ data.created_at }}</span>
          <span class="version-tag">规则版本 {{ data.rule_version }}</span>
        </div>
        <h1>合规诊断报告</h1>
        <p class="header-sub">广州电信政企事业部 · ICT项目合规智能诊断工具</p>
      </div>

      <!-- 总体结论 -->
      <div class="overall-card" :class="`risk-${data.overall_risk}`">
        <div class="overall-left">
          <div class="risk-icon">{{ riskConfig[data.overall_risk]?.icon }}</div>
          <div>
            <div class="risk-label">{{ riskConfig[data.overall_risk]?.label }}</div>
            <div class="risk-count">
              触发 <strong>{{ data.triggered_rules?.length || 0 }}</strong> 条风险规则 ·
              <strong>{{ data.tips?.length || 0 }}</strong> 条操作提示
            </div>
          </div>
        </div>
        <div class="overall-notice">
          ⚠️ 以上结论为风险等级提示，不作为项目列收的最终依据，不替代人工审核与BPM审批流程。最终决策由审核人员做出。
        </div>
      </div>

      <!-- 风险规则详情 -->
      <div v-if="data.triggered_rules?.length > 0">
        <div class="section-heading">风险详情分析</div>

        <div v-for="rule in data.triggered_rules" :key="rule.rule_id" class="rule-card">
          <!-- 高风险子类型横幅 -->
          <div v-if="rule.risk_level === 'high' && rule.high_risk_type"
               class="hrt-banner"
               :class="`hrt-${rule.high_risk_type}`">
            <span class="hrt-label">{{ hrtConfig[rule.high_risk_type]?.label }}</span>
            <span class="hrt-desc">{{ hrtConfig[rule.high_risk_type]?.desc }}</span>
          </div>

          <!-- 卡片头 -->
          <div class="rule-card-header" @click="toggleRule(rule.rule_id)">
            <div class="rule-card-left">
              <span class="risk-badge" :class="`badge-${rule.risk_level}`">
                {{ riskConfig[rule.risk_level]?.icon }} {{ riskConfig[rule.risk_level]?.label }}
              </span>
              <span class="rule-code">{{ rule.rule_id }}</span>
              <span class="rule-title">{{ rule.rule_name }}</span>
            </div>
            <span class="toggle-icon">{{ expanded[rule.rule_id] ? '▲' : '▼' }}</span>
          </div>

          <!-- 展开内容 -->
          <transition name="slide">
            <div v-if="expanded[rule.rule_id]" class="rule-card-body">

              <!-- ① 风险描述 -->
              <div class="rule-section">
                <div class="rule-section-title">⚠️ 风险描述</div>
                <div class="rule-section-body">{{ rule.risk_description }}</div>
              </div>

              <!-- ② 整改建议 -->
              <div class="rule-section highlight-section">
                <div class="rule-section-title">🔧 整改建议</div>
                <div class="rule-section-body">{{ rule.remediation }}</div>
              </div>

              <!-- ③ 条款原文 -->
              <div class="rule-section">
                <div class="rule-section-title">📖 条款依据</div>
                <div v-if="rule.clause_sources?.length > 0">
                  <div v-for="(src, si) in rule.clause_sources" :key="si" class="clause-block">
                    <div class="clause-source-name">
                      {{ src.doc_name }}
                      <span v-if="src.doc_code && !src.doc_code.includes('【')" class="clause-code">{{ src.doc_code }}</span>
                    </div>
                    <div class="clause-text">{{ src.text }}</div>
                  </div>
                </div>
                <div v-else class="no-clause">暂无条款原文</div>
              </div>

              <!-- ④ 模式优化 -->
              <div class="rule-section optimize-section">
                <div class="rule-section-title">🚀 模式优化方向</div>
                <div class="rule-section-body">{{ rule.optimization_direction }}</div>
              </div>

              <!-- 本条审计材料 -->
              <div v-if="rule.audit_materials?.length > 0" class="rule-section">
                <div class="rule-section-title">📂 本风险点相关审计材料</div>
                <div v-for="mat in rule.audit_materials" :key="mat.item" class="mini-mat-item">
                  <span class="mat-checkbox">☐</span>
                  <div>
                    <strong>{{ mat.item }}</strong>
                    <span class="mat-purpose"> — {{ mat.purpose }}</span>
                  </div>
                </div>
              </div>

            </div>
          </transition>
        </div>
      </div>

      <!-- 无风险提示 -->
      <div v-else class="no-risk-card">
        <div class="no-risk-icon">✅</div>
        <div>
          <strong>当前填报信息未触发任何风险规则</strong>
          <p>建议继续保持过程留痕，确保审计可追溯。</p>
        </div>
      </div>

      <!-- 操作提示 -->
      <div v-if="data.tips?.length > 0">
        <div class="section-heading">操作提示 <span class="heading-sub">（不计入风险等级）</span></div>
        <div v-for="tip in data.tips" :key="tip.rule_id" class="tip-card">
          <div class="tip-header">
            <span class="tip-badge">📋 操作提示</span>
            <span class="rule-code">{{ tip.rule_id }}</span>
            <span class="rule-title">{{ tip.rule_name }}</span>
          </div>
          <div class="tip-body">{{ tip.remediation }}</div>
        </div>
      </div>

      <!-- 审计材料总清单 -->
      <div class="section-heading">审计资料必备清单</div>
      <div class="checklist-card">
        <div v-if="data.audit_checklist?.length > 0">
          <div v-for="mat in data.audit_checklist" :key="mat.item" class="checklist-item">
            <input type="checkbox" class="mat-check" :id="`mat-${mat.item}`">
            <label :for="`mat-${mat.item}`">
              <strong>{{ mat.item }}</strong>
              <span class="mat-purpose">{{ mat.purpose }}</span>
            </label>
          </div>
        </div>
        <div v-else class="no-mat">无需特别准备，保持常规过程留痕即可。</div>
      </div>

      <!-- 免责声明 -->
      <div class="disclaimer">
        <strong>免责声明：</strong>本工具诊断结论为风险等级提示，仅供参考，不作为项目列收的正式依据，不替代BPM审批流程。工具基于用户填报信息进行判断，信息失真将导致诊断结论失效。条款原文库存在更新时滞，具体认定以集团/省公司最新文件为准。
        <br>本结论基于规则版本 <strong>{{ data.rule_version }}</strong> 生成。
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { getDiagnosis } from '../api/diagnosis.js'

const route = useRoute()
const diagnosisId = route.params.id

const loading = ref(true)
const error = ref(null)
const data = ref({})
const copied = ref(false)
const expanded = reactive({})

const hrtConfig = {
  forbidden:       { label: '🚫 禁止做',       desc: '该项目不符合合规条件，不得推进' },
  no_revenue:      { label: '❌ 不可列收',      desc: '该部分收入不得列入，需调整收入归属或采用差额处理' },
  no_full_revenue: { label: '⚠️ 不可全额列收', desc: '不满足全额列收条件，须采用差额法或经财务负责人审批' },
}

const riskConfig = {
  high:   { label: '高风险', icon: '🔴', class: 'risk-high' },
  medium: { label: '中风险', icon: '🟡', class: 'risk-medium' },
  low:    { label: '低风险', icon: '🟢', class: 'risk-low' },
  tip:    { label: '操作提示', icon: '📋', class: 'risk-tip' },
}

function toggleRule(ruleId) {
  expanded[ruleId] = !expanded[ruleId]
}

function copyLink() {
  navigator.clipboard.writeText(window.location.href)
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}

onMounted(async () => {
  try {
    const res = await getDiagnosis(diagnosisId)
    data.value = res.data
    // 默认展开所有高风险
    for (const rule of (data.value.triggered_rules || [])) {
      expanded[rule.rule_id] = rule.risk_level === 'high'
    }
  } catch (e) {
    error.value = '报告加载失败，请确认报告编号是否正确。'
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.report-page {
  min-height: 100vh;
  background: var(--slate-100);
}

/* 顶栏 */
.topbar {
  position: sticky;
  top: 0;
  z-index: 100;
  background: #fff;
  border-bottom: 1px solid var(--slate-200);
  padding: 12px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: var(--shadow-sm);
}
.topbar-left { display: flex; align-items: center; gap: 16px; }
.back-btn {
  font-size: 13px;
  color: var(--blue-600);
  text-decoration: none;
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid var(--blue-100);
  background: var(--blue-50);
  transition: background 0.15s;
}
.back-btn:hover { background: var(--blue-100); }
.topbar-title { font-size: 15px; font-weight: 600; color: var(--slate-700); }
.topbar-actions { display: flex; gap: 10px; }
.action-btn {
  padding: 7px 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  text-decoration: none;
  border: 1px solid var(--slate-200);
  background: #fff;
  color: var(--slate-600);
  transition: all 0.15s;
}
.action-btn:hover { background: var(--slate-50); }
.pdf-btn { color: var(--blue-600); border-color: var(--blue-200); background: var(--blue-50); }

/* 加载/错误 */
.loading-screen, .error-screen {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  height: 60vh; gap: 16px; color: var(--slate-500);
}
.spinner {
  width: 36px; height: 36px;
  border: 3px solid var(--slate-200);
  border-top-color: var(--blue-600);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.error-icon { font-size: 40px; }
.back-link { color: var(--blue-600); text-decoration: underline; font-size: 14px; }

/* 报告主体 */
.report-content { max-width: 860px; margin: 0 auto; padding: 28px 20px 80px; }

/* 报告头 */
.report-header {
  background: linear-gradient(135deg, #1e40af 0%, #1d4ed8 60%, #2563eb 100%);
  border-radius: var(--radius-lg);
  padding: 28px 32px;
  color: #fff;
  margin-bottom: 20px;
}
.header-meta {
  display: flex; gap: 20px; flex-wrap: wrap;
  font-size: 13px; opacity: 0.8; margin-bottom: 10px;
}
.version-tag { font-family: monospace; }
.report-header h1 { font-size: 24px; font-weight: 800; margin-bottom: 4px; }
.header-sub { font-size: 13px; opacity: 0.7; }

/* 总体结论 */
.overall-card {
  border-radius: var(--radius-lg);
  padding: 24px 28px;
  margin-bottom: 24px;
  border: 2px solid;
}
.overall-card.risk-high { background: #fef2f2; border-color: #fca5a5; }
.overall-card.risk-medium { background: #fffbeb; border-color: #fcd34d; }
.overall-card.risk-low { background: #f0fdf4; border-color: #86efac; }
.overall-left { display: flex; align-items: center; gap: 20px; margin-bottom: 14px; }
.risk-icon { font-size: 48px; line-height: 1; }
.risk-label {
  font-size: 26px; font-weight: 800;
}
.risk-high .risk-label { color: #dc2626; }
.risk-medium .risk-label { color: #d97706; }
.risk-low .risk-label { color: #16a34a; }
.risk-count { font-size: 14px; color: var(--slate-600); margin-top: 4px; }
.overall-notice {
  background: #fff7ed;
  border: 1px solid #fed7aa;
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 12px;
  color: #92400e;
}

/* 区块标题 */
.section-heading {
  font-size: 16px; font-weight: 700;
  color: var(--slate-800);
  margin: 28px 0 14px;
  padding-left: 12px;
  border-left: 4px solid var(--blue-600);
  display: flex; align-items: center; gap: 8px;
}
.heading-sub { font-size: 12px; font-weight: 400; color: var(--slate-400); }

/* 高风险子类型横幅 */
.hrt-banner {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 20px;
  font-size: 13px;
  border-bottom: 1px solid rgba(0,0,0,0.15);
}
.hrt-label {
  font-weight: 800;
  font-size: 14px;
  white-space: nowrap;
  letter-spacing: 0.02em;
}
.hrt-desc {
  font-size: 12px;
  opacity: 0.88;
}
.hrt-forbidden       { background: #450a0a; color: #fff; }
.hrt-no_revenue      { background: #7c2d12; color: #fff; }
.hrt-no_full_revenue { background: #78350f; color: #fff; }

/* 规则卡片 */
.rule-card {
  background: #fff;
  border: 1px solid var(--slate-200);
  border-radius: var(--radius-md);
  margin-bottom: 12px;
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}
.rule-card-header {
  padding: 14px 20px;
  background: var(--slate-50);
  border-bottom: 1px solid var(--slate-200);
  display: flex; align-items: center; justify-content: space-between;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s;
}
.rule-card-header:hover { background: var(--slate-100); }
.rule-card-left { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.risk-badge {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 20px;
  color: #fff;
  font-size: 12px; font-weight: 600;
}
.badge-high { background: #dc2626; }
.badge-medium { background: #d97706; }
.badge-low { background: #16a34a; }
.rule-code { font-size: 12px; color: var(--slate-400); font-family: monospace; }
.rule-title { font-size: 15px; font-weight: 600; color: var(--slate-800); }
.toggle-icon { color: var(--slate-400); font-size: 12px; }

/* 规则卡片体 */
.rule-card-body { border-top: 1px solid var(--slate-100); }
.rule-section {
  padding: 16px 20px;
  border-bottom: 1px solid var(--slate-100);
}
.rule-section:last-child { border-bottom: none; }
.rule-section-title {
  font-size: 11px; font-weight: 700;
  color: var(--slate-400);
  text-transform: uppercase; letter-spacing: 0.06em;
  margin-bottom: 8px;
}
.rule-section-body { font-size: 14px; color: var(--slate-700); line-height: 1.8; white-space: pre-wrap; }

.highlight-section { background: #fffbeb; }
.optimize-section { background: #f0fdf4; }

/* 条款原文 */
.clause-block { margin-bottom: 12px; }
.clause-block:last-child { margin-bottom: 0; }
.clause-source-name { font-size: 12px; color: var(--blue-600); font-weight: 600; margin-bottom: 6px; }
.clause-code { margin-left: 8px; color: var(--slate-400); font-family: monospace; font-size: 11px; }
.clause-text {
  background: var(--slate-50);
  border-left: 3px solid var(--slate-300);
  padding: 10px 14px;
  border-radius: 0 8px 8px 0;
  font-size: 13px; color: var(--slate-600); line-height: 1.8;
}
.no-clause { font-size: 13px; color: var(--slate-400); font-style: italic; }

/* 小审计材料 */
.mini-mat-item {
  display: flex; gap: 8px; align-items: flex-start;
  padding: 6px 0;
  font-size: 13px; color: var(--slate-700);
  border-bottom: 1px solid var(--slate-100);
}
.mini-mat-item:last-child { border-bottom: none; }
.mat-checkbox { color: var(--slate-400); flex-shrink: 0; }
.mat-purpose { color: var(--slate-400); font-size: 12px; margin-left: 4px; }

/* 操作提示 */
.tip-card {
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-left: 4px solid var(--blue-600);
  border-radius: var(--radius-md);
  margin-bottom: 10px;
  overflow: hidden;
}
.tip-header {
  padding: 12px 16px;
  display: flex; align-items: center; gap: 8px;
  border-bottom: 1px solid #bfdbfe;
  background: #dbeafe;
}
.tip-badge {
  background: var(--blue-600); color: #fff;
  font-size: 12px; font-weight: 600;
  padding: 2px 8px; border-radius: 20px;
}
.tip-body { padding: 14px 16px; font-size: 14px; color: var(--slate-700); line-height: 1.8; }

/* 无风险 */
.no-risk-card {
  background: var(--green-50);
  border: 1px solid var(--green-200);
  border-radius: var(--radius-md);
  padding: 20px 24px;
  display: flex; align-items: center; gap: 16px;
  margin-bottom: 24px;
}
.no-risk-icon { font-size: 32px; }
.no-risk-card p { font-size: 13px; color: var(--slate-600); margin-top: 4px; }

/* 审计清单 */
.checklist-card {
  background: #fff;
  border: 1px solid var(--slate-200);
  border-radius: var(--radius-md);
  padding: 6px 20px;
  box-shadow: var(--shadow-sm);
}
.checklist-item {
  display: flex; align-items: flex-start; gap: 12px;
  padding: 12px 0;
  border-bottom: 1px solid var(--slate-100);
}
.checklist-item:last-child { border-bottom: none; }
.mat-check { margin-top: 3px; width: 16px; height: 16px; flex-shrink: 0; cursor: pointer; }
.checklist-item label { font-size: 14px; color: var(--slate-700); cursor: pointer; line-height: 1.6; }
.checklist-item label .mat-purpose { display: block; font-size: 12px; color: var(--slate-400); margin-top: 2px; }
.no-mat { padding: 16px 0; color: var(--slate-400); font-size: 14px; }

/* 免责声明 */
.disclaimer {
  margin-top: 32px;
  background: var(--slate-50);
  border: 1px solid var(--slate-200);
  border-radius: var(--radius-sm);
  padding: 14px 18px;
  font-size: 12px;
  color: var(--slate-400);
  line-height: 1.8;
}

/* 展开动画 */
.slide-enter-active, .slide-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}
.slide-enter-from, .slide-leave-to { max-height: 0; opacity: 0; }
.slide-enter-to, .slide-leave-from { max-height: 2000px; opacity: 1; }
</style>
