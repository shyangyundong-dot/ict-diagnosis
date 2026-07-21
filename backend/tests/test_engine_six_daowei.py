"""统一六到位：事实建议、六维人工确认与强/中/无综合结论。"""

from ai_chat import get_missing_fields
from rules.engine import RULE_VERSION, assess_six_daowei, run_diagnosis


ELIGIBLE_ROLES = ["6", "7", "9", "3", "10", "13"]
DIMENSION_KEYS = [
    "six_daowei_customer_insight",
    "six_daowei_solution_control",
    "six_daowei_bid_autonomy",
    "six_daowei_procurement_autonomy",
    "six_daowei_project_management",
    "six_daowei_operations_autonomy",
]


def test_rule_version_covers_six_daowei_listing_gate():
    assert RULE_VERSION >= "v1.9.0"


def _all_dimensions(value: str) -> dict:
    return {key: value for key in DIMENSION_KEYS}


def test_strong_requires_all_dimensions_and_eligible_roles():
    fields = {
        "project_type": ["service"],
        "control_roles": ELIGIBLE_ROLES,
        "service_delivery_mode": "mixed",
        **_all_dimensions("in_place"),
    }
    check = assess_six_daowei(fields)

    assert check["suggested_level"] == "strong"
    assert check["level"] == "strong"
    assert check["level_source"] == "suggested"


def test_all_external_alone_cannot_produce_none():
    fields = {
        "project_type": ["service"],
        "control_roles": ELIGIBLE_ROLES,
        "service_delivery_mode": "all_external",
    }
    check = assess_six_daowei(fields)

    assert check["suggested_level"] == "medium"
    assert check["suggested_level"] != "none"


def test_none_requires_multiple_confirmed_negative_signals():
    fields = {
        "project_type": ["service"],
        "control_roles": ["6"],
        "service_delivery_mode": "all_external",
        "has_telecom_capability": "no",
        "capability_ratio": "all_external",
    }
    check = assess_six_daowei(fields)

    assert check["role_check"]["status"] == "ineligible"
    assert check["suggested_level"] == "none"


def test_user_confirmed_level_wins_without_rewriting_system_suggestion():
    fields = {
        "project_type": ["service"],
        "control_roles": ELIGIBLE_ROLES,
        "service_delivery_mode": "mixed",
        "six_daowei_level": "none",
        **_all_dimensions("in_place"),
    }
    check = assess_six_daowei(fields)

    assert check["suggested_level"] == "strong"
    assert check["confirmed_level"] == "none"
    assert check["level"] == "none"
    assert check["level_source"] == "confirmed"
    assert check["level_mismatch"] is True


def test_dimension_confirmation_wins_and_records_mismatch():
    fields = {
        "project_type": ["service"],
        "contract_matches_bpm": "no",
        "six_daowei_customer_insight": "in_place",
    }
    check = assess_six_daowei(fields)
    customer = next(
        item for item in check["dimensions"]
        if item["key"] == "six_daowei_customer_insight"
    )

    assert customer["suggested"] == "not_in_place"
    assert customer["effective"] == "in_place"
    assert customer["mismatch"] is True


def test_new_project_collects_six_dimensions_after_final_unit_intent_not_as_global_required_fields():
    missing = get_missing_fields({"project_type": ["other"]})

    assert not set(DIMENSION_KEYS).intersection(missing)
    assert "six_daowei_facts_confirmed" not in missing
    assert "six_daowei_level" not in missing


def test_legacy_false_base_confirmation_does_not_block_new_global_field_collection():
    missing = get_missing_fields({
        "project_type": ["other"],
        "six_daowei_facts_confirmed": False,
    })

    assert "six_daowei_facts_confirmed" not in missing


def test_run_diagnosis_exposes_merged_six_daowei_result():
    fields = {
        "project_type": ["service"],
        "control_roles": ELIGIBLE_ROLES,
        "service_delivery_mode": "mixed",
        "six_daowei_facts_confirmed": True,
        "six_daowei_level": "strong",
        **_all_dimensions("in_place"),
    }
    result = run_diagnosis(["service"], fields)

    assert result["six_daowei_check"]["level"] == "strong"
    assert result["six_daowei_check"]["level_source"] == "confirmed"
    assert result["six_daowei_check"]["listing_gate"]["passed"] is True
    assert result["control_roles_check"]["status"] == "eligible"


def test_medium_fails_full_listing_gate_and_service_falls_to_net():
    dimensions = _all_dimensions("in_place")
    dimensions["six_daowei_operations_autonomy"] = "pending_evidence"
    fields = {
        "project_type": ["service"],
        "control_roles": ELIGIBLE_ROLES,
        "service_delivery_mode": "mixed",
        "six_daowei_facts_confirmed": True,
        "six_daowei_level": "medium",
        **dimensions,
    }
    units = [{
        "name": "服务单元", "declared_type": "服务", "listed": True,
        "gross": "平进平出", "logistics": "supplier_direct", "has_self_capability": False,
    }]

    result = run_diagnosis(["service"], fields, accounting_units=units)

    assert result["six_daowei_check"]["listing_gate"]["passed"] is False
    assert result["listing_mode"]["full_listing"] is False
    assert result["accounting_units"][0]["listed"] is False
    assert result["hard_to_service"] == []
    assert result["overall_risk"] == "medium"


def test_confirmed_none_fails_gate_and_contributes_high_risk():
    fields = {
        "project_type": ["service"],
        "control_roles": ["6"],
        "service_delivery_mode": "all_external",
        "has_telecom_capability": "no",
        "capability_ratio": "all_external",
        "six_daowei_facts_confirmed": True,
        "six_daowei_level": "none",
        **_all_dimensions("not_in_place"),
    }

    result = run_diagnosis(["service"], fields)

    assert result["six_daowei_check"]["listing_gate"]["passed"] is False
    assert result["listing_mode"]["full_listing"] is False
    assert result["overall_risk"] == "high"


def test_strong_label_cannot_bypass_a_dimension_that_is_not_in_place():
    dimensions = _all_dimensions("in_place")
    dimensions["six_daowei_project_management"] = "not_in_place"
    fields = {
        "project_type": ["service"],
        "control_roles": ELIGIBLE_ROLES,
        "service_delivery_mode": "all_telecom",
        "six_daowei_facts_confirmed": True,
        "six_daowei_level": "strong",
        **dimensions,
    }

    check = assess_six_daowei(fields)

    assert check["listing_gate"]["passed"] is False
    assert check["listing_gate"]["all_dimensions_in_place"] is False


def test_strong_label_cannot_bypass_missing_required_roles():
    fields = {
        "project_type": ["service"],
        "control_roles": ["6"],
        "service_delivery_mode": "all_telecom",
        "six_daowei_facts_confirmed": True,
        "six_daowei_level": "strong",
        **_all_dimensions("in_place"),
    }

    check = assess_six_daowei(fields)

    assert check["listing_gate"]["passed"] is False
    assert check["listing_gate"]["roles_eligible"] is False


def test_telecom_standard_product_stays_full_when_six_daowei_fails():
    dimensions = _all_dimensions("in_place")
    dimensions["six_daowei_operations_autonomy"] = "pending_evidence"
    fields = {
        "project_type": ["other"],
        "control_roles": ELIGIBLE_ROLES,
        "six_daowei_facts_confirmed": True,
        "six_daowei_level": "medium",
        **dimensions,
    }
    units = [{"name": "天翼云", "declared_type": "标品", "listed": "uncertain"}]

    result = run_diagnosis(["other"], fields, accounting_units=units)

    assert result["six_daowei_check"]["listing_gate"]["passed"] is False
    assert result["accounting_units"][0]["listed"] is True
    assert result["listing_mode"]["full_listing"] is True
