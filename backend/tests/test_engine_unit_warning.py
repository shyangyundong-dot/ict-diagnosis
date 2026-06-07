"""核算单元缺失软警告（unit_warning）触发条件。

约定（见 docs/adr/0002 + 本轮修复）：含设备/系统集成等本应切分单元的项目，
若提交时没有核算单元，则诊断退化（硬件排除 #8 / 硬转服务 #9 都没跑）——
不阻断提交，但在结果里标记 unit_warning，报告顶部黄条提示。
"""

import pytest

from rules.engine import run_diagnosis, _UNIT_EXPECTED_TYPES


@pytest.mark.parametrize("ptype", sorted(_UNIT_EXPECTED_TYPES))
def test_expected_type_without_units_warns(ptype):
    result = run_diagnosis([ptype], {"project_type": [ptype]}, accounting_units=[])
    assert result["unit_warning"], f"{ptype} 无核算单元应触发软警告"
    assert result["unit_warning"]["level"] == "warn"
    assert "核算单元" in result["unit_warning"]["message"]


def test_expected_type_with_units_does_not_warn():
    units = [{"name": "设备块", "declared_type": "设备", "listed": False}]
    result = run_diagnosis(
        ["system_integration"], {"project_type": ["system_integration"]},
        accounting_units=units,
    )
    assert result["unit_warning"] is None


def test_pure_service_without_units_does_not_warn():
    """纯服务/软件可能合法地只有单一业务块，不强求切分，不应打扰。"""
    result = run_diagnosis(["service"], {"project_type": ["service"]}, accounting_units=[])
    assert result["unit_warning"] is None


def test_warning_does_not_block_diagnosis():
    """软警告不阻断：仍产出完整诊断结果。"""
    result = run_diagnosis(
        ["equipment_sales"], {"project_type": ["equipment_sales"]}, accounting_units=[],
    )
    assert result["unit_warning"]
    assert "overall_risk" in result
    assert "triggered_rules" in result
