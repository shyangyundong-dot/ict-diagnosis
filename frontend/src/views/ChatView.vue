<template>
  <GuidedIntakePanel
    v-if="!confirmationMode"
    :sections="guidedInput.sections"
    :definitions="guidedSectionDefinitions"
    :coverage="coverage"
    :max-rounds="maxFollowUpRounds"
    :loading="guidedLoading"
    :error="guidedError"
    @submit="submitGuidedSections"
    @reply="submitGuidedReply"
    @proceed="enterConfirmation"
    @reset="resetChat"
  />

  <div v-else class="layout">

    <!-- 次级：AI 助填区。规则诊断只会在表单提交后发生。 -->
    <aside class="chat-panel" :class="{ 'drawer-open': drawerOpen }">
      <div class="chat-header">
        <div class="header-logo">
          <div class="logo-icon">🛡</div>
          <div>
            <div class="logo-title">AI 助填</div>
            <div class="logo-sub">可选 · 不执行规则诊断</div>
          </div>
        </div>
        <div class="header-actions">
          <button type="button" class="assistant-close" @click="closeDrawer">收起助填</button>
        </div>
      </div>

      <!-- 消息列表 -->
      <div class="chat-messages" ref="messagesRef">
        <!-- 欢迎消息 -->
        <div v-if="messages.length === 0" class="welcome-card">
          <div class="welcome-icon">👋</div>
          <h2>AI 只负责助填</h2>
          <p>可粘贴一整段项目描述，我会把能确定的信息预填到表单中；请逐项核对后再提交。</p>
          <p class="welcome-example">不会在这里给出风险等级、列收结论或诊断结果。</p>
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
            <button v-if="msg.help?.suggestedValue !== null && msg.help?.suggestedValue !== undefined"
                    type="button" class="apply-ai-suggestion"
                    :disabled="msg.help.applied"
                    @click="applyFieldSuggestion(msg.help)">
              {{ msg.help.applied ? '已填入 · 待本步核对' : `填入「${getFieldLabel(msg.help.fieldKey)}」` }}
            </button>
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
        <div v-if="fieldHelpTarget" class="field-help-context">
          正在协助填写：<strong>{{ getFieldLabel(fieldHelpTarget) }}</strong>
          <button type="button" @click="clearFieldHelp">改为整段预填</button>
        </div>
        <div v-else class="complete-hint">
          可选：粘贴项目描述，AI 会预填明确事实；未确认的值不能提交诊断。
        </div>
        <div class="input-row">
          <textarea
            ref="inputRef"
            v-model="inputText"
            :placeholder="fieldHelpTarget ? `请描述「${getFieldLabel(fieldHelpTarget)}」的实际情况...` : '可选：粘贴项目描述，AI 帮你预填表单…'"
            @keydown.enter.exact.prevent="sendAssist"
            @input="adjustTextareaHeight"
            rows="1"
            class="chat-textarea"
            :disabled="loading"
          ></textarea>
          <button class="send-btn" @click="sendAssist" :disabled="loading || !inputText.trim()">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </button>
        </div>
        <div class="input-hint">Enter 发送 · AI 输出仅为填写建议</div>
      </div>
    </aside>

    <!-- 主区域：项目事实表 -->
    <div class="fields-panel">
      <div class="drawer-handle-bar">
        <div class="drawer-handle"></div>
        <button type="button" class="drawer-close" @click="closeDrawer">✕</button>
      </div>
      <div class="fields-header">
        <div class="fields-header-text">
          <span class="fields-header-title">核对 AI 整理的项目事实</span>
          <span class="fields-header-desc">重点核对缺口、核算结构和专业判断；仅在提交后执行规则库诊断。</span>
        </div>
        <div class="fields-header-actions">
          <button type="button" class="new-chat-btn" @click="confirmationMode = false">返回项目说明</button>
          <span class="fields-count" :class="isComplete ? 'count-done' : 'count-pending'">
            {{ isComplete ? '✅ 可运行规则诊断' : `待完成 ${pendingTotal} 项` }}
          </span>
          <button type="button" class="new-chat-btn" @click="resetChat">＋ 新建诊断</button>
        </div>
      </div>

      <div class="diagnosis-stages" aria-label="诊断流程">
        <span class="stage-active">1 填写并核对</span><span>2 规则库诊断</span><span>3 正式报告</span>
      </div>

      <div class="fields-body">
        <div v-if="!sessionId" class="fields-empty">
          <div class="empty-icon">💬</div>
          <p>正在创建填写草稿…</p>
        </div>

        <template v-else>
          <nav class="form-step-nav" aria-label="填报步骤">
            <button v-for="step in FORM_STEPS" :key="step.id" type="button"
                    :class="{ active: activeStep === step.id }" @click="activeStep = step.id">
              <strong>{{ step.label }}</strong><span>{{ stepStatus(step.id) }}</span>
            </button>
          </nav>

          <!-- 1. 基础与商务信息 -->
          <section v-if="activeStep === 1" class="fields-section primary-form-section">
            <div class="section-head">
              <span class="section-head-title">1. 六块项目事实摘要</span>
              <button type="button" class="units-segment-btn" @click="showAllSimpleFacts = !showAllSimpleFacts">
                {{ showAllSimpleFacts ? '只看待补缺口' : '展开全部结构化事实' }}
              </button>
            </div>
            <div class="confirmation-summary-grid">
              <article v-for="item in coverageSectionEntries" :key="item.key" class="confirmation-summary-card">
                <div>
                  <strong>{{ item.title }}</strong>
                  <span :class="item.status">{{ item.status === 'covered' ? '已覆盖' : (item.status === 'partial' ? '部分覆盖' : (item.status === 'unknown_confirmed' ? '已明确未知' : '需注意')) }}</span>
                </div>
                <p>{{ item.summary }}</p>
              </article>
            </div>
            <div class="confirmation-gap-head">
              <div>
                <strong>{{ showAllSimpleFacts ? '全部结构化事实' : '仍需补充的普通事实' }}</strong>
                <span>{{ showAllSimpleFacts ? '可展开复核任何 AI 已整理内容' : `共 ${generalFormFields.length} 项，原则上不超过 5 项` }}</span>
              </div>
              <button v-if="generalFormFields.length" type="button" class="field-help-btn" @click="openDrawer">使用自然语言辅助</button>
            </div>
            <div v-if="generalFormFields.length" class="form-subgroups">
              <section v-for="group in generalFieldGroups" :key="group.id" class="form-subgroup">
                <div class="form-subgroup-head">
                  <div>
                    <span class="form-subgroup-index">{{ group.step }}</span>
                    <strong>{{ group.title }}</strong>
                  </div>
                  <span>{{ group.description }}</span>
                </div>
                <div class="form-field-grid">
                  <div v-for="key in group.fields" :key="key" class="field-item"
                       :class="{ 'field-item-ai': isFieldAiPending(key) }">
                    <div class="field-label">
                      {{ getFieldLabel(key) }}
                      <button type="button" class="field-help-btn" @click="openFieldHelp(key)">问 AI</button>
                      <span v-if="isFieldAiPending(key)" class="ai-src-tag">AI 预填 · 待核对</span>
                      <span v-else-if="isFieldAiAssisted(key)" class="ai-confirmed-tag">AI 助填 · 已核对</span>
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
            </div>
            <div v-else class="pending-all-clear">普通项目事实已经通过六块摘要完成确认；请继续核对核算结构和专业判断。</div>
            <div v-if="stepPendingFields(1).length" class="step-review-band">
              <span>请核对本步骤的 {{ stepPendingFields(1).length }} 项 AI 预填内容。</span>
              <button type="button" class="units-segment-btn" @click="confirmStepAiFields(1)">确认本步 AI 预填</button>
            </div>
            <p v-else-if="generalMissingFields.length" class="structure-pending">还缺 {{ generalMissingFields.length }} 项必填信息；可直接填写或使用右侧 AI 助填。</p>
          </section>

          <!-- 1. 原始业务单元 -->
          <section v-if="activeStep === 2" class="fields-section units-section">
            <div class="section-head">
              <span class="section-head-title">1. 原始业务单元</span>
              <button class="units-segment-btn" :disabled="unitsLoading" @click="doSegmentUnits">
                {{ unitsLoading ? '切分中…' : (accountingUnits.length ? '重新切分' : 'AI 切分') }}
              </button>
            </div>
            <div class="units-hint">
              按业务实质确认最小业务块。标品指电话、宽带、天翼云等电信自有产品；成品软件指 Oracle、Windows 等独立授权软件。
            </div>
            <div v-if="unitsLoading" class="section-parsing"><span class="parsing-dot"></span>AI 正在切分核算单元…</div>
            <div v-else-if="accountingUnits.length === 0" class="section-empty">
              尚未切分。点「AI 切分」按对话拆分核算单元，或手动添加。
            </div>
            <div v-else class="units-list">
              <div v-for="(u, idx) in accountingUnits" :key="u.id || idx" class="unit-card">
                <div class="unit-row-top">
                  <input class="unit-name" v-model="u.name" placeholder="单元名称" @change="persistUnits" />
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
                </div>
                <div v-if="u.declared_type === '设备' || u.declared_type === '成品软件'" class="unit-row-fields unit-row-whitelist">
                  <label>集团白名单
                    <select v-model="u.whitelisted" @change="persistUnits">
                      <option :value="true">是（标准化成品）</option>
                      <option :value="false">否</option>
                      <option value="unknown">不确定</option>
                    </select>
                  </label>
                  <span class="unit-wl-hint">不确定不会直接改成净额，报告按暂定全额、高风险提示补充依据。</span>
                </div>
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
            <div v-if="sourceUnitsNeedReview" class="step-review-band">
              <span>AI 切分的原始业务单元仍是草稿，请核对业务实质、类型和金额。</span>
              <button type="button" class="units-segment-btn" @click="confirmSourceUnits">确认原始业务单元</button>
            </div>
            <button v-if="accountingUnits.length > 0 || sessionId" class="units-add-btn" @click="addUnit">＋ 添加原始单元</button>
            <p v-if="unitsSaveError" class="units-save-error">⚠ {{ unitsSaveError }}</p>
          </section>

          <!-- 2. 履约关系与组合 -->
          <section v-if="activeStep === 2 && accountingUnits.length" class="fields-section grouping-section">
            <div class="section-head">
              <span class="section-head-title">2. 履约关系与组合</span>
              <button class="units-segment-btn" @click="addGroup">新增候选组合</button>
            </div>
            <div class="units-hint">只有可能形成一个组合产出的原始单元才放进同一候选组。未加入组合的单元自动单独核算，标品不参与组合。</div>
            <div v-if="accountingGroups.length === 0" class="section-empty">当前全部按单独核算预览；需要组合时新增候选组合。</div>
            <div v-for="(group, groupIndex) in accountingGroups" :key="group.id" class="group-card">
              <div class="unit-row-top">
                <input class="unit-name" v-model="group.name" placeholder="候选组合名称" @change="persistUnits" />
                <button class="unit-del" @click="removeGroup(groupIndex)" title="删除候选组合">✕</button>
              </div>
              <div class="group-members">
                <label v-for="source in groupableSources" :key="source.id" class="group-member">
                  <input type="checkbox" :checked="group.source_unit_ids.includes(source.id)"
                         :disabled="sourceUsedByOtherGroup(source.id, group.id)"
                         @change="toggleGroupMember(group, source.id, $event.target.checked)" />
                  <span>{{ source.name || '未命名单元' }} · {{ source.declared_type }}</span>
                </label>
              </div>
              <div class="po-grid">
                <div v-for="question in PO_QUESTIONS" :key="question.key" class="po-row">
                  <span>{{ question.label }}</span>
                  <div class="mini-segmented">
                    <button type="button" :class="{ active: group.po_facts[question.key] === 'yes' }" @click="setPoFact(group, question.key, 'yes')">是</button>
                    <button type="button" :class="{ active: group.po_facts[question.key] === 'no' }" @click="setPoFact(group, question.key, 'no')">否</button>
                  </div>
                </div>
              </div>
              <div class="group-confirm-row">
                <span>系统建议：{{ relationshipLabel(groupSuggestion(group)) }}</span>
                <div class="mini-segmented">
                  <button type="button" :class="{ active: group.confirmed_relationship === 'combined' }" @click="confirmGroup(group, 'combined')">组合核算</button>
                  <button type="button" :class="{ active: group.confirmed_relationship === 'separate' }" @click="confirmGroup(group, 'separate')">分别核算</button>
                </div>
              </div>
            </div>
          </section>

          <!-- 3. 最终核算单元与列收意图 -->
          <section v-if="activeStep === 2 && finalUnits.length" class="fields-section final-units-section">
            <div class="section-head">
              <span class="section-head-title">3. 最终核算单元与列收意图</span>
              <span class="section-head-meta">{{ finalUnits.length }} 个</span>
            </div>
            <div class="units-hint">系统可预写建议，但最终以这里确认的拟全额或拟净额意图为输入。标品固定全额。</div>
            <div v-for="unit in finalUnits" :key="unit.id" class="final-unit-row">
              <div>
                <strong>{{ unit.name }}</strong>
                <span>{{ unit.declared_types.join('、') }} · {{ relationshipLabel(unit.relationship) }}</span>
              </div>
              <span v-if="unit.declared_type === '标品'" class="fixed-full-label">固定全额</span>
              <div v-else class="mini-segmented">
                <button type="button" :class="{ active: unit.decision.listing_intent === 'full' && unit.decision.listing_intent_confirmed }" @click="setListingIntent(unit, 'full')">拟全额</button>
                <button type="button" :class="{ active: unit.decision.listing_intent === 'net' && unit.decision.listing_intent_confirmed }" @click="setListingIntent(unit, 'net')">拟净额</button>
              </div>
            </div>
          </section>

          <!-- 4. 拟全额核算单元自查 -->
          <section v-if="activeStep === 3 && fullIntentUnits.length" class="fields-section ctrl-roles-section">
            <div class="section-head">
              <span class="section-head-title">4. 拟全额核算单元自查</span>
              <span class="section-head-meta ctrl-roles-meta">共性事实一次填写 · 单元分别确认</span>
            </div>
            <div class="ctrl-roles-hint">按实际控制权和交付事实逐项确认。本页只记录事实；规则结论和材料清单会在提交后生成。</div>
            <div class="shared-facts-title">项目共性事实</div>
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
            <div v-for="unit in fullIntentUnits" :key="unit.id" class="unit-check-card">
              <div class="unit-check-title">
                <div><strong>{{ unit.name }}</strong><span>{{ unit.declared_types.join('、') }}</span></div>
                <label><input type="checkbox" v-model="unit.decision.six_daowei.facts_confirmed" @change="persistUnits" /> 已核对本单元事实</label>
              </div>
              <div class="unit-na-row">
                <label><input type="checkbox" v-model="unit.decision.six_daowei.no_external_procurement" @change="onApplicabilityChange(unit, 'procurement')" /> 无外部采购</label>
                <label><input type="checkbox" v-model="unit.decision.six_daowei.no_operations_obligation" @change="onApplicabilityChange(unit, 'operations')" /> 无运维、售后或维保义务</label>
              </div>
              <div class="daowei-dimensions">
                <div v-for="dimension in UNIT_SIX_DIMENSIONS" :key="dimension.key" class="daowei-dimension-row compact">
                  <span class="daowei-dimension-label">{{ dimension.label }}</span>
                  <div class="daowei-segmented" role="group" :aria-label="dimension.label">
                    <button v-for="option in sixOptionsFor(unit, dimension.key)" :key="option.value" type="button"
                            :class="{ active: unit.decision.six_daowei.dimensions[dimension.key] === option.value }"
                            @click="setSixValue(unit, dimension.key, option.value)">{{ option.label }}</button>
                  </div>
                </div>
              </div>
              <div class="unit-level-row">
                <span>六到位综合结论</span>
                <div class="mini-segmented">
                  <button v-for="option in SIX_DAOWEI_LEVEL_OPTIONS" :key="option.value" type="button"
                          :class="{ active: unit.decision.six_daowei.level === option.value }"
                          @click="setSixLevel(unit, option.value)">{{ option.label }}</button>
                </div>
              </div>
              <div class="r08-block">
                <div class="shared-facts-title">R08 控制权四要件</div>
                <div v-for="question in R08_QUESTIONS" :key="question.key" class="po-row">
                  <span>{{ question.label }}</span>
                  <div class="mini-segmented">
                    <button v-for="option in R08_OPTIONS" :key="option.value" type="button"
                            :class="{ active: unit.decision.r08.answers[question.key] === option.value }"
                            @click="setR08Value(unit, question.key, option.value)">{{ option.label }}</button>
                  </div>
                </div>
                <div class="unit-level-row">
                  <span>人工控制权结论</span>
                  <div class="mini-segmented">
                    <button type="button" :class="{ active: unit.decision.r08.conclusion === 'principal' }" @click="setR08Conclusion(unit, 'principal')">主要责任人</button>
                    <button type="button" :class="{ active: unit.decision.r08.conclusion === 'agent' }" @click="setR08Conclusion(unit, 'agent')">代理人</button>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <!-- 5. 公共政策信息 -->
          <section v-if="activeStep === 3 && (needsPolicyFields || visibleListingFields.length)" class="fields-section listing-fields-section">
            <div class="section-head">
              <span class="section-head-title">5. 公共政策信息</span>
              <span class="section-head-meta listing-fields-meta">整个 BPM 项目口径</span>
            </div>
            <div class="listing-fields-hint">
              <p>仅在拟全额单元含设备、成品软件或施工时显示。金额占比和整体利润率按整个 BPM 项目计算。</p>
            </div>
            <div class="listing-fields-list">
              <div v-for="key in visibleListingFields" :key="key" class="listing-field-row"
                   :class="{ 'field-item-ai': isFieldAiPending(key) }">
                <div class="listing-field-label">
                  {{ getFieldLabel(key) }}
                  <button type="button" class="field-help-btn" @click="openFieldHelp(key)">问 AI</button>
                  <span v-if="isFieldAiPending(key)" class="ai-src-tag">AI 预填 · 待核对</span>
                </div>
                <FieldControl
                  :field-key="key"
                  :model-value="currentFields[key]"
                  :definitions="fieldDefinitions"
                  @update:model-value="(v) => onFieldUpdate(key, v)"
                />
              </div>
            </div>
            <div v-if="stepPendingFields(3).length" class="step-review-band">
              <span>请核对本步骤的 {{ stepPendingFields(3).length }} 项 AI 预填内容。</span>
              <button type="button" class="units-segment-btn" @click="confirmStepAiFields(3)">确认本步 AI 预填</button>
            </div>
          </section>

          <!-- ② 待补充信息 -->
          <section v-if="false" class="fields-section section-pending-block">
            <div class="section-head">
              <span class="section-head-title">待补充信息</span>
              <span
                v-if="!isComplete"
                class="section-head-meta section-head-warn"
              >{{ pendingTotal }} 项</span>
              <span v-else class="section-head-meta section-head-ok">已齐</span>
            </div>
            <div v-if="!structureReady" class="structure-pending">
              {{ structurePendingMessage }}
            </div>
            <div v-if="isComplete" class="pending-all-clear">
              必填项已全部收集，请核对左侧对话与上方已解析字段后，点击下方提交诊断。
            </div>
            <div v-else-if="generalMissingFields.length > 0" class="pending-list">
              <p class="pending-intro">
                可在下方直接选择或修改；也可在左侧对话中说明，系统将自动解析。
              </p>
              <div class="pending-edit-list">
                <div v-for="f in generalMissingFields" :key="'p-' + f" class="pending-field-row">
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
            <div v-else-if="structureReady" class="section-empty subtle">
              暂无待补充清单，请再发送一条消息或检查网络与 API 配置。
            </div>
          </section>

          <!-- 4. 最终核对：此处不显示风险结论，只汇总事实完成状态。 -->
          <section v-if="activeStep === 4" class="fields-section final-review-section">
            <div class="section-head">
              <span class="section-head-title">4. 最终核对</span>
              <span class="section-head-meta">完成后才执行规则库</span>
            </div>
            <div class="review-status-row">
              <span>基础与商务信息</span>
              <strong>{{ stepStatus(1) }}</strong>
            </div>
            <div class="review-status-row">
              <span>核算结构与列收意图</span>
              <strong>{{ stepStatus(2) }}</strong>
            </div>
            <div class="review-status-row">
              <span>拟全额核算单元自查</span>
              <strong>{{ stepStatus(3) }}</strong>
            </div>
            <p class="final-review-note">
              {{ isComplete ? '项目事实已完成核对。提交后，系统才会运行规则库并生成正式报告。' : completionBlocker }}
            </p>
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
          <span v-else-if="isComplete">🛡 运行规则诊断并生成报告</span>
          <span v-else>请先完成事实填写与核对</span>
        </button>

        <div v-if="submitting && submittingHint" class="submitting-hint">{{ submittingHint }}</div>

        <div v-if="diagnosisId" class="report-actions">
          <a :href="`/report/${diagnosisId}`" class="report-link">
            📄 查看正式报告
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
      <span>✨ 打开 AI 助填</span>
    </button>

  </div>
</template>

<script setup>
import { ref, nextTick, computed, watch, onMounted } from 'vue'
import FieldControl from '../components/FieldControl.vue'
import GuidedIntakePanel from '../components/GuidedIntakePanel.vue'
import { createSession, submitGuidedIntake, replyGuidedIntake, supplementGuidedIntake, confirmDiagnosis, patchSessionFields, fetchFieldDefinitions, getFieldHelp, downloadReportPdf, segmentUnits, saveUnits } from '../api/diagnosis.js'

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
  service_capability_level: '六到位服务能力等级（历史自动推导）',
  six_daowei_facts_confirmed: '六到位基础事实已核对',
  six_daowei_customer_insight: '客情掌握到位',
  six_daowei_solution_control: '方案总控到位',
  six_daowei_bid_autonomy: '谈判/应标自主到位',
  six_daowei_procurement_autonomy: '采购自主到位',
  six_daowei_project_management: '项目强管理到位',
  six_daowei_operations_autonomy: '运维自主到位',
  six_daowei_level: '六到位综合结论',
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
const fieldReview = ref({ schema_version: 1, fields: {} })
const activeStep = ref(1)
const fieldHelpTarget = ref(null)
const confirmationMode = ref(false)
const guidedLoading = ref(false)
const guidedError = ref('')
const guidedInput = ref({ schema_version: 1, sections: {} })
const guidedSectionDefinitions = ref({})
const coverage = ref({ readiness: 'not_started', round: 0, sections: {}, simple_fact_gaps: [] })
const maxFollowUpRounds = ref(3)
const showAllSimpleFacts = ref(false)

const pendingAiFields = computed(() => Object.entries(fieldReview.value?.fields || {})
  .filter(([, entry]) => ['ai_bulk', 'ai_field_help'].includes(entry?.source) && entry?.status === 'pending')
  .map(([key]) => key))

const FORM_STEPS = [
  { id: 1, label: '1 摘要与补缺' },
  { id: 2, label: '2 核算结构' },
  { id: 3, label: '3 全额资格自查' },
  { id: 4, label: '4 最终核对' },
]

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
const isComplete = computed(() =>
  sessionId.value != null
  && coverage.value?.readiness === 'ready'
  && missingFields.value.length === 0
  && pendingAiFields.value.length === 0
  && structureReady.value
)
const currentFields = ref({})
const messagesRef = ref(null)
const inputRef = ref(null)
const drawerOpen = ref(false)

function openDrawer() { drawerOpen.value = true }
function closeDrawer() { drawerOpen.value = false }

// ── 核算结构 v2：原始单元 → 组合 → 最终核算单元 → 单元级自查 ──
function emptyStructure() {
  return { schema_version: 2, source_units: [], source_units_review_status: 'confirmed', groups: [], decisions: {}, archived_decisions: [] }
}
const accountingStructure = ref(emptyStructure())
const accountingUnits = computed(() => accountingStructure.value.source_units || [])
const accountingGroups = computed(() => accountingStructure.value.groups || [])
const unitsLoading = ref(false)
const unitsSaveError = ref('')
const UNIT_TYPES = ['设备', '成品软件', '施工', '服务', '标品', '其他']
const PO_QUESTIONS = [
  { key: 'po1_independent_benefit', label: '客户能否从该商品或服务本身或结合其他易获得资源中受益？' },
  { key: 'po2_significant_integration', label: '电信是否提供重大整合服务并形成一个组合产出？' },
  { key: 'po3_modification', label: '其中一项是否对其他项进行重大修改或定制？' },
  { key: 'po4_interdependence', label: '各项是否高度依赖、无法独立交付或验收？' },
]
const UNIT_SIX_DIMENSIONS = [
  { key: 'customer_insight', label: '客情掌握到位' },
  { key: 'solution_control', label: '方案总控到位' },
  { key: 'bid_autonomy', label: '谈判/应标自主到位' },
  { key: 'procurement_autonomy', label: '采购自主到位' },
  { key: 'project_management', label: '项目强管理到位' },
  { key: 'operations_autonomy', label: '运维自主到位' },
]
const SIX_DAOWEI_OPTIONS = [
  { value: 'in_place', label: '到位' },
  { value: 'not_in_place', label: '不到位' },
  { value: 'pending_evidence', label: '待补证据' },
]
const SIX_DAOWEI_LEVEL_OPTIONS = [
  { value: 'strong', label: '强' },
  { value: 'medium', label: '中' },
  { value: 'none', label: '无' },
]
const R08_QUESTIONS = [
  { key: 'ctrl1_control_before_transfer', label: '向客户转移前已取得商品或服务控制权' },
  { key: 'ctrl2_primary_responsibility', label: '承担质量、验收及售后主要责任' },
  { key: 'ctrl3_inventory_delivery_risk', label: '承担库存、交付、返工或履约风险' },
  { key: 'ctrl4_pricing_autonomy', label: '对客户价格具有自主决定权' },
]
const R08_OPTIONS = [
  { value: 'yes', label: '是' },
  { value: 'no', label: '否' },
  { value: 'pending_evidence', label: '待补证据' },
]

function nextLocalId(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

function emptyDecision(isStandard = false) {
  return {
    listing_intent: isStandard ? 'full' : null,
    listing_intent_confirmed: isStandard,
    six_daowei: {
      facts_confirmed: false, dimensions: {}, level: null, confirmation_status: isStandard ? 'confirmed' : 'draft',
      no_external_procurement: false, no_operations_obligation: false,
    },
    r08: { answers: {}, conclusion: null, confirmation_status: isStandard ? 'confirmed' : 'draft' },
  }
}

function normalizeStructure(raw) {
  const structure = raw?.schema_version === 2 ? structuredClone(raw) : emptyStructure()
  structure.source_units ||= []
  structure.source_units_review_status = structure.source_units_review_status === 'pending' ? 'pending' : 'confirmed'
  structure.groups ||= []
  structure.decisions ||= {}
  structure.archived_decisions ||= []
  for (const [index, source] of structure.source_units.entries()) {
    source.id ||= `src-${index + 1}`
    source.logistics ??= 'unknown'
    source.has_self_capability ??= 'unknown'
    if (!['设备', '成品软件'].includes(source.declared_type)) source.whitelisted = null
  }
  for (const group of structure.groups) {
    group.id ||= nextLocalId('grp')
    group.source_unit_ids ||= []
    group.po_facts ||= {}
  }
  return structure
}

function ensureDecision(unit) {
  const decisions = accountingStructure.value.decisions
  if (!decisions[unit.id]) decisions[unit.id] = emptyDecision(unit.declared_type === '标品')
  const decision = decisions[unit.id]
  decision.six_daowei ||= emptyDecision().six_daowei
  decision.six_daowei.dimensions ||= {}
  decision.r08 ||= emptyDecision().r08
  decision.r08.answers ||= {}
  if (unit.declared_type === '标品') {
    decision.listing_intent = 'full'
    decision.listing_intent_confirmed = true
  }
  return decision
}

const finalUnits = computed(() => {
  const sources = accountingUnits.value
  const sourceById = new Map(sources.map((source) => [source.id, source]))
  const combined = new Set()
  const finals = []
  for (const group of accountingGroups.value) {
    const members = (group.source_unit_ids || []).map((id) => sourceById.get(id)).filter(Boolean)
    if (group.confirmed_relationship !== 'combined' || members.length < 2) continue
    members.forEach((member) => combined.add(member.id))
    const types = [...new Set(members.map((member) => member.declared_type))]
    const unit = {
      id: group.id, name: group.name || '组合核算单元', source_unit_ids: members.map((member) => member.id),
      declared_type: types.length === 1 ? types[0] : '组合', declared_types: types,
      relationship: 'combined', amount: members.reduce((sum, member) => sum + (Number(member.amount) || 0), 0),
    }
    unit.decision = ensureDecision(unit)
    finals.push(unit)
  }
  for (const source of sources) {
    if (combined.has(source.id)) continue
    const unit = {
      id: source.id, name: source.name || '未命名核算单元', source_unit_ids: [source.id],
      declared_type: source.declared_type, declared_types: [source.declared_type],
      relationship: 'separate', amount: source.amount,
    }
    unit.decision = ensureDecision(unit)
    finals.push(unit)
  }
  return finals
})

const fullIntentUnits = computed(() => finalUnits.value.filter((unit) => unit.decision.listing_intent === 'full'))
const needsPolicyFields = computed(() => fullIntentUnits.value.some((unit) =>
  unit.declared_types.some((type) => ['设备', '成品软件', '施工'].includes(type))
))
// 即使当前核算结构不需要项目口径字段，也要让用户能看见并处理
// 整段 AI 预填产生的值；否则会留下无法确认、也无法提交的待确认项。
const visibleListingFields = computed(() => needsPolicyFields.value
  ? LISTING_FIELDS
  : LISTING_FIELDS.filter((key) => currentFields.value[key] !== undefined || isFieldAiPending(key))
)
const groupableSources = computed(() => accountingUnits.value.filter((source) => source.declared_type !== '标品'))
const sourceUnitsNeedReview = computed(() => accountingStructure.value.source_units_review_status === 'pending')
const structureReady = computed(() => {
  if (!accountingUnits.value.length || accountingUnits.value.some((source) => source.declared_type === '其他')) return false
  if (sourceUnitsNeedReview.value) return false
  for (const group of accountingGroups.value) {
    if ((group.source_unit_ids || []).length < 2) return false
    if (PO_QUESTIONS.some((question) => !['yes', 'no'].includes(group.po_facts?.[question.key]))) return false
    if (!['combined', 'separate'].includes(group.confirmed_relationship)) return false
  }
  return finalUnits.value.every((unit) => unit.declared_type === '标品'
    || (['full', 'net'].includes(unit.decision.listing_intent) && unit.decision.listing_intent_confirmed === true))
})

async function doSegmentUnits() {
  if (!sessionId.value || unitsLoading.value) return
  unitsLoading.value = true
  try {
    const res = await segmentUnits(sessionId.value)
    accountingStructure.value = normalizeStructure(res.data.accounting_structure)
  } catch (e) {
    alert('核算单元切分失败：' + formatApiError(e))
  } finally {
    unitsLoading.value = false
  }
}

function confirmSourceUnits() {
  if (!accountingUnits.value.length) return
  accountingStructure.value.source_units_review_status = 'confirmed'
  persistUnits()
}

function onUnitTypeChange(u) {
  if (!['设备', '成品软件'].includes(u.declared_type)) u.whitelisted = null
  else if (![true, false, 'unknown'].includes(u.whitelisted)) u.whitelisted = 'unknown'
  for (const group of accountingGroups.value) {
    if (u.declared_type === '标品') group.source_unit_ids = group.source_unit_ids.filter((id) => id !== u.id)
  }
  persistUnits()
}

function addUnit() {
  accountingStructure.value.source_units.push({
    id: nextLocalId('src'),
    name: '', declared_type: '服务', amount: null, tax_rate: null,
    gross: null, logistics: 'unknown', has_self_capability: 'unknown',
    whitelisted: null, reason: '',
  })
  persistUnits()
}

function removeUnit(idx) {
  const [removed] = accountingStructure.value.source_units.splice(idx, 1)
  for (const group of accountingGroups.value) {
    group.source_unit_ids = group.source_unit_ids.filter((id) => id !== removed?.id)
  }
  persistUnits()
}

function addGroup() {
  accountingStructure.value.groups.push({
    id: nextLocalId('grp'), name: '', source_unit_ids: [], po_facts: {},
    relationship_suggestion: null, confirmed_relationship: null,
  })
}

function removeGroup(index) {
  accountingStructure.value.groups.splice(index, 1)
  persistUnits()
}

function sourceUsedByOtherGroup(sourceId, currentGroupId) {
  return accountingGroups.value.some((group) => group.id !== currentGroupId && group.source_unit_ids.includes(sourceId))
}

function toggleGroupMember(group, sourceId, checked) {
  if (checked && !group.source_unit_ids.includes(sourceId)) group.source_unit_ids.push(sourceId)
  if (!checked) group.source_unit_ids = group.source_unit_ids.filter((id) => id !== sourceId)
  group.confirmed_relationship = null
  persistUnits()
}

function groupSuggestion(group) {
  if (PO_QUESTIONS.some((question) => !['yes', 'no'].includes(group.po_facts?.[question.key]))) return null
  return group.po_facts.po1_independent_benefit === 'yes'
    && PO_QUESTIONS.slice(1).every((question) => group.po_facts[question.key] === 'no')
    ? 'separate' : 'combined'
}

function setPoFact(group, key, value) {
  group.po_facts[key] = value
  group.relationship_suggestion = groupSuggestion(group)
  group.confirmed_relationship = null
  persistUnits()
}

function confirmGroup(group, relationship) {
  group.confirmed_relationship = relationship
  persistUnits()
}

function relationshipLabel(value) {
  return { combined: '组合核算', separate: '分别核算' }[value] || '待确认'
}

function setListingIntent(unit, intent) {
  unit.decision.listing_intent = intent
  unit.decision.listing_intent_confirmed = true
  persistUnits()
}

function sixOptionsFor(unit, key) {
  const options = [...SIX_DAOWEI_OPTIONS]
  if (key === 'procurement_autonomy' && unit.decision.six_daowei.no_external_procurement) {
    options.push({ value: 'not_applicable', label: '不适用' })
  }
  if (key === 'operations_autonomy' && unit.decision.six_daowei.no_operations_obligation) {
    options.push({ value: 'not_applicable', label: '不适用' })
  }
  return options
}

function onApplicabilityChange(unit, kind) {
  const six = unit.decision.six_daowei
  if (kind === 'procurement' && !six.no_external_procurement && six.dimensions.procurement_autonomy === 'not_applicable') {
    six.dimensions.procurement_autonomy = null
  }
  if (kind === 'operations' && !six.no_operations_obligation && six.dimensions.operations_autonomy === 'not_applicable') {
    six.dimensions.operations_autonomy = null
  }
  six.confirmation_status = 'confirmed'
  persistUnits()
}

function setSixValue(unit, key, value) {
  unit.decision.six_daowei.dimensions[key] = value
  unit.decision.six_daowei.confirmation_status = 'confirmed'
  persistUnits()
}

function setSixLevel(unit, value) {
  unit.decision.six_daowei.level = value
  unit.decision.six_daowei.confirmation_status = 'confirmed'
  persistUnits()
}

function setR08Value(unit, key, value) {
  unit.decision.r08.answers[key] = value
  unit.decision.r08.confirmation_status = 'confirmed'
  persistUnits()
}

function setR08Conclusion(unit, value) {
  unit.decision.r08.conclusion = value
  unit.decision.r08.confirmation_status = 'confirmed'
  persistUnits()
}

let unitsSaveChain = Promise.resolve()
let unitsSaveRevision = 0
function persistUnits() {
  if (!sessionId.value) return Promise.resolve()
  const revision = ++unitsSaveRevision
  const payload = structuredClone(accountingStructure.value)
  unitsSaveChain = unitsSaveChain.catch(() => {}).then(async () => {
    try {
      const res = await saveUnits(sessionId.value, payload)
      if (revision === unitsSaveRevision) {
        accountingStructure.value = normalizeStructure(res.data.accounting_structure)
      }
      unitsSaveError.value = ''
    } catch {
      unitsSaveError.value = '核算单元未能保存，请检查网络后重试'
    }
  })
  return unitsSaveChain
}

// 列收模式信息独立段管的字段（27 号文，见 docs/adr/0004）——全额资格判定输入
const LISTING_FIELDS = [
  'overall_margin', 'payment_terms',
  'ownership_transfer', 'collective_procurement_ratio', 'is_capital_investment',
]
const SIX_DAOWEI_FIELDS = [
  'six_daowei_facts_confirmed', 'six_daowei_customer_insight', 'six_daowei_solution_control',
  'six_daowei_bid_autonomy', 'six_daowei_procurement_autonomy', 'six_daowei_project_management',
  'six_daowei_operations_autonomy', 'six_daowei_level',
]

// 独立段已经管的字段，不在「已解析」/「待补充」段重复渲染
const DEDICATED_FIELDS = new Set([
  'control_roles', 'service_capability_level',
  'major_integration', ...SIX_DAOWEI_FIELDS, ...LISTING_FIELDS,
])

const generalMissingFields = computed(() =>
  missingFields.value.filter(key => !DEDICATED_FIELDS.has(key))
)

const generalFormFields = computed(() => {
  const keys = showAllSimpleFacts.value
    ? new Set([...Object.keys(currentFields.value), ...generalMissingFields.value])
    : new Set([...generalMissingFields.value, ...pendingAiFields.value])
  return Object.keys(fieldDefinitions.value).filter((key) =>
    keys.has(key) && !DEDICATED_FIELDS.has(key) && !fieldDefinitions.value[key]?.deprecated
  )
})

const coverageSectionEntries = computed(() => Object.entries(guidedSectionDefinitions.value || {}).map(([key, definition]) => ({
  key,
  title: definition.title,
  summary: coverage.value?.sections?.[key]?.summary || '暂未形成摘要',
  status: coverage.value?.sections?.[key]?.status || 'missing',
})))

// 步骤一按用户掌握项目事实的自然路径组织，而不是沿用后端字段的历史定义顺序。
// 项目类型先决定适用范围，随后从前向商机一路走到交付、采购和资金事实。
const FORM_FIELD_GROUPS = [
  {
    id: 'identity', step: '1.1', title: '项目标识', description: '先确定项目类型与商机主体',
    fields: ['project_type', 'bpm_id', 'customer_type'],
  },
  {
    id: 'forward', step: '1.2', title: '前向商机与合同', description: '客户采购、合同与收入事实',
    fields: ['forward_bidding_type', 'contract_matches_bpm', 'revenue_recognition', 'is_end_user'],
  },
  {
    id: 'delivery', step: '1.3', title: '项目内容与交付', description: '项目范围、能力与交付方式',
    fields: [
      'hardware_construction', 'service_period', 'project_location',
      'has_telecom_capability', 'capability_ratio', 'service_delivery_mode',
    ],
  },
  {
    id: 'control', step: '1.4', title: '方案、实施与验收控制', description: '确认电信实际主导的交付环节',
    fields: ['scheme_reviewed', 'contract_content_same', 'acceptance_content_same', 'logistics_control'],
  },
  {
    id: 'procurement', step: '1.5', title: '后向采购与关联关系', description: '供应商、采购方式与关联事实',
    fields: ['supplier_confirmed', 'procurement_method', 'related_party', 'related_party_checked'],
  },
  {
    id: 'finance', step: '1.6', title: '财务与资金', description: '最后填写利润、预付与垫资',
    fields: ['gross_margin', 'has_prepayment', 'has_advance_funding'],
  },
]

const generalFieldGroups = computed(() => {
  const visible = new Set(generalFormFields.value)
  const groups = FORM_FIELD_GROUPS
    .map((group) => ({ ...group, fields: group.fields.filter((key) => visible.has(key)) }))
    .filter((group) => group.fields.length)
  const grouped = new Set(FORM_FIELD_GROUPS.flatMap((group) => group.fields))
  const remaining = generalFormFields.value.filter((key) => !grouped.has(key))
  if (remaining.length) {
    groups.push({
      id: 'additional', step: '1.7', title: '其他适用信息',
      description: '当前项目类型新增的补充字段', fields: remaining,
    })
  }
  return groups
})

function fieldReviewEntry(key) {
  return fieldReview.value?.fields?.[key] || null
}

function isFieldAiPending(key) {
  const entry = fieldReviewEntry(key)
  return ['ai_bulk', 'ai_field_help'].includes(entry?.source) && entry?.status === 'pending'
}

function isFieldAiAssisted(key) {
  const entry = fieldReviewEntry(key)
  return ['ai_bulk', 'ai_field_help'].includes(entry?.source) && entry?.status === 'confirmed'
}

function stepPendingFields(step) {
  if (step === 1) return generalFormFields.value.filter(isFieldAiPending)
  if (step === 3) return LISTING_FIELDS.filter(isFieldAiPending)
  return []
}

async function confirmStepAiFields(step) {
  const keys = stepPendingFields(step)
  if (!keys.length) return
  await commitFieldPatch({}, { confirmFields: keys })
}

const structurePendingMessage = computed(() => {
  if (!accountingUnits.value.length) return '请先建立至少一个原始业务单元。'
  if (sourceUnitsNeedReview.value) return '请核对并确认 AI 切分的原始业务单元。'
  if (accountingUnits.value.some((source) => source.declared_type === '其他')) return '正式诊断不能保留“其他”，请按业务实质归入明确类别。'
  for (const group of accountingGroups.value) {
    if ((group.source_unit_ids || []).length < 2) return '候选组合至少应包含两个原始单元。'
    if (PO_QUESTIONS.some((question) => !['yes', 'no'].includes(group.po_facts?.[question.key]))) return '请完成每个候选组合的四项履约关系判断。'
    if (!['combined', 'separate'].includes(group.confirmed_relationship)) return '请确认每个候选组合最终组合核算或分别核算。'
  }
  if (!finalUnits.value.every((unit) => unit.declared_type === '标品'
    || (['full', 'net'].includes(unit.decision.listing_intent) && unit.decision.listing_intent_confirmed === true))) {
    return '请为每个最终核算单元确认拟全额或拟净额列收。'
  }
  return ''
})
const pendingTotal = computed(() =>
  generalMissingFields.value.length + pendingAiFields.value.length + (structureReady.value ? 0 : 1)
)

function stepStatus(step) {
  if (step === 1) {
    if (stepPendingFields(1).length) return `待核对 ${stepPendingFields(1).length} 项`
    return generalMissingFields.value.length ? `待补充 ${generalMissingFields.value.length} 项` : '已完成'
  }
  if (step === 2) return structureReady.value ? '已完成' : (structurePendingMessage.value || '待完成')
  if (step === 3) {
    if (stepPendingFields(3).length) return `待核对 ${stepPendingFields(3).length} 项`
    return fullIntentUnits.value.length ? '按拟全额单元填写' : '无需填写'
  }
  return isComplete.value ? '可提交诊断' : '待完成'
}

const completionBlocker = computed(() => {
  if (generalMissingFields.value.length) return `基础与商务信息还缺 ${generalMissingFields.value.length} 项。`
  if (pendingAiFields.value.length) return `还有 ${pendingAiFields.value.length} 项 AI 预填内容未核对。`
  if (!structureReady.value) return structurePendingMessage.value || '请完成核算结构与列收意图。'
  return '请检查各步骤的事实是否准确。'
})

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

// ── 六到位自查：项目角色 + 服务场景证据（见 docs/adr/0003）──
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

// hardware_construction 字段定义为 bool（options: [true, false]），不是 "yes"/"no" 字符串
const hasHardware = computed(() =>
  accountingUnits.value.some(u => ['设备', '成品软件', '施工'].includes(u.declared_type))
  || currentFields.value.hardware_construction === true
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

function normalizeFieldReview(review) {
  const fields = review?.fields && typeof review.fields === 'object' ? review.fields : {}
  return { schema_version: 1, fields }
}

function applyServerState(data) {
  if (data.session_id) sessionId.value = data.session_id
  currentFields.value = normalizeFieldsFromServer(data.extracted_fields || {})
  missingFields.value = data.missing_fields || []
  if (data.field_review) fieldReview.value = normalizeFieldReview(data.field_review)
  if (data.accounting_structure) accountingStructure.value = normalizeStructure(data.accounting_structure)
  if (data.guided_input) guidedInput.value = data.guided_input
  if (data.guided_section_definitions) guidedSectionDefinitions.value = data.guided_section_definitions
  if (data.coverage) coverage.value = data.coverage
  if (data.max_follow_up_rounds) maxFollowUpRounds.value = data.max_follow_up_rounds
  if (Array.isArray(data.chat_messages)) messages.value = data.chat_messages
  if (data.ai_error) guidedError.value = String(data.ai_error)
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

async function commitFieldPatch(partial, { sources, confirmFields } = {}) {
  Object.assign(currentFields.value, partial)
  if (!sessionId.value) return
  try {
    const res = await patchSessionFields(sessionId.value, partial, { sources, confirmFields })
    applyServerState(res.data)
    return true
  } catch (e) {
    alert(`保存失败：${formatApiError(e)}`)
    return false
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

async function startNewSession() {
  try {
    const res = await createSession()
    applyServerState(res.data)
  } catch (e) {
    alert(`无法创建填写草稿：${formatApiError(e)}`)
  }
}

async function submitGuidedSections(sections) {
  if (!sessionId.value || guidedLoading.value) return
  guidedLoading.value = true
  guidedError.value = ''
  try {
    const res = await submitGuidedIntake(sessionId.value, sections)
    applyServerState(res.data)
  } catch (e) {
    guidedError.value = formatApiError(e)
  } finally {
    guidedLoading.value = false
  }
}

async function submitGuidedReply(message) {
  if (!sessionId.value || guidedLoading.value) return
  guidedLoading.value = true
  guidedError.value = ''
  try {
    const res = await replyGuidedIntake(sessionId.value, message)
    applyServerState(res.data)
  } catch (e) {
    guidedError.value = formatApiError(e)
  } finally {
    guidedLoading.value = false
  }
}

async function enterConfirmation() {
  if (coverage.value?.readiness !== 'ready' || guidedLoading.value) return
  guidedLoading.value = true
  guidedError.value = ''
  try {
    // 用户已经在六块摘要页整体确认 AI 整理结果；一次性确认其中的普通预填事实。
    const keys = [...pendingAiFields.value]
    if (keys.length) {
      const res = await patchSessionFields(sessionId.value, {}, { confirmFields: keys })
      applyServerState(res.data)
    }
    confirmationMode.value = true
    activeStep.value = 1
    showAllSimpleFacts.value = false
    drawerOpen.value = false
  } catch (e) {
    guidedError.value = formatApiError(e)
  } finally {
    guidedLoading.value = false
  }
}

onMounted(async () => {
  adjustTextareaHeight()
  try {
    const res = await fetchFieldDefinitions()
    fieldDefinitions.value = res.data || {}
  } catch {
    fieldDefinitions.value = {}
  }
  await startNewSession()
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
    const res = await supplementGuidedIntake(sessionId.value, text)
    const data = res.data
    const hasServerSnapshot = Array.isArray(data.chat_messages)
    applyServerState(data)

    let replyText = data.reply != null ? String(data.reply).trim() : ''
    if (!replyText) {
      replyText =
        '未识别到可安全预填的信息；请继续在项目事实表中填写。'
    }
    // 引导式补充接口会返回包含本轮问答的完整快照；只有兼容旧响应时才本地追加。
    if (!hasServerSnapshot) messages.value.push({ role: 'assistant', content: replyText })
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

function openFieldHelp(fieldKey) {
  fieldHelpTarget.value = fieldKey
  inputText.value = ''
  nextTick(() => inputRef.value?.focus())
}

function clearFieldHelp() {
  fieldHelpTarget.value = null
  inputText.value = ''
}

async function sendAssist() {
  if (fieldHelpTarget.value) {
    await requestFieldHelp()
    return
  }
  await sendMessage()
}

async function requestFieldHelp() {
  const text = inputText.value.trim()
  const fieldKey = fieldHelpTarget.value
  if (!text || !fieldKey || loading.value) return
  messages.value.push({ role: 'user', content: `关于「${getFieldLabel(fieldKey)}」：${text}` })
  inputText.value = ''
  loading.value = true
  await scrollToBottom()
  try {
    const res = await getFieldHelp(sessionId.value, fieldKey, text)
    const data = res.data
    const reply = [data.explanation, data.reason, data.follow_up ? `需要确认：${data.follow_up}` : '']
      .filter(Boolean).join('\n\n')
    messages.value.push({
      role: 'assistant',
      content: reply || '请按该字段的项目实际情况填写。',
      help: { fieldKey, suggestedValue: data.suggested_value, applied: false },
    })
  } catch (e) {
    messages.value.push({ role: 'assistant', content: `暂时无法提供字段建议：${formatApiError(e)}` })
  } finally {
    loading.value = false
    await scrollToBottom()
    adjustTextareaHeight()
  }
}

async function applyFieldSuggestion(help) {
  if (!help || help.applied || help.suggestedValue === null || help.suggestedValue === undefined) return
  const saved = await commitFieldPatch(
    { [help.fieldKey]: help.suggestedValue },
    { sources: { [help.fieldKey]: 'ai_field_help' } },
  )
  if (saved) help.applied = true
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
    await unitsSaveChain
    const res = await confirmDiagnosis(sessionId.value, currentFields.value)
    diagnosisId.value = res.data.diagnosis_id
    window.location.assign(`/report/${diagnosisId.value}`)
  } catch (e) {
    alert(`提交失败：${formatApiError(e)}`)
  } finally {
    clearInterval(hintTimer)
    submitting.value = false
    submittingHint.value = ''
  }
}

async function resetChat() {
  messages.value = []
  inputText.value = ''
  loading.value = false
  submitting.value = false
  sessionId.value = null
  missingFields.value = []
  diagnosisId.value = null
  currentFields.value = {}
  fieldReview.value = { schema_version: 1, fields: {} }
  fieldHelpTarget.value = null
  activeStep.value = 1
  confirmationMode.value = false
  guidedLoading.value = false
  guidedError.value = ''
  guidedInput.value = { schema_version: 1, sections: {} }
  guidedSectionDefinitions.value = {}
  coverage.value = { readiness: 'not_started', round: 0, sections: {}, simple_fact_gaps: [] }
  maxFollowUpRounds.value = 3
  showAllSimpleFacts.value = false
  accountingStructure.value = emptyStructure()
  drawerOpen.value = false
  await startNewSession()
}
</script>

<style scoped>
.layout {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* ── 次级 AI 助填区 ── */
.chat-panel {
  order: 2;
  flex: 0 0 360px;
  width: 360px;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-left: 1px solid var(--slate-200);
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

/* ── 主项目事实表 ── */
.fields-panel {
  order: 1;
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--slate-50);
  border-right: 1px solid var(--slate-200);
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
.fields-header-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
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

.diagnosis-stages {
  display: flex;
  gap: 20px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--slate-200);
  background: var(--slate-50);
  font-size: 12px;
  color: var(--slate-400);
  flex-shrink: 0;
}
.diagnosis-stages .stage-active { color: var(--blue-700); font-weight: 600; }
.form-step-nav {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}
.form-step-nav button {
  min-width: 0;
  padding: 9px 10px;
  border: 1px solid var(--slate-200);
  border-radius: var(--radius-sm);
  background: #fff;
  color: var(--slate-600);
  text-align: left;
  cursor: pointer;
}
.form-step-nav button.active { border-color: var(--blue-500); background: var(--blue-50); color: var(--blue-700); }
.form-step-nav strong, .form-step-nav span { display: block; }
.form-step-nav strong { font-size: 12px; }
.form-step-nav span { margin-top: 3px; font-size: 11px; color: var(--slate-400); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.form-step-nav button.active span { color: var(--blue-600); }
.confirmation-summary-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-bottom: 14px; }
.confirmation-summary-card { border: 1px solid var(--slate-200); border-radius: var(--radius-sm); padding: 10px 11px; background: #fff; }
.confirmation-summary-card > div { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.confirmation-summary-card strong { color: var(--slate-800); font-size: 12px; }
.confirmation-summary-card span { padding: 2px 6px; border-radius: 999px; background: var(--slate-100); color: var(--slate-500); font-size: 9px; white-space: nowrap; }
.confirmation-summary-card span.covered { color: var(--green-700); background: var(--green-50); }
.confirmation-summary-card span.partial, .confirmation-summary-card span.unknown_confirmed { color: #8a6420; background: #fff5cc; }
.confirmation-summary-card p { margin: 7px 0 0; color: var(--slate-600); font-size: 11px; line-height: 1.55; }
.confirmation-gap-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin: 3px 0 10px; padding-top: 12px; border-top: 1px solid var(--slate-100); }
.confirmation-gap-head > div { display: flex; flex-direction: column; gap: 2px; }
.confirmation-gap-head strong { color: var(--slate-800); font-size: 12px; }
.confirmation-gap-head span { color: var(--slate-400); font-size: 10px; }
.form-subgroups { display: flex; flex-direction: column; gap: 12px; }
.form-subgroup {
  padding: 11px;
  border: 1px solid var(--slate-200);
  border-radius: var(--radius-sm);
  background: var(--slate-50);
}
.form-subgroup-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 9px;
}
.form-subgroup-head > div { display: flex; align-items: center; gap: 7px; }
.form-subgroup-head strong { font-size: 12px; color: var(--slate-800); }
.form-subgroup-head > span { font-size: 11px; color: var(--slate-400); text-align: right; }
.form-subgroup-index {
  padding: 2px 6px;
  border-radius: 999px;
  background: var(--blue-50);
  color: var(--blue-700);
  font-size: 10px;
  font-weight: 700;
}
.form-field-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.primary-form-section .field-item { margin-bottom: 0; }
.field-help-btn {
  border: 0;
  padding: 0;
  background: transparent;
  color: var(--blue-600);
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}
.ai-confirmed-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  background: var(--green-50);
  color: var(--green-700);
  white-space: nowrap;
}
.step-review-band {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 12px;
  padding: 9px 10px;
  border: 1px solid var(--blue-200);
  border-radius: var(--radius-sm);
  background: var(--blue-50);
  color: var(--blue-700);
  font-size: 12px;
}
.review-status-row { display: flex; justify-content: space-between; gap: 12px; padding: 10px 2px; border-bottom: 1px solid var(--slate-100); font-size: 13px; color: var(--slate-700); }
.review-status-row strong { color: var(--slate-600); font-weight: 600; }
.final-review-note { margin: 14px 0 0; padding: 10px 12px; border-radius: var(--radius-sm); background: var(--blue-50); color: var(--blue-700); font-size: 12px; line-height: 1.6; }
.field-help-context { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 10px; padding: 8px 10px; border-radius: var(--radius-sm); background: var(--blue-50); color: var(--blue-700); font-size: 12px; }
.field-help-context button, .assistant-close { border: 0; background: transparent; color: inherit; font: inherit; cursor: pointer; }
.assistant-close { display: none; }
.apply-ai-suggestion { margin: 6px 0 0 44px; padding: 5px 9px; border: 1px solid var(--blue-300); border-radius: 12px; background: var(--blue-50); color: var(--blue-700); font-size: 11px; cursor: pointer; }
.apply-ai-suggestion:disabled { opacity: .65; cursor: default; }

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
.unit-row-whitelist { margin-top: 6px; align-items: flex-end; }
.unit-wl-hint { flex: 2; font-size: 10px; color: var(--slate-400); line-height: 1.4; }
.listing-fields-meta { font-size: 11px; color: var(--blue-600, #2563eb); }
.listing-fields-hint { font-size: 12px; color: var(--slate-500); line-height: 1.55; margin: 4px 0 8px; }
.listing-fields-hint p { margin: 0; }
.listing-fields-list { display: flex; flex-direction: column; gap: 10px; }
.listing-field-label { font-size: 12px; color: var(--slate-600, #475569); margin-bottom: 3px; }
.unit-reason { font-size: 11px; color: var(--slate-500); margin-top: 6px; line-height: 1.5; }
.units-save-error { margin-top: 8px; font-size: 12px; color: var(--red-600, #dc2626); }
.units-add-btn {
  margin-top: 8px; width: 100%; padding: 6px; border: 1px dashed var(--slate-300);
  border-radius: 8px; background: transparent; color: var(--slate-500); font-size: 12px; cursor: pointer;
}
.units-add-btn:hover { border-color: var(--blue-400); color: var(--blue-600); }

.group-card, .unit-check-card {
  border: 1px solid var(--slate-200); border-radius: 8px; padding: 12px;
  background: #fff; margin-top: 10px;
}
.group-members { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; margin: 10px 0; }
.group-member { display: flex; align-items: flex-start; gap: 7px; font-size: 11px; color: var(--slate-700); }
.group-member input { margin-top: 2px; accent-color: var(--blue-600); }
.group-member:has(input:disabled) { color: var(--slate-400); }
.po-grid { border-top: 1px solid var(--slate-100); margin-top: 8px; }
.po-row {
  display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; align-items: center;
  padding: 8px 0; border-bottom: 1px solid var(--slate-100); font-size: 11px; color: var(--slate-700);
}
.mini-segmented { display: inline-flex; border: 1px solid var(--slate-200); border-radius: 6px; overflow: hidden; flex-shrink: 0; }
.mini-segmented button {
  border: 0; border-right: 1px solid var(--slate-200); min-height: 30px; padding: 4px 10px;
  background: #fff; color: var(--slate-600); font-size: 11px; cursor: pointer; white-space: nowrap;
}
.mini-segmented button:last-child { border-right: 0; }
.mini-segmented button.active { background: var(--blue-600); color: #fff; font-weight: 700; }
.group-confirm-row, .unit-level-row {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding-top: 10px; font-size: 11px; color: var(--slate-600);
}
.final-unit-row {
  display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--slate-100);
}
.final-unit-row > div:first-child { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.final-unit-row strong { font-size: 13px; color: var(--slate-800); }
.final-unit-row span { font-size: 10px; color: var(--slate-500); }
.fixed-full-label { color: var(--green-700) !important; font-weight: 700; }
.shared-facts-title { font-size: 12px; font-weight: 700; color: var(--slate-700); margin: 12px 0 8px; }
.unit-check-card { border-left: 3px solid var(--blue-500); }
.unit-check-title { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px; }
.unit-check-title > div { display: flex; flex-direction: column; gap: 2px; }
.unit-check-title strong { font-size: 13px; color: var(--slate-800); }
.unit-check-title span { font-size: 10px; color: var(--slate-500); }
.unit-check-title label, .unit-na-row label { font-size: 10px; color: var(--slate-600); display: flex; align-items: center; gap: 5px; }
.unit-check-title input, .unit-na-row input { accent-color: var(--blue-600); }
.unit-na-row { display: flex; flex-wrap: wrap; gap: 12px; padding: 8px; background: var(--slate-50); border-radius: 6px; }
.daowei-dimension-row.compact { display: grid; grid-template-columns: minmax(120px, 1fr) minmax(210px, 1.5fr); gap: 10px; align-items: center; padding: 8px 0; }
.r08-block { margin-top: 12px; border-top: 1px solid var(--slate-200); }

/* ── 六到位自查：项目角色 + 服务场景证据（见 docs/adr/0003）── */
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
.ctrl-service-evidence { margin-bottom: 10px; }
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
.daowei-facts-confirm {
  display: flex; align-items: flex-start; gap: 8px; margin-top: 10px; padding: 9px 10px;
  border: 1px solid var(--slate-200); border-radius: 6px; background: #fff;
  color: var(--slate-700); font-size: 11px; line-height: 1.5; cursor: pointer;
}
.daowei-facts-confirm input { margin-top: 2px; accent-color: var(--blue-600); }
.daowei-step-head {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  margin-top: 14px;
}
.daowei-step-title {
  display: flex; align-items: center; gap: 7px;
  margin: 12px 0 8px; font-size: 12px; font-weight: 700; color: var(--slate-700);
}
.daowei-step-title span {
  display: inline-flex; align-items: center; justify-content: center;
  width: 20px; height: 20px; border-radius: 50%;
  background: var(--slate-700); color: #fff; font-size: 11px;
}
.daowei-adopt-btn {
  border: 1px solid var(--blue-300); border-radius: 6px; background: #fff;
  color: var(--blue-700); padding: 5px 9px; font-size: 11px; cursor: pointer;
}
.daowei-adopt-btn:hover:not(:disabled) { background: var(--blue-50); }
.daowei-adopt-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.daowei-dimensions { border-top: 1px solid var(--slate-200); }
.daowei-dimension-row {
  padding: 11px 0; border-bottom: 1px solid var(--slate-200);
}
.daowei-dimension-main {
  display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 7px;
}
.daowei-dimension-label { font-size: 12px; font-weight: 650; color: var(--slate-800); }
.daowei-suggestion {
  font-size: 10px; padding: 2px 6px; border-radius: 6px; white-space: nowrap;
  background: var(--slate-100); color: var(--slate-600);
}
.daowei-suggestion.suggest-in_place { background: #ecfdf5; color: #047857; }
.daowei-suggestion.suggest-not_in_place { background: #fef2f2; color: #b91c1c; }
.daowei-suggestion.suggest-pending_evidence { background: #fffbeb; color: #92400e; }
.daowei-segmented, .daowei-level-options {
  display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
  border: 1px solid var(--slate-200); border-radius: 6px; overflow: hidden;
}
.daowei-segmented button, .daowei-level-options button {
  min-width: 0; min-height: 32px; border: 0; border-right: 1px solid var(--slate-200);
  background: #fff; color: var(--slate-600); font-size: 11px; cursor: pointer;
}
.daowei-segmented button:last-child, .daowei-level-options button:last-child { border-right: 0; }
.daowei-segmented button.active, .daowei-level-options button.active {
  background: var(--blue-600); color: #fff; font-weight: 700;
}
.daowei-segmented button:disabled, .daowei-level-options button:disabled {
  cursor: not-allowed; color: var(--slate-400); background: var(--slate-50);
}
.daowei-basis { margin-top: 6px; font-size: 10px; line-height: 1.5; color: var(--slate-500); }
.daowei-mismatch { margin-top: 6px; font-size: 10px; line-height: 1.5; color: #92400e; }
.daowei-level-step { margin-top: 15px; }
.daowei-level-box { padding: 10px; background: var(--slate-50); border: 1px solid var(--slate-200); border-radius: 6px; }
.daowei-level-copy { display: flex; flex-direction: column; gap: 3px; margin-bottom: 8px; }
.daowei-level-copy strong { font-size: 12px; color: var(--slate-800); }
.daowei-level-copy span, .daowei-level-note { font-size: 10px; line-height: 1.5; color: var(--slate-500); }
.daowei-level-note { margin-top: 7px; }
.daowei-gate { margin-top: 8px; padding: 7px 8px; border-radius: 6px; font-size: 10px; line-height: 1.5; }
.daowei-gate-passed { background: #ecfdf5; color: #166534; border: 1px solid #bbf7d0; }
.daowei-gate-failed { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
.daowei-gate-incomplete { background: #fffbeb; color: #92400e; border: 1px solid #fde68a; }

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
.structure-pending {
  margin-bottom: 8px; padding: 8px 10px; border: 1px solid var(--yellow-200);
  border-radius: 6px; background: var(--yellow-50); color: var(--yellow-800);
  font-size: 12px; line-height: 1.55;
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
    display: block;
    overflow: visible;
  }

  .fields-panel {
    min-height: 100vh;
    border: none;
  }

  .confirmation-summary-grid { grid-template-columns: 1fr; }

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

  .drawer-trigger {
    background: var(--blue-600);
    border-color: var(--blue-600);
    color: #fff;
  }

  .chat-panel {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 200;
    width: 100%;
    height: 75vh;
    min-height: 0;
    transform: translateY(100%);
    transition: transform .3s ease;
    border: none;
    border-radius: 16px 16px 0 0;
    box-shadow: 0 -4px 24px rgba(0, 0, 0, .15);
  }
  .chat-panel.drawer-open { transform: translateY(0); }
  .chat-header { padding: 12px 14px; }
  .assistant-close { display: inline-block; }
  .form-step-nav { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .form-field-grid { grid-template-columns: 1fr; }
  .form-subgroup-head { align-items: flex-start; flex-direction: column; gap: 4px; }
  .form-subgroup-head > span { text-align: left; }
  .diagnosis-stages { gap: 10px; overflow-x: auto; white-space: nowrap; }
  .step-review-band { align-items: flex-start; flex-direction: column; }

  .group-members { grid-template-columns: 1fr; }
  .po-row, .daowei-dimension-row.compact { grid-template-columns: 1fr; }
  .group-confirm-row, .unit-level-row, .unit-check-title { align-items: flex-start; flex-direction: column; }
  .mini-segmented { width: 100%; }
  .mini-segmented button { flex: 1; }
  .final-unit-row { align-items: flex-start; flex-direction: column; }
}
</style>
