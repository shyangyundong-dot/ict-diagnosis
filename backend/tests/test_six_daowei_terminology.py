"""业务术语回归：服务能力框架统一称为“六到位”。"""

import json
from pathlib import Path

import ai_chat
import ai_report


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_runtime_labels_use_six_daowei():
    capability = ai_chat.FIELD_DEFINITIONS["service_capability_level"]
    delivery = ai_chat.FIELD_DEFINITIONS["service_delivery_mode"]

    assert capability["deprecated"] is True
    assert "六到位" in capability["label"]
    assert "六到位" in delivery["hint"]
    assert "六到位" in ai_report.FIELD_LABELS["service_capability_level"]
    assert "六到位" in ai_chat.FIELD_DEFINITIONS["control_roles"]["label"]
    assert ai_chat.FIELD_DEFINITIONS["six_daowei_level"]["options"] == ["strong", "medium", "none"]

    rendered = json.dumps(
        {
            "capability": capability,
            "report_values": ai_report.FIELD_VALUE_LABELS["service_capability_level"],
        },
        ensure_ascii=False,
    )
    assert "六必要" not in rendered


def test_new_diagnosis_strips_legacy_global_capability_fields():
    fields = {
        "project_type": ["service"],
        "service_delivery_mode": "mixed",
        "service_capability_level": "medium",
        "six_daowei_level": "strong",
        "major_integration": True,
    }

    ai_chat.apply_derived_fields_for_diagnosis(fields)

    assert fields["service_delivery_mode"] == "mixed"
    assert "service_capability_level" not in fields
    assert "six_daowei_level" not in fields
    assert "major_integration" not in fields


def test_six_dimensions_are_manual_unit_level_confirmations_not_global_required_fields():
    fact_confirmation = ai_chat.FIELD_DEFINITIONS["six_daowei_facts_confirmed"]
    assert fact_confirmation["required"] is False
    assert fact_confirmation["manual_confirmation"] is True
    assert fact_confirmation["options"] == [True]

    keys = [
        "six_daowei_customer_insight",
        "six_daowei_solution_control",
        "six_daowei_bid_autonomy",
        "six_daowei_procurement_autonomy",
        "six_daowei_project_management",
        "six_daowei_operations_autonomy",
    ]
    for key in keys:
        spec = ai_chat.FIELD_DEFINITIONS[key]
        assert spec["required"] is False
        assert spec["manual_confirmation"] is True
        expected = ["in_place", "not_in_place", "pending_evidence"]
        if key in {"six_daowei_procurement_autonomy", "six_daowei_operations_autonomy"}:
            expected.append("not_applicable")
        assert spec["options"] == expected


def test_rule_library_uses_six_daowei():
    rules_text = (BACKEND_ROOT / "rules" / "rules.json").read_text(encoding="utf-8")
    clauses_text = (BACKEND_ROOT / "rules" / "clauses.json").read_text(encoding="utf-8")

    assert "六必要" not in rules_text
    assert "六必要" not in clauses_text
    assert "六到位缺失" in rules_text
