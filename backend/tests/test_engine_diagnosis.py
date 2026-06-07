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
        "unit_warning", "overall_risk", "rule_version",
    ):
        assert key in result, f"结果缺少键 {key}"


def test_hardware_unit_suppresses_listing_rules():
    """#8：设备单元归类不列收时，列收违规规则 R24/R25/R26 应被抑制而非误报。"""
    fields = {
        "project_type": ["equipment_sales"],
        # 构造会触发列收违规的扁平字段（具体取值无需精确，重点看抑制行为）
        "logistics_control": "supplier_direct",
        "revenue_recognition": "point_in_time",
    }
    units = [
        {"name": "设备采购", "declared_type": "设备", "amount": 1_000_000,
         "listed": False, "gross": None, "logistics": "supplier_direct",
         "has_self_capability": "unknown"},
    ]
    result = run_diagnosis(["equipment_sales"], fields, accounting_units=units)
    triggered_ids = _ids(result["triggered_rules"])
    listing_rules = {"R24", "R25", "R26"}
    # 被抑制的列收规则不应出现在触发列表里
    assert not (triggered_ids & listing_rules), \
        f"硬件不列收时仍误触发列收规则：{triggered_ids & listing_rules}"


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
