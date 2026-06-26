# ICT 项目合规诊断工具 — AI 工作指南

广州电信云中台 · ICT项目合规智能诊断工具

---

## 项目定位

给广州电信云中台团队使用的内部工具，通过 AI 对话收集 ICT 项目的结构化字段，用规则引擎做合规风险诊断，再用 AI 生成个性化报告。不对外部开放。

2026-05-23 上线账号与权限管理模块（角色 + 线条隔离 + admin 后台），不再是匿名工具。

---

## 快速启动

```bash
./start.sh          # 一键启动前后端
# 前端：http://localhost:5173
# 后端：http://localhost:8000/docs
```

`.env` 在 `backend/` 目录下。除原有 `DEEPSEEK_API_KEY` 外，需配置：
- `JWT_SECRET`（必填）—— `python -c "import secrets; print(secrets.token_urlsafe(32))"` 生成
- `INITIAL_ADMIN_USERNAME` / `INITIAL_ADMIN_PASSWORD` —— 首次启动若 user 表为空时自举 admin
- `CORS_ALLOWED_ORIGINS` —— 生产部署必填，逗号分隔；未配置时回退开发白名单 `localhost:5173`

完整变量见 `backend/.env.example`。

---

## 技术栈

- **后端**：FastAPI + SQLite（SQLAlchemy ORM）+ DeepSeek API
- **前端**：Vue 3 + Vite（无 TypeScript，无状态管理库；用 `composables/useAuth.js` 管全局 user 态）
- **AI**：DeepSeek `deepseek-chat`，用于对话收集字段和生成个性化报告分析
- **PDF**：WeasyPrint（可选，未安装时降级为 HTML 下载）
- **认证**：JWT (HS256) + bcrypt + localStorage；7 天有效期；登出仅前端清理；禁号即时生效（每次请求查 `is_active`）

---

## 核心流程

```
登录 → 用户自然语言描述 → DeepSeek 提取结构化字段 + 切分核算单元 → 用户确认
→ 规则引擎 run_diagnosis()（列收模式级联分类 + 硬转服务检测 + 控制权自查）→ DeepSeek AI 个性化分析
→ 报告写入数据库（含 created_by + line_id + 核算单元快照）→ 前端按角色过滤展示 / PDF 下载
```

---

## 关键约定

### 规则库
- 规则文件：`backend/rules/rules.json`（当前 v1.8.0，共 35 条，编号 R01–R37，跳号 R04/R33）
- 条款原文：`backend/rules/clauses.json`
- 集团白名单：`backend/rules/whitelist.json`（27 号文，版本化大类粒度，喂列收模式分类器，见下「列收模式」）
- 改规则无需动代码，重启后端即生效；每次更新必须修改 `version` 字段
- `"logic": "MANUAL"` 的规则（R01/R05/R13/R19/R20/R28）系统不自动触发，统一收集进 `manual_check_rules` 在报告中单独展示
- 规则覆盖广东电信「六到位核查清单」六个维度（客情掌握 / 方案总控 / 谈判应标自主 / 采购自主 / 项目强管理 / 运维自主）

### 字段与项目类型
- 项目类型（`project_type`）是多选数组，决定哪些字段为必填、哪些规则生效
- `project_type` 在 `/api/confirm` 时为绝对必填，缺失返回 400
- `service_capability_level` 由系统根据 `service_delivery_mode` 推导，不接受手填
- BPM 商机编号存入和查询时统一转大写

### 核算单元（2026-06-05 上线，见 `CONTEXT.md` / `docs/adr/0002`）
- 项目按「**核算单元**」切分——一笔合同（=一个 BPM 商机）内被分别核算的业务块，每块有：申报类型（设备/施工/服务/标品）、金额、税率、毛利、物流、是否有自有能力、**是否属集团白名单**（`whitelisted` 三态，仅设备/标品有意义）。**列收方式（`listed`）不再是用户填的字段，而是分类器派生输出**（见下「列收模式」）
- AI 切分为草稿，用户在「信息解析」面板确认/微调；确认后随诊断落库（`accounting_units_json`）。**服务单元卡片可编辑驱动硬转服务检测的三信号** `gross`/`logistics`/`has_self_capability`（取值对齐引擎：`logistics ∈ {self, supplier_direct, unknown}`、`has_self_capability ∈ {true, false, unknown}`）；**设备/标品单元卡片可编辑 `whitelisted`**（`true`/`false`/`unknown`，AI 提议、用户确认、`unknown` 保守当非白名单）
- **单元角色（27 号文重构后，见 docs/adr/0004）**：第一遍项目级判列收模式时单元是**数据采集层**（贡献申报类型/金额/白名单/利润算占比）；走不通退第二遍单元才是**兜底判定单位**。`enforce_hardware_no_listing()` 语义已从「无条件钉死 `listed=False`」降级为「**设默认净额**」（铁律→默认兜底），分类器反向 upgrade 合格全额单元
- **硬转服务（举证式）**：申报为服务且列收的单元若呈现硬件/施工实质（零毛利平进平出 / 物流供应商直发 / 无自有能力）→ 标记嫌疑 + 列需举证材料，**不自动定性**；嫌疑等级计入整体风险。与列收模式正交（误申报轴 vs 正当申报硬件的全额/净额轴）
- **服务侧毛利率 `gross_margin`**（喂 R03/R12/R32/硬转服务）语义为「**应列收/服务侧毛利**」，AI 抽取与用户填写**绝不能把设备/施工毛利混算进来**（否则被硬件块拖进 `lte_0` 误报三零/过手）。**项目整体利润率另立 `overall_margin`**（含硬件、只喂列收模式门槛 ≥10%/≥5%，严禁喂三零/过手）——两者同源不同用、严禁互串
- **核算单元缺失软警告**：含设备/系统集成等本应切分单元的项目（`_UNIT_EXPECTED_TYPES`）若未切分就提交，引擎注入 `unit_warning`——**不阻断诊断**，但报告顶部黄条提示「列收模式/硬转服务检测未生效，结论可能偏严」。纯服务/软件单单元项目不触发
- 贯穿原则：**工具标风险、举证定生死，不替审核人定罪**
- 引擎入口 `run_diagnosis(project_type, fields, accounting_units=None)`；结果含 `accounting_units` / `suppressed_rules` / `hard_to_service` / `unit_warning` / `control_roles_check` / **`listing_mode`**

### 列收模式（2026-06-26 上线，见 `CONTEXT.md` / `docs/adr/0004`）
- **集团 27 号文重构**：旧「硬件/施工铁律不列收」被推翻——集团白名单硬件/成品软件在「门槛 + 控制权」齐备时可全额列收，「净额」从铁律降级为**默认兜底**
- **分类器** `classify_listing_mode(type_set, fields, units, control_status)`（`rules/engine.py` 计算式，不进 rules.json）：**级联**——第一遍项目级实质路由（资本/服务整合/单一履约/净额）套全额，过线整项目全额；走不通退第二遍逐单元白名单兜底。就地把合格全额单元的 `listed` 置 True（**派生输出**）
- **四模式实质路由**（非门槛排队）：①电信投资设备打包→资本（留出口、打标，不实现收投比门槛）②重大整合（`major_integration`）→服务整合 ③标准白名单+单独履约→单一履约·白名单 ④都不是→收支差净额
- **两套占比公式**（逐字核对 27 号文）：服务整合 `(设备+施工)/项目整体 ≤60%`（集成施工进分子）；单一履约场景一 `(设备+标品)/(设备+标品+服务) ≤80%`（施工排除出分母）。详见 `CONTEXT.md`「两套占比公式」词条
- **门槛字段**：`overall_margin`（≥10%服务整合/≥5%单一履约）；**全额准入闸硬/软分治**——硬否决=`customer_type` 闭集外（仅 private/other 软，state_owned/institution/government 过）+ `payment_terms != standard`；软=`ownership_transfer`/`collective_procurement_ratio`
- **控制权是所有全额模式的总闸门**：`control_status != "eligible"` → 全部硬件落净额
- **时点法 v1 走轻做**：占比默认全算非周期 + 报告口径提示 + 人工复核兜，未加 `recurring` 字段（升级触发点见 ADR 0004）
- **存量规则对齐**（v1.8.0）：R24/R25（误申报轴）让位单元级硬转服务 #9、被抑制；R26（物权轴）升格为单元级全额否决闸、保留为真实风险；R21/R22/R23（全额/差额单值判定）reframe 为服务/控制权视角，与 listing_mode 并立不互否
- 结果键 `listing_mode`（mode/full_listing/ratios/gates/unit_decisions/blockers/softs）；报告「列收模式判定」板块 + 前端「信息解析」面板「列收模式信息」独立段

### 控制权角色自查（2026-06-09 上线，见 `CONTEXT.md` / `docs/adr/0003`）
- **项目级**控制权判定，对应省公司《产数ICT业务高质量发展专项部署材料》（2026-06-03）**官方 19 角色 / 8 情形矩阵**。与单元级硬转服务（ADR 0002）是「同一根问题——控制权——的两个尺度」，分层互补不冲突
- **判定**：10 角色进矩阵——必选 6/7/9（涉硬件加 16）+ 三组二选一各占一个（方案 {3\|4} / 交付实施 {10\|11} / 实施开发 {13\|14}）→ 落在 8 情形之一 → 资格成立。必选与二选一**等权**
- **字段** `control_roles`：多选数组（`multi: True`，非必填），10 个编号字符串。AI 解析能抽则自动（明确说"主导/决策/责任"才抽，不臆测），否则面板手动填——spike 已证伪"AI 预勾"，角色通常需手填。引擎对字符串误输入（如 `"6,7,9"`）按分隔符拆分容错，不逐字符迭代（2026-06-10 加固）
- **采集形态**：「信息解析」面板独立段「控制权角色」，按 4 组分区（必选灰底 / 三组二选一虚框），角色 16 由 `hasHardware`（核算单元含设备/施工 或 `hardware_construction==yes`）联动显示
- **定级（举证式）**：占齐→`eligible/low`（绿正向提示）；缺任一必要元素→`ineligible/high`（红，定性倾向代理人/净额、可举证翻案）；未填但项目奔全额（R21 触发 或 `service_delivery_mode ∈ {all_telecom, mixed}`）→`unfilled_wants_full/medium`（黄）；未填+不奔全额→`unfilled/tip`（灰，留痕不打扰）
- **防撞**：R09 纯外采触发时**抑制**本检查的 ineligible（避免对纯外采项目重复报无控制权）
- **融合不替换**：R08 控制权证据核查（C1-C6 → 附件1 六维度官方表述）保留为**会计要件视角**；本检查为**流程角色视角**，两套官方框架并立、互补不重复
- 引擎入口 `assess_control_roles(control_roles, has_hardware, wants_full)`（不进 `rules.json`，组合逻辑现有 DSL 表达不了，沿用计算式模式）；结果键 `control_roles_check`

### AI 个性化分析
- 提交确认后，规则引擎先跑（同步），AI 分析后跑（并发，每条规则一次调用）
- AI 分析完成才返回响应，可能需要 30–90 秒——这是设计意图，报告必须完整
- 对话历史全部作为 AI 分析上下文（不截断条数，每条限 500 字）

### 报告渲染安全（HTML 转义红线）
- **所有拼进 HTML 的动态内容（AI 输出 / 用户输入如 `bpm_id`/核算单元名 / 规则库文本）必须先转义**，杜绝 XSS（token 存 localStorage，影响放大）
- 后端 `report_generator.py`：用模块内 `_esc()`（`html.escape`）包裹每个 f-string 插值；`suspicion_level` 这类拼进 class 属性的值要走白名单
- 前端 `ChatView.vue`/`TraceabilityView.vue` 的 `formatAiMsg()`：先转义 `&<>` 再叠加 `**加粗**`/`<br>` 等安全格式（`v-html` 渲染 AI 回复）
- 新增任何「动态值 → HTML」路径时，默认转义；回归测试见 `backend/tests/test_report_escaping.py`

### 账号与权限（2026-05-23 上线）
- **三级角色**：`admin`（全权 + 管账号）/ `reviewer`（线条主管）/ `user`（员工）
- **数据隔离**：user 仅看自己创建的；reviewer 看自己 + 本线条内全员；admin 全部（含 `created_by IS NULL` 存量）
- **诊断 `line_id` 是创建时快照**：员工调线条后旧诊断**留原线条**，新诊断走新线条（审计原则）
- **`created_by IS NULL` 是「上线前存量数据」**：admin 唯一可见；可通过「存量认领」批量归属
- **删用户 / 删线条永远软删**（`is_active=false`）；硬删会破坏审计链
- **JWT 不维护黑名单**：禁号即时生效靠 `is_active` 而非 token 失效
- **复核写权限**：仅 admin 与本线条 reviewer；user 提交复核会被 403
- **首次登录强制改密**：admin 创建账号 / 重置密码时置 `must_change_password=true`
- 完整设计见本地 `docs/auth-and-rbac-design.md`（gitignored，未入库）

### 数据库
- SQLite，文件在 `data/diagnosis.db`
- **六张表**：
  - `users`（账号）
  - `lines`（组织线条）
  - `admin_audit_log`（admin 写操作审计，读不记）
  - `diagnosis_records`（诊断记录；`created_by` + `line_id` 快照，`created_by NULL` 表示存量；`accounting_units_json` 核算单元快照）
  - `chat_sessions`（对话会话；`created_by`；`accounting_units_json` 核算单元草稿/确认）
  - `dissent_records`（人工复核；新增 `reviewer_user_id` 外键，旧 `reviewer_id` 字符串字段保留兼容）
- 会话自动清理：`status=collecting` 且 24 小时未更新的会话每 6 小时清理一次
- 启动 schema 迁移在 `database._migrate_sqlite()` 中幂等执行

---

## API 路由清单

### 认证 / 当前用户
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 登录，返回 `{ token, user }` |
| POST | `/api/auth/change-password` | 改自己的密码（需旧密码） |
| GET | `/api/me` | 当前用户 profile |

### 诊断核心
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat` | 对话，提取字段（仅创建者可续写） |
| PATCH | `/api/session/{id}/fields` | 手动修改字段（仅创建者） |
| POST / PATCH | `/api/session/{id}/units` | 核算单元：POST 让 AI 切分草稿 / PATCH 保存用户确认 |
| GET | `/api/field-definitions` | 返回字段定义 |
| POST | `/api/confirm` | 确认提交，触发诊断（写入 `created_by` + 快照 `line_id`） |
| GET | `/api/diagnose/{id}` | 读取历史报告（按角色过滤） |
| GET | `/api/diagnoses` | **合并列表**，按角色自动过滤行 + 分页 |
| GET | `/api/diagnose/by-bpm` | 按 BPM 编号查历史（大小写不敏感，按角色过滤） |
| GET | `/api/diagnose/{id}/traceability` | 填报溯源（字段 + 对话快照） |
| POST | `/api/diagnose/{id}/review` | 提交人工复核结论（仅 admin 与本线条 reviewer） |
| GET | `/api/diagnose/{id}/reviews` | 查询复核记录 |
| GET | `/api/report/{id}/html` | HTML 报告 |
| GET | `/api/report/{id}/pdf` | PDF 下载（前端走 blob，带 Authorization） |
| GET | `/api/health` | 健康检查（**唯一公开端点**） |

### Admin 后台（`require_admin` 守卫）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET / POST | `/api/admin/lines` | 列表 / 新建 |
| PATCH | `/api/admin/lines/{id}` | 改名 / 启用禁用 |
| GET / POST | `/api/admin/users` | 列表 / 新建 |
| GET / PATCH | `/api/admin/users/{id}` | 详情 / 改 role/line/active |
| POST | `/api/admin/users/{id}/reset-password` | 重置密码（置 `must_change_password=true`） |
| GET | `/api/admin/users/{id}/activity` | 该账号的诊断 / 复核 / 对话三栏 |
| GET | `/api/admin/audit` | 审计日志查询（admin / action / 日期 三组筛选） |
| GET | `/api/admin/legacy` | 列出 `created_by IS NULL` 的存量诊断 |
| POST | `/api/admin/legacy/claim` | 批量归属存量诊断 |

权限语义：越权（不是 403 而是）**404**，避免泄漏「这条记录存在但你看不到」。复核写权限例外，明确返回 403。

---

## 前端页面

| 文件 | 路由 | 谁能访问 | 功能 |
|------|------|---------|------|
| `LoginView.vue` | `/login` | 公开 | 登录（未登录唯一可访问的路由） |
| `ChangePasswordView.vue` | `/profile/password` | 任何登录用户 | 改密；`must_change_password=true` 时强制跳转 |
| `ChatView.vue` | `/` | 任何登录用户 | 主对话页，信息收集 + 核算单元切分确认（含白名单三态）+ 列收模式信息段 + 控制权角色段 + 提交 |
| `DiagnosesView.vue` | `/diagnoses` | 任何登录用户 | 合并列表，按角色过滤行 |
| `ReportView.vue` | `/report/:id` | 权限内可访问 | 报告展示（含「列收模式判定」「已排除列收」「硬转服务嫌疑」「控制权角色自查」板块）+ 人工复核弹窗（PDF 下载用 blob） |
| `BpmLookupView.vue` | `/lookup` | 任何登录用户 | 按 BPM 查历史诊断（后端按角色过滤结果） |
| `TraceabilityView.vue` | `/trace` | 权限内可访问 | 填报溯源 |
| `AdminLinesView.vue` | `/admin/lines` | admin | 线条 CRUD |
| `AdminUsersView.vue` | `/admin/users` | admin | 账号 CRUD + 重置密码 |
| `AdminUserDetailView.vue` | `/admin/users/:id` | admin | 账号详情（三标签页活动记录） |
| `AdminLegacyClaimView.vue` | `/admin/legacy-claim` | admin | 存量诊断批量认领 |
| `AdminAuditView.vue` | `/admin/audit` | admin | 审计日志查询 |

全局组件：
- 顶栏 `App.vue`：左侧导航 + 右侧用户菜单（display_name + 角色 + 改密 + 登出）；admin 区入口仅 admin 可见
- `composables/useAuth.js`：基于 `reactive` 的全局 user 态 + localStorage token；`api/diagnosis.js` 通过 axios 拦截器自动注入 `Authorization`，401 自动登出
- `main.js` 路由守卫：未登录跳 `/login`；`must_change_password=true` 强跳改密页；非 admin 访问 `/admin/*` 跳首页

---

## 测试

- pytest 测试位于 `backend/tests/`，配置 `backend/pytest.ini`，依赖 `backend/requirements-dev.txt`（生产 `requirements.txt` 不含 pytest）
- 跑：`cd backend && pip install -r requirements-dev.txt && pytest`（纯函数、无需 DB/DeepSeek、秒级）
- 覆盖（85 条）：引擎核心（#9 硬转服务 / 结果契约键）、`unit_warning` 条件、枚举↔标签完整性（`test_enum_labels.py` 防英文 key 漏到报告）、报告 XSS 转义、**控制权角色矩阵**（`test_engine_control_roles.py`）、**控制权板块渲染**（`test_report_control_roles.py`）、**API 返回契约**（`test_api_diagnose_payload.py` 防 SPA 静默丢键，含 `listing_mode`）、**铁律默认归一**（`test_units_iron_rule.py`：`enforce_hardware_no_listing` 设默认净额）、**列收模式分类器**（`test_engine_listing_mode.py` 四模式/级联/两套占比/准入闸/控制权闸/物权否决/listed 派生）、**列收模式板块渲染**（`test_report_listing_mode.py` 四模式/class 白名单/XSS）、**规则与 listing_mode 对齐**（`test_rules_listing_alignment.py` reframe 触发不变/并立共存/版本上调）、**抑制重写**（`test_engine_diagnosis.py` R24/R25 让位 #9、R26 保留物权风险）
- 新增规则/字段/「动态值→HTML」路径时，同步补一条断言
- **类型契约红线**：`ai_chat FIELD_DEFINITIONS` 的 `options` 是各字段的真值类型 source-of-truth。bool 字段（如 `hardware_construction`、`supplier_confirmed`、`is_end_user`、`is_capital_investment`）engine/前端必须用 `is True` / `=== true` 比较，不要写 `== "yes"`；字符串字段（如 `has_telecom_capability` 取 `"yes"/"no"/"partial"`）按字段定义的字面值比较。核算单元 `whitelisted` 为三态（`true`/`false`/`"unknown"`），引擎只在 `is True` 时认白名单、`unknown` 保守当非白名单

---

## 部署相关

- Nginx 反代示例：`deploy/nginx.ict-diagnosis.conf.example`（前端静态 + 后端 `/api` 同源代理）
- 代码审查打包脚本：`scripts/make-review-bundle.sh`
- start.sh 用 `--reload-exclude '.venv'` 避免误重载
- 试运行服务器 `183.131.86.84:8090`：systemd 服务 `ict-diagnosis`，单进程伺服 API + 前端 dist，scp 部署（非 git/nginx）。具体步骤见 agent 记忆 `project-deploy-runbook`

---

## 注意事项

- `.env` 含敏感信息（DeepSeek key、JWT_SECRET、初始 admin 密码），永远不提交 Git；已在 `.gitignore`
- **CORS 已从 `["*"]` 改为 env 驱动白名单**（`CORS_ALLOWED_ORIGINS`）；生产部署必须显式配置
- `data/diagnosis.db` 需定期备份
- 二期规划（N1–N6 逐项举证评分等）见 `docs/phase2-memo-service-capability-level.md`
- 账号与权限模块完整设计见 `docs/auth-and-rbac-design.md`（两份 docs 都 gitignored，是本地参考；不提交是 项目惯例）
- 领域术语表见 `CONTEXT.md`（**已入库**）：核算单元 / 列收 / 硬转服务 / 准标识符四要素 等
- ADR 见 `docs/adr/`（gitignored，本地参考）：`0001` 公网脱敏过渡方案、`0002` 按核算单元重构
- **规划中（未实现）**：内网部署受限时的「公网部署 + 客户端脱敏」过渡方案，见 `CONTEXT.md` + `docs/adr/0001` + GitHub issues #2–#6（#10/#11/#12 人工核查措辞 / 政府机关枚举 / 毛利桶洞 已于 `7d04153` 修复）
