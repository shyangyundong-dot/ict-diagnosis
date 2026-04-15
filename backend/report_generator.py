"""
PDF报告生成模块
使用纯HTML+CSS生成报告，通过WeasyPrint转换为PDF
如果WeasyPrint不可用，返回HTML格式
"""

RISK_CONFIG = {
    "high":   {"label": "高风险", "color": "#dc2626", "bg": "#fef2f2", "border": "#fca5a5", "icon": "🔴"},
    "medium": {"label": "中风险", "color": "#d97706", "bg": "#fffbeb", "border": "#fcd34d", "icon": "🟡"},
    "low":    {"label": "低风险", "color": "#16a34a", "bg": "#f0fdf4", "border": "#86efac", "icon": "🟢"},
    "tip":    {"label": "操作提示", "color": "#2563eb", "bg": "#eff6ff", "border": "#93c5fd", "icon": "📋"},
}



def _render_rule_card(
    rule: dict,
    HIGH_RISK_TYPE_CONFIG: dict,
    RISK_CONFIG: dict,
    *,
    show_ai_tag: bool = True,
) -> str:
    """渲染单张规则卡片HTML，支持AI个性化分析字段"""
    rcfg = RISK_CONFIG.get(rule["risk_level"], RISK_CONFIG["low"])
    hrt = rule.get("high_risk_type")
    hrt_cfg = HIGH_RISK_TYPE_CONFIG.get(hrt) if hrt else None

    # 高风险子类型横幅
    hrt_banner = ""
    if hrt_cfg:
        hrt_banner = f'''
        <div class="hrt-banner" style="background:{hrt_cfg['bg']};color:{hrt_cfg['color']};">
            <span class="hrt-label">{hrt_cfg['label']}</span>
            <span class="hrt-desc">{hrt_cfg['desc']}</span>
        </div>'''

    # 条款原文
    clauses_html = ""
    for src in rule.get("clause_sources", []):
        doc_code = src.get("doc_code", "")
        code_part = f"（{doc_code}）" if doc_code and "【" not in doc_code else ""
        clauses_html += f'''
        <div class="clause-item">
            <div class="clause-source">📄 {src.get("doc_name", "")}{code_part}</div>
            <div class="clause-text">{src.get("text", "")}</div>
        </div>'''

    # 审计材料（版式与条款引用框一致：浅底 + 左竖线 + 行内 ☐ 对齐）
    mats_html = ""
    for mat in rule.get("audit_materials", []):
        mats_html += (
            f'<div class="audit-item">'
            f'<span class="audit-check">☐</span>'
            f'<div class="audit-item-main">'
            f'<strong>{mat["item"]}</strong>'
            f'<span class="audit-sep"> — </span>'
            f'<span class="audit-purpose">{mat["purpose"]}</span>'
            f"</div></div>"
        )

    # AI个性化分析（优先使用，没有则降级到标准文本）
    risk_desc = rule.get("ai_risk_analysis") or rule.get("risk_description", "")
    remediation = rule.get("ai_remediation") or rule.get("remediation", "")
    optimization = rule.get("ai_optimization") or rule.get("optimization_direction", "")

    # AI标记（仅在实际启用 API 丰富化时展示，避免与规则原文混淆）
    ai_tag = (
        '<span class="ai-tag">✨ AI个性化分析</span>'
        if (show_ai_tag and rule.get("ai_risk_analysis"))
        else ""
    )

    return f'''
    <div class="rule-card" style="border-left: 4px solid {rcfg['color']};">
        {hrt_banner}
        <div class="rule-header">
            <span class="rule-badge" style="background:{rcfg['color']}">{rcfg['icon']} {rcfg['label']}</span>
            <span class="rule-id">{rule['rule_id']}</span>
            <span class="rule-name">{rule['rule_name']}</span>
            {ai_tag}
        </div>
        <div class="rule-section">
            <div class="section-title">⚠️ 风险分析</div>
            <div class="section-body">{risk_desc}</div>
        </div>
        <div class="rule-section highlight-section">
            <div class="section-title">🔧 整改建议</div>
            <div class="section-body">{remediation}</div>
        </div>
        <div class="rule-section">
            <div class="section-title">📖 条款依据</div>
            <div class="section-body">{clauses_html if clauses_html else '<span class="muted">暂无条款原文</span>'}</div>
        </div>
        <div class="rule-section optimize-section">
            <div class="section-title">🚀 模式优化方向</div>
            <div class="section-body">{optimization}</div>
        </div>
        {f'<div class="rule-section audit-materials-section"><div class="section-title">📁 本风险点相关审计材料</div><div class="section-body"><div class="audit-mats">{mats_html}</div></div></div>' if mats_html else ""}
    </div>'''


def _render_segment(
    seg: dict,
    HIGH_RISK_TYPE_CONFIG: dict,
    RISK_CONFIG: dict,
    *,
    show_ai_tag: bool = True,
) -> str:
    """渲染一个业务板块（含板块标题、总述、规则列表）"""
    label = seg.get("segment_label", "")
    overview = seg.get("overview", "")
    triggered = seg.get("triggered_rules", [])
    tips = seg.get("tips", [])

    if seg.get("segment_id") == "tips":
        # 操作提示板块
        tips_html = ""
        for tip in tips:
            tips_html += f'''
        <div class="rule-card tip-card">
            <div class="rule-header">
                <span class="rule-badge tip-badge">📋 操作提示</span>
                <span class="rule-id">{tip['rule_id']}</span>
                <span class="rule-name">{tip['rule_name']}</span>
            </div>
            <div class="rule-section">
                <div class="section-body">{tip.get("ai_remediation") or tip.get("remediation", "")}</div>
            </div>
        </div>'''
        return f'<div class="section-heading tips-heading">操作提示 <span class="heading-sub">（不计入风险等级）</span></div>{tips_html}'

    if not triggered and not tips:
        # 与 report_test.html 一致：蓝条左侧仍用 📦，右侧为「✅ 无风险」胶囊标
        return f'''
    <div class="segment-block">
        <div class="segment-header">
            <span class="segment-icon">📦</span>
            <span class="segment-title">{label}</span>
            <span class="segment-count" style="background:rgba(255,255,255,0.15);">✅ 无风险</span>
        </div>
        <div class="segment-ok">该业务板块未触发风险规则，请保持过程留痕。</div>
    </div>'''

    rules_cards = "".join(
        _render_rule_card(r, HIGH_RISK_TYPE_CONFIG, RISK_CONFIG, show_ai_tag=show_ai_tag)
        for r in triggered
    )
    rules_html = f'<div class="segment-rules-container">{rules_cards}</div>' if rules_cards else ""

    overview_block = ""
    if overview:
        overview_block = f'<div class="segment-overview">{overview}</div>'

    return f'''
    <div class="segment-block">
        <div class="segment-header">
            <span class="segment-icon">📦</span>
            <span class="segment-title">{label}</span>
            <span class="segment-count">{len(triggered)} 条风险</span>
        </div>
        {overview_block}
        {rules_html}
    </div>'''


def generate_report_html(diagnosis_id: int, bpm_id: str, result: dict, created_at: str) -> str:
    overall = result.get("overall_risk", "low")
    cfg = RISK_CONFIG.get(overall, RISK_CONFIG["low"])
    triggered = result.get("triggered_rules", [])
    tips = result.get("tips", [])
    checklist = result.get("audit_checklist", [])
    # 后端在成功调用 DeepSeek 做丰富化后置 ai_enriched=True；未配置 Key、无触发项或异常时为 False
    show_ai = bool(result.get("ai_enriched"))

    # 高风险子类型配置
    HIGH_RISK_TYPE_CONFIG = {
        "forbidden": {
            "label": "🚫 禁止做",
            "desc": "该项目不符合合规条件，不得推进",
            "bg": "#450a0a", "color": "#fff", "bar": "#7f1d1d",
        },
        "no_revenue": {
            "label": "❌ 不可列收",
            "desc": "该部分收入不得列入，需调整收入归属或差额处理",
            "bg": "#7c2d12", "color": "#fff", "bar": "#9a3412",
        },
        "no_full_revenue": {
            "label": "⚠️ 不可全额列收",
            "desc": "不满足全额列收条件，须采用差额法或经审批",
            "bg": "#78350f", "color": "#fff", "bar": "#92400e",
        },
    }

    # 风险规则渲染（支持AI分段 / 降级兼容）
    segments = result.get("segments")

    if segments:
        # A+B方案：按板块分节渲染
        main_content_html = ""
        for seg in segments:
            main_content_html += _render_segment(
                seg, HIGH_RISK_TYPE_CONFIG, RISK_CONFIG, show_ai_tag=show_ai
            )
        # 操作提示已在段内，rules_html / tips_html 置空
        rules_html = ""
        tips_html = ""
    else:
        # 降级：原始平铺渲染
        rules_html = ""
        for i, rule in enumerate(triggered, 1):
            rules_html += _render_rule_card(
                rule, HIGH_RISK_TYPE_CONFIG, RISK_CONFIG, show_ai_tag=show_ai
            )
        tips_html = ""
        main_content_html = None

    # 操作提示卡片（仅在降级模式下生成，segments模式已在板块内处理）
    if not segments:
        for tip in tips:
            tips_html += f"""
        <div class="rule-card tip-card">
            <div class="rule-header">
                <span class="rule-badge tip-badge">📋 操作提示</span>
                <span class="rule-id">{tip['rule_id']}</span>
                <span class="rule-name">{tip['rule_name']}</span>
            </div>
            <div class="rule-section">
                <div class="section-body">{tip.get('ai_remediation') or tip.get('remediation', '')}</div>
            </div>
        </div>"""

    rule_ver = result.get("rule_version", "v1.1")
    _disclaimer_tail = (
        f"<br>本结论基于规则版本 <strong>{rule_ver}</strong> 生成。 AI个性化分析由 DeepSeek V3 生成，仅供参考。"
        if show_ai
        else f"<br>本结论基于规则版本 <strong>{rule_ver}</strong> 生成。"
    )
    disclaimer = (
        "本工具诊断结论为风险等级提示，仅供参考，不作为项目列收的正式依据，不替代BPM审批流程。"
        "工具基于用户填报信息进行判断，信息失真将导致诊断结论失效。条款原文库存在更新时滞，具体认定以集团/省公司最新文件为准。"
        + _disclaimer_tail
    )

    checklist_inner = (
        "".join(
            f'<div class="checklist-item"><span class="mat-checkbox">☐</span><div><strong>{m["item"]}</strong>'
            f'<div class="mat-purpose">{m["purpose"]}</div></div></div>'
            for m in checklist
        )
        if checklist
        else '<p style="color:#94a3b8">无需特别准备，保持常规过程留痕即可。</p>'
    )

    seg_note = " · 已按业务板块分节分析" if segments else ""
    overall_summary_line = (
        f'共触发 <strong>{len(triggered)}</strong> 条风险规则 · <strong>{len(tips)}</strong> 条操作提示{seg_note}'
    )

    # 预处理f-string内不能含反斜杠的表达式（Python 3.11兼容）
    _sh = "section-heading"
    _heading_risk_plain = f'<div class="{_sh}">风险详情分析</div>'
    _heading_risk_ai = (
        f'<div class="{_sh}">风险详情分析 <span class="heading-ai-tag">✨ AI个性化</span></div>'
    )
    _risk_heading = _heading_risk_ai if show_ai else _heading_risk_plain
    _no_triggered = (
        f'<div class="{_sh}">风险详情分析</div>'
        f'<div class="rule-card" style="padding:20px;color:#16a34a;">'
        f'✅ 当前填报信息未触发任何风险规则，建议保持过程留痕。</div>'
    )
    if main_content_html is not None:
        _risk_section_html = _risk_heading + main_content_html
    elif triggered:
        _risk_section_html = _risk_heading + rules_html
    else:
        _risk_section_html = _no_triggered
    _tips_label = f'<div class="{_sh}">操作提示 <span class="heading-sub">(不计入风险等级)</span></div>'
    _tips_section_html = (_tips_label + tips_html) if (tips_html and main_content_html is None) else ""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ICT项目合规诊断报告 — {bpm_id}</title>
<style>
  /* 与产品稿对齐：主字色 #333、次级 #4b5563、条款链接 #315efb、引用底 #f4f7fb */
  /* PDF：A4 分页 + 版心（与网页 max-width 880px 视觉接近，但按纸张宽度自适应，避免整页被缩成窄条） */
  @page {{
    size: A4;
    margin: 12mm 14mm;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html {{ background: #fff; }}
  body {{
    font-family: system-ui, -apple-system, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    background: #fff;
    color: #333333;
    font-size: 14px;
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
  }}
  .page {{
    max-width: 100%;
    width: 100%;
    margin: 0 auto;
    padding: 0 0 24px;
  }}

  /* 报告头部 */
  .report-header {{
    background: linear-gradient(135deg, #1e40af 0%, #1d4ed8 60%, #2563eb 100%);
    border-radius: 16px;
    padding: 28px 32px;
    color: #fff;
    margin-bottom: 20px;
    page-break-inside: avoid;
    break-inside: avoid;
  }}
  .report-header .logo {{ font-size: 13px; opacity: 0.75; margin-bottom: 8px; }}
  .report-header h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 4px; }}
  .report-header .meta {{ font-size: 13px; opacity: 0.8; margin-top: 12px; display:flex; gap:24px; flex-wrap:wrap; }}

  /* 总体结论卡（与 report_test.html 一致：左侧图标 + 右侧文案列） */
  .overall-card {{
    background: {cfg['bg']};
    border: 2px solid {cfg['border']};
    border-radius: 14px;
    padding: 24px 28px;
    margin-bottom: 24px;
    page-break-inside: avoid;
    break-inside: avoid;
  }}
  .overall-left {{
    display: flex;
    align-items: center;
    gap: 20px;
  }}
  .overall-icon {{ font-size: 52px; line-height: 1; flex-shrink: 0; }}
  .overall-text {{ flex: 1; min-width: 0; }}
  .overall-text h2 {{ font-size: 24px; font-weight: 800; color: {cfg['color']}; }}
  .overall-text p {{ color: #4b5563; margin-top: 4px; font-size: 13px; line-height: 1.6; }}
  .overall-notice {{
    background: #fff7ed;
    border: 1px solid #fed7aa;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 12px;
    color: #92400e;
    margin-top: 12px;
  }}

  /* 区块标题（报告级大标题） */
  .section-heading {{
    font-size: 16px;
    font-weight: 700;
    color: #333333;
    margin: 28px 0 14px;
    padding-left: 12px;
    border-left: 4px solid #2563eb;
    display: flex;
    align-items: center;
    gap: 8px;
    page-break-after: avoid;
    break-after: avoid;
  }}
  .heading-sub {{ font-size: 12px; font-weight: 400; color: #94a3b8; }}
  .heading-ai-tag {{
    font-size: 12px;
    padding: 2px 8px;
    border-radius: 12px;
    background: linear-gradient(90deg, #7c3aed, #2563eb);
    color: #fff;
    font-weight: 500;
  }}

  /* 高风险子类型横幅 */
  .hrt-banner {{
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 9px 20px;
    font-size: 13px;
  }}
  .hrt-label {{
    font-weight: 800;
    font-size: 14px;
    white-space: nowrap;
    letter-spacing: 0.02em;
  }}
  .hrt-desc {{
    opacity: 0.85;
    font-size: 12px;
  }}

  /* 业务板块 */
  .segment-block {{
    margin-bottom: 28px;
    border-radius: 14px;
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  }}
  .segment-header {{
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 16px 24px;
    background: linear-gradient(135deg, #1e40af 0%, #2563eb 100%);
    color: #fff;
    page-break-after: avoid;
    break-after: avoid;
  }}
  .segment-icon {{ font-size: 20px; }}
  .segment-title {{
    font-size: 16px;
    font-weight: 700;
    color: #fff;
    flex: 1;
  }}
  .segment-count {{
    font-size: 12px;
    background: rgba(255,255,255,0.2);
    color: #fff;
    padding: 3px 12px;
    border-radius: 20px;
    font-weight: 600;
  }}
  .segment-overview {{
    padding: 16px 24px;
    background: #f0f9ff;
    border-bottom: 1px solid #e0f2fe;
    font-size: 14px;
    color: #0369a1;
    line-height: 1.8;
    border-left: 4px solid #2563eb;
  }}
  .segment-ok {{
    padding: 16px 24px;
    background: #f0fdf4;
    color: #16a34a;
    font-size: 14px;
  }}
  .segment-rules-container {{
    padding: 12px;
    background: #f8fafc;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }}
  .segment-rules-container .rule-card {{
    border-radius: 10px !important;
    border: 1px solid #e2e8f0 !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
    margin-bottom: 0 !important;
  }}
  /* 板块内卡片通过 segment-rules-container 控制，不覆盖颜色条 */
  .tips-heading {{
    margin-top: 24px;
  }}
  /* AI个性化标签（规则卡片标题行） */
  .ai-tag {{
    display: inline-block;
    font-size: 11px;
    background: linear-gradient(90deg, #7c3aed, #2563eb);
    color: #fff;
    padding: 2px 8px;
    border-radius: 10px;
    font-weight: 500;
    vertical-align: middle;
  }}
  /* 整改建议高亮 */
  .highlight-section {{ background: #fffbeb; }}
  .optimize-section {{ background: #f0fdf4; }}

  /* 规则卡片 */
  .rule-card {{
    background: #fff;
    border-radius: 12px;
    border: 1px solid #e2e8f0;
    margin-bottom: 16px;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  }}
  .rule-header {{
    padding: 14px 20px;
    background: #f8fafc;
    border-bottom: 1px solid #e2e8f0;
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    page-break-after: avoid;
    break-after: avoid;
  }}
  .rule-badge {{
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    color: #fff;
    font-size: 12px;
    font-weight: 600;
  }}
  .tip-badge {{ background: #2563eb; }}
  .rule-id {{ font-size: 12px; color: #94a3b8; font-family: monospace; }}
  .rule-name {{ font-size: 15px; font-weight: 600; color: #333333; }}
  .rule-section {{ padding: 16px 20px; border-bottom: 1px solid #f1f5f9; }}
  .rule-section:last-child {{ border-bottom: none; }}
  /* 卡片内小节标题（风险分析 / 条款依据 等），不用 uppercase 以免中文异常 */
  .section-title {{
    font-size: 13px;
    font-weight: 700;
    color: #333333;
    text-transform: none;
    letter-spacing: 0.02em;
    margin-bottom: 10px;
  }}
  .section-body {{ color: #4b5563; line-height: 1.6; font-size: 14px; white-space: pre-wrap; }}
  .muted {{ color: #94a3b8; font-style: italic; }}
  .highlight-section {{ background: #fffbeb !important; }}
  .optimize-section {{ background: #f0fdf4 !important; }}

  /* 条款原文：文档标题蓝 + 浅灰蓝引用框 */
  .clause-item {{ margin-bottom: 16px; }}
  .clause-item:last-child {{ margin-bottom: 0; }}
  .clause-source {{
    font-size: 13px;
    color: #315efb;
    font-weight: 600;
    margin-bottom: 8px;
    line-height: 1.5;
  }}
  .clause-text {{
    background: #f4f7fb;
    border-left: 3px solid #cbd5e1;
    padding: 14px 16px;
    border-radius: 6px;
    font-size: 14px;
    color: #4b5563;
    line-height: 1.6;
  }}

  /* 规则内：本风险点相关审计材料（与条款 clause-text 同系色） */
  .audit-materials-section .section-body {{ padding-top: 0; }}
  .audit-mats {{
    background: #f4f7fb;
    border-left: 3px solid #cbd5e1;
    border-radius: 6px;
    padding: 12px 14px;
  }}
  .audit-item {{
    display: flex;
    gap: 10px;
    align-items: flex-start;
    padding: 8px 0;
    font-size: 14px;
    color: #4b5563;
    line-height: 1.6;
    border-bottom: 1px solid #e2e8f0;
  }}
  .audit-item:first-child {{ padding-top: 0; }}
  .audit-item:last-child {{ border-bottom: none; padding-bottom: 0; }}
  .audit-check {{ color: #94a3b8; flex-shrink: 0; margin-top: 2px; font-size: 14px; }}
  .audit-item-main {{ flex: 1; min-width: 0; }}
  .audit-item-main strong {{ color: #333333; font-weight: 600; }}
  .audit-sep {{ color: #9ca3af; }}
  .audit-purpose {{ color: #6b7280; }}
  .tip-card {{ border-left: 4px solid #2563eb !important; }}

  /* 审计清单 */
  .checklist-box {{
    background: #fff;
    border-radius: 12px;
    border: 1px solid #e2e8f0;
    padding: 6px 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  }}
  .checklist-item {{
    padding: 10px 0;
    border-bottom: 1px solid #f1f5f9;
    font-size: 14px;
    display: flex;
    gap: 10px;
    align-items: flex-start;
  }}
  .checklist-item:last-child {{ border-bottom: none; }}
  .mat-checkbox {{ color: #94a3b8; flex-shrink: 0; margin-top: 2px; }}
  .mat-purpose {{ color: #6b7280; font-size: 12px; margin-top: 2px; line-height: 1.5; }}

  /* 免责声明 */
  .disclaimer {{
    margin-top: 32px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 14px 18px;
    font-size: 12px;
    color: #94a3b8;
    line-height: 1.7;
  }}
  @media print {{
    body {{ background: #fff; }}
    .page {{ padding: 0 0 16px; max-width: 100%; }}
  }}
</style>
</head>
<body>
<div class="page">

  <!-- 报告头部 -->
  <div class="report-header">
    <div class="logo">广州电信云中台 · ICT项目合规智能诊断工具</div>
    <h1>合规诊断报告</h1>
    <div class="meta">
      <span>📋 商机编号：{bpm_id}</span>
      <span>🕐 诊断时间：{created_at}</span>
      <span>📌 报告编号：#{diagnosis_id}</span>
      <span>规则版本：{rule_ver}</span>
    </div>
  </div>

  <!-- 总体结论 -->
  <div class="overall-card">
    <div class="overall-left">
      <div class="overall-icon">{cfg['icon']}</div>
      <div class="overall-text">
        <h2>{cfg['label']}</h2>
        <p>{overall_summary_line}</p>
        <div class="overall-notice">⚠️ 以上结论为风险等级提示，不作为项目列收的最终依据，不替代人工审核与BPM审批流程。最终决策由审核人员做出。</div>
      </div>
    </div>
  </div>

  <!-- 风险详情：segments模式按板块分节，降级模式平铺 -->
  {_risk_section_html}

  <!-- 操作提示（降级模式）-->
  {_tips_section_html}

    <!-- 审计材料清单 -->
  <div class="section-heading">审计资料必备清单</div>
  <div class="checklist-box">
    {checklist_inner}
  </div>

  <!-- 免责声明 -->
  <div class="disclaimer">
    <strong>免责声明：</strong>{disclaimer}
  </div>

</div>
</body>
</html>"""
    return html


async def generate_pdf(html_content: str) -> bytes | None:
    """尝试用WeasyPrint生成PDF，失败则返回None"""
    try:
        from weasyprint import HTML
        return HTML(string=html_content).write_pdf()
    except ImportError:
        return None
    except Exception:
        return None
