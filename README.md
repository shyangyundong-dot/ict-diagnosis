# 🛡 ICT项目合规诊断工具

广州电信云中台 · ICT项目合规智能诊断工具

> 2026-05-23 起已上线账号与权限管理模块，不再是匿名工具。首次部署需准备 admin 自举密钥（见下文「首次部署」）。

---

## 快速启动

```bash
# 1. 进入项目目录
cd ict-diagnosis

# 2. 一键启动（自动安装依赖、启动前后端、打开浏览器）
./start.sh
```

访问 **http://localhost:5173**，先用 `.env` 里配置的初始 admin 账号登录。

---

## 填报流程

新建诊断采用「六块引导说明 → AI 有限追问 → 信息预填确认 → 规则诊断」：用户先按模板用自然语言说明项目基本情况、交付内容、职责分工、验收形态、商务采购和收入成本；AI 判断这些信息能否支撑后续填表，只针对关键缺口追问，最多 3 轮。覆盖达标后，系统展示六块摘要并预填项目事实，用户确认或继续用自然语言补充，最后才进入规则引擎。

放行由服务端确定性规则裁决：形成项目及核算单元骨架、无关键矛盾、确认页简单事实缺口不超过 5 项即可进入确认；AI 额外想追问的细节只作为确认页待核对项。结构化预填必须携带用户原文证据，“暂不清楚”不会被改写成“否”；跨轮会保留既有摘要和核算单元。配置 `deepseek-v4-*` 时，结构化采集会自动关闭 thinking 并请求 JSON 输出，避免推理内容耗尽正式输出预算。

采集阶段的 AI 只做事实提取、缺口识别和摘要整理，不输出风险、列收或合规结论。详细交互和判定契约见 `docs/ai-guided-intake-redesign.md`。

---

## 首次部署

在 `backend/.env` 中按 `backend/.env.example` 配置：

```env
# 必填
DEEPSEEK_API_KEY=...
JWT_SECRET=...                          # python -c "import secrets; print(secrets.token_urlsafe(32))"
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=ChangeMeOnFirstLogin

# 生产部署必填（开发可省略，回退到 localhost:5173）
# CORS_ALLOWED_ORIGINS=https://ict.yourdomain.com
```

启动后系统检测到 user 表为空，会按 `INITIAL_ADMIN_*` 自举一个 admin 账号；首次登录后**必须修改密码**。后续账号由这个 admin 在「账号管理」页面创建。

---

## 手动启动

**后端**
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**前端**（新终端窗口）
```bash
cd frontend
npm install
npm run dev
```

---

## 项目结构

```
ict-diagnosis/
├── start.sh                          # 一键启动脚本
├── backend/
│   ├── main.py                       # FastAPI 入口；CORS / 路由注册 / admin 自举
│   ├── .env                          # 环境变量（含敏感 key，勿提交 Git）
│   ├── .env.example                  # 配置模板
│   ├── database.py                   # SQLite 连接 + schema 迁移
│   ├── auth.py                       # 密码哈希 / JWT / get_current_user / require_admin
│   ├── audit.py                      # admin 审计日志辅助
│   ├── ai_chat.py                    # DeepSeek 对话与字段提取
│   ├── guided_intake.py              # 六块模板、覆盖状态与有限追问门槛
│   ├── ai_report.py                  # 报告 AI 个性化分析
│   ├── report_generator.py           # HTML/PDF 报告生成
│   ├── session_cleanup.py            # 未完成会话定期清理
│   ├── requirements.txt
│   ├── models/
│   │   └── diagnosis.py              # 数据库模型（6 张表）
│   ├── routers/
│   │   ├── diagnosis.py              # 诊断核心路由 + 权限过滤 helper
│   │   ├── auth.py                   # 登录 / 改密 / /me
│   │   └── admin.py                  # admin 后台路由（require_admin 守卫）
│   └── rules/
│       ├── engine.py                 # 规则引擎核心 + 列收模式分类器（classify_listing_mode）
│       ├── rules.json                # 规则库（R01-R37，跳号 R04/R33，当前 v1.8.0）
│       ├── whitelist.json            # 集团白名单（27 号文，喂列收模式分类器）
│       └── clauses.json              # 条款原文库
├── frontend/
│   ├── src/
│   │   ├── main.js                   # 路由 + beforeEach 全局守卫
│   │   ├── App.vue                   # 顶栏（导航 + 用户菜单）
│   │   ├── api/
│   │   │   ├── diagnosis.js          # axios 实例 + 拦截器（Auth header + 401 处理）
│   │   │   └── admin.js              # admin 接口客户端
│   │   ├── composables/
│   │   │   └── useAuth.js            # 全局 user 态 + token 管理
│   │   ├── components/
│   │   │   └── GuidedIntakePanel.vue  # 六块自然语言填报与追问面板
│   │   └── views/
│   │       ├── LoginView.vue              # 登录
│   │       ├── ChangePasswordView.vue     # 改密（强制 + 自主两用）
│   │       ├── ChatView.vue               # 对话式信息收集 + 核算单元切分确认
│   │       ├── DiagnosesView.vue          # 诊断列表（按角色过滤行）
│   │       ├── BpmLookupView.vue          # 按 BPM 查询
│   │       ├── TraceabilityView.vue       # 填报溯源
│   │       ├── ReportView.vue             # 报告展示（含已排除列收/硬转服务）+ 人工复核弹窗
│   │       ├── AdminLinesView.vue         # admin: 线条管理
│   │       ├── AdminUsersView.vue         # admin: 账号管理
│   │       ├── AdminUserDetailView.vue    # admin: 账号详情 + 活动记录
│   │       ├── AdminLegacyClaimView.vue   # admin: 存量诊断批量认领
│   │       └── AdminAuditView.vue         # admin: 审计日志查询
├── deploy/
│   └── nginx.ict-diagnosis.conf.example   # 生产 Nginx 反代示例
├── scripts/
│   ├── make-review-bundle.sh              # 代码审查打包
│   └── make-gemini-review-bundle.sh
└── data/
    └── diagnosis.db                  # SQLite 数据库（自动生成）
```

---

## 账号与权限

**三级角色：**
- **admin** —— 全权 + 管账号/线条/审计
- **reviewer**（线条主管） —— 可看本线条所有员工的诊断 + 自己创建的；可写复核
- **user**（员工） —— 仅看自己创建的诊断；不可写复核

**数据隔离：**
- user 只能看自己的诊断、对话、BPM 查询结果
- reviewer 看本线条所有员工的 + 自己的
- admin 看全部，包括 `created_by IS NULL` 的存量数据
- 越权访问统一返回 404（不泄漏「记录存在但你看不到」）

**存量数据：** 2026-05-23 之前的 29 条诊断 `created_by` 为空，仅 admin 可见；可在「存量认领」页批量归属到具体 user/reviewer。

**审计：** admin 的写操作（建账号、改角色、重置密码、建/改线条、认领存量）落 `admin_audit_log` 表；admin 在「审计日志」页可查并筛选。

完整设计见本地 `docs/auth-and-rbac-design.md`（gitignored）。

---

## API 接口

### 认证 / 当前用户
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 登录，返回 `{ token, user }` |
| POST | `/api/auth/change-password` | 改自己的密码 |
| GET  | `/api/me` | 当前用户 profile |

### 诊断核心（除 `/api/health` 外均需登录）
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat` | 旧对话入口（保留兼容） |
| POST | `/api/session/{id}/guided-intake` | 提交六块项目说明并做首次覆盖判断 |
| POST | `/api/session/{id}/guided-reply` | 回答关键缺口；最多追问 3 轮 |
| POST | `/api/session/{id}/guided-supplement` | 确认页用自然语言补充事实并重新预填 |
| POST / PATCH | `/api/session/{id}/units` | 核算单元：POST 让 AI 切分草稿、PATCH 保存用户确认 |
| POST | `/api/confirm` | 用户确认字段，提交诊断；`project_type` 缺失返回 400 |
| GET  | `/api/diagnoses` | 合并列表，按角色过滤行 + 分页 |
| GET  | `/api/diagnose/{id}` | 获取历史诊断报告（按角色过滤；越权 404） |
| GET  | `/api/diagnose/by-bpm?bpm_id=` | 按 BPM 商机编码列出（大小写不敏感，按角色过滤） |
| GET  | `/api/diagnose/{id}/traceability` | 填报溯源 |
| POST | `/api/diagnose/{id}/review` | 提交人工复核（仅 admin 与本线条 reviewer） |
| GET  | `/api/diagnose/{id}/reviews` | 查询某条诊断的所有复核 |
| GET  | `/api/report/{id}/html` | HTML 报告（带 Authorization） |
| GET  | `/api/report/{id}/pdf` | PDF 报告下载 |
| GET  | `/api/health` | 健康检查（唯一公开端点） |

### Admin 后台
| 方法 | 路径 | 说明 |
|------|------|------|
| GET / POST | `/api/admin/lines` | 线条列表 / 新建 |
| PATCH | `/api/admin/lines/{id}` | 改名 / 启用禁用 |
| GET / POST | `/api/admin/users` | 账号列表 / 新建 |
| GET / PATCH | `/api/admin/users/{id}` | 详情 / 改 role / line / active |
| POST | `/api/admin/users/{id}/reset-password` | 重置密码 |
| GET | `/api/admin/users/{id}/activity` | 该账号的活动记录 |
| GET | `/api/admin/audit` | 审计日志查询 |
| GET | `/api/admin/legacy` | 列出存量数据 |
| POST | `/api/admin/legacy/claim` | 批量归属 |

**`/api/confirm` 与 `/api/diagnose/{id}` 响应中的关键字段：**
- `triggered_rules`：自动触发的风险规则列表
- `manual_check_rules`：需人工逐项核查的规则（系统无法自动判断）
- `tips`：操作提示（不计入风险等级）
- `audit_checklist`：汇总审计材料清单
- `accounting_units`：核算单元列表（项目按业务块切分；`listed` 为列收模式分类器的派生输出）
- `listing_mode`：列收模式判定（27 号文，级联四模式：资本/服务整合/单一履约·白名单/收支差净额；含 mode/full_listing/占比/资格闸/单元列收派生/硬否决/软提示）
- `suppressed_rules`：被抑制的规则（R24/R25 误申报轴让位单元级硬转服务 #9）
- `hard_to_service`：硬转服务嫌疑（举证式，按服务单元检测零毛利/直发/无自有能力）
- `unit_warning`：核算单元缺失软警告（含设备/系统集成等本应切分单元的项目却未切分时置位；不阻断诊断，报告顶部黄条提示退化模式）
- `control_roles_check`：控制权角色自查（项目级总额法资格，对应官方 19 角色/8 情形矩阵；4 种 status——eligible/ineligible/unfilled_wants_full/unfilled）

完整接口文档：http://localhost:8000/docs

---

## 更新规则库

规则库和条款原文库独立于代码维护：

- **规则逻辑**：编辑 `backend/rules/rules.json`
- **条款原文**：编辑 `backend/rules/clauses.json`
- **集团白名单**：编辑 `backend/rules/whitelist.json`（27 号文可全额列收的标准化硬件/成品软件大类目录）

更新后重启后端即生效。每次更新请修改 `version` 字段，历史诊断记录会保留对应的规则版本号。

---

## 测试

后端测试用 pytest，位于 `backend/tests/`：

```bash
cd backend
pip install -r requirements-dev.txt   # 含 pytest（生产 requirements.txt 不含）
pytest                                 # 配置见 backend/pytest.ini
```

当前覆盖（纯函数，无需 DB / DeepSeek，秒级跑完）：

- `test_engine_diagnosis.py` —— 规则引擎核心：基础触发、误申报抑制（R24/R25 让位 #9）、硬转服务举证检测（#9）、结果契约键
- `test_engine_listing_mode.py` —— 列收模式分类器（27 号文）：四模式/级联/两套占比/准入闸/控制权闸/物权否决/listed 派生
- `test_report_listing_mode.py` —— 列收模式判定板块渲染（四模式 / class 白名单 / XSS）
- `test_rules_listing_alignment.py` —— 全额/差额规则与 listing_mode 并立对齐（reframe 后触发不变、并立共存、版本上调）
- `test_engine_unit_warning.py` —— 核算单元缺失软警告的触发与豁免条件
- `test_enum_labels.py` —— `ai_chat` 枚举与 `ai_report` 中文标签的完整性（防英文 key 漏到报告）
- `test_report_escaping.py` —— 报告 HTML 对 AI 输出 / 用户输入 / 规则文本的转义（防 XSS）

新增规则或字段时，建议同步在此补一条断言。

---

## PDF 导出

如本地安装了 `weasyprint` 生成真正的 PDF；否则自动降级为 HTML 下载。

```bash
brew install weasyprint
pip install weasyprint
```

前端通过 fetch + blob 下载（带 `Authorization` header），不再是直链 `<a href>`。

---

## 生产部署

两种形态：

**A. Nginx 反代（推荐）**——参考 `deploy/nginx.ict-diagnosis.conf.example`：前端 `npm run build` 后的 `dist` 放静态目录，`/api/*` 反代到 uvicorn。

**B. 单进程自伺服**——若 `frontend/dist` 存在，`main.py` 会直接挂载 `/assets` 静态目录、对非 `api/` 路径做 SPA 回退（返回 `index.html`），无需 Nginx。适合轻量试运行：`npm run build` 后裸跑 uvicorn 即可同时提供 API + 前端。回退分支已做防路径穿越校验（候选路径 `.resolve()` 后必须落在 `dist` 内）；`dist` 不存在则该逻辑不启用，不影响本地开发。

部署前 checklist：
- [ ] `.env` 设了 `JWT_SECRET`（强随机）+ `INITIAL_ADMIN_*`（首次部署后建议清空 `INITIAL_ADMIN_PASSWORD`）
- [ ] `.env` 设了 `CORS_ALLOWED_ORIGINS`（你的生产域名）
- [ ] `data/diagnosis.db` 备份策略已就位
- [ ] 形态 A：后端监听 `127.0.0.1:8000`，由 Nginx 暴露；形态 B：uvicorn 直接监听对外端口（注意此时 `.env`/`data/` 与 `dist` 同处一台机，务必确认上述穿越校验已生效）

---

## 注意事项

- `.env` 含 DeepSeek API Key、JWT_SECRET、初始 admin 密码，不要提交 Git
- `data/diagnosis.db` 为诊断留痕数据库；每条诊断含提交时的六块原文（`guided_input_json`）、覆盖判断（`coverage_json`）、结构化字段（`input_json`）、对话快照（`chat_snapshot_json`）与核算单元快照（`accounting_units_json`），可通过 `GET /api/diagnose/{id}/traceability` 或前端「填报溯源」查询，**不写入合规报告正文**
- BPM 商机编号在写入和查询时均统一转为大写
- 规则库中标注 `"logic": "MANUAL"` 的规则系统无法自动判断，以「人工核查项目」板块单独列出，不计入自动风险等级
- 规则版本号记录在每条诊断记录中，便于审计追溯
