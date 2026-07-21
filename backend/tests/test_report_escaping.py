"""报告 HTML 转义：AI 输出 / 用户输入 / 规则文本里的标签不得被当真渲染。

防回归：report_generator 用 f-string 拼 HTML，任何动态内容必须经 _esc()，
否则 DeepSeek 回复或 bpm_id 里的 <script> 会形成 XSS（token 存 localStorage，影响放大）。
"""

import report_generator as rg
from rules.engine import run_diagnosis


def _base_result_with_payload(payload: str) -> dict:
    return {
        "overall_risk": "high",
        "overall_risk_label": "高风险",
        "rule_version": "v1.7.1",
        "ai_enriched": True,
        "triggered_rules": [{
            "rule_id": "R02",
            "rule_name": payload,                 # 规则名注入点
            "risk_level": "high",
            "ai_risk_analysis": payload,          # AI 输出注入点
            "risk_description": "x", "remediation": "x", "optimization_direction": "x",
            "audit_materials": [{"item": payload, "purpose": payload}],
            "clause_sources": [{"doc_name": payload, "text": payload}],
        }],
        "tips": [], "audit_checklist": [], "manual_check_rules": [],
        "accounting_units": [], "hard_to_service": [], "unit_warning": None,
    }


def test_script_tag_in_ai_output_is_escaped():
    html = rg.generate_report_html(1, "BPM1", _base_result_with_payload("<script>alert(1)</script>"), "2026-06-07")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_img_onerror_in_ai_output_is_escaped():
    html = rg.generate_report_html(1, "BPM1", _base_result_with_payload("<img src=x onerror=alert(2)>"), "2026-06-07")
    assert "<img src=x onerror" not in html
    assert "&lt;img" in html


def test_bpm_id_user_input_is_escaped():
    html = rg.generate_report_html(1, "<b>BPM&amp;</b>", _base_result_with_payload("safe"), "2026-06-07")
    # 原始 <b> 标签不得出现（应被转义）
    assert "<b>BPM" not in html


def test_hard_to_service_fields_escaped():
    result = _base_result_with_payload("safe")
    result["hard_to_service"] = [{
        "unit_name": "<script>x</script>",
        "amount": 100,
        "signals": ["<b>signal</b>"],
        "suspicion_level": "high",
        "suspicion_label": "高嫌疑",
        "message": "<i>msg</i>",
        "required_evidence": ["<u>ev</u>"],
    }]
    html = rg.generate_report_html(1, "BPM1", result, "2026-06-07")
    for raw in ("<script>x</script>", "<b>signal</b>", "<i>msg</i>", "<u>ev</u>"):
        assert raw not in html, f"硬转服务字段未转义：{raw}"
    assert "历史材料" in html


def test_suspicion_level_class_is_whitelisted():
    """suspicion_level 拼进 class 属性，必须限定白名单，防属性注入。"""
    result = _base_result_with_payload("safe")
    result["hard_to_service"] = [{
        "unit_name": "u", "amount": 1, "signals": [], "suspicion_label": "嫌疑",
        "message": "m", "required_evidence": [],
        "suspicion_level": 'high" onmouseover="alert(1)',   # 恶意 level
    }]
    html = rg.generate_report_html(1, "BPM1", result, "2026-06-07")
    assert 'onmouseover' not in html


def test_unit_warning_banner_rendered_and_escaped():
    result = run_diagnosis(["system_integration"], {"project_type": ["system_integration"]}, accounting_units=[])
    result["ai_enriched"] = False
    html = rg.generate_report_html(1, "BPM1", result, "2026-06-07")
    assert "unit-warning-banner" in html
    assert "未切分核算单元" in html
