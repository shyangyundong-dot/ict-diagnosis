"""表单优先改造：AI 助填只能给建议，必须人工核对后才能进入正式诊断。"""

import inspect
import json

from accounting_structure import structure_from_units, validate_structure
from ai_chat import _legal_field_suggestion
from models.diagnosis import ChatSession
from routers import diagnosis as router_mod


def test_pending_ai_field_is_distinct_from_confirmed_manual_field():
    session = ChatSession(
        session_id="review-test",
        field_review_json=json.dumps({
            "schema_version": 1,
            "fields": {
                "customer_type": {"source": "ai_bulk", "status": "pending"},
                "bpm_id": {"source": "manual", "status": "confirmed"},
            },
        }),
    )

    review = router_mod._load_field_review(session)
    assert router_mod._pending_ai_fields(review) == ["customer_type"]

    review["fields"]["customer_type"]["status"] = "confirmed"
    assert router_mod._pending_ai_fields(review) == []


def test_ai_cannot_replace_a_confirmed_value_in_bulk_merge_policy():
    review = {"schema_version": 1, "fields": {}}
    router_mod._set_field_review(review, "customer_type", "manual", "confirmed")
    assert router_mod._pending_ai_fields(review) == []
    assert review["fields"]["customer_type"] == {"source": "manual", "status": "confirmed"}


def test_field_help_suggestion_must_be_a_legal_field_option():
    assert _legal_field_suggestion("customer_type", "state_owned") == "state_owned"
    assert _legal_field_suggestion("customer_type", "made_up_value") is None
    assert _legal_field_suggestion("project_type", ["service", "system_integration"]) == ["service", "system_integration"]
    assert _legal_field_suggestion("project_type", ["service", "bad_type"]) is None


def test_ai_segmented_source_units_must_be_explicitly_reviewed_before_submit():
    structure = structure_from_units([{"name": "实施服务", "declared_type": "服务"}])
    source_id = structure["source_units"][0]["id"]
    structure["decisions"][source_id].update({"listing_intent": "net", "listing_intent_confirmed": True})
    structure["source_units_review_status"] = "pending"

    assert any("AI 切分" in error for error in validate_structure(structure, for_submit=True))

    structure["source_units_review_status"] = "confirmed"
    assert validate_structure(structure, for_submit=True) == []


def test_confirm_endpoint_enforces_pending_ai_review_before_running_rules():
    source = inspect.getsource(router_mod.confirm_and_diagnose)
    assert "_pending_ai_fields(review)" in source
    assert "请先核对 AI 预填字段" in source
    assert source.index("_pending_ai_fields(review)") < source.index("run_diagnosis(")


def test_assist_endpoints_do_not_execute_rule_engine():
    assert "run_diagnosis" not in inspect.getsource(router_mod.chat)
    assert "run_diagnosis" not in inspect.getsource(router_mod.get_field_help)


def test_guided_intake_endpoints_do_not_execute_rule_engine():
    for endpoint in (
        router_mod._assess_guided_session,
        router_mod.submit_guided_intake,
        router_mod.reply_guided_intake,
        router_mod.supplement_guided_intake,
    ):
        assert "run_diagnosis" not in inspect.getsource(endpoint)


def test_guided_follow_up_has_hard_round_limit_and_confirm_gate():
    reply_source = inspect.getsource(router_mod.reply_guided_intake)
    assert "MAX_FOLLOW_UP_ROUNDS" in reply_source
    assert "集中追问已结束" in reply_source

    confirm_source = inspect.getsource(router_mod.confirm_and_diagnose)
    assert "coverage.get(\"readiness\") != \"ready\"" in confirm_source
    assert confirm_source.index("coverage.get(\"readiness\")") < confirm_source.index("run_diagnosis(")
