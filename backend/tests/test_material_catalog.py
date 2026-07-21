import json
from pathlib import Path

from accounting_structure import structure_from_units
from report_generator import generate_report_html
from rules.engine import MATERIAL_CATEGORIES, MATERIALS, MATERIAL_VERSION, run_diagnosis


RULES_DIR = Path(__file__).resolve().parents[1] / "rules"
VALID_CATEGORIES = {"process", "conditional", "financial", "exception"}
PDF_CORE_ROLES = {"1", "3", "4", "6", "7", "9", "10", "11", "13", "14", "16", "18"}
PDF_SUPPORTING_ROLES = {"2", "5", "8", "12", "15", "17", "19"}


def _load_rules():
    return json.loads((RULES_DIR / "rules.json").read_text(encoding="utf-8"))["rules"]


def test_material_catalog_has_unique_ids_names_and_four_categories():
    ids = [material["id"] for material in MATERIALS.values()]
    names = [material["name"] for material in MATERIALS.values()]

    assert len(ids) == len(set(ids))
    assert len(names) == len(set(names))
    assert set(MATERIAL_CATEGORIES) == VALID_CATEGORIES
    assert {material["category"] for material in MATERIALS.values()} <= VALID_CATEGORIES


def test_pdf_core_roles_have_complete_evidence_packages_only():
    role_materials = [material for material in MATERIALS.values() if material.get("roles")]
    represented_roles = {
        role
        for material in role_materials
        for role in material.get("roles", [])
    }

    assert PDF_CORE_ROLES <= represented_roles
    assert represented_roles.isdisjoint(PDF_SUPPORTING_ROLES)
    for role in PDF_CORE_ROLES:
        package = next(
            material
            for material in role_materials
            if material["id"] == f"MAT-PROC-R{int(role):02d}"
        )
        assert package["evidence_strength"] == "core"
        assert package["components"]
        assert "ICT项目全流程控制权角色职责和佐证材料" in package["source"]


def test_supporting_materials_cannot_substitute_for_control_evidence():
    supporting_ids = {
        "MAT-PROC-STAFF-001",
        "MAT-PROC-MANAGER-001",
        "MAT-COND-PHOTO-001",
    }
    by_id = MATERIALS

    assert all(by_id[material_id]["evidence_strength"] == "supporting" for material_id in supporting_ids)
    assert all(not by_id[material_id].get("roles") for material_id in supporting_ids)


def test_rules_reference_catalog_ids_instead_of_embedding_material_lists():
    catalog_ids = set(MATERIALS)

    for rule in _load_rules():
        assert "audit_materials" not in rule
        refs = rule.get("audit_material_refs", [])
        ref_ids = [ref["material_id"] for ref in refs]
        assert len(ref_ids) == len(set(ref_ids))
        assert set(ref_ids) <= catalog_ids


def test_reviewed_merges_and_false_duplicates_are_preserved_correctly():
    rules = {rule["id"]: rule for rule in _load_rules()}
    catalog_ids = set(MATERIALS)
    active_names = {material["name"] for material in MATERIALS.values()}

    assert "控制权证明材料" not in active_names
    assert "六到位关键角色及职责分工留痕" not in active_names
    assert {"MAT-EXC-X001", "MAT-FIN-X001", "MAT-FIN-X002", "MAT-FIN-X015"}.isdisjoint(catalog_ids)

    r01_ids = {ref["material_id"] for ref in rules["R01"]["audit_material_refs"]}
    assert "MAT-FIN-OWNERSHIP-001" in r01_ids

    r15_ids = {ref["material_id"] for ref in rules["R15"]["audit_material_refs"]}
    r28_ids = {ref["material_id"] for ref in rules["R28"]["audit_material_refs"]}
    assert "MAT-COND-SPECIAL-PROJECT-001" in r15_ids
    assert "MAT-COND-SPECIAL-BIDDER-001" in r28_ids

    r29_ids = {ref["material_id"] for ref in rules["R29"]["audit_material_refs"]}
    r30_ids = {ref["material_id"] for ref in rules["R30"]["audit_material_refs"]}
    assert "MAT-EXC-PREPAY-001" in r29_ids
    assert "MAT-EXC-ADVANCE-001" in r30_ids
    assert "MAT-EXC-ADVANCE-001" not in r29_ids
    assert "MAT-EXC-PREPAY-001" not in r30_ids


def test_runtime_checklist_uses_catalog_metadata_and_deduplicates_by_id():
    structure = structure_from_units([
        {"name": "服务单元", "declared_type": "服务", "amount": 100},
    ])
    source_id = structure["source_units"][0]["id"]
    structure["decisions"][source_id].update({
        "listing_intent": "full",
        "listing_intent_confirmed": True,
    })

    result = run_diagnosis(["service"], {"project_type": ["service"]}, structure)
    checklist = result["audit_checklist"]
    material_ids = [item["material_id"] for item in checklist]

    assert result["material_version"] == MATERIAL_VERSION
    assert len(material_ids) == len(set(material_ids))
    assert all(item["category"] in VALID_CATEGORIES for item in checklist)
    assert all(item["item"] for item in checklist)
    assert not any("≥300" in item["item"] or "取得商品或服务控制权" in item["item"] for item in checklist)


def test_report_renders_material_details_once_in_four_catalog_groups():
    result = run_diagnosis(["service"], {"project_type": ["service"]})
    by_category = {}
    for material in MATERIALS.values():
        by_category.setdefault(material["category"], material)
    result["audit_checklist"] = [
        {
            "material_id": material["id"],
            "item": material["name"],
            "purpose": material["purpose"],
            "purposes": [material["purpose"]],
            "risk_level": "tip",
            "category": material["category"],
            "evidence_strength": material["evidence_strength"],
            "components": material.get("components", []),
            "rule_ids": [],
            "unit_names": [],
        }
        for material in by_category.values()
    ]

    html = generate_report_html(1, "BPM-MATERIAL", result, "2026-07-19 12:00")

    assert "项目材料准备清单" in html
    assert "统一目录、按编号去重" in html
    assert "基础过程材料" in html
    assert "条件性合规材料" in html
    assert "财务列收材料" in html
    assert "异常补正材料" in html
    assert MATERIAL_VERSION in html
