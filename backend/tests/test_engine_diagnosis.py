"""规则引擎核心行为回归测试。

覆盖核算单元重构（docs/adr/0002）的两条铁律：
- #8 硬件/施工 单元正确归类为不列收 → 抑制 R24/R25/R26 误报
- #9 申报服务且列收的单元呈现硬件实质 → 举证式硬转服务嫌疑

外加一条基础规则触发的冒烟测试，确保引擎主路径不退化。
"""

from rules.engine import run_diagnosis


def _ids(rules):
    return {r["rule_id"] for r in rules}


def test_basic_rule_trigger_related_party_no_capability():
    """R02：前后向关联 + 无自有能力 → 高风险触发。"""
    result = run_diagnosis(
        ["system_integration"],
        {
            "project_type": ["system_integration"],
            "related_party": "yes",
            "has_telecom_capability": "no",
        },
    )
    assert "R02" in _ids(result["triggered_rules"])
    assert result["overall_risk"] == "high"


def test_result_has_expected_keys():
    """结果契约：核算单元重构后新增的键必须存在，前端/报告依赖它们。"""
    result = run_diagnosis(["service"], {"project_type": ["service"]})
    for key in (
        "triggered_rules", "tips", "manual_check_rules", "audit_checklist",
        "suppressed_rules", "accounting_units", "hard_to_service",
        "unit_warning", "overall_risk", "rule_version", "material_version",
    ):
        assert key in result, f"结果缺少键 {key}"


def test_misdeclaration_rules_suppressed_logistics_rule_kept():
    """27 号文重构（ADR 0004 决策13）：切分核算单元时——
    R24/R25「硬件/施工包装为服务」(误申报轴) 让位单元级硬转服务(#9)、被抑制；
    R26「设备物流非主控」(物权轴) 升格为全额否决闸、保留为真实风险，不再抑制。"""
    fields = {
        "project_type": ["equipment_sales"],
        "logistics_control": "supplier_direct",  # 触发 R26
        "revenue_recognition": "point_in_time",
    }
    units = [
        {"name": "设备采购", "declared_type": "设备", "amount": 1_000_000,
         "gross": None, "logistics": "supplier_direct", "has_self_capability": "unknown"},
    ]
    result = run_diagnosis(["equipment_sales"], fields, accounting_units=units)
    triggered_ids = _ids(result["triggered_rules"])
    suppressed_ids = _ids(result["suppressed_rules"])
    # 误申报轴 R24/R25 被抑制
    assert "R24" not in triggered_ids and "R25" not in triggered_ids
    # 物权轴 R26 不再被抑制（若其 trigger 条件命中，应出现在触发或保持可见，不进 suppressed）
    assert "R26" not in suppressed_ids


def test_hard_to_service_detection_three_signals():
    """#9：申报服务且列收的单元三信号齐发 → 高嫌疑硬转服务。"""
    units = [
        {"name": "所谓服务块", "declared_type": "服务", "amount": 2_000_000,
         "listed": True, "gross": "平进平出", "logistics": "supplier_direct",
         "has_self_capability": False},
    ]
    result = run_diagnosis(["service"], {"project_type": ["service"]}, accounting_units=units)
    hts = result["hard_to_service"]
    assert len(hts) == 1
    flag = hts[0]
    assert flag["suspicion_level"] == "high"          # 三信号 → 高嫌疑
    assert len(flag["signals"]) == 3
    assert flag["required_evidence"]                   # 举证式：必须列出举证材料


def test_hard_to_service_skips_non_service_and_unlisted():
    """硬转服务只盯「申报服务且列收」的单元——设备块、不列收块都不进检测。"""
    units = [
        {"name": "设备块", "declared_type": "设备", "listed": False,
         "gross": "平进平出", "logistics": "supplier_direct", "has_self_capability": False},
        {"name": "不列收服务块", "declared_type": "服务", "listed": False,
         "gross": "平进平出", "logistics": "supplier_direct", "has_self_capability": False},
    ]
    result = run_diagnosis(["service"], {"project_type": ["service"]}, accounting_units=units)
    assert result["hard_to_service"] == []
