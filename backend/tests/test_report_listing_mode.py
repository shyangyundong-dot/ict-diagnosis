"""报告渲染：列收模式判定板块（27 号文重构，docs/adr/0004）。

确保模式/占比/资格闸/单元列收派生/硬否决/软提示各自呈现，且动态值经 _esc 转义、
mode 走 class 白名单。
"""

import report_generator as rg


def _base_result(listing):
    return {
        "overall_risk": "medium", "overall_risk_label": "中风险",
        "rule_version": "v1.7.3", "ai_enriched": False,
        "triggered_rules": [], "tips": [], "audit_checklist": [], "manual_check_rules": [],
        "accounting_units": [], "hard_to_service": [], "unit_warning": None,
        "control_roles_check": None,
        "listing_mode": listing,
    }


def _lm(**over):
    base = {
        "mode": "single_fulfillment", "mode_label": "单一履约·白名单（全额）",
        "full_listing": False, "basis": "白名单设备全额，其余净额",
        "ratios": {"service_integration_pct": None, "single_fulfillment_pct": 0.7},
        "gates": [{"name": "软硬件 >100 万", "ok": True},
                  {"name": "占比 ≤80%", "ok": True, "value": "70.0%"}],
        "unit_decisions": [
            {"unit_name": "白名单设备", "declared_type": "设备", "amount": 7000000,
             "whitelisted": True, "listed": True, "listing": "全额列收"},
        ],
        "blockers": [], "softs": [],
    }
    base.update(over)
    return base


def test_single_fulfillment_renders_green_with_ratio_and_units():
    html = rg.generate_report_html(1, "BPM1", _base_result(_lm()), "2026-06-26")
    assert "列收模式判定" in html
    assert "lm-single_fulfillment" in html
    assert "70.0%" in html
    assert "白名单设备" in html
    assert "全额列收" in html


def test_service_integration_full_listing_green():
    lm = _lm(mode="service_integration", full_listing=True,
             ratios={"service_integration_pct": 0.45, "single_fulfillment_pct": None},
             unit_decisions=[{"unit_name": "设备", "declared_type": "设备", "amount": 4000000,
                              "whitelisted": True, "listed": True, "listing": "全额列收"}])
    html = rg.generate_report_html(1, "BPM1", _base_result(lm), "2026-06-26")
    assert "lm-service_integration" in html
    assert "45.0%" in html


def test_net_settlement_with_blockers_and_softs():
    lm = _lm(mode="net_settlement", full_listing=False,
             blockers=["控制权资格未成立/未自证（19 角色矩阵），全额列收总闸门未过"],
             softs=["客户类型为民企/其他，需举证属于全额准入闭集"],
             unit_decisions=[{"unit_name": "设备", "declared_type": "设备", "amount": 7000000,
                              "whitelisted": True, "listed": False, "listing": "净额"}])
    html = rg.generate_report_html(1, "BPM1", _base_result(lm), "2026-06-26")
    assert "lm-net_settlement" in html
    assert "硬否决" in html and "控制权" in html
    assert "需举证/补正" in html
    assert "净额" in html


def test_regular_mode_skips_section():
    lm = _lm(mode="regular", mode_label="常规 ICT", full_listing=True,
             ratios={}, gates=[], unit_decisions=[])
    html = rg.generate_report_html(1, "BPM1", _base_result(lm), "2026-06-26")
    assert '<div class="lm-card' not in html  # 纯服务/无硬件不渲染该板块卡片


def test_mode_class_whitelisted_against_injection():
    lm = _lm(mode='" onload="alert(1)')  # 非法 mode 不得拼进 class
    html = rg.generate_report_html(1, "BPM1", _base_result(lm), "2026-06-26")
    assert 'onload="alert(1)' not in html
    assert "lm-net_settlement" in html  # fallback 到净额类


def test_dynamic_values_escaped():
    lm = _lm(basis="<script>x</script>",
             unit_decisions=[{"unit_name": "<img src=x>设备", "declared_type": "设备",
                              "amount": 7000000, "whitelisted": True, "listed": True}],
             softs=["<b>注入</b>"])
    html = rg.generate_report_html(1, "BPM1", _base_result(lm), "2026-06-26")
    assert "<script>x</script>" not in html
    assert "&lt;img src=x&gt;设备" in html
    assert "&lt;b&gt;注入&lt;/b&gt;" in html
