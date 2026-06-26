"""35 规则重审：全额/差额单值判定（R21/R22/R23）与新列收模式分类器并立对齐
（27 号文重构，docs/adr/0004）。

确认：(1) reframe 后 R21/R22/R23/R26 触发条件**未变**（仅措辞交叉引用 listing_mode）；
(2) 服务/控制权视角的 R21/R22 可与硬件/整体视角的 listing_mode **并立共存、不互相否决**；
(3) 规则库版本已随重构上调。
"""
import json
import os

from rules.engine import run_diagnosis, RULES, RULE_VERSION

W = 10000


def _rule(rid):
    return next(r for r in RULES if r["id"] == rid)


def _ids(items):
    return {it["rule_id"] for it in items}


def test_version_bumped_for_27hao():
    # 27 号文重构是规则库的实质改动，版本须上调到 v1.8.x
    assert RULE_VERSION >= "v1.8", f"规则库版本未随 27 号文重构上调：{RULE_VERSION}"


def test_listing_rules_cross_reference_listing_mode():
    """R21/R22/R23/R26 措辞已交叉引用「列收模式判定」/ADR 0004，避免与 listing_mode 结论打架。"""
    assert "列收模式判定" in _rule("R21")["risk_description"]
    assert "列收模式判定" in _rule("R22")["risk_description"]
    assert "0004" in _rule("R23")["risk_description"]
    assert "否决闸" in _rule("R26")["remediation"]


def test_triggers_unchanged():
    """reframe 只动措辞，触发条件不变（防误改逻辑）。"""
    assert _rule("R21")["trigger"]["conditions"][0]["field"] == "has_telecom_capability"
    assert _rule("R21")["trigger"]["conditions"][1]["value"] == ["medium", "high"]
    assert _rule("R22")["trigger"]["conditions"][1]["value"] == "very_low"
    assert _rule("R26")["trigger"]["conditions"][0]["field"] == "logistics_control"


def test_r21_coexists_with_listing_mode_net_settlement():
    """服务侧 R21（主要责任人/全额法）触发，同时硬件侧因控制权未占齐落 net_settlement——
    两套尺度并立，报告同时呈现、不矛盾、不崩。"""
    fields = {
        "project_type": ["system_integration"],
        "has_telecom_capability": "yes", "capability_ratio": "high",  # → R21 触发
        "major_integration": "no", "overall_margin": "pct_5_6",
        "customer_type": "state_owned", "payment_terms": "standard",
        # 控制权角色未填 → 控制权总闸门不过 → 硬件落净额
    }
    units = [
        {"name": "设备", "declared_type": "设备", "amount": 700 * W, "whitelisted": True, "logistics": "self"},
        {"name": "服务", "declared_type": "服务", "amount": 300 * W},
    ]
    result = run_diagnosis(["system_integration"], fields, accounting_units=units)
    assert "R21" in _ids(result["triggered_rules"])           # 服务侧视角仍报全额法适用
    lm = result["listing_mode"]
    assert lm["mode"] == "net_settlement"                      # 硬件侧因控制权未自证落净额
    # 两个结论同时存在、各自有依据——这是「两套尺度并立」的预期，不是 bug
    assert lm["unit_decisions"][0]["listed"] is False
