"""引导式自然语言填报的规范化与放行状态机。

本模块只处理交互完整性，不运行规则引擎，也不产生风险或列收结论。
"""

from __future__ import annotations

import copy
import re


MAX_FOLLOW_UP_ROUNDS = 3
MAX_SIMPLE_FACT_GAPS = 5

SECTION_DEFINITIONS = {
    "basic": {
        "title": "项目基本情况",
        "prompt": (
            "请先介绍这是一个什么项目，包括客户名称和类型、BPM 商机编号、项目背景、"
            "建设或服务地点，以及预计实施和服务周期。可以说明项目目前处于投标、合同签订"
            "还是实施阶段；暂时不知道的信息可以直接写“尚未确定”。"
        ),
        "example": (
            "本项目客户为某政府单位，BPM 编号为 BPM2026XXXXX，主要解决现有视频监控系统"
            "升级和三年运维问题，计划于 2026 年开始实施。"
        ),
    },
    "delivery": {
        "title": "项目交付内容",
        "prompt": (
            "请用自己的话说明项目具体要向客户提供什么，以及客户最终能够使用或获得什么。"
            "如果同时包含设备、软件、施工、系统集成、运维服务、线路或机柜，请尽量分开描述，"
            "并说明已知的大致金额或占比；暂时不需要自行判断核算方式。"
        ),
        "example": (
            "项目包括监控设备升级、部分点位迁移施工、IDC 机柜租赁和三年运维服务。设备和"
            "施工由合作方提供，线路及部分机柜为电信自有产品。"
        ),
    },
    "responsibilities": {
        "title": "电信与供应商分工",
        "prompt": (
            "请说明从前期方案到最终交付过程中，电信和供应商分别负责什么。重点描述谁确认需求、"
            "制定和确定方案、谈判应标、决定采购、组织实施、管理进度质量、编制验收材料和负责运维；"
            "请说清电信是主导并承担责任，还是仅协调、配合或转交材料。"
        ),
        "example": (
            "电信负责需求沟通、总体方案确定、项目进度管理和客户验收；供应商负责设备安装和"
            "现场施工，并向电信提交施工及测试材料。"
        ),
    },
    "acceptance": {
        "title": "最终交付与验收形态",
        "prompt": (
            "请说明项目完成后客户最终收到什么、怎样确认项目完成。还请说明由谁组织客户验收、"
            "谁编制最终验收报告、供应商材料是否经过电信整理审核，以及设备或其他资产验收后归谁所有。"
        ),
        "example": (
            "项目最终交付一套可以正常运行的室分覆盖系统，由电信组织测试并向客户提交验收报告。"
            "供应商提供施工和测试资料，电信审核整理后形成面向客户的最终交付材料。"
        ),
    },
    "commercial": {
        "title": "商务与采购安排",
        "prompt": (
            "请介绍客户如何采购本项目、电信如何采购供应商服务，以及前后向合同和付款安排。"
            "可以说明采购方式、供应商是否确定、前后向是否存在关联关系、客户付款节点，以及"
            "电信采购是否需要预付款、项目是否存在垫资。"
        ),
        "example": (
            "客户通过公开招标采购，合同签订后支付 30%，后续按年度考核结果分期支付。后向供应商"
            "尚未确定，计划公开招标，不涉及关联关系，但可能存在前期垫资。"
        ),
    },
    "financial": {
        "title": "收入、成本与利润情况",
        "prompt": (
            "请尽量按不同交付内容说明收入和成本，不要只填写项目总金额。如果同时包含服务、设备、"
            "软件或施工，请分别说明各部分收入、成本和预计利润率，并区分服务部分利润率与项目整体"
            "利润率；没有数据时可以说明“暂不清楚，待测算”。"
        ),
        "example": (
            "项目总收入约 730 万元。其中技术服务收入 351.8 万元、成本 319.7 万元，预计利润率"
            "8.48%；设备和施工收入约 378.6 万元、成本 375 万元；整体利润率尚未最终测算。"
        ),
    },
}

SECTION_KEYS = tuple(SECTION_DEFINITIONS)
SKELETON_SECTIONS = ("basic", "delivery", "responsibilities", "acceptance", "financial")
VALID_SECTION_STATUSES = {
    "covered", "partial", "missing", "not_applicable", "unknown_confirmed",
}
VALID_READINESS_STATUSES = {
    "not_started", "insufficient", "near_ready", "ready", "blocked",
}


def empty_guided_input() -> dict:
    return {
        "schema_version": 1,
        "sections": {
            key: {"text": "", "explicit_unknown": False}
            for key in SECTION_KEYS
        },
    }


def normalize_guided_input(value) -> dict:
    raw = value if isinstance(value, dict) else {}
    raw_sections = raw.get("sections") if isinstance(raw.get("sections"), dict) else raw
    normalized = empty_guided_input()
    for key in SECTION_KEYS:
        incoming = raw_sections.get(key) if isinstance(raw_sections, dict) else None
        if isinstance(incoming, str):
            text = incoming
            explicit_unknown = False
        elif isinstance(incoming, dict):
            text = incoming.get("text") or ""
            explicit_unknown = incoming.get("explicit_unknown") is True
        else:
            text = ""
            explicit_unknown = False
        normalized["sections"][key] = {
            "text": str(text).strip()[:12000],
            "explicit_unknown": explicit_unknown,
        }
    return normalized


def has_minimum_starting_content(guided_input: dict) -> bool:
    sections = normalize_guided_input(guided_input)["sections"]
    return bool(sections["basic"]["text"] and sections["delivery"]["text"])


def empty_coverage() -> dict:
    return {
        "schema_version": 1,
        "round": 0,
        "readiness": "not_started",
        "sections": {
            key: {
                "status": "missing",
                "summary": "",
                "missing_topics": [],
                "contradictions": [],
                "evidence": [],
            }
            for key in SECTION_KEYS
        },
        "blocking_topics": [],
        "deferred_topics": [],
        "acknowledged_unknown_fields": [],
        "simple_fact_gaps": [],
        "unresolved_simple_fact_gaps": [],
        "contradictions": [],
        "follow_up_questions": [],
    }


def _string_list(value, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip()[:500] for item in value if str(item).strip()][:limit]


_DIAGNOSIS_TERMS = re.compile(
    r"全额列收|净额列收|差额列收|风险|合规|不合规|规则命中|规则诊断|后续规则|整改|主要责任人|代理人"
)


def sanitize_fact_summary(value) -> str:
    """移除事实整理阶段越界的诊断/列收判断，尽量保留同句中的事实。"""
    text = str(value or "").strip()
    if not text or not _DIAGNOSIS_TERMS.search(text):
        return text[:2000]
    kept: list[str] = []
    for sentence in re.split(r"[。！？；\n]+", text):
        sentence = sentence.strip(" ，,;；")
        if not sentence:
            continue
        safe_clauses = [
            clause.strip(" ，,;；")
            for clause in re.split(r"[，,]+", sentence)
            if clause.strip(" ，,;；") and not _DIAGNOSIS_TERMS.search(clause)
        ]
        if safe_clauses:
            kept.append("，".join(safe_clauses))
    return "；".join(kept)[:2000]


def normalize_coverage(value, *, round_no: int = 0) -> dict:
    raw = value if isinstance(value, dict) else {}
    normalized = empty_coverage()
    normalized["round"] = max(0, min(int(round_no or 0), MAX_FOLLOW_UP_ROUNDS))
    if raw.get("readiness") in VALID_READINESS_STATUSES:
        normalized["readiness"] = raw["readiness"]
    raw_sections = raw.get("sections") if isinstance(raw.get("sections"), dict) else {}
    for key in SECTION_KEYS:
        item = raw_sections.get(key) if isinstance(raw_sections.get(key), dict) else {}
        status = item.get("status")
        if status not in VALID_SECTION_STATUSES:
            status = "missing"
        normalized["sections"][key] = {
            "status": status,
            "summary": sanitize_fact_summary(item.get("summary")),
            "missing_topics": _string_list(item.get("missing_topics"), 12),
            "contradictions": _string_list(item.get("contradictions"), 12),
            "evidence": _string_list(item.get("evidence"), 20),
        }
    normalized["blocking_topics"] = _string_list(raw.get("blocking_topics"), 20)
    normalized["deferred_topics"] = _string_list(raw.get("deferred_topics"), 30)
    normalized["acknowledged_unknown_fields"] = _string_list(
        raw.get("acknowledged_unknown_fields"), 50,
    )
    normalized["simple_fact_gaps"] = _string_list(raw.get("simple_fact_gaps"), 50)
    normalized["unresolved_simple_fact_gaps"] = _string_list(
        raw.get("unresolved_simple_fact_gaps"), 50,
    )
    normalized["contradictions"] = _string_list(raw.get("contradictions"), 20)
    normalized["follow_up_questions"] = [
        question for question in _string_list(raw.get("follow_up_questions"), 12)
        if not _DIAGNOSIS_TERMS.search(question)
    ][:5]
    return normalized


_STATUS_RANK = {
    "missing": 0,
    "unknown_confirmed": 1,
    "partial": 2,
    "covered": 3,
    "not_applicable": 3,
}
_CORRECTION_MARKERS = re.compile(r"更正|纠正|前述有误|之前说错|改为|应为")


def _merge_summary(previous: str, incoming: str, *, allow_replace: bool) -> str:
    previous = sanitize_fact_summary(previous)
    incoming = sanitize_fact_summary(incoming)
    if allow_replace or not previous:
        return incoming or previous
    if not incoming:
        return previous
    if incoming in previous:
        return previous
    if previous in incoming:
        return incoming
    return f"{previous}；补充：{incoming}"[:2000]


def _resolved_by_metric_correction(contradiction: str, correction: str) -> bool:
    if not re.search(r"不是同一|口径.*(?:区分|不同)|分别(?:是|为)", correction or ""):
        return False
    metrics = re.findall(r"\d+(?:\.\d+)?\s*%", contradiction or "")
    return bool(metrics) and all(metric.replace(" ", "") in (correction or "").replace(" ", "") for metric in metrics)


def merge_coverage(previous, incoming, *, round_no: int, latest_user_text: str = "") -> dict:
    """跨轮累积已确认事实，避免模型重算时把既有摘要和覆盖度弄丢。"""
    old = normalize_coverage(previous, round_no=round_no)
    new = normalize_coverage(incoming, round_no=round_no)
    allow_replace = bool(_CORRECTION_MARKERS.search(latest_user_text or ""))
    merged = copy.deepcopy(new)
    for key in SECTION_KEYS:
        old_item = old["sections"][key]
        new_item = new["sections"][key]
        if _STATUS_RANK[new_item["status"]] < _STATUS_RANK[old_item["status"]]:
            merged["sections"][key]["status"] = old_item["status"]
        merged["sections"][key]["summary"] = _merge_summary(
            old_item["summary"], new_item["summary"], allow_replace=allow_replace,
        )
        merged["sections"][key]["evidence"] = list(dict.fromkeys([
            *old_item.get("evidence", []), *new_item.get("evidence", []),
        ]))[:20]
        if allow_replace:
            merged["sections"][key]["contradictions"] = [
                item for item in merged["sections"][key].get("contradictions", [])
                if not _resolved_by_metric_correction(item, latest_user_text)
            ]
    if allow_replace:
        merged["contradictions"] = [
            item for item in merged.get("contradictions", [])
            if not _resolved_by_metric_correction(item, latest_user_text)
        ]
    # 待确认主题以本轮为准；旧矛盾一旦解决不能继续残留。
    merged["deferred_topics"] = list(new.get("deferred_topics", []))[:30]
    if allow_replace and not merged.get("contradictions") and not any(
        item.get("contradictions") for item in merged.get("sections", {}).values()
    ):
        merged["deferred_topics"] = [
            topic for topic in merged["deferred_topics"] if "矛盾" not in topic
        ]
    merged["acknowledged_unknown_fields"] = list(dict.fromkeys([
        *old.get("acknowledged_unknown_fields", []),
        *new.get("acknowledged_unknown_fields", []),
    ]))[:50]
    return merged


def evaluate_readiness(
    coverage: dict,
    *,
    simple_fact_gaps: list[str] | None = None,
    has_source_units: bool = False,
) -> dict:
    """根据可解释覆盖信息计算交互状态，AI 不能自行声明 ready。"""
    result = copy.deepcopy(normalize_coverage(coverage, round_no=coverage.get("round", 0)))
    if simple_fact_gaps is not None:
        result["simple_fact_gaps"] = list(dict.fromkeys(simple_fact_gaps))

    section_blockers: list[str] = []
    for key in SKELETON_SECTIONS:
        item = result["sections"][key]
        status = item["status"]
        # 财务信息允许明确“待测算”；其余项目骨架不能只用“不知道”放行。
        allowed = {"covered", "partial"}
        if key == "financial":
            allowed.add("unknown_confirmed")
        if status not in allowed:
            section_blockers.append(SECTION_DEFINITIONS[key]["title"])

    contradictions = list(result["contradictions"])
    for item in result["sections"].values():
        contradictions.extend(item.get("contradictions") or [])
    contradictions = list(dict.fromkeys(contradictions))
    result["contradictions"] = contradictions

    # 模型提出的主题只是“可继续补充”，不能夺走服务端的放行权。
    advisory_topics = list(dict.fromkeys([
        *result.get("deferred_topics", []), *result.get("blocking_topics", []),
    ]))
    blockers: list[str] = []
    blockers.extend(f"缺少{label}" for label in section_blockers)
    if not has_source_units:
        blockers.append("尚不能形成初步核算单元")
    if contradictions:
        blockers.append("存在未解决的事实矛盾")
    blockers = list(dict.fromkeys(blockers))
    result["blocking_topics"] = blockers
    result["deferred_topics"] = advisory_topics

    skeleton_ready = not section_blockers and has_source_units and not contradictions
    acknowledged_unknown = set(result.get("acknowledged_unknown_fields") or [])
    unresolved_simple_gaps = [
        key for key in result["simple_fact_gaps"] if key not in acknowledged_unknown
    ]
    result["unresolved_simple_fact_gaps"] = unresolved_simple_gaps
    gaps_ready = len(unresolved_simple_gaps) <= MAX_SIMPLE_FACT_GAPS
    if skeleton_ready and gaps_ready:
        readiness = "ready"
        result["follow_up_questions"] = []
    elif result["round"] >= MAX_FOLLOW_UP_ROUNDS:
        readiness = "blocked"
        result["follow_up_questions"] = []
    else:
        covered_count = sum(
            1 for key in SKELETON_SECTIONS
            if result["sections"][key]["status"] in {"covered", "partial", "unknown_confirmed"}
        )
        readiness = "near_ready" if covered_count >= 3 else "insufficient"
    result["readiness"] = readiness
    return result


def guided_input_as_message(guided_input: dict) -> str:
    sections = normalize_guided_input(guided_input)["sections"]
    chunks = ["【六块引导式项目说明】"]
    for key, definition in SECTION_DEFINITIONS.items():
        item = sections[key]
        text = item["text"] or ("暂不清楚" if item["explicit_unknown"] else "未填写")
        chunks.append(f"\n## {definition['title']}\n{text}")
    return "\n".join(chunks)
