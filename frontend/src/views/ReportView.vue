<template>
  <div class="report-page">

    <!-- 顶栏 -->
    <div class="topbar">
      <div class="topbar-left">
        <a href="/" class="back-btn">← 返回诊断</a>
        <span class="topbar-title">ICT项目合规诊断报告</span>
        <span v-if="data.ai_enriched" class="ai-badge">✨ AI个性化分析</span>
        <span v-if="data.is_mixed_project" class="mixed-badge">📦 混合型项目</span>
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
        <p class="header-sub">广州电信云中台 · ICT项目合规智能诊断工具</p>
      </div>

      <!-- 总体结论 -->
      <div class="overall-card" :class="`risk-${data.overall_risk}`">
        <div class="overall-left">
          <div class="risk-icon">{{ riskConfig[data.overall_risk]?.icon }}</div>
          <div>
            <div class="risk-label">{{ riskConfig[data.overall_risk]?.label }}</div>
            <div class="risk-count">
              触发 <strong>{{ totalTriggered }}</strong> 条风险规则 ·
              <strong>{{ totalTips }}</strong> 条操作提示
              <span v-if="data.is_mixed_project" class="mixed-note">· 已按业务板块分节分析</span>
            </div>
          </div>
        </div>
        <div class="overall-notice">
          ⚠️ 以上结论为风险等级提示，不作为项目列收的最终依据，不替代人工审核与BPM审批流程。最终决策由审核人员做出。
        </div>
      </div>

      <!-- ===== 分段模式（AI丰富化成功）===== -->
      <template v-if="data.segments && data.segments.length">
        <div class="section-heading">风险详情分析
          <span v-if="data.ai_enriched" class="heading-ai-tag">✨ AI个性化</span>
        </div>

        <div v-for="seg in data.segments" :key="seg.segment_id" class="segment-block">

          <!-- 操作提示板块 -->
          <template v-if="seg.segment_id === 'tips'">
            <div v-if="seg.tips && seg.tips.length">
              <div class="section-heading tips-heading">
                操作提示 <span class="heading-sub">（不计入风险等级）</span>
              </div>
              <div v-for="tip in seg.tips" :key="tip.rule_id" class="tip-card">
                <div class="tip-header">
                  <span class="tip-badge">📋 操作提示</span>
                  <span class="rule-code">{{ tip.rule_id }}</span>
                  <span class="rule-title">{{ tip.rule_name }}</span>
                </div>
                <div class="tip-body">{{ tip.ai_remediation || tip.remediation }}</div>
              </div>
            </div>
          </template>

          <!-- 普通业务板块 -->
          <template v-else>
            <div class="segment-header">
              <span class="segment-icon">📦</span>
              <span class="segment-title">{{ seg.segment_label }}</span>
              <span v-if="seg.triggered_rules?.length" class="segment-count">
                {{ seg.triggered_rules.length }} 条风险
              </span>
              <span v-else class="segment-ok-badge">✅ 无风险</span>
            </div>

            <!-- 板块总述 -->
            <div v-if="seg.overview" class="segment-overview">
              {{ seg.overview }}
            </div>

            <!-- 板块无风险 -->
            <div v-if="!seg.triggered_rules?.length" class="segment-empty">
              该业务板块未触发风险规则，请保持过程留痕。
            </div>

            <!-- 板块规则列表（与后端 HTML 报告同结构的浅灰底容器） -->
            <div v-else class="segment-rules-container">
            <div v-for="rule in seg.triggered_rules" :key="rule.rule_id" class="rule-card">
              <!-- 高风险子类型横幅 -->
              <div v-if="rule.risk_level === 'high' && rule.high_risk_type"
                   class="hrt-banner"
                   :class="`hrt-${rule.high_risk_type}`">
                <span class="hrt-label">{{ hrtConfig[rule.high_risk_type]?.label }}</span>
                <span class="hrt-desc">{{ hrtConfig[rule.high_risk_type]?.desc }}</span>
              </div>

              <!-- 卡片头 -->
              <div class="rule-card-header" @click="toggleRule(rule.rule_id + seg.segment_id)">
                <div class="rule-card-left">
                  <span class="risk-badge" :class="`badge-${rule.risk_level}`">
                    {{ riskConfig[rule.risk_level]?.icon }} {{ riskConfig[rule.risk_level]?.label }}
                  </span>
                  <span class="rule-code">{{ rule.rule_id }}</span>
                  <span class="rule-title">{{ rule.rule_name }}</span>
                  <span v-if="data.ai_enriched && rule.ai_risk_analysis" class="ai-inline-tag">✨ AI个性化分析</span>
                </div>
                <span class="toggle-icon">{{ expanded[rule.rule_id + seg.segment_id] ? '▲' : '▼' }}</span>
              </div>

              <!-- 展开内容 -->
              <transition name="slide">
                <div v-if="expanded[rule.rule_id + seg.segment_id]" class="rule-card-body">
                  <RuleBody :rule="rule" />
                </div>
              </transition>
            </div>
            </div>
          </template>
        </div>
      </template>

      <!-- ===== 降级模式（无segments，平铺渲染）===== -->
      <template v-else>
        <div v-if="data.triggered_rules?.length">
          <div class="section-heading">风险详情分析
            <span v-if="data.ai_enriched" class="heading-ai-tag">✨ AI个性化</span>
          </div>
          <div v-for="rule in data.triggered_rules" :key="rule.rule_id" class="rule-card">
            <div v-if="rule.risk_level === 'high' && rule.high_risk_type"
                 class="hrt-banner" :class="`hrt-${rule.high_risk_type}`">
              <span class="hrt-label">{{ hrtConfig[rule.high_risk_type]?.label }}</span>
              <span class="hrt-desc">{{ hrtConfig[rule.high_risk_type]?.desc }}</span>
            </div>
            <div class="rule-card-header" @click="toggleRule(rule.rule_id)">
              <div class="rule-card-left">
                <span class="risk-badge" :class="`badge-${rule.risk_level}`">
                  {{ riskConfig[rule.risk_level]?.icon }} {{ riskConfig[rule.risk_level]?.label }}
                </span>
                <span class="rule-code">{{ rule.rule_id }}</span>
                <span class="rule-title">{{ rule.rule_name }}</span>
                <span v-if="data.ai_enriched && rule.ai_risk_analysis" class="ai-inline-tag">✨ AI个性化分析</span>
              </div>
              <span class="toggle-icon">{{ expanded[rule.rule_id] ? '▲' : '▼' }}</span>
            </div>
            <transition name="slide">
              <div v-if="expanded[rule.rule_id]" class="rule-card-body">
                <RuleBody :rule="rule" />
              </div>
            </transition>
          </div>
        </div>
        <div v-else class="no-risk-card">
          <div class="no-risk-icon">✅</div>
          <div>
            <strong>当前填报信息未触发任何风险规则</strong>
            <p>建议继续保持过程留痕，确保审计可追溯。</p>
          </div>
        </div>

        <!-- 降级模式操作提示 -->
        <div v-if="data.tips?.length">
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
      </template>

      <!-- 审计材料总清单 -->
      <div class="section-heading">审计资料必备清单</div>
      <div class="checklist-card">
        <div v-if="data.audit_checklist?.length">
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
        <span v-if="data.ai_enriched"> AI个性化分析由 DeepSeek V3 生成，仅供参考。</span>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, defineComponent, h } from 'vue'
import { useRoute } from 'vue-router'
import { getDiagnosis } from '../api/diagnosis.js'

// ── 规则体子组件（内联定义，避免单独文件）──
const RuleBody = defineComponent({
  props: { rule: Object },
  setup(props) {
    return () => h('div', null, [
      // ① 风险分析
      h('div', { class: 'rule-section' }, [
        h('div', { class: 'rule-section-title' }, '⚠️ 风险分析'),
        h('div', { class: 'rule-section-body' },
          props.rule.ai_risk_analysis || props.rule.risk_description || '')
      ]),
      // ② 整改建议（高亮）
      h('div', { class: 'rule-section highlight-section' }, [
        h('div', { class: 'rule-section-title' }, '🔧 整改建议'),
        h('div', { class: 'rule-section-body' },
          props.rule.ai_remediation || props.rule.remediation || '')
      ]),
      // ③ 条款依据
      h('div', { class: 'rule-section' }, [
        h('div', { class: 'rule-section-title' }, '📖 条款依据'),
        ...(props.rule.clause_sources?.length
          ? props.rule.clause_sources.map(src =>
              h('div', { class: 'clause-block' }, [
                h('div', { class: 'clause-source-name' }, [
                  '📄 ',
                  src.doc_name,
                  src.doc_code && !src.doc_code.includes('【')
                    ? h('span', { class: 'clause-code' }, `（${src.doc_code}）`)
                    : null
                ]),
                h('div', { class: 'clause-text' }, src.text || '')
              ])
            )
          : [h('div', { class: 'no-clause' }, '暂无条款原文')]
        )
      ]),
      // ④ 模式优化
      h('div', { class: 'rule-section optimize-section' }, [
        h('div', { class: 'rule-section-title' }, '🚀 模式优化方向'),
        h('div', { class: 'rule-section-body' },
          props.rule.ai_optimization || props.rule.optimization_direction || '')
      ]),
      // ⑤ 审计材料（版式与后端 HTML / 条款引用框一致）
      ...(props.rule.audit_materials?.length ? [
        h('div', { class: 'rule-section audit-materials-section' }, [
          h('div', { class: 'rule-section-title' }, '📁 本风险点相关审计材料'),
          h('div', { class: 'audit-mats' },
            props.rule.audit_materials.map((mat) =>
              h('div', { class: 'audit-item' }, [
                h('span', { class: 'audit-check' }, '☐'),
                h('div', { class: 'audit-item-main' }, [
                  h('strong', null, mat.item),
                  h('span', { class: 'audit-sep' }, ' — '),
                  h('span', { class: 'audit-purpose' }, mat.purpose)
                ])
              ])
            )
          )
        ])
      ] : [])
    ])
  }
})

// ── 主组件逻辑 ──
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
  high:   { label: '高风险', icon: '🔴' },
  medium: { label: '中风险', icon: '🟡' },
  low:    { label: '低风险', icon: '🟢' },
  tip:    { label: '操作提示', icon: '📋' },
}

// 计算总风险条数（支持segments和平铺两种数据结构）
const totalTriggered = computed(() => {
  if (data.value.segments) {
    return data.value.segments
      .filter(s => s.segment_id !== 'tips')
      .reduce((sum, s) => sum + (s.triggered_rules?.length || 0), 0)
  }
  return data.value.triggered_rules?.length || 0
})

const totalTips = computed(() => {
  if (data.value.segments) {
    const tipSeg = data.value.segments.find(s => s.segment_id === 'tips')
    return tipSeg?.tips?.length || 0
  }
  return data.value.tips?.length || 0
})

function toggleRule(key) {
  expanded[key] = !expanded[key]
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
    // 默认展开所有高风险规则（兼容两种结构）
    if (data.value.segments) {
      for (const seg of data.value.segments) {
        for (const rule of (seg.triggered_rules || [])) {
          if (rule.risk_level === 'high') {
            expanded[rule.rule_id + seg.segment_id] = true
          }
        }
      }
    } else {
      for (const rule of (data.value.triggered_rules || [])) {
        if (rule.risk_level === 'high') {
          expanded[rule.rule_id] = true
        }
      }
    }
  } catch (e) {
    error.value = '报告加载失败，请确认报告编号是否正确。'
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.report-page { min-height: 100vh; background: var(--slate-100); }

/* 顶栏 */
.topbar {
  position: sticky; top: 0; z-index: 100;
  background: #fff; border-bottom: 1px solid var(--slate-200);
  padding: 12px 24px;
  display: flex; align-items: center; justify-content: space-between;
  box-shadow: var(--shadow-sm);
}
.topbar-left { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.back-btn {
  font-size: 13px; color: var(--blue-600); text-decoration: none;
  padding: 6px 12px; border-radius: 6px;
  border: 1px solid var(--blue-100); background: var(--blue-50);
}
.back-btn:hover { background: var(--blue-100); }
.topbar-title { font-size: 15px; font-weight: 600; color: var(--slate-700); }
.ai-badge {
  font-size: 12px; padding: 3px 10px; border-radius: 20px; font-weight: 500;
  background: linear-gradient(90deg, #7c3aed, #2563eb); color: #fff;
}
.mixed-badge {
  font-size: 12px; padding: 3px 10px; border-radius: 20px; font-weight: 500;
  background: #f0fdf4; color: #16a34a; border: 1px solid #bbf7d0;
}
.topbar-actions { display: flex; gap: 10px; }
.action-btn {
  padding: 7px 16px; border-radius: 8px; font-size: 13px; font-weight: 500;
  cursor: pointer; text-decoration: none; border: 1px solid var(--slate-200);
  background: #fff; color: var(--slate-600); transition: all 0.15s;
}
.action-btn:hover { background: var(--slate-50); }
.pdf-btn { color: var(--blue-600); border-color: var(--blue-200); background: var(--blue-50); }

/* 加载/错误 */
.loading-screen, .error-screen {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; height: 60vh; gap: 16px; color: var(--slate-500);
}
.spinner {
  width: 36px; height: 36px; border: 3px solid var(--slate-200);
  border-top-color: var(--blue-600); border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.error-icon { font-size: 40px; }
.back-link { color: var(--blue-600); text-decoration: underline; font-size: 14px; }

/* 报告主体 */
.report-content {
  max-width: 880px;
  margin: 0 auto;
  padding: 28px 20px 80px;
  font-family: system-ui, -apple-system, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  color: #333;
  -webkit-font-smoothing: antialiased;
}

/* 报告头 */
.report-header {
  background: linear-gradient(135deg, #1e40af 0%, #1d4ed8 60%, #2563eb 100%);
  border-radius: var(--radius-lg); padding: 28px 32px; color: #fff; margin-bottom: 20px;
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
  border-radius: var(--radius-lg); padding: 24px 28px;
  margin-bottom: 24px; border: 2px solid;
}
.overall-card.risk-high { background: #fef2f2; border-color: #fca5a5; }
.overall-card.risk-medium { background: #fffbeb; border-color: #fcd34d; }
.overall-card.risk-low { background: #f0fdf4; border-color: #86efac; }
.overall-left { display: flex; align-items: center; gap: 20px; margin-bottom: 14px; }
.risk-icon { font-size: 48px; line-height: 1; }
.risk-label { font-size: 26px; font-weight: 800; }
.risk-high .risk-label { color: #dc2626; }
.risk-medium .risk-label { color: #d97706; }
.risk-low .risk-label { color: #16a34a; }
.risk-count { font-size: 14px; color: var(--slate-600); margin-top: 4px; }
.mixed-note { color: #7c3aed; font-weight: 500; }
.overall-notice {
  background: #fff7ed; border: 1px solid #fed7aa;
  border-radius: 8px; padding: 10px 14px; font-size: 12px; color: #92400e;
}

/* 区块标题 */
.section-heading {
  font-size: 16px; font-weight: 700; color: #333;
  margin: 28px 0 14px; padding-left: 12px;
  border-left: 4px solid var(--blue-600);
  display: flex; align-items: center; gap: 8px;
}
.heading-sub { font-size: 12px; font-weight: 400; color: var(--slate-400); }
.heading-ai-tag {
  font-size: 12px; padding: 2px 8px; border-radius: 12px;
  background: linear-gradient(90deg, #7c3aed, #2563eb); color: #fff; font-weight: 500;
}
.tips-heading { margin-top: 20px; }

/* ── 板块（与后端 report_generator 蓝色分块一致）── */
.segment-block {
  background: #fff;
  border-radius: 14px;
  margin-bottom: 28px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
.segment-header {
  display: flex; align-items: center; gap: 12px;
  padding: 16px 24px;
  background: linear-gradient(135deg, #1e40af 0%, #2563eb 100%);
  color: #fff;
}
.segment-icon { font-size: 20px; }
.segment-title { font-size: 16px; font-weight: 700; color: #fff; flex: 1; }
.segment-count {
  font-size: 12px;
  background: rgba(255,255,255,0.2);
  color: #fff;
  padding: 3px 12px;
  border-radius: 20px;
  font-weight: 600;
}
.segment-ok-badge {
  font-size: 12px;
  background: rgba(255,255,255,0.15);
  color: #fff;
  padding: 3px 12px;
  border-radius: 20px;
  font-weight: 500;
}
.segment-overview {
  padding: 16px 24px;
  background: #f0f9ff;
  border-bottom: 1px solid #e0f2fe;
  font-size: 14px;
  color: #0369a1;
  line-height: 1.8;
  border-left: 4px solid #2563eb;
}
.segment-empty {
  padding: 16px 24px;
  background: #f0fdf4;
  color: #16a34a;
  font-size: 14px;
}
.segment-rules-container {
  padding: 12px;
  background: #f8fafc;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
/* 板块内规则卡片 */
.segment-rules-container .rule-card {
  border-radius: 10px !important;
  border: 1px solid #e2e8f0 !important;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
  margin-bottom: 0 !important;
}

/* ── 规则卡片 ── */
.rule-card {
  background: #fff; border: 1px solid var(--slate-200);
  border-radius: var(--radius-md); margin-bottom: 12px;
  overflow: hidden; box-shadow: var(--shadow-sm);
}
.rule-card-header {
  padding: 14px 20px; background: var(--slate-50);
  border-bottom: 1px solid var(--slate-200);
  display: flex; align-items: center; justify-content: space-between;
  cursor: pointer; user-select: none; transition: background 0.15s;
}
.rule-card-header:hover { background: var(--slate-100); }
.rule-card-left { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.risk-badge {
  display: inline-block; padding: 3px 10px; border-radius: 20px;
  color: #fff; font-size: 12px; font-weight: 600;
}
.badge-high { background: #dc2626; }
.badge-medium { background: #d97706; }
.badge-low { background: #16a34a; }
.rule-code { font-size: 12px; color: var(--slate-400); font-family: monospace; }
.rule-title { font-size: 15px; font-weight: 600; color: #333; }
.ai-inline-tag {
  font-size: 11px; padding: 1px 7px; border-radius: 10px;
  background: linear-gradient(90deg, #7c3aed22, #2563eb22);
  color: #5b21b6; font-weight: 500; border: 1px solid #c4b5fd;
}
.toggle-icon { color: var(--slate-400); font-size: 12px; }

/* 高风险子类型横幅 */
.hrt-banner {
  display: flex; align-items: center; gap: 14px;
  padding: 10px 20px; font-size: 13px;
  border-bottom: 1px solid rgba(0,0,0,0.15);
}
.hrt-label { font-weight: 800; font-size: 14px; white-space: nowrap; }
.hrt-desc { font-size: 12px; opacity: 0.88; }
.hrt-forbidden       { background: #450a0a; color: #fff; }
.hrt-no_revenue      { background: #7c2d12; color: #fff; }
.hrt-no_full_revenue { background: #78350f; color: #fff; }

/* 规则卡片体（含内联 RuleBody，需 :deep） */
.rule-card-body { border-top: 1px solid var(--slate-100); }
:deep(.rule-section) { padding: 16px 20px; border-bottom: 1px solid var(--slate-100); }
:deep(.rule-section:last-child) { border-bottom: none; }
:deep(.rule-section-title) {
  font-size: 13px;
  font-weight: 700;
  color: #333;
  text-transform: none;
  letter-spacing: 0.02em;
  margin-bottom: 10px;
}
:deep(.rule-section-body) {
  font-size: 14px;
  color: #4b5563;
  line-height: 1.6;
  white-space: pre-wrap;
}
:deep(.highlight-section) { background: #fffbeb; }
:deep(.optimize-section) { background: #f0fdf4; }

/* 条款原文（与 report_generator 一致） */
:deep(.clause-block) { margin-bottom: 16px; }
:deep(.clause-block:last-child) { margin-bottom: 0; }
:deep(.clause-source-name) {
  font-size: 13px;
  color: #315efb;
  font-weight: 600;
  margin-bottom: 8px;
  line-height: 1.5;
}
:deep(.clause-code) { margin-left: 4px; color: #94a3b8; font-family: monospace; font-size: 11px; }
:deep(.clause-text) {
  background: #f4f7fb;
  border-left: 3px solid #cbd5e1;
  padding: 14px 16px;
  border-radius: 6px;
  font-size: 14px;
  color: #4b5563;
  line-height: 1.6;
}
:deep(.no-clause) { font-size: 13px; color: #94a3b8; font-style: italic; }

/* 规则内 · 本风险点相关审计材料（与后端 audit-mats 一致） */
:deep(.audit-mats) {
  background: #f4f7fb;
  border-left: 3px solid #cbd5e1;
  border-radius: 6px;
  padding: 12px 14px;
}
:deep(.audit-item) {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 8px 0;
  font-size: 14px;
  color: #4b5563;
  line-height: 1.6;
  border-bottom: 1px solid #e2e8f0;
}
:deep(.audit-item:first-child) { padding-top: 0; }
:deep(.audit-item:last-child) { border-bottom: none; padding-bottom: 0; }
:deep(.audit-check) { color: #94a3b8; flex-shrink: 0; margin-top: 2px; }
:deep(.audit-item-main) { flex: 1; min-width: 0; }
:deep(.audit-item-main strong) { color: #333; font-weight: 600; }
:deep(.audit-sep) { color: #9ca3af; }
:deep(.audit-purpose) { color: #6b7280; }

/* 操作提示 */
.tip-card {
  background: #eff6ff; border: 1px solid #bfdbfe;
  border-left: 4px solid var(--blue-600);
  border-radius: var(--radius-md); margin-bottom: 10px; overflow: hidden;
}
.tip-header {
  padding: 12px 16px; display: flex; align-items: center; gap: 8px;
  border-bottom: 1px solid #bfdbfe; background: #dbeafe;
}
.tip-badge {
  background: var(--blue-600); color: #fff;
  font-size: 12px; font-weight: 600; padding: 2px 8px; border-radius: 20px;
}
.tip-body { padding: 14px 16px; font-size: 14px; color: var(--slate-700); line-height: 1.8; }

/* 无风险 */
.no-risk-card {
  background: var(--green-50); border: 1px solid var(--green-200);
  border-radius: var(--radius-md); padding: 20px 24px;
  display: flex; align-items: center; gap: 16px; margin-bottom: 24px;
}
.no-risk-icon { font-size: 32px; }
.no-risk-card p { font-size: 13px; color: var(--slate-600); margin-top: 4px; }

/* 审计清单 */
.checklist-card {
  background: #fff; border: 1px solid var(--slate-200);
  border-radius: var(--radius-md); padding: 6px 20px; box-shadow: var(--shadow-sm);
}
.checklist-item {
  display: flex; align-items: flex-start; gap: 12px;
  padding: 12px 0; border-bottom: 1px solid var(--slate-100);
}
.checklist-item:last-child { border-bottom: none; }
.mat-check { margin-top: 3px; width: 16px; height: 16px; flex-shrink: 0; cursor: pointer; }
.checklist-item label { font-size: 14px; color: var(--slate-700); cursor: pointer; line-height: 1.6; }
.checklist-item label .mat-purpose { display: block; font-size: 12px; color: var(--slate-400); margin-top: 2px; }
.no-mat { padding: 16px 0; color: var(--slate-400); font-size: 14px; }

/* 免责声明 */
.disclaimer {
  margin-top: 32px; background: var(--slate-50);
  border: 1px solid var(--slate-200); border-radius: var(--radius-sm);
  padding: 14px 18px; font-size: 12px; color: var(--slate-400); line-height: 1.8;
}

/* 展开动画 */
.slide-enter-active, .slide-leave-active { transition: all 0.2s ease; overflow: hidden; }
.slide-enter-from, .slide-leave-to { max-height: 0; opacity: 0; }
.slide-enter-to, .slide-leave-from { max-height: 3000px; opacity: 1; }
</style>
