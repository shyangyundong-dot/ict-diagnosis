"""控制权角色自查（总额法资格）的判定逻辑（docs/adr/0003）。

矩阵：必选 6/7/9（涉硬件再加 16）全占 + 三组二选一 {3|4}/{10|11}/{13|14} 各≥1
→ 落在 8 情形之一 → 资格成立(low)；缺任一必要元素 → 资格不成立(high)；未填 → tip。
"""

import pytest

from rules.engine import assess_control_roles, run_diagnosis

# 一个合法情形（情形1）：必选 6/7/9 + 各组第一个 3/10/13
SCENARIO_1 = ["6", "7", "9", "3", "10", "13"]


def test_unfilled_returns_tip_not_high():
    r = assess_control_roles([], has_hardware=False)
    assert r["status"] == "unfilled"
    assert r["level"] == "tip"


def test_eligible_no_hardware():
    r = assess_control_roles(SCENARIO_1, has_hardware=False)
    assert r["status"] == "eligible"
    assert r["level"] == "low"
    assert r["missing"] == []


@pytest.mark.parametrize("combo", [
    ["6", "7", "9", "3", "10", "13"],   # 情形1
    ["6", "7", "9", "3", "10", "14"],   # 情形2
    ["6", "7", "9", "3", "11", "13"],   # 情形3
    ["6", "7", "9", "4", "10", "13"],   # 情形5
    ["6", "7", "9", "4", "11", "14"],   # 情形8
])
def test_all_eight_scenarios_are_eligible(combo):
    """三组二选一的任意组合 + 必选齐 → 都应成立（覆盖 8 情形的代表）。"""
    assert assess_control_roles(combo, has_hardware=False)["status"] == "eligible"


def test_missing_mandatory_is_ineligible_high():
    """缺一个必选角色（7 采购决策）→ 资格不成立、high。"""
    combo = ["6", "9", "3", "10", "13"]  # 少了 7
    r = assess_control_roles(combo, has_hardware=False)
    assert r["status"] == "ineligible"
    assert r["level"] == "high"
    assert any("7" in m for m in r["missing"])


def test_missing_either_or_group_is_ineligible_high():
    """某个二选一组全空（方案 3/4 都没占）→ 资格不成立、high（与缺必选等权）。"""
    combo = ["6", "7", "9", "10", "13"]  # 方案组 3/4 都缺
    r = assess_control_roles(combo, has_hardware=False)
    assert r["status"] == "ineligible"
    assert any("方案" in m for m in r["missing"])


def test_hardware_makes_16_mandatory():
    """涉硬件时角色16 变必选：占齐 6/7/9+三组但缺 16 → 不成立。"""
    combo = SCENARIO_1  # 没有 16
    assert assess_control_roles(combo, has_hardware=False)["status"] == "eligible"
    assert assess_control_roles(combo, has_hardware=True)["status"] == "ineligible"
    assert assess_control_roles(combo + ["16"], has_hardware=True)["status"] == "eligible"


def test_run_diagnosis_injects_control_roles_check():
    """结果契约：run_diagnosis 注入 control_roles_check。"""
    result = run_diagnosis(["system_integration"],
                           {"project_type": ["system_integration"], "control_roles": SCENARIO_1})
    assert "control_roles_check" in result
    assert result["control_roles_check"]["status"] == "eligible"


def test_ineligible_contributes_high_to_overall_risk():
    fields = {"project_type": ["system_integration"], "control_roles": ["6", "9"]}  # 缺很多
    result = run_diagnosis(["system_integration"], fields)
    assert result["control_roles_check"]["status"] == "ineligible"
    assert result["overall_risk"] == "high"


def test_unfilled_with_r21_wants_full_is_medium():
    """系统集成 + 能力够主要责任人（R21 触发）+ 未填角色 → unfilled_wants_full medium。"""
    fields = {
        "project_type": ["system_integration"],
        # R21 触发：has_telecom_capability ∈ {yes,partial} 且 capability_ratio ∈ {medium,high}
        "has_telecom_capability": "yes",
        "capability_ratio": "high",
        "scheme_reviewed": "yes",
        # control_roles 未填
    }
    result = run_diagnosis(["system_integration"], fields)
    assert any(r["rule_id"] == "R21" for r in result["triggered_rules"]), "前置：R21 应触发"
    c = result["control_roles_check"]
    assert c["status"] == "unfilled_wants_full"
    assert c["level"] == "medium"
    assert result["overall_risk"] in ("medium", "high")


@pytest.mark.parametrize("mode", ["all_telecom", "mixed"])
def test_unfilled_service_self_or_mixed_is_medium(mode):
    """服务类自有/混合交付 + 未填角色 → unfilled_wants_full medium（服务奔全额）。"""
    fields = {"project_type": ["service"], "service_delivery_mode": mode}
    result = run_diagnosis(["service"], fields)
    c = result["control_roles_check"]
    assert c["status"] == "unfilled_wants_full"
    assert c["level"] == "medium"


def test_unfilled_service_all_external_stays_tip():
    """服务类全外包 → R31 已判差额，不算奔全额；未填角色应维持 tip 不打扰。"""
    fields = {"project_type": ["service"], "service_delivery_mode": "all_external"}
    result = run_diagnosis(["service"], fields)
    c = result["control_roles_check"]
    assert c["status"] == "unfilled"
    assert c["level"] == "tip"


def test_unfilled_equipment_sales_stays_tip():
    """设备销售独占（硬件铁律不列收、本就不奔全额）+ 未填角色 → tip 不打扰。"""
    fields = {"project_type": ["equipment_sales"]}
    result = run_diagnosis(["equipment_sales"], fields)
    c = result["control_roles_check"]
    assert c["status"] == "unfilled"
    assert c["level"] == "tip"


def test_filled_eligible_overrides_wants_full():
    """填了且占齐 → eligible，不论 wants_full 是否成立。"""
    fields = {
        "project_type": ["system_integration"],
        "has_telecom_capability": "yes", "capability_ratio": "high", "scheme_reviewed": "yes",
        "control_roles": ["6", "7", "9", "3", "10", "13"],
    }
    result = run_diagnosis(["system_integration"], fields)
    assert result["control_roles_check"]["status"] == "eligible"


def test_r09_suppresses_control_check():
    """R09 纯外采触发时，抑制角色检查的『资格不成立』，避免重复报无控制权。"""
    # 构造 R09 触发：capability_ratio=all_external + contract_content_same=yes + has_telecom_capability=no
    fields = {
        "project_type": ["system_integration"],
        "capability_ratio": "all_external",
        "contract_content_same": "yes",
        "has_telecom_capability": "no",
        "control_roles": ["6", "9"],  # 本会判 ineligible
    }
    result = run_diagnosis(["system_integration"], fields)
    assert any(r["rule_id"] == "R09" for r in result["triggered_rules"]), "前置：R09 应触发"
    assert result["control_roles_check"] is None, "R09 触发时角色检查应被抑制"
