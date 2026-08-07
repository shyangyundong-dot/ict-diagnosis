from guided_intake import (
    MAX_FOLLOW_UP_ROUNDS,
    SECTION_KEYS,
    empty_coverage,
    empty_guided_input,
    evaluate_readiness,
    guided_input_as_message,
    has_minimum_starting_content,
    merge_coverage,
    normalize_coverage,
    normalize_guided_input,
)
from ai_chat import (
    _build_deepseek_payload,
    augment_project_types_from_units,
    derive_safe_guided_fields,
    merge_guided_source_units,
    sanitize_guided_extracted_fields,
    sanitize_guided_source_units,
)


def _covered_payload(round_no=0):
    value = empty_coverage()
    value["round"] = round_no
    for key in SECTION_KEYS:
        value["sections"][key]["status"] = "covered"
        value["sections"][key]["summary"] = f"{key} summary"
    return value


def test_guided_input_requires_basic_and_delivery_to_start():
    value = empty_guided_input()
    assert has_minimum_starting_content(value) is False

    value["sections"]["basic"]["text"] = "某政府客户的视频运维项目"
    assert has_minimum_starting_content(value) is False

    value["sections"]["delivery"]["text"] = "交付设备升级和三年运维服务"
    assert has_minimum_starting_content(value) is True


def test_guided_input_normalizes_text_and_explicit_unknown():
    value = normalize_guided_input({
        "basic": "  项目背景  ",
        "financial": {"text": "", "explicit_unknown": True},
        "unexpected": "drop me",
    })
    assert set(value["sections"]) == set(SECTION_KEYS)
    assert value["sections"]["basic"]["text"] == "项目背景"
    assert value["sections"]["financial"]["explicit_unknown"] is True
    assert "unexpected" not in value["sections"]


def test_ai_cannot_mark_ready_without_source_units():
    result = evaluate_readiness(_covered_payload(), simple_fact_gaps=[], has_source_units=False)
    assert result["readiness"] != "ready"
    assert "尚不能形成初步核算单元" in result["blocking_topics"]


def test_ready_requires_no_more_than_five_simple_fact_gaps():
    ready = evaluate_readiness(
        _covered_payload(), simple_fact_gaps=[f"f{i}" for i in range(5)], has_source_units=True,
    )
    assert ready["readiness"] == "ready"

    too_many = evaluate_readiness(
        _covered_payload(), simple_fact_gaps=[f"f{i}" for i in range(6)], has_source_units=True,
    )
    assert too_many["readiness"] == "near_ready"


def test_explicitly_unknown_simple_fields_are_deferred_instead_of_reasked():
    coverage = _covered_payload()
    coverage["acknowledged_unknown_fields"] = [
        "supplier_confirmed", "procurement_method", "related_party",
        "has_prepayment", "has_advance_funding",
    ]
    coverage["follow_up_questions"] = ["后向供应商、采购方式和垫资情况是什么？"]
    result = evaluate_readiness(
        coverage,
        simple_fact_gaps=[
            "bpm_id", "supplier_confirmed", "procurement_method", "related_party",
            "gross_margin", "has_prepayment", "has_advance_funding", "service_delivery_mode",
        ],
        has_source_units=True,
    )
    assert result["readiness"] == "ready"
    assert result["follow_up_questions"] == []
    assert result["acknowledged_unknown_fields"] == coverage["acknowledged_unknown_fields"]
    assert result["unresolved_simple_fact_gaps"] == ["bpm_id", "gross_margin", "service_delivery_mode"]


def test_ai_advisory_topics_cannot_block_a_deterministically_ready_project():
    coverage = _covered_payload()
    coverage["blocking_topics"] = ["付款细节仍可继续补充", "供应商名称尚未明确"]
    coverage["follow_up_questions"] = ["请继续补充付款细节"]

    result = evaluate_readiness(
        coverage,
        simple_fact_gaps=["has_prepayment", "has_advance_funding"],
        has_source_units=True,
    )

    assert result["readiness"] == "ready"
    assert result["blocking_topics"] == []
    assert result["deferred_topics"] == ["付款细节仍可继续补充", "供应商名称尚未明确"]
    assert result["follow_up_questions"] == []


def test_unresolved_contradictions_block_confirmation():
    coverage = _covered_payload()
    coverage["sections"]["acceptance"]["contradictions"] = ["验收报告责任主体前后不一致"]
    result = evaluate_readiness(coverage, simple_fact_gaps=[], has_source_units=True)
    assert result["readiness"] == "near_ready"
    assert "存在未解决的事实矛盾" in result["blocking_topics"]


def test_round_three_becomes_terminal_blocked_when_still_incomplete():
    coverage = _covered_payload(round_no=MAX_FOLLOW_UP_ROUNDS)
    coverage["sections"]["acceptance"]["status"] = "missing"
    coverage["follow_up_questions"] = ["继续问下去"]
    result = evaluate_readiness(coverage, simple_fact_gaps=[], has_source_units=True)
    assert result["readiness"] == "blocked"
    assert result["follow_up_questions"] == []


def test_financial_explicit_unknown_can_pass_but_acceptance_cannot():
    coverage = _covered_payload()
    coverage["sections"]["financial"]["status"] = "unknown_confirmed"
    assert evaluate_readiness(
        coverage, simple_fact_gaps=[], has_source_units=True,
    )["readiness"] == "ready"

    coverage["sections"]["acceptance"]["status"] = "unknown_confirmed"
    assert evaluate_readiness(
        coverage, simple_fact_gaps=[], has_source_units=True,
    )["readiness"] != "ready"


def test_coverage_contract_limits_questions_and_drops_unknown_status():
    raw = {
        "sections": {"basic": {"status": "AI-says-ready"}},
        "follow_up_questions": [f"q{i}" for i in range(8)],
    }
    normalized = normalize_coverage(raw, round_no=99)
    assert normalized["sections"]["basic"]["status"] == "missing"
    assert normalized["round"] == MAX_FOLLOW_UP_ROUNDS
    assert len(normalized["follow_up_questions"]) == 5


def test_coverage_round_trip_preserves_computed_readiness():
    stored = _covered_payload()
    stored["readiness"] = "near_ready"
    assert normalize_coverage(stored)["readiness"] == "near_ready"


def test_follow_up_merge_does_not_lose_previously_covered_facts():
    previous = _covered_payload(round_no=0)
    previous["sections"]["delivery"]["summary"] = "包含移动标包、线路和运维服务。"
    incoming = _covered_payload(round_no=1)
    incoming["sections"]["delivery"].update({
        "status": "partial",
        "summary": "补充了设备安装施工。",
        "evidence": ["设备安装施工"],
    })

    merged = merge_coverage(previous, incoming, round_no=1, latest_user_text="设备还需要安装施工")

    assert merged["sections"]["delivery"]["status"] == "covered"
    assert "移动标包" in merged["sections"]["delivery"]["summary"]
    assert "设备安装施工" in merged["sections"]["delivery"]["summary"]


def test_follow_up_merge_drops_resolved_advisory_topics():
    previous = _covered_payload()
    previous["deferred_topics"] = ["存在未解决的事实矛盾", "旧问题"]
    incoming = _covered_payload(round_no=1)
    incoming["deferred_topics"] = ["当前仍待确认的事项"]
    merged = merge_coverage(previous, incoming, round_no=1)
    assert merged["deferred_topics"] == ["当前仍待确认的事项"]


def test_explicit_metric_correction_clears_the_matching_numeric_contradiction():
    previous = _covered_payload()
    incoming = _covered_payload(round_no=1)
    contradiction = "全项目利润率6.04%，按服务收入成本计算约6.67%，两者口径冲突"
    incoming["contradictions"] = [contradiction]
    incoming["sections"]["financial"]["contradictions"] = [contradiction]
    incoming["deferred_topics"] = ["存在未解决的事实矛盾"]
    correction = "口径更正：6.67%是服务利润率，6.04%是全项目利润率，二者不是同一指标。"
    merged = merge_coverage(previous, incoming, round_no=1, latest_user_text=correction)
    assert merged["contradictions"] == []
    assert merged["sections"]["financial"]["contradictions"] == []
    assert merged["deferred_topics"] == []


def test_fact_summary_drops_collection_stage_listing_conclusions():
    raw = _covered_payload()
    raw["sections"]["financial"]["summary"] = "服务收入100万元，利润率8%；该项目可申请全额列收，风险较低。"
    normalized = normalize_coverage(raw)
    summary = normalized["sections"]["financial"]["summary"]
    assert "服务收入100万元" in summary
    assert "全额列收" not in summary
    assert "风险" not in summary


def test_guided_message_has_all_six_named_sections():
    text = guided_input_as_message(empty_guided_input())
    assert text.startswith("【六块引导式项目说明】")
    assert text.count("\n## ") == 6


def test_guided_extraction_only_accepts_legal_field_values():
    source = "客户是政府机关，项目类型包括服务。BPM编号是BPM20260001。采购方式暂不清楚。"
    value = sanitize_guided_extracted_fields({
        "project_type": {"value": ["service"], "evidence": "项目类型包括服务"},
        "customer_type": {"value": "government", "evidence": "客户是政府机关"},
        "procurement_method": {"value": "invented", "evidence": "采购方式暂不清楚"},
        "control_roles": {"value": ["6", "7", "9"], "evidence": "客户是政府机关"},
        "bpm_id": {"value": "BPM20260001", "evidence": "BPM编号是BPM20260001"},
        "unknown_key": {"value": "drop", "evidence": "客户是政府机关"},
    }, source_text=source)
    assert value == {
        "project_type": ["service"],
        "customer_type": "government",
        "bpm_id": "BPM20260001",
    }


def test_unknown_evidence_cannot_be_converted_to_false_boolean():
    source = "前后向合同、付款节点、预付款和垫资目前都暂不清楚。"
    value = sanitize_guided_extracted_fields({
        "has_prepayment": {"value": False, "evidence": "预付款和垫资目前都暂不清楚"},
        "has_advance_funding": {"value": False, "evidence": "预付款和垫资目前都暂不清楚"},
        "related_party": {"value": "uncertain", "evidence": "前后向合同、付款节点、预付款和垫资目前都暂不清楚"},
    }, source_text=source)

    assert value == {"related_party": "uncertain"}


def test_forward_installment_schedule_cannot_be_mislabeled_as_standard_payment_terms():
    source = "前向付款为客户支付10%预付款、每月进度款至85%、竣工验收支付12%、3%质保金。"
    value = sanitize_guided_extracted_fields({
        "payment_terms": {"value": "standard", "evidence": source},
        "has_prepayment": {"value": True, "evidence": "客户支付10%预付款"},
    }, source_text=source)
    assert value == {}


def test_v4_structured_payload_disables_thinking_and_requests_json():
    payload = _build_deepseek_payload(
        [{"role": "user", "content": "JSON"}],
        7000,
        model="deepseek-v4-flash",
        json_output=True,
    )
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["response_format"] == {"type": "json_object"}

    chat_payload = _build_deepseek_payload(
        [{"role": "user", "content": "JSON"}],
        7000,
        model="deepseek-chat",
        json_output=True,
    )
    assert "thinking" not in chat_payload


def test_source_units_split_mixed_device_and_construction_without_inventing_amounts():
    source = "本标包包括室分天线设备供货及安装施工，合计100万元，物流和白名单情况暂不清楚。"
    units = sanitize_guided_source_units([{
        "name": "室分设备及安装施工",
        "declared_type": "设备",
        "amount": 1_000_000,
        "logistics": "supplier_direct",
        "has_self_capability": False,
        "whitelisted": False,
        "reason": "可全额列收，风险较低",
        "evidence": {
            "type": "室分天线设备供货及安装施工",
            "amount": "合计100万元",
            "logistics": "物流和白名单情况暂不清楚",
            "capability": "物流和白名单情况暂不清楚",
            "whitelist": "物流和白名单情况暂不清楚",
        },
    }], source_text=source)

    assert [unit["declared_type"] for unit in units] == ["设备", "施工"]
    assert all(unit["amount"] is None for unit in units)
    assert all(unit["logistics"] == "unknown" for unit in units)
    assert all(unit["has_self_capability"] == "unknown" for unit in units)
    assert units[0]["whitelisted"] == "unknown"
    assert units[1]["whitelisted"] is None
    assert all("列收" not in unit["reason"] and "风险" not in unit["reason"] for unit in units)


def test_mixed_unit_declared_other_is_still_split_into_device_and_construction():
    source = "设备、施工代收代付约378.6万元。"
    units = sanitize_guided_source_units([{
        "name": "设备及施工代收代付",
        "declared_type": "其他",
        "amount": None,
        "evidence": {"type": "设备、施工代收代付"},
    }], source_text=source)
    assert [unit["declared_type"] for unit in units] == ["设备", "施工"]


def test_already_split_units_are_not_recursively_split_again():
    source = "设备及工程代收代付202.55万元。"
    units = sanitize_guided_source_units([
        {
            "name": "设备及工程代收代付（设备部分）",
            "declared_type": "设备",
            "amount": 202.55,
            "evidence": {"type": "设备及工程代收代付", "amount": "202.55万元"},
        },
        {
            "name": "设备及工程代收代付-施工部分",
            "declared_type": "施工",
            "amount": None,
            "evidence": {"type": "设备及工程代收代付"},
        },
    ], source_text=source)
    assert len(units) == 2
    assert not any(unit["name"].count("部分") > 1 for unit in units)
    assert units[0]["amount"] == 2_025_500


def test_cross_round_unit_merge_treats_hyphen_and_parentheses_split_names_as_same():
    previous = [
        {"name": "设备及工程代收代付（设备部分）", "declared_type": "设备"},
        {"name": "设备及工程代收代付（施工部分）", "declared_type": "施工"},
        {"name": "设备及工程代收代付-设备部分", "declared_type": "设备", "duplicate": True},
        {"name": "设备及工程代收代付-施工部分", "declared_type": "施工", "duplicate": True},
    ]
    incoming = [
        {"name": "设备及工程代收代付-设备部分", "declared_type": "设备", "amount": 1},
        {"name": "设备及工程代收代付-施工部分", "declared_type": "施工", "amount": 2},
    ]
    merged = merge_guided_source_units(previous, incoming)
    assert len(merged) == 2
    assert [unit.get("amount") for unit in merged] == [1, 2]


def test_mixed_service_device_construction_units_augment_project_type():
    fields = {"project_type": ["service"]}
    changed = augment_project_types_from_units(fields, [
        {"declared_type": "服务"}, {"declared_type": "设备"}, {"declared_type": "施工"},
    ])
    assert changed is True
    assert fields["project_type"] == ["service", "system_integration"]


def test_server_adds_missing_device_construction_and_named_lot_placeholders():
    source = (
        "交付内容包括天线设备、光缆布放和安装施工以及覆盖维保服务。"
        "电联标段约730.4万元，服务收入351.8万元。移动标段约730.4万元，内部拆分暂不清楚。"
    )
    units = sanitize_guided_source_units([{
        "name": "电联标段ICT成本服务",
        "declared_type": "服务",
        "amount": 3_518_000,
        "evidence": {"type": "服务", "amount": "服务收入351.8万元"},
    }], source_text=source)

    assert {unit["declared_type"] for unit in units} >= {"服务", "设备", "施工", "其他"}
    mobile = [unit for unit in units if "移动标段" in unit["name"]]
    assert len(mobile) == 1
    assert mobile[0]["amount"] == 7_304_000
    assert not any("电联标段和" in unit["name"] for unit in units)


def test_server_safely_derives_service_margin_delivery_mode_and_nonstandard_payment():
    source = (
        "ICT成本服务收入351.8万元，利润率约为8.48%。"
        "异地项目无法由电信自维，供应商负责现场施工和维保。"
        "前向付款为10%预付款、每月进度款、验收款及24个月后的质保金。"
    )
    assert derive_safe_guided_fields(source) == {
        "gross_margin": "pct_6_10",
        "payment_terms": "other",
        "service_delivery_mode": "all_external",
    }

    mixed = derive_safe_guided_fields(
        "BPM编号暂未提供。电信自维主投设备，其他部分采用合作方代维。"
    )
    assert mixed == {
        "service_delivery_mode": "mixed",
        "contract_matches_bpm": "uncertain",
    }
