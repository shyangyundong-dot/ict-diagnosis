# 🛡 ICT项目合规诊断工具

广州电信云中台 · ICT项目合规智能诊断工具 MVP版本

---

## 快速启动

```bash
# 1. 进入项目目录
cd ict-diagnosis

# 2. 一键启动（自动安装依赖、启动前后端、打开浏览器）
./start.sh
```

访问 **http://localhost:5173** 开始使用。

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
├── start.sh                    # 一键启动脚本
├── backend/
│   ├── main.py                 # FastAPI 入口
│   ├── .env                    # 环境变量（含 API Key，勿提交 Git）
│   ├── database.py             # SQLite 数据库连接
│   ├── ai_chat.py              # DeepSeek 对话与字段提取
│   ├── report_generator.py     # HTML/PDF 报告生成
│   ├── requirements.txt
│   ├── models/
│   │   └── diagnosis.py        # 数据库模型
│   ├── routers/
│   │   └── diagnosis.py        # API 路由
│   └── rules/
│       ├── engine.py           # 规则引擎核心
│       ├── rules.json          # 规则库（R01-R30）
│       └── clauses.json        # 条款原文库
├── frontend/
│   ├── index.html
│   ├── vite.config.js
│   └── src/
│       ├── main.js
│       ├── App.vue
│       ├── api/diagnosis.js
│       └── views/
│           ├── ChatView.vue      # 对话式信息收集页
│           ├── BpmLookupView.vue    # 按 BPM 查询历史诊断
│           ├── TraceabilityView.vue # 填报溯源（字段 + 对话快照）
│           └── ReportView.vue       # 诊断报告展示页
└── data/
    └── diagnosis.db            # SQLite 数据库（自动生成）
```

---

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat` | 对话，返回AI回复和提取字段 |
| POST | `/api/confirm` | 用户确认字段，提交诊断 |
| GET  | `/api/diagnose/{id}` | 获取历史诊断报告 |
| GET  | `/api/diagnose/by-bpm?bpm_id=` | 按 BPM 商机编码列出历史诊断摘要（可多条） |
| GET  | `/api/diagnose/{id}/traceability` | 填报溯源：确认字段 + 对话快照（不写入报告正文） |
| GET  | `/api/report/{id}/html` | 获取HTML格式报告 |
| GET  | `/api/report/{id}/pdf` | 下载PDF报告 |
| GET  | `/api/health` | 健康检查 |

完整接口文档：http://localhost:8000/docs

---

## 更新规则库

规则库和条款原文库独立于代码维护，无需改代码：

- **规则逻辑**：编辑 `backend/rules/rules.json`
- **条款原文**：编辑 `backend/rules/clauses.json`

更新后重启后端即生效。每次更新请修改 `version` 字段，历史诊断记录会保留对应的规则版本号。

---

## PDF 导出（可选增强）

当前 PDF 导出：如本地安装了 `weasyprint`，生成真正的 PDF；否则自动降级为 HTML 下载。

安装 WeasyPrint（Mac）：
```bash
brew install weasyprint
pip install weasyprint
```

---

## 注意事项

- `.env` 文件含 DeepSeek API Key，请勿提交到 Git
- `data/diagnosis.db` 为诊断留痕数据库，请定期备份；每条诊断含提交时的结构化字段（`input_json`）与对话快照（`chat_snapshot_json`），可通过 `GET /api/diagnose/{id}/traceability` 或前端「填报溯源」查询，**不写入合规报告正文**
- 当前为本地开发版本，生产部署需收紧 CORS 设置
- 规则版本号记录在每条诊断记录中，便于审计追溯
