"""列收模式分类器测试（27 号文重构，见 docs/adr/0004）。

覆盖：四模式实质路由、级联（项目级全额→单元级白名单兜底）、两套占比公式、
overall_margin 门槛、控制权总闸门、准入闸硬/软分治、物权否决、listed 派生输出。
纯函数，无需 DB/DeepSeek。
"""
from rules.engine import classify_listing_mode, run_diagnosis

W = 10000  # 万 → 元

_PT = ["system_integration"]


def _run(fields, units, ctrl="eligible"):
    u = [dict(x) for x in units]
    r = classify_listing_mode(_PT, fields, u, ctrl)
    return r, u


def _listed(units):
    return {x["name"]: x.get("listed") for x in units}


# ── 服务整合（重大整合 → 整项目全额，含非白名单硬件）──
def test_service_integration_full_listing_whole_project():
    fields = {"major_integration": "yes", "overall_margin": "gt_10",
              "customer_type": "government", "payment_terms": "standard"}
    units = [
        {"name": "设备", "declared_type": "设备", "amount": 400 * W, "whitelisted": True, "logistics": "self"},
        {"name": "施工", "declared_type": "施工", "amount": 50 * W, "logistics": "self"},
        {"name": "服务", "declared_type": "服务", "amount": 550 * W},
    ]
    r, u = _run(fields, units)
    assert r["mode"] == "service_integration"
    assert r["full_listing"] is True
    assert r["ratios"]["service_integration_pct"] == 0.45  # (400+50)/1000
    # 整项目全额：设备 + 施工都 listed（施工进服务整合分子，也随整项目全额）
    assert _listed(u)["设备"] is True
    assert _listed(u)["施工"] is True


def test_service_integration_ratio_over_60_falls_to_unit_backstop():
    """服务整合占比超 60% → 项目级走不通，退第二遍逐单元白名单兜底。"""
    fields = {"major_integration": "yes", "overall_margin": "gt_10",
              "customer_type": "government", "payment_terms": "standard"}
    units = [
        {"name": "设备", "declared_type": "设备", "amount": 700 * W, "whitelisted": True, "logistics": "self"},
        {"name": "服务", "declared_type": "服务", "amount": 300 * W},
    ]
    r, u = _run(fields, units)
    assert r["full_listing"] is False               # 整项目全额不成立
    # 但白名单设备走单一履约兜底仍可全额（占比 70% ≤80%、margin gt_10≥5%）
    assert _listed(u)["设备"] is True
    assert r["mode"] == "single_fulfillment"


# ── 单一履约·场景一（含服务，≤80%）──
def test_single_fulfillment_scene_one():
    fields = {"major_integration": "no", "overall_margin": "pct_5_6",
              "customer_type": "state_owned", "payment_terms": "standard"}
    units = [
        {"name": "设备", "declared_type": "设备", "amount": 700 * W, "whitelisted": True, "logistics": "self"},
        {"name": "服务", "declared_type": "服务", "amount": 300 * W},
    ]
    r, u = _run(fields, units)
    assert r["mode"] == "single_fulfillment"
    assert r["ratios"]["single_fulfillment_pct"] == 0.7
    assert _listed(u)["设备"] is True


def test_single_fulfillment_ratio_over_80_net():
    fields = {"major_integration": "no", "overall_margin": "pct_5_6",
              "customer_type": "state_owned", "payment_terms": "standard"}
    units = [
        {"name": "设备", "declared_type": "设备", "amount": 900 * W, "whitelisted": True, "logistics": "self"},
        {"name": "服务", "declared_type": "服务", "amount": 100 * W},
    ]
    r, u = _run(fields, units)
    assert r["ratios"]["single_fulfillment_pct"] == 0.9
    assert _listed(u)["设备"] is False              # 占比 90% 超 80% → 净额
    assert r["mode"] == "net_settlement"


# ── 单一履约·场景二（纯硬件 ≥500万）──
def test_single_fulfillment_scene_two_pure_hardware():
    fields = {"major_integration": "no", "overall_margin": "pct_5_6",
              "customer_type": "state_owned", "payment_terms": "standard"}
    units = [{"name": "白名单设备", "declared_type": "设备", "amount": 600 * W, "whitelisted": True, "logistics": "self"}]
    r, u = _run(fields, units)
    assert r["mode"] == "single_fulfillment"
    assert _listed(u)["白名单设备"] is True


def test_single_fulfillment_scene_two_below_500w_net():
    fields = {"major_integration": "no", "overall_margin": "pct_5_6",
              "customer_type": "state_owned", "payment_terms": "standard"}
    units = [{"name": "白名单设备", "declared_type": "设备", "amount": 300 * W, "whitelisted": True, "logistics": "self"}]
    r, u = _run(fields, units)
    assert _listed(u)["白名单设备"] is False
    assert r["mode"] == "net_settlement"


# ── 控制权总闸门 ──
def test_control_gate_blocks_all_full_listing():
    fields = {"major_integration": "yes", "overall_margin": "gt_10",
              "customer_type": "government", "payment_terms": "standard"}
    units = [
        {"name": "设备", "declared_type": "设备", "amount": 700 * W, "whitelisted": True, "logistics": "self"},
        {"name": "服务", "declared_type": "服务", "amount": 300 * W},
    ]
    r, u = _run(fields, units, ctrl="ineligible")
    assert r["mode"] == "net_settlement"
    assert _listed(u)["设备"] is False
    assert any("控制权" in b for b in r["blockers"])


# ── 物权三流合一否决闸（原 R26）──
def test_supplier_direct_logistics_disqualifies_unit():
    fields = {"major_integration": "no", "overall_margin": "pct_5_6",
              "customer_type": "state_owned", "payment_terms": "standard"}
    units = [
        {"name": "设备", "declared_type": "设备", "amount": 700 * W, "whitelisted": True, "logistics": "supplier_direct"},
        {"name": "服务", "declared_type": "服务", "amount": 300 * W},
    ]
    r, u = _run(fields, units)
    assert _listed(u)["设备"] is False              # 供应商直发 → 物权否决 → 净额
    assert r["mode"] == "net_settlement"


# ── 白名单：非白名单硬件落网兜底 ──
def test_non_whitelisted_hardware_net():
    fields = {"major_integration": "no", "overall_margin": "pct_5_6",
              "customer_type": "state_owned", "payment_terms": "standard"}
    units = [
        {"name": "LED屏", "declared_type": "设备", "amount": 700 * W, "whitelisted": False, "logistics": "self"},
        {"name": "服务", "declared_type": "服务", "amount": 300 * W},
    ]
    r, u = _run(fields, units)
    assert _listed(u)["LED屏"] is False


def test_whitelisted_unknown_treated_as_non_whitelist():
    """whitelisted=unknown 保守当非白名单（偏严待举证）。"""
    fields = {"major_integration": "no", "overall_margin": "pct_5_6",
              "customer_type": "state_owned", "payment_terms": "standard"}
    units = [
        {"name": "存疑设备", "declared_type": "设备", "amount": 700 * W, "whitelisted": "unknown", "logistics": "self"},
        {"name": "服务", "declared_type": "服务", "amount": 300 * W},
    ]
    r, u = _run(fields, units)
    assert _listed(u)["存疑设备"] is False


# ── 准入闸硬/软分治（Q8）──
def test_payment_terms_other_hard_blocks():
    fields = {"major_integration": "no", "overall_margin": "pct_5_6",
              "customer_type": "state_owned", "payment_terms": "other"}
    units = [
        {"name": "设备", "declared_type": "设备", "amount": 700 * W, "whitelisted": True, "logistics": "self"},
        {"name": "服务", "declared_type": "服务", "amount": 300 * W},
    ]
    r, u = _run(fields, units)
    assert any("付款节点" in b for b in r["blockers"])
    assert _listed(u)["设备"] is False              # 硬否决 → 净额


def test_private_customer_soft_not_hard():
    """民企/其他客户 → 软提示（可能是互联网头部/5A 外企），不硬否决。"""
    fields = {"major_integration": "no", "overall_margin": "pct_5_6",
              "customer_type": "private", "payment_terms": "standard"}
    units = [
        {"name": "设备", "declared_type": "设备", "amount": 700 * W, "whitelisted": True, "logistics": "self"},
        {"name": "服务", "declared_type": "服务", "amount": 300 * W},
    ]
    r, u = _run(fields, units)
    assert any("民企" in s or "准入闭集" in s for s in r["softs"])
    assert not any("客户" in b for b in r["blockers"])
    assert _listed(u)["设备"] is True               # 软提示不踢出全额


# ── 实质路由出口 ──
def test_pure_service_is_regular():
    r, u = _run({"customer_type": "government"}, [{"name": "服务", "declared_type": "服务", "amount": 100 * W}])
    assert r["mode"] == "regular"
    assert r["full_listing"] is True


def test_capital_investment_tagged_not_judged():
    fields = {"is_capital_investment": True}
    units = [{"name": "设备", "declared_type": "设备", "amount": 700 * W, "whitelisted": True, "logistics": "self"}]
    r, u = _run(fields, units)
    assert r["mode"] == "capital"
    assert r["full_listing"] is False               # 留出口、打标，不实现门槛


# ── 集成到 run_diagnosis 结果契约 ──
def test_run_diagnosis_exposes_listing_mode():
    fields = {"project_type": ["system_integration"], "major_integration": "no",
              "overall_margin": "pct_5_6", "customer_type": "state_owned",
              "payment_terms": "standard", "control_roles": ["3", "6", "7", "9", "10", "13", "16"]}
    units = [
        {"name": "设备", "declared_type": "设备", "amount": 700 * W, "whitelisted": True, "logistics": "self"},
        {"name": "服务", "declared_type": "服务", "amount": 300 * W},
    ]
    result = run_diagnosis(["system_integration"], fields, accounting_units=units)
    assert "listing_mode" in result
    lm = result["listing_mode"]
    assert lm["mode"] in {"regular", "capital", "service_integration", "single_fulfillment", "net_settlement"}
    assert "mode_label" in lm and "unit_decisions" in lm
