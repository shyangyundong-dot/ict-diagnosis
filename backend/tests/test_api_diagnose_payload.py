"""API 返回契约（回归外部审查 P2）：/api/diagnose/{id} 和 /api/confirm 必须
带出 ReportView.vue 依赖的所有 result 键——unit_warning（ADR 0002）和
control_roles_check（ADR 0003）此前曾遗漏，导致浏览器 SPA 报告页静默丢失
对应板块（HTML/PDF 直链报告不受影响）。
"""

import inspect

from routers import diagnosis as router_mod


# get_diagnosis 返回体里必须出现的键（基于 ReportView.vue + 报告渲染依赖）
REQUIRED_KEYS_IN_GET_DIAGNOSIS = {
    "diagnosis_id", "bpm_id", "overall_risk", "overall_risk_label",
    "triggered_rules", "tips", "audit_checklist", "manual_check_rules",
    "rule_version", "created_at", "segments", "ai_enriched",
    "is_mixed_project",
    "accounting_units", "suppressed_rules", "hard_to_service",
    # 下方三个是 ADR 0002/0003/0004 关键板块，曾因漏传导致 SPA 报告静默缺失
    "unit_warning", "control_roles_check", "listing_mode",
}


def _source_of(fn) -> str:
    return inspect.getsource(fn)


def test_get_diagnosis_returns_all_report_keys():
    """字符串扫描法：get_diagnosis 函数源码里所有必需键名都出现过。
    比起跑完整 HTTP 调用，这种契约级检查更轻、回归覆盖足够。
    """
    src = _source_of(router_mod.get_diagnosis)
    missing = [k for k in REQUIRED_KEYS_IN_GET_DIAGNOSIS if f'"{k}"' not in src]
    assert not missing, f"/api/diagnose/{{id}} 返回体遗漏关键键：{missing}"


def test_confirm_returns_all_report_keys():
    """/api/confirm 返回体（confirm_and_diagnose）同样应覆盖关键键，便于客户端直接用而非二次拉。"""
    src = _source_of(router_mod.confirm_and_diagnose)
    # confirm 必须至少含 ADR 0002/0003 的两个关键板块
    for k in ("unit_warning", "control_roles_check", "listing_mode", "accounting_units", "hard_to_service"):
        assert f'"{k}"' in src, f"/api/confirm 返回体遗漏 {k}"
