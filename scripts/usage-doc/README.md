# 使用说明文档生成

给使用人员看的《ICT 项目合规诊断工具 — 使用说明》Word 文档由脚本生成，**docx 本身不入库**（二进制、每次重生成会污染 git 历史），只入库可复现的源头：脚本 + 截图。

## 文件

- `generate.py` —— 用 python-docx 拼装 Word（封面 / 目录 / 十章正文 / 内嵌截图）
- `screenshots/` —— 文档引用的界面截图（脚本按文件名引用）

## 重新生成

```bash
pip install python-docx
python scripts/usage-doc/generate.py
# 产物：仓库根 ICT项目合规诊断工具-使用说明.docx（gitignored）
```

路径都相对脚本自身，clone 后可直接跑。改文字只动 `generate.py`（纯文本 diff）。

## 更新截图

界面变化时才需要重截。截图用 Playwright + 本机 Chrome，对照各页面：登录 / 主对话 / 诊断列表 / BPM 查询 / 报告 / 填报溯源 / admin 三页。其中 `11_unit_warning_banner.png` 是「核算单元缺失软警告」黄条的特写——构造一个系统集成且无核算单元的诊断，渲染报告 HTML 后裁剪 `.unit-warning-banner` 元素即可。

> 截图涉及登录态和真实数据，非确定性，故按需手动更新、连同 `generate.py` 一起入库，而不是每次跑 CI 重截。
