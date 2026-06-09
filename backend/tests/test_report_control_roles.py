"""报告渲染：控制权角色自查板块（P2，docs/adr/0003）。

确保四种 status 各自呈现且 missing/message 经 _esc 转义、status 走白名单。
"""

import report_generator as rg


def _base_result(ctrl):
    return {
        "overall_risk": "medium", "overall_risk_label": "中风险",
        "rule_version": "v1.7.2", "ai_enriched": False,
        "triggered_rules": [], "tips": [], "audit_checklist": [], "manual_check_rules": [],
        "accounting_units": [], "hard_to_service": [], "unit_warning": None,
        "control_roles_check": ctrl,
    }


def test_eligible_renders_green_badge():
    ctrl = {"status": "eligible", "level": "low", "missing": [],
            "message": "电信占据全部必选关键角色及三组二选一各一。"}
    html = rg.generate_report_html(1, "BPM1", _base_result(ctrl), "2026-06-09")
    assert "控制权角色自查" in html
    assert "ctrl-eligible" in html
    assert "✅ 总额法资格成立" in html


def test_ineligible_renders_red_badge_and_missing():
    ctrl = {"status": "ineligible", "level": "high",
            "missing": ["必选角色7 软硬件采购决策者", "二选一·方案"],
            "message": "未占齐关键角色，总额法资格不成立。"}
    html = rg.generate_report_html(1, "BPM1", _base_result(ctrl), "2026-06-09")
    assert "ctrl-ineligible" in html
    assert "❌ 总额法资格不成立" in html
    assert "必选角色7" in html
    assert "二选一·方案" in html


def test_unfilled_wants_full_renders_yellow_badge():
    ctrl = {"status": "unfilled_wants_full", "level": "medium", "missing": [],
            "message": "本项目明显奔全额列收，但尚未自查控制权。"}
    html = rg.generate_report_html(1, "BPM1", _base_result(ctrl), "2026-06-09")
    assert "ctrl-unfilled_wants_full" in html
    assert "⚠️ 控制权未自证" in html


def test_unfilled_renders_grey_unobtrusive():
    ctrl = {"status": "unfilled", "level": "tip", "missing": [],
            "message": "未填写控制权关键角色，未参与判定。"}
    html = rg.generate_report_html(1, "BPM1", _base_result(ctrl), "2026-06-09")
    assert "ctrl-unfilled" in html
    assert "ⓘ 未参与判定" in html


def test_no_control_roles_check_section_absent():
    """control_roles_check 为 None（如 R09 抑制后）→ 板块整段不渲染。"""
    html = rg.generate_report_html(1, "BPM1", _base_result(None), "2026-06-09")
    # 用 div class 元素的写法做断言（避开 CSS 定义里的 .ctrl-card 命中）
    assert '<div class="ctrl-card' not in html
    # 板块标题（实际渲染的 section-heading）
    assert '<div class="section-heading">控制权角色自查' not in html


def test_missing_and_message_are_escaped():
    """missing/message 走 _esc，防 XSS。"""
    ctrl = {"status": "ineligible", "level": "high",
            "missing": ["<script>alert(1)</script>"],
            "message": "<img src=x onerror=alert(2)>"}
    html = rg.generate_report_html(1, "BPM1", _base_result(ctrl), "2026-06-09")
    assert "<script>alert(1)</script>" not in html
    assert "<img src=x onerror" not in html
    assert "&lt;script&gt;" in html


def test_status_class_whitelisted():
    """恶意 status 不应污染 class 属性。"""
    ctrl = {"status": 'eligible" onmouseover="alert(1)', "level": "low",
            "missing": [], "message": "x"}
    html = rg.generate_report_html(1, "BPM1", _base_result(ctrl), "2026-06-09")
    assert "onmouseover" not in html
    # 应回退到 unfilled 白名单
    assert "ctrl-unfilled" in html
