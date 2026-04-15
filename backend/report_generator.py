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


def generate_report_html(diagnosis_id: int, bpm_id: str, result: dict, created_at: str) -> str:
    overall = result.get("overall_risk", "low")
    cfg = RISK_CONFIG.get(overall, RISK_CONFIG["low"])
    triggered = result.get("triggered_rules", [])
    tips = result.get("tips", [])
    checklist = result.get("audit_checklist", [])

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

    # 风险规则卡片HTML
    rules_html = ""
    for i, rule in enumerate(triggered, 1):
        rcfg = RISK_CONFIG.get(rule["risk_level"], RISK_CONFIG["low"])
        hrt = rule.get("high_risk_type")
        hrt_cfg = HIGH_RISK_TYPE_CONFIG.get(hrt) if hrt else None

        # 高风险子类型横幅
        hrt_banner = ""
        if hrt_cfg:
            hrt_banner = f"""
            <div class="hrt-banner" style="background:{hrt_cfg['bg']};color:{hrt_cfg['color']};">
                <span class="hrt-label">{hrt_cfg['label']}</span>
                <span class="hrt-desc">{hrt_cfg['desc']}</span>
            </div>"""

        # 条款原文
        clauses_html = ""
        for src in rule.get("clause_sources", []):
            clauses_html += f"""
            <div class="clause-item">
                <div class="clause-source">📄 {src.get('doc_name', '')}
                    {"（" + src.get('doc_code', '') + "）" if src.get('doc_code') and '【' not in src.get('doc_code','') else ""}
                </div>
                <div class="clause-text">{src.get('text', '')}</div>
            </div>"""

        # 审计材料
        mats_html = ""
        for mat in rule.get("audit_materials", []):
            mats_html += f'<div class="audit-item">☐ <strong>{mat["item"]}</strong> — {mat["purpose"]}</div>'

        rules_html += f"""
        <div class="rule-card" style="border-left: 4px solid {rcfg['color']};">
            {hrt_banner}
            <div class="rule-header">
                <span class="rule-badge" style="background:{rcfg['color']}">{rcfg['icon']} {rcfg['label']}</span>
                <span class="rule-id">{rule['rule_id']}</span>
                <span class="rule-name">{rule['rule_name']}</span>
            </div>
            <div class="rule-section">
                <div class="section-title">⚠️ 风险描述</div>
                <div class="section-body">{rule['risk_description']}</div>
            </div>
            <div class="rule-section">
                <div class="section-title">🔧 整改建议</div>
                <div class="section-body">{rule['remediation']}</div>
            </div>
            <div class="rule-section">
                <div class="section-title">📖 条款依据</div>
                <div class="section-body">{clauses_html if clauses_html else '<span class="muted">暂无条款原文</span>'}</div>
            </div>
            <div class="rule-section">
                <div class="section-title">🚀 模式优化方向</div>
                <div class="section-body">{rule['optimization_direction']}</div>
            </div>
            {"<div class='rule-section'><div class='section-title'>📂 本风险点相关审计材料</div><div class='section-body audit-mats'>" + mats_html + "</div></div>" if mats_html else ""}
        </div>"""

    # 操作提示卡片
    tips_html = ""
    for tip in tips:
        tips_html += f"""
        <div class="rule-card tip-card">
            <div class="rule-header">
                <span class="rule-badge tip-badge">📋 操作提示</span>
                <span class="rule-id">{tip['rule_id']}</span>
                <span class="rule-name">{tip['rule_name']}</span>
            </div>
            <div class="rule-section">
                <div class="section-body">{tip['remediation']}</div>
            </div>
        </div>"""

    disclaimer = "本工具诊断结论为风险等级提示，仅供参考，不作为项目列收的正式依据，不替代BPM审批流程。工具基于用户填报信息进行判断，信息失真将导致诊断结论失效。条款原文库存在更新时滞，具体认定以集团/省公司最新文件为准。"

    checklist_inner = (
        "".join(
            f'<div class="checklist-item">☐ <div><strong>{m["item"]}</strong><div class="mat-purpose">{m["purpose"]}</div></div></div>'
            for m in checklist
        )
        if checklist
        else '<p style="color:#94a3b8">无需特别准备，保持常规过程留痕即可。</p>'
    )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ICT项目合规诊断报告 — {bpm_id}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    background: #f5f7fa;
    color: #1e293b;
    font-size: 14px;
    line-height: 1.7;
  }}
  .page {{ max-width: 860px; margin: 0 auto; padding: 32px 16px 80px; }}

  /* 报告头部 */
  .report-header {{
    background: linear-gradient(135deg, #1e40af 0%, #1d4ed8 60%, #2563eb 100%);
    border-radius: 16px;
    padding: 32px 36px;
    color: #fff;
    margin-bottom: 24px;
  }}
  .report-header .logo {{ font-size: 13px; opacity: 0.75; margin-bottom: 8px; }}
  .report-header h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 4px; }}
  .report-header .meta {{ font-size: 13px; opacity: 0.8; margin-top: 12px; display:flex; gap:24px; flex-wrap:wrap; }}

  /* 总体结论卡 */
  .overall-card {{
    background: {cfg['bg']};
    border: 2px solid {cfg['border']};
    border-radius: 14px;
    padding: 28px 32px;
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    gap: 24px;
  }}
  .overall-icon {{ font-size: 52px; line-height: 1; }}
  .overall-text h2 {{ font-size: 24px; font-weight: 800; color: {cfg['color']}; }}
  .overall-text p {{ color: #475569; margin-top: 4px; font-size: 13px; }}
  .overall-notice {{
    background: #fff7ed;
    border: 1px solid #fed7aa;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 12px;
    color: #92400e;
    margin-top: 12px;
  }}

  /* 区块标题 */
  .section-heading {{
    font-size: 16px;
    font-weight: 700;
    color: #1e293b;
    margin: 28px 0 14px;
    padding-left: 12px;
    border-left: 4px solid #2563eb;
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
  .rule-name {{ font-size: 15px; font-weight: 600; color: #1e293b; }}
  .rule-section {{ padding: 14px 20px; border-bottom: 1px solid #f1f5f9; }}
  .rule-section:last-child {{ border-bottom: none; }}
  .section-title {{
    font-size: 12px;
    font-weight: 700;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 8px;
  }}
  .section-body {{ color: #334155; line-height: 1.8; font-size: 14px; }}
  .muted {{ color: #94a3b8; font-style: italic; }}

  /* 条款原文 */
  .clause-item {{ margin-bottom: 12px; }}
  .clause-source {{
    font-size: 12px;
    color: #2563eb;
    font-weight: 600;
    margin-bottom: 4px;
  }}
  .clause-text {{
    background: #f8fafc;
    border-left: 3px solid #cbd5e1;
    padding: 8px 12px;
    border-radius: 0 6px 6px 0;
    font-size: 13px;
    color: #475569;
    line-height: 1.7;
  }}

  /* 审计材料 */
  .audit-item {{ margin: 6px 0; font-size: 13px; }}
  .tip-card {{ border-left: 4px solid #2563eb !important; }}

  /* 审计清单 */
  .checklist-box {{
    background: #fff;
    border-radius: 12px;
    border: 1px solid #e2e8f0;
    padding: 20px 24px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  }}
  .checklist-item {{
    padding: 9px 0;
    border-bottom: 1px solid #f1f5f9;
    font-size: 14px;
    display: flex;
    gap: 8px;
    align-items: flex-start;
  }}
  .checklist-item:last-child {{ border-bottom: none; }}
  .mat-purpose {{ color: #64748b; font-size: 13px; }}

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
  .version-tag {{ font-family: monospace; }}

  @media print {{
    body {{ background: #fff; }}
    .page {{ padding: 20px; }}
  }}
</style>
</head>
<body>
<div class="page">

  <!-- 报告头部 -->
  <div class="report-header">
    <div class="logo">广州电信政企事业部 · ICT项目合规智能诊断工具</div>
    <h1>合规诊断报告</h1>
    <div class="meta">
      <span>📋 商机编号：{bpm_id}</span>
      <span>🕐 诊断时间：{created_at}</span>
      <span>📌 报告编号：#{diagnosis_id}</span>
      <span class="version-tag">规则版本：{result.get('rule_version', 'v1.1')}</span>
    </div>
  </div>

  <!-- 总体结论 -->
  <div class="overall-card">
    <div class="overall-icon">{cfg['icon']}</div>
    <div class="overall-text">
      <h2>{cfg['label']}</h2>
      <p>共触发 <strong>{len(triggered)}</strong> 条风险规则，<strong>{len(tips)}</strong> 条操作提示</p>
      <div class="overall-notice">⚠️ 以上结论为风险等级提示，不作为项目列收的最终依据，不替代人工审核与BPM审批流程。最终决策由审核人员做出。</div>
    </div>
  </div>

  <!-- 风险详情 -->
  {"<div class='section-heading'>风险详情分析</div>" + rules_html if triggered else "<div class='section-heading'>风险详情分析</div><div class='rule-card' style='padding:20px;color:#16a34a;'>✅ 当前填报信息未触发任何风险规则，建议保持过程留痕。</div>"}

  <!-- 操作提示 -->
  {"<div class='section-heading'>操作提示（不计入风险等级）</div>" + tips_html if tips else ""}

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
