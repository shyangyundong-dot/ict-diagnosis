from accounting_structure import normalize_structure, structure_from_units
from rules.engine import run_diagnosis


W = 10_000
ROLES_WITH_HARDWARE = ["3", "6", "7", "9", "10", "13", "16"]


def _structure(units, intents):
    structure = structure_from_units(units)
    for source, intent in zip(structure["source_units"], intents):
        decision = structure["decisions"][source["id"]]
        decision.update({"listing_intent": intent, "listing_intent_confirmed": True})
    return structure


def _pass_checks(decision):
    decision["six_daowei"] = {
        "facts_confirmed": True,
        "dimensions": {
            "customer_insight": "in_place",
            "solution_control": "in_place",
            "bid_autonomy": "in_place",
            "procurement_autonomy": "in_place",
            "project_management": "in_place",
            "operations_autonomy": "in_place",
        },
        "level": "strong",
        "confirmation_status": "confirmed",
        "no_external_procurement": False,
        "no_operations_obligation": False,
    }
    decision["r08"] = {
        "answers": {
            "ctrl1_control_before_transfer": "yes",
            "ctrl2_primary_responsibility": "yes",
            "ctrl3_inventory_delivery_risk": "yes",
            "ctrl4_pricing_autonomy": "yes",
        },
        "conclusion": "principal",
        "confirmation_status": "confirmed",
    }


def _base_fields(margin="pct_5_6"):
    return {
        "project_type": ["system_integration"],
        "control_roles": ROLES_WITH_HARDWARE,
        "overall_margin": margin,
        "customer_type": "state_owned",
        "payment_terms": "standard",
        "ownership_transfer": "yes",
    }


def test_full_intent_with_missing_evidence_stays_full_provisional_high():
    structure = _structure([
        {"name": "真实服务", "declared_type": "服务", "amount": 100 * W},
    ], ["full"])

    result = run_diagnosis(["service"], _base_fields(), structure)
    decision = result["listing_mode"]["unit_decisions"][0]

    assert decision["listing_result"] == "full"
    assert decision["listing_result_status"] == "provisional"
    assert result["overall_risk"] == "high"
    assert result["audit_checklist"]


def test_explicit_six_failure_changes_only_that_unit_to_net():
    structure = _structure([
        {"name": "服务A", "declared_type": "服务", "amount": 100 * W},
        {"name": "服务B", "declared_type": "服务", "amount": 100 * W},
    ], ["full", "full"])
    first, second = structure["source_units"]
    _pass_checks(structure["decisions"][first["id"]])
    _pass_checks(structure["decisions"][second["id"]])
    structure["decisions"][first["id"]]["six_daowei"]["dimensions"]["project_management"] = "not_in_place"

    result = run_diagnosis(["service"], _base_fields(), structure)
    decisions = {item["unit_name"]: item for item in result["listing_mode"]["unit_decisions"]}

    assert decisions["服务A"]["listing_result"] == "net"
    assert decisions["服务B"]["listing_result"] == "full"


def test_net_intent_skips_six_r08_and_does_not_raise_unit_risk():
    structure = _structure([
        {"name": "净额服务", "declared_type": "服务", "amount": 100 * W},
    ], ["net"])

    result = run_diagnosis(["service"], _base_fields(), structure)
    decision = result["listing_mode"]["unit_decisions"][0]

    assert decision["listing_result"] == "net"
    assert decision["six_daowei_status"] == "skipped"
    assert result["six_daowei_checks"] == []


def test_standard_product_is_always_full_and_skips_27_and_six():
    structure = _structure([
        {"name": "天翼云", "declared_type": "标品", "amount": 100 * W},
    ], ["full"])

    result = run_diagnosis(["other"], {}, structure)
    decision = result["listing_mode"]["unit_decisions"][0]

    assert decision["listing_result"] == "full"
    assert decision["listing_result_status"] == "confirmed"
    assert decision["mode"] == "standard_product"


def test_whitelist_unknown_keeps_full_provisional_in_self_check():
    structure = _structure([
        {"name": "服务器", "declared_type": "设备", "amount": 600 * W, "whitelisted": "unknown", "logistics": "self"},
    ], ["full"])
    source_id = structure["source_units"][0]["id"]
    _pass_checks(structure["decisions"][source_id])

    result = run_diagnosis(["equipment_sales"], _base_fields(), structure)
    decision = result["listing_mode"]["unit_decisions"][0]

    assert decision["listing_result"] == "full"
    assert decision["listing_result_status"] == "provisional"
    assert result["overall_risk"] == "high"


def test_whitelist_false_is_known_failure_and_net():
    structure = _structure([
        {"name": "非白名单设备", "declared_type": "设备", "amount": 600 * W, "whitelisted": False, "logistics": "self"},
    ], ["full"])
    source_id = structure["source_units"][0]["id"]
    _pass_checks(structure["decisions"][source_id])

    result = run_diagnosis(["equipment_sales"], _base_fields(), structure)
    decision = result["listing_mode"]["unit_decisions"][0]

    assert decision["listing_result"] == "net"
    assert decision["listing_result_status"] == "confirmed"


def test_service_integration_formula_includes_finished_software_and_construction():
    structure = structure_from_units([
        {"name": "设备", "declared_type": "设备", "amount": 100 * W, "whitelisted": True},
        {"name": "成品软件", "declared_type": "成品软件", "amount": 100 * W, "whitelisted": True},
        {"name": "施工", "declared_type": "施工", "amount": 100 * W},
        {"name": "服务", "declared_type": "服务", "amount": 200 * W},
        {"name": "标品", "declared_type": "标品", "amount": 500 * W},
    ])
    ids = [source["id"] for source in structure["source_units"][:4]]
    structure["groups"] = [{
        "id": "grp-system", "name": "系统整体交付", "source_unit_ids": ids,
        "po_facts": {
            "po1_independent_benefit": "no", "po2_significant_integration": "yes",
            "po3_modification": "no", "po4_interdependence": "yes",
        },
        "confirmed_relationship": "combined",
    }]
    structure = normalize_structure(structure)
    structure["decisions"]["grp-system"].update({"listing_intent": "full", "listing_intent_confirmed": True})
    _pass_checks(structure["decisions"]["grp-system"])

    result = run_diagnosis(["system_integration"], _base_fields("gt_10"), structure)

    assert result["listing_mode"]["ratios"]["service_integration_pct"] == 0.3


def test_hard_to_service_scans_service_component_inside_combined_unit():
    structure = structure_from_units([
        {"name": "设备", "declared_type": "设备", "amount": 100 * W, "whitelisted": True},
        {"name": "申报服务部分", "declared_type": "服务", "amount": 900 * W,
         "gross": "平进平出", "logistics": "supplier_direct", "has_self_capability": False},
    ])
    ids = [source["id"] for source in structure["source_units"]]
    structure["groups"] = [{
        "id": "grp-system", "name": "组合单元", "source_unit_ids": ids,
        "po_facts": {
            "po1_independent_benefit": "no", "po2_significant_integration": "yes",
            "po3_modification": "no", "po4_interdependence": "yes",
        },
        "confirmed_relationship": "combined",
    }]
    structure = normalize_structure(structure)
    structure["decisions"]["grp-system"].update({"listing_intent": "full", "listing_intent_confirmed": True})
    _pass_checks(structure["decisions"]["grp-system"])

    result = run_diagnosis(["system_integration"], _base_fields("gt_10"), structure)

    assert len(result["hard_to_service"]) == 1
    assert result["hard_to_service"][0]["source_unit_name"] == "申报服务部分"
    assert result["listing_mode"]["unit_decisions"][0]["listing_result"] == "full"
    assert result["overall_risk"] == "high"
