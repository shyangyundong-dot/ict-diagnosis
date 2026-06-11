"""硬件/施工「铁律不列收」的数据层归一（#8 抑制的前置条件，见 docs/adr/0002）。

回归背景：铁律此前只靠 AI prompt 嘱咐 + 前端「手动改类型时」强制。AI 切分草稿
给设备/施工单元留下 listed=null/"uncertain"/true 时，引擎对 R24/R25/R26 的
抑制静默失效（正是 #8 要消灭的误报）；而前端又对硬件单元禁用了列收选择器，
用户无法手动修复。修法：enforce_hardware_no_listing 在所有入库路径强制归一。
"""

import inspect

import pytest

from rules.engine import enforce_hardware_no_listing, run_diagnosis
from routers import diagnosis as router_mod


@pytest.mark.parametrize("bad_listed", [None, True, "uncertain"])
def test_equipment_unit_forced_unlisted(bad_listed):
    units = [{"name": "硬件", "declared_type": "设备", "listed": bad_listed}]
    enforce_hardware_no_listing(units)
    assert units[0]["listed"] is False


def test_construction_unit_forced_unlisted():
    units = [{"name": "布线施工", "declared_type": "施工", "listed": "uncertain"}]
    enforce_hardware_no_listing(units)
    assert units[0]["listed"] is False


def test_non_hardware_units_untouched():
    """服务/标品单元的 listed 不受铁律影响（服务列收由硬转服务检测把关）。"""
    units = [
        {"declared_type": "服务", "listed": True},
        {"declared_type": "标品", "listed": "uncertain"},
    ]
    enforce_hardware_no_listing(units)
    assert units[0]["listed"] is True
    assert units[1]["listed"] == "uncertain"


def test_none_and_empty_input_safe():
    assert enforce_hardware_no_listing(None) == []
    assert enforce_hardware_no_listing([]) == []


def test_normalized_units_restore_r24_r25_suppression():
    """归一后，AI 草稿漏标的硬件单元不再阻断 #8 抑制——R24/R25 进 suppressed 而非误报。"""
    fields = {
        "project_type": ["system_integration", "service"],
        "hardware_construction": True,
    }
    units = [
        {"name": "硬件", "declared_type": "设备", "listed": None},  # AI 漏标
        {"name": "运维", "declared_type": "服务", "listed": True},
    ]
    enforce_hardware_no_listing(units)
    result = run_diagnosis(["system_integration", "service"], fields, accounting_units=units)
    suppressed_ids = {r["rule_id"] for r in result["suppressed_rules"]}
    assert {"R24", "R25"} <= suppressed_ids
    assert not any(r["rule_id"] in ("R24", "R25") for r in result["triggered_rules"])


def test_all_unit_entrypoints_enforce_iron_rule():
    """契约扫描：核算单元的三个入库/使用路径都必须调用 enforce_hardware_no_listing
    （AI 切分草稿 / 用户确认保存 / 提交诊断兜底）。"""
    for fn in (
        router_mod.segment_session_units,
        router_mod.save_session_units,
        router_mod.confirm_and_diagnose,
    ):
        src = inspect.getsource(fn)
        assert "enforce_hardware_no_listing" in src, f"{fn.__name__} 漏调铁律归一"
