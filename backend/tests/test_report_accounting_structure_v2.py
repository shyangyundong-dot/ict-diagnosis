from accounting_structure import structure_from_units
from report_generator import generate_report_html
from rules.engine import run_diagnosis


def test_v2_report_distinguishes_intent_provisional_result_and_advisory_boundary():
    structure = structure_from_units([
        {"name": "服务<script>alert(1)</script>", "declared_type": "服务", "amount": 100},
    ])
    source_id = structure["source_units"][0]["id"]
    structure["decisions"][source_id].update({
        "listing_intent": "full",
        "listing_intent_confirmed": True,
    })
    result = run_diagnosis(["service"], {"project_type": ["service"]}, structure)

    html = generate_report_html(1, "BPM-X", result, "2026-07-18 12:00")

    assert "拟全额列收" in html
    assert "暂按全额列收测算" in html
    assert "辅助测算，不替代最终审核与决策" in html
    assert "本报告不发起送审" in html
    assert "<script>alert(1)</script>" not in html
    assert "服务&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_v2_report_renders_unit_level_six_and_r08_sections():
    structure = structure_from_units([
        {"name": "服务单元", "declared_type": "服务", "amount": 100},
    ])
    source_id = structure["source_units"][0]["id"]
    decision = structure["decisions"][source_id]
    decision.update({"listing_intent": "full", "listing_intent_confirmed": True})
    decision["six_daowei"].update({
        "facts_confirmed": True,
        "dimensions": {
            "customer_insight": "in_place",
            "solution_control": "pending_evidence",
            "bid_autonomy": "in_place",
            "procurement_autonomy": "not_applicable",
            "project_management": "in_place",
            "operations_autonomy": "not_applicable",
        },
        "level": "strong",
        "no_external_procurement": True,
        "no_operations_obligation": True,
        "confirmation_status": "confirmed",
    })
    decision["r08"].update({
        "answers": {"ctrl1_control_before_transfer": "pending_evidence"},
        "conclusion": "principal",
        "confirmation_status": "confirmed",
    })
    result = run_diagnosis(["service"], {"project_type": ["service"]}, structure)

    html = generate_report_html(1, "BPM-X", result, "2026-07-18 12:00")

    assert "拟全额核算单元自查" in html
    assert "六到位 + R08" in html
    assert "不适用" in html
    assert "待补证据" in html
