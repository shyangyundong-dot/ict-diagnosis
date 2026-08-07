<template>
  <main class="guided-shell">
    <header class="guided-hero">
      <div>
        <div class="guided-kicker">新建诊断</div>
        <h1>先用六段话，把项目讲清楚</h1>
        <p>按实际情况自然描述即可。AI 会整理事实并集中追问，但不会在这里给出风险或列收结论。</p>
      </div>
      <button type="button" class="quiet-btn" @click="$emit('reset')">＋ 新建诊断</button>
    </header>

    <div class="guided-stages" aria-label="诊断流程">
      <span :class="{ active: !canProceed }">1 引导填报与追问</span>
      <span :class="{ active: canProceed }">2 信息确认</span>
      <span>3 规则诊断与报告</span>
    </div>

    <section v-if="editing || !hasAssessment" class="guided-editor">
      <div class="section-lead">
        <div>
          <h2>六块项目说明</h2>
          <p>至少先填写“项目基本情况”和“项目交付内容”。其他暂不掌握的内容可以明确标记。</p>
        </div>
        <span>统一提交后由 AI 整理</span>
      </div>

      <div class="guided-grid">
        <article v-for="(definition, key, index) in definitions" :key="key" class="guided-card">
          <div class="card-heading">
            <span>{{ index + 1 }}</span>
            <div><h3>{{ definition.title }}</h3><small>{{ draft[key]?.text.length || 0 }} 字</small></div>
          </div>
          <p class="card-prompt">{{ definition.prompt }}</p>
          <textarea
            v-model="draft[key].text"
            :disabled="draft[key].explicit_unknown"
            :placeholder="`请描述${definition.title}…`"
            rows="6"
            @input="draft[key].explicit_unknown = false"
          ></textarea>
          <div class="card-actions">
            <button type="button" class="example-toggle" @click="toggleExample(key)">
              {{ openExamples.has(key) ? '收起示例' : '查看参考示例' }}
            </button>
            <label class="unknown-toggle">
              <input v-model="draft[key].explicit_unknown" type="checkbox" @change="markUnknown(key)" />
              暂不清楚
            </label>
          </div>
          <blockquote v-if="openExamples.has(key)">{{ definition.example }}</blockquote>
          <div v-if="draft[key].explicit_unknown" class="unknown-note">已记录为“暂不清楚”，AI 不会反复追问非关键内容。</div>
        </article>
      </div>

      <div v-if="localError || error" class="guided-error">{{ localError || error }}</div>
      <div class="guided-submit-row">
        <p>提交后会评估项目骨架；描述不完整时只追问最关键的内容。</p>
        <button type="button" class="primary-btn" :disabled="loading" @click="submitDraft">
          {{ loading ? 'AI 正在整理项目事实…' : (hasAssessment ? '重新评估六块说明' : '提交并让 AI 整理') }}
        </button>
      </div>
    </section>

    <template v-else>
      <section class="coverage-overview">
        <div class="section-lead">
          <div>
            <h2>AI 整理结果</h2>
            <p>{{ readinessDescription }}</p>
          </div>
          <div class="coverage-actions">
            <span class="readiness-pill" :class="coverage.readiness">{{ readinessLabel }}</span>
            <button type="button" class="quiet-btn" @click="editing = true">修改六块说明</button>
          </div>
        </div>

        <div class="coverage-grid">
          <article v-for="(definition, key, index) in definitions" :key="key" class="coverage-card">
            <div class="coverage-title">
              <span>{{ index + 1 }}</span>
              <strong>{{ definition.title }}</strong>
              <em :class="sectionStatus(key)">{{ sectionStatusLabel(key) }}</em>
            </div>
            <p>{{ coverage.sections?.[key]?.summary || '暂未整理出有效摘要。' }}</p>
            <div v-if="coverage.sections?.[key]?.missing_topics?.length" class="missing-topics">
              还需补充：{{ coverage.sections[key].missing_topics.join('、') }}
            </div>
            <div v-if="coverage.sections?.[key]?.contradictions?.length" class="contradiction">
              信息冲突：{{ coverage.sections[key].contradictions.join('、') }}
            </div>
          </article>
        </div>
      </section>

      <section v-if="canProceed" class="guided-result ready-result">
        <div>
          <span class="result-icon">✓</span>
          <div>
            <h2>项目骨架已经形成</h2>
            <p>
              AI 已形成初步核算单元。确认页共有 {{ coverage.simple_fact_gaps?.length || 0 }} 项待核对，
              其中 {{ acknowledgedGapCount }} 项已明确“暂不清楚”，
              仍需补充 {{ coverage.unresolved_simple_fact_gaps?.length || 0 }} 项。进入下一步后请核对摘要、核算结构和专业判断。
            </p>
            <div v-if="coverage.deferred_topics?.length" class="deferred-topics">
              <strong>以下内容不阻断进入确认页：</strong>
              {{ coverage.deferred_topics.join('；') }}
            </div>
          </div>
        </div>
        <button type="button" class="primary-btn" :disabled="loading" @click="$emit('proceed')">以上整理无误，进入信息确认</button>
      </section>

      <section v-else-if="coverage.readiness === 'blocked'" class="guided-result blocked-result">
        <div>
          <span class="result-icon">!</span>
          <div>
            <h2>三轮追问已结束，当前资料不足</h2>
            <p>草稿已经保存。请取得合同清单、报价构成、职责界面或验收方案后，修改六块说明并重新评估。</p>
          </div>
        </div>
        <ul v-if="coverage.blocking_topics?.length">
          <li v-for="topic in coverage.blocking_topics" :key="topic">{{ topic }}</li>
        </ul>
      </section>

      <section v-else class="follow-up-panel">
        <div class="follow-up-head">
          <div>
            <span>集中追问</span>
            <h2>第 {{ nextRound }} / {{ maxRounds }} 轮</h2>
          </div>
          <p>一次回答整组问题；不清楚的项目请明确写“暂不清楚”。</p>
        </div>
        <ol v-if="coverage.follow_up_questions?.length" class="question-list">
          <li v-for="question in coverage.follow_up_questions" :key="question">{{ question }}</li>
        </ol>
        <div v-else-if="coverage.blocking_topics?.length" class="question-list plain-list">
          请补充：{{ coverage.blocking_topics.join('；') }}
        </div>
        <textarea v-model="followUpText" rows="6" placeholder="请在这里集中回答以上问题…"></textarea>
        <div v-if="localError || error" class="guided-error">{{ localError || error }}</div>
        <div class="follow-up-actions">
          <span>本轮回答会与六块原文一起重新评估。</span>
          <button type="button" class="primary-btn" :disabled="loading || !followUpText.trim()" @click="submitFollowUp">
            {{ loading ? 'AI 正在重新评估…' : '提交本轮补充' }}
          </button>
        </div>
      </section>
    </template>
  </main>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'

const props = defineProps({
  sections: { type: Object, default: () => ({}) },
  definitions: { type: Object, default: () => ({}) },
  coverage: { type: Object, default: () => ({ readiness: 'not_started', sections: {} }) },
  maxRounds: { type: Number, default: 3 },
  loading: Boolean,
  error: { type: String, default: '' },
})

const emit = defineEmits(['submit', 'reply', 'proceed', 'reset'])
const draft = reactive({})
const editing = ref(true)
const followUpText = ref('')
const localError = ref('')
const openExamples = reactive(new Set())

watch(
  () => [props.sections, props.definitions],
  () => {
    for (const key of Object.keys(props.definitions || {})) {
      const incoming = props.sections?.[key] || {}
      if (!draft[key]) draft[key] = { text: '', explicit_unknown: false }
      draft[key].text = incoming.text || ''
      draft[key].explicit_unknown = incoming.explicit_unknown === true
    }
  },
  { immediate: true, deep: true },
)

watch(
  () => props.coverage?.readiness,
  (value) => {
    if (value && value !== 'not_started') editing.value = false
  },
)

const hasAssessment = computed(() => props.coverage?.readiness && props.coverage.readiness !== 'not_started')
const canProceed = computed(() => props.coverage?.readiness === 'ready')
const nextRound = computed(() => Math.min((props.coverage?.round || 0) + 1, props.maxRounds))
const acknowledgedGapCount = computed(() => Math.max(
  0,
  (props.coverage?.simple_fact_gaps?.length || 0)
    - (props.coverage?.unresolved_simple_fact_gaps?.length || 0),
))

const readinessLabel = computed(() => ({
  ready: '可进入确认', near_ready: '接近完整', insufficient: '资料不足', blocked: '暂不能诊断',
}[props.coverage?.readiness] || '待评估'))

const readinessDescription = computed(() => ({
  ready: '六块内容已经形成完整项目骨架，请进入信息确认。',
  near_ready: '主要内容已经掌握，再集中补充一轮信息即可。',
  insufficient: '当前描述还不足以形成项目骨架，请按问题补充。',
  blocked: '三轮追问后仍缺关键材料，本次草稿已保存。',
}[props.coverage?.readiness] || '等待 AI 评估六块项目说明。'))

function sectionStatus(key) {
  return props.coverage?.sections?.[key]?.status || 'missing'
}

function sectionStatusLabel(key) {
  return ({
    covered: '已覆盖', partial: '部分覆盖', missing: '缺失', not_applicable: '不适用', unknown_confirmed: '已明确未知',
  })[sectionStatus(key)] || '缺失'
}

function toggleExample(key) {
  if (openExamples.has(key)) openExamples.delete(key)
  else openExamples.add(key)
}

function markUnknown(key) {
  if (draft[key].explicit_unknown) draft[key].text = ''
}

function normalizedDraft() {
  const result = {}
  for (const key of Object.keys(props.definitions || {})) {
    result[key] = {
      text: (draft[key]?.text || '').trim(),
      explicit_unknown: draft[key]?.explicit_unknown === true,
    }
  }
  return result
}

function submitDraft() {
  localError.value = ''
  const value = normalizedDraft()
  if (!value.basic?.text || !value.delivery?.text) {
    localError.value = '请至少填写“项目基本情况”和“项目交付内容”。'
    return
  }
  editing.value = false
  emit('submit', value)
}

function submitFollowUp() {
  localError.value = ''
  const value = followUpText.value.trim()
  if (!value) return
  followUpText.value = ''
  emit('reply', value)
}
</script>

<style scoped>
.guided-shell { flex: 1; min-height: 0; overflow-y: auto; background: #f5f7fb; padding: 30px clamp(20px, 4vw, 64px) 56px; }
.guided-hero { max-width: 1260px; margin: 0 auto 18px; display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; }
.guided-kicker { color: var(--blue-600); font-size: 13px; font-weight: 700; letter-spacing: .08em; }
.guided-hero h1 { margin: 6px 0 8px; color: var(--slate-900); font-size: clamp(28px, 3vw, 40px); letter-spacing: -.03em; }
.guided-hero p { margin: 0; max-width: 760px; color: var(--slate-500); line-height: 1.75; }
.quiet-btn { border: 1px solid var(--slate-200); background: #fff; color: var(--slate-600); border-radius: 9px; padding: 9px 14px; cursor: pointer; white-space: nowrap; }
.guided-stages { max-width: 1260px; margin: 0 auto 24px; display: grid; grid-template-columns: repeat(3, 1fr); border: 1px solid var(--slate-200); border-radius: 12px; overflow: hidden; background: #fff; }
.guided-stages span { padding: 12px 16px; text-align: center; color: var(--slate-400); font-size: 13px; border-right: 1px solid var(--slate-200); }
.guided-stages span:last-child { border-right: 0; }
.guided-stages span.active { color: var(--blue-700); background: var(--blue-50); font-weight: 700; }
.guided-editor, .coverage-overview, .follow-up-panel, .guided-result { max-width: 1260px; margin: 0 auto; }
.section-lead { display: flex; justify-content: space-between; gap: 24px; align-items: flex-end; margin-bottom: 16px; }
.section-lead h2, .follow-up-head h2, .guided-result h2 { margin: 0 0 5px; color: var(--slate-800); }
.section-lead p, .follow-up-head p, .guided-result p { margin: 0; color: var(--slate-500); line-height: 1.6; }
.section-lead > span { color: var(--slate-400); font-size: 13px; }
.guided-grid, .coverage-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.guided-card, .coverage-card { background: #fff; border: 1px solid var(--slate-200); border-radius: 14px; padding: 20px; box-shadow: 0 4px 18px rgba(15, 23, 42, .035); }
.card-heading, .coverage-title { display: flex; align-items: center; gap: 10px; }
.card-heading > span, .coverage-title > span { width: 28px; height: 28px; display: grid; place-items: center; border-radius: 8px; color: #fff; background: var(--blue-600); font-weight: 700; font-size: 13px; }
.card-heading h3 { margin: 0; color: var(--slate-800); font-size: 17px; }
.card-heading small { color: var(--slate-400); }
.card-prompt { min-height: 76px; margin: 14px 0 10px; color: var(--slate-600); line-height: 1.65; font-size: 14px; }
textarea { width: 100%; resize: vertical; border: 1px solid var(--slate-200); border-radius: 10px; padding: 12px 14px; color: var(--slate-800); background: #fbfcfe; font: inherit; line-height: 1.65; box-sizing: border-box; }
textarea:focus { outline: 3px solid rgba(37, 99, 235, .1); border-color: var(--blue-500); background: #fff; }
textarea:disabled { color: var(--slate-400); background: var(--slate-50); }
.card-actions { margin-top: 10px; display: flex; justify-content: space-between; align-items: center; }
.example-toggle { border: 0; background: transparent; color: var(--blue-600); cursor: pointer; padding: 4px 0; }
.unknown-toggle { color: var(--slate-500); font-size: 13px; display: flex; gap: 6px; align-items: center; }
blockquote { margin: 12px 0 0; padding: 11px 13px; border-left: 3px solid var(--blue-300); background: var(--blue-50); color: var(--slate-600); font-size: 13px; line-height: 1.6; }
.unknown-note { margin-top: 10px; color: #8a6420; background: #fff8df; border-radius: 8px; padding: 9px 11px; font-size: 13px; }
.guided-submit-row, .follow-up-actions { margin-top: 18px; display: flex; justify-content: space-between; gap: 24px; align-items: center; }
.guided-submit-row p, .follow-up-actions span { margin: 0; color: var(--slate-500); font-size: 13px; }
.primary-btn { border: 0; border-radius: 10px; padding: 12px 20px; color: #fff; background: var(--blue-600); font-weight: 700; cursor: pointer; box-shadow: 0 7px 18px rgba(37, 99, 235, .18); }
.primary-btn:disabled { opacity: .55; cursor: not-allowed; box-shadow: none; }
.guided-error { margin-top: 14px; padding: 10px 13px; border-radius: 9px; color: #b42318; background: #fff0ee; border: 1px solid #ffd3cf; }
.coverage-actions { display: flex; align-items: center; gap: 10px; }
.readiness-pill { border-radius: 999px; padding: 6px 10px; font-size: 12px; font-style: normal; font-weight: 700; }
.readiness-pill.ready { color: #087443; background: #dcfce7; }
.readiness-pill.near_ready { color: #8a6420; background: #fff5cc; }
.readiness-pill.insufficient, .readiness-pill.blocked { color: #b42318; background: #feeceb; }
.coverage-card { padding: 16px; }
.coverage-title strong { color: var(--slate-800); }
.coverage-title em { margin-left: auto; font-size: 12px; font-style: normal; border-radius: 999px; padding: 4px 8px; color: var(--slate-500); background: var(--slate-100); }
.coverage-title em.covered { color: #087443; background: #dcfce7; }
.coverage-title em.partial, .coverage-title em.unknown_confirmed { color: #8a6420; background: #fff5cc; }
.coverage-title em.missing { color: #b42318; background: #feeceb; }
.coverage-card > p { margin: 12px 0 0; color: var(--slate-600); line-height: 1.65; }
.missing-topics, .contradiction { margin-top: 10px; border-radius: 8px; padding: 8px 10px; font-size: 13px; }
.missing-topics { color: #8a6420; background: #fff8df; }
.contradiction { color: #b42318; background: #fff0ee; }
.guided-result, .follow-up-panel { margin-top: 18px; background: #fff; border: 1px solid var(--slate-200); border-radius: 14px; padding: 22px; }
.guided-result > div { display: flex; gap: 14px; align-items: flex-start; }
.deferred-topics { margin-top: 10px; color: var(--slate-500); font-size: 13px; line-height: 1.65; }
.deferred-topics strong { color: var(--slate-700); }
.ready-result { border-color: #b9e9d0; background: #f6fff9; display: flex; justify-content: space-between; gap: 24px; align-items: center; }
.blocked-result { border-color: #ffd3cf; background: #fffaf9; }
.result-icon { width: 34px; height: 34px; display: grid; place-items: center; border-radius: 50%; color: #fff; background: #16a267; font-weight: 800; }
.blocked-result .result-icon { background: #d92d20; }
.blocked-result ul { margin: 16px 0 0 48px; color: var(--slate-600); }
.follow-up-head { display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; }
.follow-up-head span { color: var(--blue-600); font-size: 12px; font-weight: 700; }
.question-list { margin: 18px 0; padding: 16px 16px 16px 38px; border-radius: 10px; background: var(--blue-50); color: var(--slate-700); line-height: 1.75; }
.plain-list { padding-left: 16px; }
@media (max-width: 860px) {
  .guided-shell { padding: 22px 14px 40px; }
  .guided-hero, .section-lead, .ready-result, .follow-up-head, .guided-submit-row, .follow-up-actions { align-items: stretch; flex-direction: column; }
  .guided-grid, .coverage-grid { grid-template-columns: 1fr; }
  .guided-stages span { padding: 10px 6px; font-size: 11px; }
  .card-prompt { min-height: 0; }
}
</style>
