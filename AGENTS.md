# ICT 项目合规诊断工具 — AI 工作指南

广州电信云中台 · ICT项目合规智能诊断工具

---

## 项目定位

给广州电信云中台团队使用的内部工具，通过 AI 对话收集 ICT 项目的结构化字段，用规则引擎做合规风险诊断，再用 AI 生成个性化报告。不对外部开放。

---

## 快速启动

```bash
./start.sh          # 一键启动前后端
# 前端：http://localhost:5173
# 后端：http://localhost:8000/docs
```

`.env` 在 `backend/` 目录下，需配置 `DEEPSEEK_API_KEY`。

---

## 技术栈

- **后端**：FastAPI + SQLite（SQLAlchemy ORM）+ DeepSeek API
- **前端**：Vue 3 + Vite（无 TypeScript，无状态管理库）
- **AI**：DeepSeek `deepseek-chat`，用于对话收集字段和生成个性化报告分析
- **PDF**：WeasyPrint（可选，未安装时降级为 HTML 下载）

---

## 核心流程

```
用户自然语言描述 → DeepSeek 提取结构化字段 → 用户确认
→ 规则引擎 run_diagnosis() → DeepSeek AI 个性化分析
→ 报告写入数据库 → 前端展示 / PDF 下载
```

---

## 关键约定

### 规则库
- 规则文件：`backend/rules/rules.json`（当前 v1.6，共 35 条，编号 R01–R37，跳号 R04/R33）
- 条款原文：`backend/rules/clauses.json`
- 改规则无需动代码，重启后端即生效；每次更新必须修改 `version` 字段
- `"logic": "MANUAL"` 的规则（R01/R05/R13/R19/R20/R28）系统不自动触发，统一收集进 `manual_check_rules` 在报告中单独展示
- 规则覆盖广东电信「六到位核查清单」六个维度（客情掌握 / 方案总控 / 谈判应标自主 / 采购自主 / 项目强管理 / 运维自主）

### 字段与项目类型
- 项目类型（`project_type`）是多选数组，决定哪些字段为必填、哪些规则生效
- `project_type` 在 `/api/confirm` 时为绝对必填，缺失返回 400
- `service_capability_level` 由系统根据 `service_delivery_mode` 推导，不接受手填
- BPM 商机编号存入和查询时统一转大写

### AI 个性化分析
- 提交确认后，规则引擎先跑（同步），AI 分析后跑（并发，每条规则一次调用）
- AI 分析完成才返回响应，可能需要 30–90 秒——这是设计意图，报告必须完整
- 对话历史全部作为 AI 分析上下文（不截断条数，每条限 500 字）

### 数据库
- SQLite，文件在 `data/diagnosis.db`
- 三张表：`diagnosis_records`（诊断记录）、`chat_sessions`（对话会话）、`dissent_records`（人工复核）
- 会话自动清理：`status=collecting` 且 24 小时未更新的会话每 6 小时清理一次

---

## API 路由清单

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat` | 对话，提取字段 |
| PATCH | `/api/session/{id}/fields` | 手动修改字段（不触发对话） |
| GET | `/api/field-definitions` | 返回字段定义（前端下拉渲染用） |
| POST | `/api/confirm` | 确认提交，触发诊断 |
| GET | `/api/diagnose/{id}` | 读取历史报告 |
| GET | `/api/diagnose/by-bpm` | 按 BPM 编号查历史（大小写不敏感） |
| GET | `/api/diagnose/{id}/traceability` | 填报溯源（字段 + 对话快照） |
| POST | `/api/diagnose/{id}/review` | 提交人工复核结论 |
| GET | `/api/diagnose/{id}/reviews` | 查询复核记录 |
| GET | `/api/report/{id}/html` | HTML 报告 |
| GET | `/api/report/{id}/pdf` | PDF 下载 |
| GET | `/api/health` | 健康检查 |

---

## 前端页面

| 文件 | 路由 | 功能 |
|------|------|------|
| `ChatView.vue` | `/` | 主对话页，信息收集 + 提交 |
| `ReportView.vue` | `/report/:id` | 报告展示 + 人工复核弹窗 |
| `BpmLookupView.vue` | `/lookup` | 按 BPM 查历史诊断 |
| `TraceabilityView.vue` | `/trace` | 填报溯源 |

---

## 注意事项

- `.env` 含 API Key，永远不提交 Git
- 生产部署需收紧 CORS（当前全开放）
- `data/diagnosis.db` 需定期备份
- 二期规划（N1–N6 逐项举证评分等）见 `docs/phase2-memo-service-capability-level.md`
