from accounting_structure import (
    derive_final_units,
    invalidate_full_unit_checks,
    normalize_structure,
    prepare_structure_update,
    relationship_suggestion,
    structure_from_units,
    validate_structure,
)


def _source(name, declared_type, amount=100):
    return {"name": name, "declared_type": declared_type, "amount": amount}


def test_project_can_have_combined_and_independent_final_units_together():
    structure = structure_from_units([
        _source("设备", "设备"),
        _source("集成服务", "服务"),
        _source("运维", "服务"),
    ])
    first, second, _third = structure["source_units"]
    structure["groups"] = [{
        "id": "grp-main",
        "name": "系统交付",
        "source_unit_ids": [first["id"], second["id"]],
        "po_facts": {
            "po1_independent_benefit": "no",
            "po2_significant_integration": "yes",
            "po3_modification": "no",
            "po4_interdependence": "yes",
        },
        "confirmed_relationship": "combined",
    }]
    structure = normalize_structure(structure)

    finals = derive_final_units(structure)

    assert {unit["id"] for unit in finals} == {"grp-main", structure["source_units"][2]["id"]}
    assert next(unit for unit in finals if unit["id"] == "grp-main")["relationship"] == "combined"


def test_po_answers_generate_relationship_suggestion():
    assert relationship_suggestion({
        "po1_independent_benefit": "yes",
        "po2_significant_integration": "no",
        "po3_modification": "no",
        "po4_interdependence": "no",
    }) == "separate"
    assert relationship_suggestion({
        "po1_independent_benefit": "yes",
        "po2_significant_integration": "yes",
        "po3_modification": "no",
        "po4_interdependence": "no",
    }) == "combined"


def test_standard_product_is_fixed_full_and_cannot_join_group():
    structure = structure_from_units([_source("天翼云", "标品"), _source("服务", "服务")])
    standard, service = structure["source_units"]
    assert structure["decisions"][standard["id"]]["listing_intent"] == "full"
    structure["groups"] = [{
        "id": "grp-1", "name": "错误组合",
        "source_unit_ids": [standard["id"], service["id"]],
        "po_facts": {}, "confirmed_relationship": None,
    }]
    assert any("标品" in error for error in validate_structure(structure, for_submit=True))


def test_amount_only_change_keeps_confirmed_unit_checks():
    old = structure_from_units([_source("设备", "设备", 100)])
    source_id = old["source_units"][0]["id"]
    old["decisions"][source_id].update({"listing_intent": "full", "listing_intent_confirmed": True})
    old["decisions"][source_id]["six_daowei"]["confirmation_status"] = "confirmed"
    old["decisions"][source_id]["r08"]["confirmation_status"] = "confirmed"
    incoming = normalize_structure(old)
    incoming["source_units"][0]["amount"] = 200

    updated = prepare_structure_update(old, incoming)

    assert updated["decisions"][source_id]["six_daowei"]["confirmation_status"] == "confirmed"
    assert updated["decisions"][source_id]["r08"]["confirmation_status"] == "confirmed"


def test_type_change_stales_only_affected_unit_checks():
    old = structure_from_units([_source("A", "设备"), _source("B", "服务")])
    for source in old["source_units"]:
        decision = old["decisions"][source["id"]]
        decision.update({"listing_intent": "full", "listing_intent_confirmed": True})
        decision["six_daowei"]["confirmation_status"] = "confirmed"
        decision["r08"]["confirmation_status"] = "confirmed"
    changed_id = old["source_units"][0]["id"]
    untouched_id = old["source_units"][1]["id"]
    incoming = normalize_structure(old)
    incoming["source_units"][0]["declared_type"] = "成品软件"

    updated = prepare_structure_update(old, incoming)

    assert updated["decisions"][changed_id]["listing_intent_confirmed"] is False
    assert updated["decisions"][untouched_id]["listing_intent_confirmed"] is True
    assert updated["decisions"][changed_id]["six_daowei"]["confirmation_status"] == "stale"
    assert updated["decisions"][untouched_id]["six_daowei"]["confirmation_status"] == "confirmed"


def test_shared_fact_change_stales_all_full_intent_units_only():
    structure = structure_from_units([_source("A", "设备"), _source("B", "服务")])
    first, second = structure["source_units"]
    for source, intent in ((first, "full"), (second, "net")):
        decision = structure["decisions"][source["id"]]
        decision.update({"listing_intent": intent, "listing_intent_confirmed": True})
        decision["six_daowei"]["confirmation_status"] = "confirmed"
        decision["r08"]["confirmation_status"] = "confirmed"

    updated = invalidate_full_unit_checks(structure)

    assert updated["decisions"][first["id"]]["six_daowei"]["confirmation_status"] == "stale"
    assert updated["decisions"][second["id"]]["six_daowei"]["confirmation_status"] == "confirmed"


def test_submit_requires_grouping_and_intent_but_not_evidence_completion():
    structure = structure_from_units([_source("服务", "服务")])
    source_id = structure["source_units"][0]["id"]
    structure["decisions"][source_id].update({"listing_intent": "full", "listing_intent_confirmed": True})

    assert validate_structure(structure, for_submit=True) == []


def test_other_type_must_be_reclassified_before_submit():
    structure = structure_from_units([_source("待分类内容", "其他")])
    source_id = structure["source_units"][0]["id"]
    structure["decisions"][source_id].update({"listing_intent": "net", "listing_intent_confirmed": True})

    assert any("其他" in error for error in validate_structure(structure, for_submit=True))
