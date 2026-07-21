import json
import os
import re

from accounting_structure import (
    R08_KEYS,
    SIX_DIMENSIONS as UNIT_SIX_DIMENSIONS,
    WHITELIST_TYPES,
    derive_final_units,
    is_v2_structure,
    legal_six_value,
    normalize_structure,
)

# 加载规则库和条款原文库
_RULES_PATH = os.path.join(os.path.dirname(__file__), "rules.json")
_CLAUSES_PATH = os.path.join(os.path.dirname(__file__), "clauses.json")
_WHITELIST_PATH = os.path.join(os.path.dirname(__file__), "whitelist.json")
_MATERIALS_PATH = os.path.join(os.path.dirname(__file__), "materials.json")

with open(_RULES_PATH, encoding="utf-8") as f:
    _RULES_DATA = json.load(f)

with open(_CLAUSES_PATH, encoding="utf-8") as f:
    _CLAUSES_DATA = json.load(f)

with open(_WHITELIST_PATH, encoding="utf-8") as f:
    _WHITELIST_DATA = json.load(f)

with open(_MATERIALS_PATH, encoding="utf-8") as f:
    _MATERIALS_DATA = json.load(f)

RULES = _RULES_DATA["rules"]
CLAUSES = _CLAUSES_DATA["clauses"]
RULE_VERSION = _RULES_DATA.get("version", "v1.0")
WHITELIST_VERSION = _WHITELIST_DATA.get("version", "v1.0")
MATERIAL_VERSION = _MATERIALS_DATA.get("version", "v1.0")
MATERIALS = {item["id"]: item for item in _MATERIALS_DATA.get("materials", [])}
MATERIAL_CATEGORIES = {
    item["id"]: item for item in _MATERIALS_DATA.get("categories", [])
}


def _material_from_id(material_id: str, purposes: list[str] | None = None) -> dict:
    source = MATERIALS.get(material_id)
    if source is None:
        raise ValueError(f"未知材料编号：{material_id}")
    category = source.get("category", "conditional")
    category_meta = MATERIAL_CATEGORIES.get(category, {})
    return {
        "material_id": material_id,
        "item": source["name"],
        "purpose": source.get("purpose", ""),
        "purposes": list(dict.fromkeys(purposes or [source.get("purpose", "")])),
        "category": category,
        "category_label": category_meta.get("label", category),
        "category_description": category_meta.get("description", ""),
        "evidence_strength": source.get("evidence_strength", "core"),
        "stage": source.get("stage"),
        "roles": source.get("roles", []),
        "components": source.get("components", []),
        "source": source.get("source"),
    }


def _resolve_rule_materials(rule: dict) -> list[dict]:
    refs = rule.get("audit_material_refs")
    if refs is None:
        return rule.get("audit_materials", [])
    resolved = []
    seen = set()
    for ref in refs:
        material_id = ref if isinstance(ref, str) else ref.get("material_id")
        if not material_id or material_id in seen:
            continue
        seen.add(material_id)
        purposes = [] if isinstance(ref, str) else ref.get("purposes") or []
        resolved.append(_material_from_id(material_id, purposes))
    return resolved


for _rule in RULES:
    _rule["audit_materials"] = _resolve_rule_materials(_rule)


def _merge_audit_material(
    audit_set: dict[str, dict],
    material: dict,
    risk_level: str,
    *,
    rule: dict | None = None,
    unit_name: str | None = None,
    purpose: str | None = None,
) -> None:
    material_id = material.get("material_id") or material.get("item")
    entry = audit_set.setdefault(material_id, {
        "material_id": material.get("material_id"),
        "item": material.get("item", ""),
        "purposes": [],
        "rule_ids": [],
        "rule_names": [],
        "unit_names": [],
        "risk_level": risk_level,
        "category": material.get("category", "conditional"),
        "category_label": material.get("category_label", "条件性合规材料"),
        "category_description": material.get("category_description", ""),
        "evidence_strength": material.get("evidence_strength", "core"),
        "stage": material.get("stage"),
        "roles": material.get("roles", []),
        "components": material.get("components", []),
        "source": material.get("source"),
    })
    purposes = [purpose] if purpose else material.get("purposes") or [material.get("purpose", "")]
    for value in purposes:
        if value and value not in entry["purposes"]:
            entry["purposes"].append(value)
    if rule and rule["rule_id"] not in entry["rule_ids"]:
        entry["rule_ids"].append(rule["rule_id"])
        entry["rule_names"].append(rule["rule_name"])
    if unit_name and unit_name not in entry["unit_names"]:
        entry["unit_names"].append(unit_name)
    if RISK_ORDER.get(risk_level, 0) > RISK_ORDER.get(entry["risk_level"], 0):
        entry["risk_level"] = risk_level

RISK_ORDER = {"high": 3, "medium": 2, "low": 1, "tip": 0}
RISK_LABEL = {"high": "高风险", "medium": "中风险", "low": "低风险", "tip": "操作提示"}

# 单字段即时预警表：填写某字段为某值时，前端立即展示预警
# 格式：{ field_key: { trigger_value, message, level } }
REALTIME_WARNINGS: dict[str, dict] = {
    "related_party": {
        "trigger_value": "yes",
        "message": "⚠️ 前后向存在关联关系，属于高风险信号，需提供商机管理员业务真实性审核记录及关联关系核查材料。",
        "level": "high",
    },
    "contract_content_same": {
        "trigger_value": "yes",
        "message": "⚠️ 前后向合同内容高度一致，是\"过手项目\"核心判断依据，高风险。请准备电信自主完成的增值服务证明。",
        "level": "high",
    },
    "acceptance_content_same": {
        "trigger_value": "yes",
        "message": "⚠️ 计划直接用供应商验收材料交客户，验收交付自主性缺失，审计时会被视为\"空转走单\"证据。建议由电信独立编制客户验收报告，并确保后向验收早于前向验收。",
        "level": "medium",
    },
    "logistics_control": {
        "trigger_value": "supplier_direct",
        "message": "⚠️ 供应商直发客户，物权流转不经电信，属于\"走单/空转\"高风险特征，不得全额列收。",
        "level": "high",
    },
    "has_prepayment": {
        "trigger_value": True,
        "message": "🚫 我方采购含预付款，触发\"十个不准\"禁止性规则，当前模式不可推进。",
        "level": "high",
    },
    "has_advance_funding": {
        "trigger_value": True,
        "message": "🚫 我方存在垫资，触发\"十个不准\"禁止性规则，当前模式不可推进。",
        "level": "high",
    },
    "hardware_construction": {
        "trigger_value": True,
        "message": "⚠️ 含硬件/施工类内容，需区分货物类与工程类成本；工程类收入禁止列入产数业绩。",
        "level": "medium",
    },
    "project_location": {
        "trigger_value": "remote_without_capability",
        "message": "⚠️ 异地项目且电信无实施能力，存在交付能力缺失风险，需提供驻场或委托实施的合规依据。",
        "level": "high",
    },
    "gross_margin": {
        "trigger_value": "lte_0",
        "message": "🚫 毛利率≤0%，触发\"三零项目\"特征（零利润），当前模式存在重大合规隐患。",
        "level": "high",
    },
    "gross_margin_low": {  # 伪键，在函数中特殊处理 lte_3
        "trigger_value": "lte_3",
        "message": "🟡 毛利率1%-3%，处于预警区间，需准备成本明细表与差额列收计算说明。",
        "level": "medium",
    },
    "procurement_method": {
        "trigger_value": "sole_source",
        "message": "🟡 单一来源采购是重要风险信号，需提供标前决策会纪要及单一来源采购说明书。",
        "level": "medium",
    },
    "has_telecom_capability": {
        "trigger_value": "no",
        "message": "⚠️ 无电信自有能力融入，符合虚假贸易三大特征之一，结合其他字段可能触发高风险结论。",
        "level": "medium",
    },
    "capability_ratio": {
        "trigger_value": "all_external",
        "message": "⚠️ 全部外采（自有能力占比为0），需通过控制权证据核查（C1-C6）方可判定列收方式。",
        "level": "medium",
    },
    "scheme_reviewed": {
        "trigger_value": "no",
        "message": "🟡 方案未经中台把关/评审，不满足\"六到位\"中方案评审到位要求，建议尽快安排评审。",
        "level": "medium",
    },
}


def get_realtime_warnings(field_key: str, field_value) -> dict | None:
    """
    给定单个字段名和值，返回即时预警信息（用于填表时实时反馈）。
    返回 None 表示无预警。
    """
    # gross_margin 有两档预警，分开处理
    if field_key == "gross_margin":
        if field_value == "lte_0":
            w = REALTIME_WARNINGS["gross_margin"]
            return {"field": field_key, "message": w["message"], "level": w["level"]}
        if field_value == "lte_3":
            w = REALTIME_WARNINGS["gross_margin_low"]
            return {"field": field_key, "message": w["message"], "level": w["level"]}
        return None

    # 跳过伪键
    if field_key == "gross_margin_low":
        return None

    w = REALTIME_WARNINGS.get(field_key)
    if not w:
        return None
    if field_value == w["trigger_value"]:
        return {"field": field_key, "message": w["message"], "level": w["level"]}
    return None


def _eval_condition(cond: dict, fields: dict) -> bool:
    field = cond["field"]
    op = cond["operator"]
    expected = cond["value"]
    actual = fields.get(field)

    if actual is None:
        return False
    if op == "eq":
        return actual == expected
    if op == "neq":
        return actual != expected
    if op == "in":
        return actual in expected
    if op == "nin":
        return actual not in expected
    return False


def _eval_trigger(trigger: dict, fields: dict) -> bool:
    logic = trigger.get("logic", "AND")
    conditions = trigger.get("conditions", [])

    if logic == "MANUAL":
        return False
    if logic == "AND":
        return all(_eval_condition(c, fields) for c in conditions)
    if logic == "OR":
        return any(_eval_condition(c, fields) for c in conditions)
    if logic == "MIN_MATCH":
        min_count = trigger.get("min_count", 1)
        matched = sum(1 for c in conditions if _eval_condition(c, fields))
        return matched >= min_count
    return False


def _get_clause_text(clause_id: str) -> list[dict]:
    clause = CLAUSES.get(clause_id, {})
    return clause.get("sources", [])


# ── 硬转服务检测（#9，见 docs/adr/0002）──
# 申报为「服务」且列收的核算单元，若呈现硬件/施工实质（零毛利平进平出 / 物流供应商直发 /
# 无自有能力），即有「硬转服务」嫌疑。举证式：标记嫌疑 + 要求举证，不自动定性；旁证数量决定嫌疑等级。
_ZERO_MARGIN_HINTS = ("平进平出", "零毛利", "无加价")
_SUSPICION_LABEL = {"high": "高嫌疑", "medium": "中嫌疑", "low": "低嫌疑"}

# 这些项目类型通常含硬件/施工或多业务块，本应切分核算单元；未切分则硬件排除/硬转服务检测失效。
_UNIT_EXPECTED_TYPES = {"equipment_sales", "system_integration"}

# 申报为这些类型的核算单元适用「铁律不列收」（#8，见 docs/adr/0002）
_HW_UNIT_TYPES = {"设备", "施工"}


def enforce_hardware_no_listing(units: list | None) -> list:
    """硬件/施工 默认净额（27 号文重构后语义，见 docs/adr/0004 决策13）。

    旧语义（ADR 0002 铁律）是「无条件钉死 listed=False」；27 号文推翻铁律后——白名单硬件
    在「门槛+控制权」齐备时可全额列收——本函数降级为「**设默认值=净额**」（铁律→默认兜底）：
    入库时把 设备/施工 单元的 listed 归一为 False 作为兜底默认。真正的列收结论是
    `classify_listing_mode` 在 run_diagnosis 内算出来的派生输出——它会反向把合格全额单元
    upgrade 回 listed=True。即 listed 不再是 AI/用户填的事实，而是工具算出的结论。
    核算单元所有入库路径都应过此函数（设默认），诊断时由分类器定最终值。
    """
    for u in units or []:
        if isinstance(u, dict) and u.get("declared_type") in _HW_UNIT_TYPES:
            u["listed"] = False
    return units or []


def _is_zero_margin(gross) -> bool:
    if gross is None:
        return False
    s = str(gross).strip()
    if s in ("0", "0元", "0%", "0.0", "毛利0", "毛利率0"):
        return True
    return any(h in s for h in _ZERO_MARGIN_HINTS)


def _hard_to_service_signals(unit: dict) -> list[str]:
    sig = []
    if _is_zero_margin(unit.get("gross")):
        sig.append("毛利≈0（平进平出）")
    if unit.get("logistics") == "supplier_direct":
        sig.append("物流供应商直发")
    if unit.get("has_self_capability") is False:
        sig.append("无自有能力融入")
    return sig


def detect_hard_to_service(accounting_units: list | None) -> list[dict]:
    """对申报服务且列收的核算单元做硬转服务嫌疑检测（举证式）。"""
    flags = []
    for u in accounting_units or []:
        if u.get("declared_type") != "服务" or u.get("listed") is False:
            continue
        sig = _hard_to_service_signals(u)
        if not sig:
            continue
        level = "high" if len(sig) >= 3 else ("medium" if len(sig) >= 2 else "low")
        flags.append({
            "unit_name": u.get("name") or "未命名服务单元",
            "amount": u.get("amount"),
            "signals": sig,
            "suspicion_level": level,
            "suspicion_label": _SUSPICION_LABEL[level],
            "message": (
                f"该服务单元呈现硬件/施工实质（{'、'.join(sig)}），有「硬转服务」嫌疑，"
                f"请举证其服务实质，否则相应部分应调整列收。"
            ),
            "required_evidence": [
                "自有人力投入记录 / 工时单",
                "增值服务内容与方案说明",
                "电信主导交付与验收证据",
            ],
        })
    return flags


# ── 六到位关键角色自查（项目级共性证据，见 docs/adr/0003）──
# 官方 19 角色 / 8 情形矩阵：10 个角色进判定。必选电信全占 6/7/9（涉硬件再加 16），
# 三组二选一各占一个 → 落在 8 情形之一 → 总额法资格成立。缺任一必要元素 → 资格不成立（举证式 high）。
_CTRL_MANDATORY = ("6", "7", "9")            # 必选（恒）
_CTRL_HW_MANDATORY = "16"                     # 到货验收及设备管理，仅涉硬件时必选
_CTRL_EITHER_OR = (                           # 三组二选一，每组至少占一个
    ("方案", ("3", "4")),
    ("交付实施方案", ("10", "11")),
    ("实施开发", ("13", "14")),
)
_CTRL_ROLE_NAMES = {
    "3": "解决方案设计者", "4": "解决方案整合确定者",
    "6": "应标与签约统筹者", "7": "软硬件采购决策者",
    "9": "全流程交付管理与质量责任者",
    "10": "交付实施方案设计者", "11": "交付实施方案确定及责任者",
    "13": "项目实施/技术开发/联调实施者", "14": "项目实施/技术开发主导与联调实操责任者",
    "16": "到货验收及设备管理者",
}

SIX_DAOWEI_DIMENSIONS = (
    ("six_daowei_customer_insight", "客情掌握到位"),
    ("six_daowei_solution_control", "方案总控到位"),
    ("six_daowei_bid_autonomy", "谈判/应标自主到位"),
    ("six_daowei_procurement_autonomy", "采购自主到位"),
    ("six_daowei_project_management", "项目强管理到位"),
    ("six_daowei_operations_autonomy", "运维自主到位"),
)
_SIX_DAOWEI_VALUES = {"in_place", "not_in_place", "pending_evidence", "not_applicable"}
_SIX_DAOWEI_LEVELS = {"strong", "medium", "none"}


def _normalize_control_roles(control_roles) -> set[str]:
    if isinstance(control_roles, str):
        control_roles = [p for p in re.split(r"[,;/\s、，；]+", control_roles) if p]
    return {str(r).strip() for r in (control_roles or []) if str(r).strip()}


def assess_control_roles(control_roles, has_hardware: bool, wants_full: bool = False) -> dict | None:
    """六到位关键角色自查（项目级共性证据，见 docs/adr/0003）。

    control_roles: 电信占据的关键角色编号列表（字符串/数字皆可）。
    has_hardware: 项目是否涉硬件（决定角色 16 是否必选）。
    wants_full: 项目从字段上看是否「明显奔全额列收」（R21 触发或服务自有/混合交付）。
                影响 unfilled 时的严重度：奔全额 → medium「控制权未自证」；否则 tip 不打扰。
    返回 dict（status / level / message / missing）；R09 防撞置 None 在 run_diagnosis 内处理。
    举证式：资格不成立给 high + 举证路，不自动定性。high 仅在已填角色时落。
    """
    # AI 偶尔把数组误输出成字符串（如 "6,7,9"）——按分隔符拆开，绝不能逐字符迭代
    # （否则 "10"/"13" 等两位编号永远拆不出，给用户展示错误的缺失清单）
    held = _normalize_control_roles(control_roles)
    if not held:
        if wants_full:
            return {
                "status": "unfilled_wants_full", "level": "medium", "missing": [],
                "message": (
                    "本项目从字段上看明显奔全额列收，但尚未完成六到位 19 角色/8 情形自查。"
                    "请在「信息解析」面板填写电信占据的关键角色，否则项目级共性证据未自证。"
                ),
            }
        return {
            "status": "unfilled", "level": "tip", "missing": [],
            "message": "尚未填写六到位关键角色，项目级共性证据尚未完成。如需自证，请在「信息解析」面板补充。",
        }
    mandatory = list(_CTRL_MANDATORY) + ([_CTRL_HW_MANDATORY] if has_hardware else [])
    missing_mandatory = [r for r in mandatory if r not in held]
    missing_groups = [name for name, grp in _CTRL_EITHER_OR if not (set(grp) & held)]

    if not missing_mandatory and not missing_groups:
        return {
            "status": "eligible", "level": "low", "missing": [],
            "message": "电信占据全部必选关键角色及三组二选一各一，符合总额法资格（控制权成立）。",
        }

    miss = [f"必选角色{r} {_CTRL_ROLE_NAMES.get(r, '')}" for r in missing_mandatory]
    miss += [f"二选一·{name}（三组中此组一个都未占）" for name in missing_groups]
    return {
        "status": "ineligible", "level": "high", "missing": miss,
        "message": (
            "按官方 19 角色/8 情形框架，电信未占齐关键角色，总额法资格不成立、定性倾向代理人/净额。"
            "如维持全额列收，须举证以下缺失的关键角色实际到位。"
        ),
    }


def assess_six_daowei(
    fields: dict,
    has_hardware: bool = False,
    wants_full: bool = False,
    role_check: dict | None = None,
) -> dict:
    """合并后的六到位自查：事实给建议、六维和综合等级以用户确认为准。

    建议只用于预写，不替代用户结论，也不进入 R08 或列收模式硬判断。六维字段允许
    `pending_evidence`，便于初步自检；综合等级仅有 strong/medium/none 三档。
    """
    roles_raw = fields.get("control_roles")
    roles_answered = roles_raw is not None
    held = _normalize_control_roles(roles_raw)
    role_check = role_check or assess_control_roles(roles_raw, has_hardware, wants_full=wants_full)

    project_types = fields.get("project_type") or []
    if isinstance(project_types, str):
        project_types = [project_types]
    type_set = set(project_types)
    needs_acceptance = bool(type_set & {"system_integration", "software_development", "service"})

    contract_match = fields.get("contract_matches_bpm")
    related_party = fields.get("related_party")
    customer_type = fields.get("customer_type")
    scheme = fields.get("scheme_reviewed")
    procurement = fields.get("procurement_method")
    acceptance = fields.get("acceptance_content_same")
    location = fields.get("project_location")
    delivery_mode = fields.get("service_delivery_mode")

    suggestions: dict[str, tuple[str, list[str]]] = {}

    if contract_match == "no":
        suggestions["six_daowei_customer_insight"] = (
            "not_in_place", ["前向合同客户与 BPM 商机客户不一致"],
        )
    elif contract_match == "yes" and customer_type and related_party not in (None, "uncertain"):
        suggestions["six_daowei_customer_insight"] = (
            "in_place", ["客户类型、合同客户一致性及前后向关系已确认"],
        )
    else:
        suggestions["six_daowei_customer_insight"] = (
            "pending_evidence", ["仍需确认客户关系、真实需求及合同客户一致性证据"],
        )

    has_solution_role = bool(held & {"3", "4"})
    if scheme == "no" or (roles_answered and not has_solution_role):
        suggestions["six_daowei_solution_control"] = (
            "not_in_place", ["方案主导角色或方案评审尚未到位"],
        )
    elif has_solution_role and scheme != "planned":
        suggestions["six_daowei_solution_control"] = (
            "in_place", ["电信占据方案设计/整合确定角色，且无方案评审否定信号"],
        )
    else:
        suggestions["six_daowei_solution_control"] = (
            "pending_evidence", ["仍需确认方案主导角色及评审留痕"],
        )

    if contract_match == "no" or (roles_answered and "6" not in held):
        suggestions["six_daowei_bid_autonomy"] = (
            "not_in_place", ["应标签约统筹角色或合同客户一致性未满足"],
        )
    elif "6" in held and contract_match == "yes":
        suggestions["six_daowei_bid_autonomy"] = (
            "in_place", ["电信承担应标签约统筹，且合同客户与商机客户一致"],
        )
    else:
        suggestions["six_daowei_bid_autonomy"] = (
            "pending_evidence", ["仍需确认应标签约统筹角色及前向材料"],
        )

    if roles_answered and "7" not in held:
        suggestions["six_daowei_procurement_autonomy"] = (
            "not_in_place", ["电信未确认承担软硬件采购决策角色"],
        )
    elif "7" in held and procurement:
        suggestions["six_daowei_procurement_autonomy"] = (
            "in_place", ["电信承担采购决策，且后向采购方式已确认"],
        )
    else:
        suggestions["six_daowei_procurement_autonomy"] = (
            "pending_evidence", ["仍需确认采购决策角色及采购流程留痕"],
        )

    delivery_roles_ok = bool(held & {"10", "11"})
    implementation_roles_ok = bool(held & {"13", "14"})
    management_roles_ok = (
        "9" in held
        and delivery_roles_ok
        and implementation_roles_ok
        and (not has_hardware or "16" in held)
    )
    management_hard_no = acceptance == "yes" or location == "remote_without_capability"
    if management_hard_no or (roles_answered and not management_roles_ok):
        suggestions["six_daowei_project_management"] = (
            "not_in_place", ["交付管理角色不完整，或验收/异地实施存在明确失控信号"],
        )
    elif management_roles_ok and (not needs_acceptance or acceptance == "no"):
        suggestions["six_daowei_project_management"] = (
            "in_place", ["交付管理、实施开发及适用的设备管理角色齐备，验收由电信独立组织"],
        )
    else:
        suggestions["six_daowei_project_management"] = (
            "pending_evidence", ["仍需确认交付实施、验收及项目过程管理证据"],
        )

    operations_hard_no = (
        acceptance == "yes"
        or location == "remote_without_capability"
        or delivery_mode == "all_external"
    )
    operations_positive = "9" in held and (
        delivery_mode == "all_telecom" or (delivery_mode is None and acceptance == "no")
    )
    if operations_hard_no:
        suggestions["six_daowei_operations_autonomy"] = (
            "not_in_place", ["服务全部外部执行，或验收/异地实施存在明确自主性缺失信号"],
        )
    elif operations_positive:
        suggestions["six_daowei_operations_autonomy"] = (
            "in_place", ["电信承担全流程质量责任，并有自有交付或独立验收事实"],
        )
    else:
        suggestions["six_daowei_operations_autonomy"] = (
            "pending_evidence", ["仍需确认运维资源、供应商管控及售后兜底责任"],
        )

    dimensions = []
    effective: dict[str, str] = {}
    for key, label in SIX_DAOWEI_DIMENSIONS:
        suggested, basis = suggestions[key]
        raw_confirmed = fields.get(key)
        confirmed = raw_confirmed if raw_confirmed in _SIX_DAOWEI_VALUES else None
        effective[key] = confirmed or suggested
        dimensions.append({
            "key": key,
            "label": label,
            "suggested": suggested,
            "confirmed": confirmed,
            "effective": effective[key],
            "basis": basis,
            "mismatch": confirmed is not None and confirmed != suggested,
        })

    role_status = (role_check or {}).get("status")
    all_in_place = all(v == "in_place" for v in effective.values())
    if all_in_place and role_status == "eligible" and delivery_mode != "all_external":
        suggested_level = "strong"
        level_basis = "六个维度均到位、关键角色齐备，且不存在全部外部交付信号"
    else:
        no_capability = (
            fields.get("has_telecom_capability") == "no"
            or fields.get("capability_ratio") == "all_external"
        )
        external_delivery = delivery_mode == "all_external" or fields.get("capability_ratio") == "all_external"
        core_missing = (
            effective["six_daowei_project_management"] == "not_in_place"
            and effective["six_daowei_operations_autonomy"] == "not_in_place"
        )
        if external_delivery and no_capability and role_status == "ineligible" and core_missing:
            suggested_level = "none"
            level_basis = "外部交付、无自有能力、关键角色缺失及核心履约维度不到位等多项事实同时成立"
        else:
            suggested_level = "medium"
            level_basis = "尚未同时满足“六维全到位 + 关键角色齐备”，但也不足以据此认定为无能力"

    raw_level = fields.get("six_daowei_level")
    confirmed_level = raw_level if raw_level in _SIX_DAOWEI_LEVELS else None
    final_level = confirmed_level or suggested_level
    manual_gate_present = (
        "six_daowei_facts_confirmed" in fields
        or confirmed_level is not None
        or any(fields.get(key) in _SIX_DAOWEI_VALUES for key, _label in SIX_DAOWEI_DIMENSIONS)
    )
    all_dimensions_confirmed = all(dim["confirmed"] is not None for dim in dimensions)
    all_dimensions_confirmed_in_place = all(dim["confirmed"] == "in_place" for dim in dimensions)
    gate_complete = (
        fields.get("six_daowei_facts_confirmed") is True
        and all_dimensions_confirmed
        and confirmed_level is not None
    )
    gate_passed = (
        gate_complete
        and confirmed_level == "strong"
        and all_dimensions_confirmed_in_place
        and role_status == "eligible"
    )
    if not manual_gate_present:
        gate_status = "legacy_not_evaluated"
        gate_passed_value = None
        gate_message = "历史诊断未采集六到位统一确认字段，不在本次结果中追溯改写列收结论。"
    elif not gate_complete:
        gate_status = "incomplete"
        gate_passed_value = False
        gate_message = "六到位人工确认尚未完成，当前不能证明项目主控及验收主责，只能按净额列收。"
    elif gate_passed:
        gate_status = "passed"
        gate_passed_value = True
        gate_message = "六到位六个维度全部通过，具备继续判断项目主控权、验收主责及全额列收其他条件的基础。"
    else:
        gate_status = "failed"
        gate_passed_value = False
        gate_message = "六到位未全部通过，无法证明项目主控权及验收主责，只能按净额列收；需提升后重新确认。"
    return {
        "dimensions": dimensions,
        "suggested_level": suggested_level,
        "confirmed_level": confirmed_level,
        "level": final_level,
        "level_source": "confirmed" if confirmed_level else "suggested",
        "level_mismatch": confirmed_level is not None and confirmed_level != suggested_level,
        "level_basis": level_basis,
        "role_check": role_check,
        "listing_gate": {
            "status": gate_status,
            "passed": gate_passed_value,
            "complete": gate_complete,
            "all_dimensions_in_place": all_dimensions_confirmed_in_place,
            "roles_eligible": role_status == "eligible",
            "message": gate_message,
        },
        "message": (
            "系统建议仅用于预写；六维结论和强/中/无最终以用户确认为准。"
            "六到位必须全部通过才可继续争取全额列收；未通过则无法证明主控及验收主责，只能净额。"
            "通过后仍需继续满足 R08 及其他全额条件。"
        ),
    }


# ── 列收模式分类器（27 号文重构，见 docs/adr/0004）──
# 级联：第一遍项目级套全额模式（实质路由 + 资格闸），过线则整项目全额；走不通退第二遍
# 逐核算单元兜底（达标白名单单元仍全额、其余净额）。listed 由此派生，不是 AI/用户填的事实。
# 不进 rules.json——吃单元 amount 算占比，现有 DSL（eq/in/neq）无数值比较表达不了。

# overall_margin 与 gross_margin 共用分桶枚举（切点正好卡 5%/10%）
_MARGIN_ORDER = {
    "lte_0": 0, "lte_3": 1, "pct_3_4": 2, "pct_4_5": 3,
    "pct_5_6": 4, "pct_6_10": 5, "gt_10": 6,
}
_MARGIN_GTE_5 = 4    # pct_5_6 及以上 = ≥5%
_MARGIN_GTE_10 = 6   # 仅 gt_10（10%以上）；10% 边界取严（偏严）
_WL_UNIT_TYPES = {"设备", "标品"}  # 仅这两类适用白名单（施工恒非白名单、服务不适用）
# 全额准入闭集中可硬判定的客户类型；private/other 因可能是互联网头部/5A 外企，退软提示
_ADMISSION_CUSTOMER_INSET = {"state_owned", "institution", "government"}
_MODE_LABEL = {
    "regular": "常规 ICT（服务成本型，按常规列收）",
    "capital": "资本投资模式（疑似，门槛走线下投资流程）",
    "service_integration": "服务整合业务模式（全额）",
    "single_fulfillment": "单一履约·白名单（全额）",
    "net_settlement": "收支差净额（代收代付）",
}


def _unit_amount(u: dict) -> float:
    try:
        return float(u.get("amount"))
    except (TypeError, ValueError):
        return 0.0


def _margin_at_least(bucket, threshold_index: int) -> bool:
    idx = _MARGIN_ORDER.get(bucket)
    return idx is not None and idx >= threshold_index


def classify_listing_mode(
    type_set,
    fields: dict,
    units: list | None,
    control_status: str | None,
    six_daowei_passed: bool | None = None,
) -> dict:
    """27 号文列收模式级联分类（见 docs/adr/0004）。

    就地把合格全额单元的 `listed` 置 True（派生输出），返回 listing 结论 dict：
      mode/mode_label/full_listing/basis/ratios/gates/blockers/softs/unit_decisions/margin_ok。
    control_status: assess_control_roles 的 status（"eligible"=关键角色成立）。
    six_daowei_passed: 新诊断六到位总闸门；False 时直接净额，None 仅兼容历史/旧调用。
    """
    units = units or []
    amt = {"设备": 0.0, "施工": 0.0, "服务": 0.0, "标品": 0.0, "其他": 0.0}
    amount_incomplete = False
    for u in units:
        t = u.get("declared_type")
        if t == "标品":
            # 电信自有电话/宽带/天翼云等标品始终全额，不吃 27 白名单或六到位闸门。
            u["listed"] = True
        if u.get("amount") in (None, ""):
            amount_incomplete = True
        amt[t if t in amt else "其他"] += _unit_amount(u)

    total = sum(amt.values())
    hw_constr = amt["设备"] + amt["施工"]                 # 服务整合分子（含集成施工）
    hw_goods = amt["设备"] + amt["标品"]                  # 软硬件（白名单口径）
    single_denom = amt["设备"] + amt["标品"] + amt["服务"]  # 单一履约场景一分母（施工排除）

    has_hardware = any(u.get("declared_type") in _HW_UNIT_TYPES for u in units) or fields.get("hardware_construction") is True
    # 标品不属于 27 号文分类对象；当前实现中只有设备进入该分类器的商品侧。
    has_goods_unit = any(u.get("declared_type") == "设备" for u in units)
    role_control_ok = control_status == "eligible"
    control_ok = role_control_ok and six_daowei_passed is not False
    margin = fields.get("overall_margin")

    blockers: list[str] = []   # 硬否决（→ 无全额资格）
    softs: list[str] = []      # 软提示（仍算建议模式、不踢出全额）

    # ── 全额准入闸（硬/软分治，Q8）──
    cust = fields.get("customer_type")
    if cust in ("private", "other"):
        softs.append("客户类型为民企/其他，需举证属于全额准入闭集（党政军/央国企/事业单位/互联网头部/5A 级外企）")
    pay = fields.get("payment_terms")
    if pay == "other":
        blockers.append("付款节点非「首付款+到货验收尾款」，不符合全额准入硬条件")
    elif pay in (None, ""):
        softs.append("付款节点未填，全额准入要求「首付款+到货验收尾款」，请补充确认")
    if fields.get("ownership_transfer") in ("no", "uncertain"):
        softs.append("产权转移未明确（验收后转移客户），需举证产权实质性转移")
    if fields.get("collective_procurement_ratio") == "lt_60":
        softs.append("后向集采比例 <60%（建议 ≥60%，省授权市采购待定），非一票否决但建议补正")
    if amount_incomplete:
        softs.append("部分核算单元金额缺失，占比按现有金额估算，请补全后复核")

    # ── 控制权总闸门：不成立则任何全额模式都不可（落净额兜底）──
    if not role_control_ok:
        blockers.append("控制权资格未成立/未自证（19 角色矩阵），全额列收总闸门未过")
    if six_daowei_passed is False:
        blockers.append("六到位未全部通过，无法证明项目主控权及验收主责，只能按净额列收")

    # 占比（派生比值，不破脱敏边界）
    ratio_si = (hw_constr / total) if total > 0 else None
    ratio_sf = (hw_goods / single_denom) if single_denom > 0 else None

    # ── 实质路由 ──
    # 无 27 号文设备 → 常规 ICT/标品口径，本分类器不主导。
    if not has_hardware and not has_goods_unit:
        only_telecom_products = bool(units) and all(u.get("declared_type") == "标品" for u in units)
        regular_full = only_telecom_products or six_daowei_passed is not False
        return {
            "mode": "regular", "mode_label": _MODE_LABEL["regular"],
            "full_listing": regular_full,
            "basis": (
                "项目无 27 号文设备，但六到位未全部通过，服务等 ICT 内容只能净额列收"
                if not regular_full
                else "项目无 27 号文设备，按常规 ICT/标品口径继续判断"
            ),
            "ratios": {}, "gates": [], "blockers": blockers, "softs": softs,
            "unit_decisions": [], "margin_ok": True if regular_full else False,
        }

    # 资本投资模式：留出口、打标，不实现收投比 1.2 门槛（决策12）
    if fields.get("is_capital_investment") is True:
        return {
            "mode": "capital", "mode_label": _MODE_LABEL["capital"],
            "full_listing": False,
            "basis": "识别为「电信自投资设备打包」实质；收投比 1.2 评估走线下投资流程，本工具不判定门槛",
            "ratios": {}, "gates": [], "blockers": [], "softs": softs,
            "unit_decisions": [], "margin_ok": None,
        }

    gates: list[dict] = []
    full_listing = False
    mode = "net_settlement"
    basis = ""
    major = fields.get("major_integration")  # yes/no/uncertain

    # 第一遍·项目级全额：服务整合（重大整合 → 整项目含非白名单硬件全额）
    if control_ok and major == "yes":
        si_amount_ok = total >= 3_000_000
        si_ratio_ok = ratio_si is not None and ratio_si <= 0.60
        si_margin_ok = _margin_at_least(margin, _MARGIN_GTE_10)
        gates = [
            {"name": "签约额 ≥300 万", "ok": si_amount_ok},
            {"name": "硬件+集成施工占比 ≤60%", "ok": si_ratio_ok,
             "value": (f"{ratio_si:.1%}" if ratio_si is not None else "金额不足无法计算")},
            {"name": "整体税前利润率 ≥10%", "ok": si_margin_ok},
            {"name": "控制权资格成立", "ok": True},
        ]
        if si_amount_ok and si_ratio_ok and si_margin_ok and not blockers:
            full_listing = True
            mode = "service_integration"
            basis = "重大整合（单一组合产出）+ 项目级资格闸全过 → 整项目全额（含非白名单硬件）"
            for u in units:
                if u.get("declared_type") in _HW_UNIT_TYPES:
                    u["listed"] = True
        else:
            mode = "service_integration"
            basis = "路由为服务整合，但项目级资格闸未全过 → 退第二遍逐单元兜底"

    # 第二遍·逐单元白名单兜底（单一履约）：控制权 ok、项目级未走通时，达标白名单单元仍可全额
    if control_ok and not full_listing:
        has_service = amt["服务"] > 0
        if has_service:
            sf_amount_ok = hw_goods >= 1_000_000
            sf_ratio_ok = ratio_sf is not None and ratio_sf <= 0.80
            sf_margin_ok = _margin_at_least(margin, _MARGIN_GTE_5)
            gates = (gates or []) + [
                {"name": "单一履约·场景一：软硬件 >100 万", "ok": sf_amount_ok},
                {"name": "软硬件占比 ≤80%（施工已排除）", "ok": sf_ratio_ok,
                 "value": (f"{ratio_sf:.1%}" if ratio_sf is not None else "金额不足无法计算")},
                {"name": "整体税前利润率 ≥5%", "ok": sf_margin_ok},
            ]
            sf_ok = sf_amount_ok and sf_ratio_ok and sf_margin_ok and not blockers
        else:
            sf_amount_ok = hw_goods >= 5_000_000
            sf_margin_ok = _margin_at_least(margin, _MARGIN_GTE_5)
            gates = (gates or []) + [
                {"name": "单一履约·场景二（纯硬件）：软硬件 ≥500 万", "ok": sf_amount_ok},
                {"name": "整体税前利润率 ≥5%", "ok": sf_margin_ok},
            ]
            sf_ok = sf_amount_ok and sf_margin_ok and not blockers

        any_unit_full = False
        for u in units:
            if u.get("declared_type") not in _WL_UNIT_TYPES:
                continue
            if u.get("declared_type") == "标品":
                continue
            wl = u.get("whitelisted")
            logistics_ok = u.get("logistics") != "supplier_direct"  # 物权三流合一否决闸（原 R26）
            if sf_ok and wl is True and logistics_ok:
                u["listed"] = True
                any_unit_full = True
            else:
                u["listed"] = False
        if any_unit_full:
            mode = "single_fulfillment"
            basis = "单一履约·白名单：达标白名单单元全额，非白名单/不达标/供应商直发单元落净额"
        elif mode != "service_integration":
            mode = "net_settlement"
            basis = basis or "未走通任何全额模式 → 收支差净额（代收代付）兜底"

    # 控制权未过：所有硬件落净额
    if not control_ok:
        for u in units:
            if u.get("declared_type") in _HW_UNIT_TYPES:
                u["listed"] = False
        mode = "net_settlement"
        basis = "控制权或六到位总闸门未过 → 相关 ICT 单元落净额兜底"

    unit_decisions = [
        {"unit_name": u.get("name") or "未命名单元",
         "declared_type": u.get("declared_type"),
         "amount": u.get("amount"),
         "whitelisted": u.get("whitelisted"),
         "listed": u.get("listed"),
         "listing": "全额列收" if u.get("listed") is True else "净额（不列收/代收代付）"}
        for u in units if u.get("declared_type") in (_HW_UNIT_TYPES | _WL_UNIT_TYPES)
    ]

    return {
        "mode": mode, "mode_label": _MODE_LABEL.get(mode, mode),
        "full_listing": full_listing,
        "basis": basis,
        "ratios": {
            "service_integration_pct": (round(ratio_si, 4) if ratio_si is not None else None),
            "single_fulfillment_pct": (round(ratio_sf, 4) if ratio_sf is not None else None),
        },
        "gates": gates,
        "blockers": blockers,
        "softs": softs,
        "unit_decisions": unit_decisions,
        "margin_ok": _margin_at_least(margin, _MARGIN_GTE_5),
        "whitelist_version": WHITELIST_VERSION,
    }


# ── 核算结构 v2：最终核算单元级辅助判断 ───────────────────────
_UNIT_SIX_LABELS = {
    "customer_insight": "客情掌握到位",
    "solution_control": "方案总控到位",
    "bid_autonomy": "谈判/应标自主到位",
    "procurement_autonomy": "采购自主到位",
    "project_management": "项目强管理到位",
    "operations_autonomy": "运维自主到位",
}
_UNIT_SIX_MATERIAL_IDS = {
    "customer_insight": ["MAT-PROC-R01"],
    "solution_control": ["MAT-PROC-GRP-SOLUTION"],
    "bid_autonomy": ["MAT-PROC-R06"],
    "procurement_autonomy": ["MAT-PROC-R07"],
    "project_management": [
        "MAT-PROC-R09",
        "MAT-PROC-GRP-DELIVERY",
        "MAT-PROC-GRP-IMPLEMENT",
    ],
    "operations_autonomy": ["MAT-PROC-R18"],
}
_R08_LABELS = {
    "ctrl1_control_before_transfer": "向客户转移前已取得商品或服务控制权",
    "ctrl2_primary_responsibility": "承担质量、验收及售后主要责任",
    "ctrl3_inventory_delivery_risk": "承担库存、交付、返工或履约风险",
    "ctrl4_pricing_autonomy": "对客户价格具有自主决定权",
}
_R08_MATERIAL_IDS = {
    "ctrl1_control_before_transfer": ["MAT-FIN-OWNERSHIP-001"],
    "ctrl2_primary_responsibility": ["MAT-FIN-RESP-001", "MAT-PROC-R09", "MAT-PROC-R18"],
    "ctrl3_inventory_delivery_risk": ["MAT-FIN-RESP-001", "MAT-PROC-R09"],
    "ctrl4_pricing_autonomy": ["MAT-FIN-PRICE-001"],
}
_ROLE_MATERIAL_IDS = {
    "3": "MAT-PROC-R03", "4": "MAT-PROC-R04", "6": "MAT-PROC-R06",
    "7": "MAT-PROC-R07", "9": "MAT-PROC-R09", "10": "MAT-PROC-R10",
    "11": "MAT-PROC-R11", "13": "MAT-PROC-R13", "14": "MAT-PROC-R14",
    "16": "MAT-PROC-R16",
}


def _material_names(material_ids: list[str]) -> list[str]:
    return [
        MATERIALS[material_id]["name"]
        for material_id in dict.fromkeys(material_ids)
        if material_id in MATERIALS
    ]


def _role_evidence_material_ids(fields: dict, has_hardware: bool) -> list[str]:
    held = _normalize_control_roles(fields.get("control_roles"))
    result = ["MAT-PROC-R06", "MAT-PROC-R07", "MAT-PROC-R09"]
    if has_hardware:
        result.append("MAT-PROC-R16")
    for roles, group_material in (
        (("3", "4"), "MAT-PROC-GRP-SOLUTION"),
        (("10", "11"), "MAT-PROC-GRP-DELIVERY"),
        (("13", "14"), "MAT-PROC-GRP-IMPLEMENT"),
    ):
        selected = next((role for role in roles if role in held), None)
        result.append(_ROLE_MATERIAL_IDS[selected] if selected else group_material)
    return list(dict.fromkeys(result))


def _unit_material_refs(final_unit: dict, material_ids: list[str], purpose: str) -> list[dict]:
    return [
        {
            "material_id": material_id,
            "unit_id": final_unit.get("id"),
            "unit_name": final_unit.get("name"),
            "purpose": purpose,
        }
        for material_id in dict.fromkeys(material_ids)
    ]


def _policy_gate_material_ids(gate_name: str) -> list[str]:
    if "利润率" in gate_name:
        return ["MAT-FIN-MARGIN-001"]
    if "白名单" in gate_name:
        return ["MAT-COND-WHITELIST-001"]
    if "付款节点" in gate_name:
        return ["MAT-FIN-PAYMENT-001"]
    if "物流与物权" in gate_name:
        return ["MAT-FIN-OWNERSHIP-001", "MAT-PROC-R16"]
    if "金额" in gate_name or "%" in gate_name:
        return ["MAT-FIN-AMOUNT-001"]
    return []


def _project_amount_metrics(source_units: list[dict]) -> dict:
    amounts = {name: 0.0 for name in ("设备", "成品软件", "施工", "服务", "标品", "其他")}
    incomplete = False
    for source in source_units:
        declared_type = source.get("declared_type")
        if source.get("amount") in (None, ""):
            incomplete = True
        amounts[declared_type if declared_type in amounts else "其他"] += _unit_amount(source)
    total = sum(amounts.values())
    service_integration_numerator = amounts["设备"] + amounts["成品软件"] + amounts["施工"]
    single_numerator = amounts["设备"] + amounts["成品软件"]
    single_denominator = single_numerator + amounts["服务"] + amounts["标品"]
    return {
        "amounts": amounts,
        "project_total": total,
        "amount_incomplete": incomplete,
        "service_integration_pct": (
            round(service_integration_numerator / total, 4) if total > 0 else None
        ),
        "single_fulfillment_pct": (
            round(single_numerator / single_denominator, 4) if single_denominator > 0 else None
        ),
        "single_denominator": single_denominator,
    }


def _unit_sources(final_unit: dict, source_by_id: dict[str, dict]) -> list[dict]:
    return [source_by_id[source_id] for source_id in final_unit.get("source_unit_ids") or [] if source_id in source_by_id]


def _unit_six_check(final_unit: dict, decision: dict, fields: dict, sources: list[dict]) -> dict:
    six = decision.get("six_daowei") if isinstance(decision.get("six_daowei"), dict) else {}
    dimensions_raw = six.get("dimensions") if isinstance(six.get("dimensions"), dict) else {}
    has_hardware = any(source.get("declared_type") in {"设备", "成品软件", "施工"} for source in sources)
    role_check = assess_control_roles(fields.get("control_roles"), has_hardware, wants_full=True)
    dimensions = []
    failures = []
    pending = []
    material_ids = []
    for key in UNIT_SIX_DIMENSIONS:
        value = dimensions_raw.get(key)
        legal = legal_six_value(key, value, six) if value is not None else False
        if value == "not_in_place" or (value == "not_applicable" and not legal):
            failures.append(_UNIT_SIX_LABELS[key])
        elif value in (None, "pending_evidence"):
            pending.append(_UNIT_SIX_LABELS[key])
            material_ids.extend(_UNIT_SIX_MATERIAL_IDS[key])
        dimensions.append({
            "key": key,
            "label": _UNIT_SIX_LABELS[key],
            "value": value,
            "legal": legal,
        })

    level = six.get("level")
    stale = six.get("confirmation_status") == "stale"
    if level in {"medium", "none"}:
        failures.append(f"六到位综合结论为{'中' if level == 'medium' else '无'}")
    if role_check and role_check.get("status") == "ineligible":
        failures.append("关键角色未占齐")
        material_ids.extend(_role_evidence_material_ids(fields, has_hardware))
    elif not role_check or role_check.get("status") != "eligible":
        pending.append("关键角色事实尚未完整自证")
        material_ids.extend(_role_evidence_material_ids(fields, has_hardware))
    if six.get("facts_confirmed") is not True:
        pending.append("六到位基础事实尚未确认")
    if level not in {"strong", "medium", "none"}:
        pending.append("六到位综合结论尚未确认")
    if stale:
        pending.append("项目共性事实或核算单元已变更，原结论需重新确认")

    if failures:
        status = "failed"
    elif pending:
        status = "provisional"
    else:
        status = "passed"
    material_ids = list(dict.fromkeys(material_ids))
    return {
        "unit_id": final_unit["id"],
        "unit_name": final_unit["name"],
        "status": status,
        "level": level,
        "dimensions": dimensions,
        "role_check": role_check,
        "failures": list(dict.fromkeys(failures)),
        "pending": list(dict.fromkeys(pending)),
        "required_material_ids": material_ids,
        "required_evidence": _material_names(material_ids),
        "message": {
            "passed": "六到位已全部通过，可继续判断其他全额列收条件。",
            "failed": "六到位存在明确不到位项，当前单元不能按全额列收。",
            "provisional": "六到位仍有待确认或待补证据项，暂按拟全额测算并计高风险。",
        }[status],
    }


def _unit_r08_check(final_unit: dict, decision: dict, sources: list[dict]) -> dict:
    r08 = decision.get("r08") if isinstance(decision.get("r08"), dict) else {}
    answers = r08.get("answers") if isinstance(r08.get("answers"), dict) else {}
    conclusion = r08.get("conclusion")
    no_answers = [key for key in R08_KEYS if answers.get(key) == "no"]
    pending_keys = [key for key in R08_KEYS if answers.get(key) not in {"yes", "no"}]
    stale = r08.get("confirmation_status") == "stale"
    suggested = "agent" if no_answers else ("principal" if not pending_keys else "pending")

    failures = []
    pending = []
    if conclusion == "agent":
        failures.append("人工确认电信为代理人")
    elif conclusion != "principal":
        pending.append("主要责任人/代理人结论尚未确认")
    if pending_keys:
        pending.extend(_R08_LABELS[key] for key in pending_keys)
    # 人工主责结论与客观答案冲突时只提示复核，不自动推翻人工输入。
    if conclusion == "principal" and no_answers:
        pending.extend(f"与主要责任人结论冲突：{_R08_LABELS[key]}回答为否" for key in no_answers)
    if stale:
        pending.append("项目共性事实或核算单元已变更，原 R08 结论需重新确认")

    if failures:
        status = "failed"
    elif pending:
        status = "provisional"
    else:
        status = "passed"
    material_ids = []
    for key in pending_keys + no_answers:
        material_ids.extend(_R08_MATERIAL_IDS[key])
    if any(source.get("declared_type") in {"设备", "成品软件"} for source in sources):
        if "ctrl1_control_before_transfer" in pending_keys + no_answers or "ctrl3_inventory_delivery_risk" in pending_keys + no_answers:
            material_ids.append("MAT-PROC-R16")
    material_ids = list(dict.fromkeys(material_ids))
    return {
        "unit_id": final_unit["id"],
        "unit_name": final_unit["name"],
        "status": status,
        "answers": [{"key": key, "label": _R08_LABELS[key], "value": answers.get(key)} for key in R08_KEYS],
        "suggested_conclusion": suggested,
        "confirmed_conclusion": conclusion,
        "failures": failures,
        "pending": list(dict.fromkeys(pending)),
        "required_material_ids": material_ids,
        "required_evidence": _material_names(material_ids),
        "message": {
            "passed": "R08 控制权四要件与主要责任人结论一致。",
            "failed": "人工确认电信为代理人，当前单元只能净额列收。",
            "provisional": "R08 仍有待确认、待补证据或冲突项，暂按拟全额测算并计高风险。",
        }[status],
    }


def _hard_to_service_v2(final_units: list[dict], source_by_id: dict[str, dict]) -> list[dict]:
    flags = []
    for final in final_units:
        decision = final.get("decision") or {}
        if decision.get("listing_intent") != "full":
            continue
        for source in _unit_sources(final, source_by_id):
            if source.get("declared_type") != "服务":
                continue
            signals = _hard_to_service_signals(source)
            if not signals:
                continue
            level = "high" if len(signals) >= 3 else ("medium" if len(signals) >= 2 else "low")
            flags.append({
                "unit_id": final["id"],
                "unit_name": final["name"],
                "source_unit_name": source.get("name") or "未命名服务部分",
                "amount": source.get("amount"),
                "signals": signals,
                "suspicion_level": level,
                "suspicion_label": _SUSPICION_LABEL[level],
                "message": "原始服务部分呈现硬件或施工实质，需按业务实质举证；本工具不自动改类、不自动改为净额。",
                "required_material_ids": [
                    "MAT-PROC-STAFF-001",
                    "MAT-PROC-GRP-SOLUTION",
                    "MAT-PROC-R09",
                ],
                "required_evidence": _material_names([
                    "MAT-PROC-STAFF-001",
                    "MAT-PROC-GRP-SOLUTION",
                    "MAT-PROC-R09",
                ]),
            })
    return flags


def evaluate_accounting_structure(structure: dict, fields: dict) -> dict:
    """Evaluate v2 final units as a self-check report, never as an approval action."""
    structure = normalize_structure(structure)
    source_units = structure["source_units"]
    source_by_id = {source["id"]: source for source in source_units}
    final_units = derive_final_units(structure)
    metrics = _project_amount_metrics(source_units)
    decisions = []
    six_checks = []
    r08_checks = []
    evidence_items = []
    risk_levels = []

    for final in final_units:
        decision = final.get("decision") or {}
        intent = "full" if final.get("declared_type") == "标品" else decision.get("listing_intent")
        sources = _unit_sources(final, source_by_id)
        types = set(final.get("declared_types") or [])
        reasons = []
        policy_gates = []
        status = "confirmed"
        result = "full" if intent == "full" else "net"
        mode = "standard_product" if final.get("declared_type") == "标品" else "regular"
        unit_six = None
        unit_r08 = None

        if final.get("declared_type") == "标品":
            reasons.append("电信自有标品固定全额列收，不进入 27 号文或六到位判断")
        elif intent == "net":
            reasons.append("用户拟按净额列收，跳过全额列收资格自查")
        elif intent != "full":
            result = "full"
            status = "provisional"
            reasons.append("列收意图尚未最终确认，暂按拟全额提示风险")
        else:
            unit_six = _unit_six_check(final, decision, fields, sources)
            unit_r08 = _unit_r08_check(final, decision, sources)
            six_checks.append(unit_six)
            r08_checks.append(unit_r08)
            evidence_items.extend(_unit_material_refs(final, unit_six["required_material_ids"], "六到位"))
            evidence_items.extend(_unit_material_refs(final, unit_r08["required_material_ids"], "R08控制权"))
            if unit_six["status"] == "failed" or unit_r08["status"] == "failed":
                result = "net"
                status = "confirmed"
                reasons.extend(unit_six["failures"] + unit_r08["failures"])
            elif unit_six["status"] == "provisional" or unit_r08["status"] == "provisional":
                status = "provisional"
                reasons.extend(unit_six["pending"] + unit_r08["pending"])

            has_policy_goods = bool(types & {"设备", "成品软件", "施工"})
            if result == "full" and fields.get("is_capital_investment") is True and "设备" in types:
                mode = "capital"
                status = "provisional"
                reasons.append("电信自投资设备打包需在线下投资流程核验收投比 1.2，本工具只提示不审批")
                evidence_items.extend(_unit_material_refs(final, ["MAT-FIN-CAPITAL-001"], "资本投资"))
            elif result == "full" and final.get("relationship") == "combined" and has_policy_goods:
                mode = "service_integration"
                amount_ok = metrics["project_total"] >= 3_000_000 if not metrics["amount_incomplete"] else None
                ratio = metrics["service_integration_pct"]
                ratio_ok = ratio <= 0.60 if ratio is not None and not metrics["amount_incomplete"] else None
                margin_ok = _margin_at_least(fields.get("overall_margin"), _MARGIN_GTE_10)
                margin_known = fields.get("overall_margin") in _MARGIN_ORDER
                policy_gates = [
                    {"name": "整个 BPM 项目金额 ≥300 万", "ok": amount_ok},
                    {"name": "设备+成品软件+施工/整个 BPM ≤60%", "ok": ratio_ok, "value": ratio},
                    {"name": "整个 BPM 项目税前利润率 ≥10%", "ok": margin_ok if margin_known else None},
                ]
            elif result == "full" and final.get("relationship") == "separate" and bool(types & WHITELIST_TYPES):
                mode = "single_fulfillment"
                has_service_or_standard = metrics["amounts"]["服务"] > 0 or metrics["amounts"]["标品"] > 0
                if has_service_or_standard:
                    ratio = metrics["single_fulfillment_pct"]
                    amount_ok = (metrics["amounts"]["设备"] + metrics["amounts"]["成品软件"]) > 1_000_000 if not metrics["amount_incomplete"] else None
                    ratio_ok = ratio <= 0.80 if ratio is not None and not metrics["amount_incomplete"] else None
                    policy_gates = [
                        {"name": "设备+成品软件 >100 万", "ok": amount_ok},
                        {"name": "设备+成品软件/(设备+成品软件+服务+标品) ≤80%", "ok": ratio_ok, "value": ratio},
                    ]
                else:
                    unit_goods_amount = sum(_unit_amount(source) for source in sources if source.get("declared_type") in WHITELIST_TYPES)
                    amount_ok = unit_goods_amount >= 5_000_000 if all(source.get("amount") not in (None, "") for source in sources) else None
                    policy_gates = [{"name": "单独设备或成品软件金额 ≥500 万", "ok": amount_ok}]
                margin_known = fields.get("overall_margin") in _MARGIN_ORDER
                policy_gates.append({"name": "整个 BPM 项目税前利润率 ≥5%", "ok": _margin_at_least(fields.get("overall_margin"), _MARGIN_GTE_5) if margin_known else None})

                whitelist_values = [source.get("whitelisted") for source in sources if source.get("declared_type") in WHITELIST_TYPES]
                if any(value is False for value in whitelist_values):
                    policy_gates.append({"name": "设备/成品软件属于集团白名单", "ok": False})
                elif any(value != True for value in whitelist_values):
                    policy_gates.append({"name": "设备/成品软件属于集团白名单", "ok": None})
                    evidence_items.extend(_unit_material_refs(final, ["MAT-COND-WHITELIST-001"], "27号文自检"))
                else:
                    policy_gates.append({"name": "设备/成品软件属于集团白名单", "ok": True})
            elif result == "full" and final.get("relationship") == "separate" and "施工" in types:
                mode = "net_settlement"
                policy_gates = [{"name": "施工单元须纳入满足条件的服务整合组合后判断", "ok": False}]

            if result == "full" and mode in {"service_integration", "single_fulfillment"}:
                if fields.get("payment_terms") == "other":
                    policy_gates.append({"name": "付款节点符合全额准入要求", "ok": False})
                elif fields.get("payment_terms") in (None, ""):
                    policy_gates.append({"name": "付款节点符合全额准入要求", "ok": None})
                if fields.get("customer_type") in {"private", "other"}:
                    status = "provisional"
                    reasons.append("客户类型需进一步核实是否属于全额准入范围")
                    evidence_items.extend(_unit_material_refs(final, ["MAT-COND-CUSTOMER-001"], "27号文自检"))
                if fields.get("ownership_transfer") in {"no", "uncertain"}:
                    status = "provisional"
                    reasons.append("产权转移事实需补充核实")
                    evidence_items.extend(_unit_material_refs(final, ["MAT-FIN-OWNERSHIP-001"], "27号文自检"))
                if fields.get("collective_procurement_ratio") == "lt_60":
                    status = "provisional"
                    reasons.append("后向集采比例低于建议值，需在报告中提示复核")

            if result == "full" and any(
                source.get("declared_type") in {"设备", "成品软件"} and source.get("logistics") == "supplier_direct"
                for source in sources
            ):
                policy_gates.append({"name": "设备/成品软件物流与物权由电信主控", "ok": False})

            failed_gates = [gate["name"] for gate in policy_gates if gate.get("ok") is False]
            pending_gates = [gate["name"] for gate in policy_gates if gate.get("ok") is None]
            if result == "full" and failed_gates:
                result = "net"
                status = "confirmed"
                reasons.extend(f"未满足：{name}" for name in failed_gates)
            elif result == "full" and pending_gates:
                status = "provisional"
                reasons.extend(f"待确认：{name}" for name in pending_gates)
                for name in pending_gates:
                    evidence_items.extend(_unit_material_refs(final, _policy_gate_material_ids(name), "27号文自检"))

        if intent == "full" and (status == "provisional" or result == "net"):
            risk_levels.append("high")
        decisions.append({
            "unit_id": final["id"],
            "unit_name": final["name"],
            "declared_type": final.get("declared_type"),
            "declared_types": final.get("declared_types") or [],
            "amount": final.get("amount"),
            "relationship": final.get("relationship"),
            "listing_intent": intent,
            "listing_result": result,
            "listing_result_status": status,
            "listed": result == "full",
            "mode": mode,
            "mode_label": _MODE_LABEL.get(mode, {"standard_product": "电信自有标品", "mixed": "混合"}.get(mode, mode)),
            "reasons": list(dict.fromkeys(reasons)),
            "policy_gates": policy_gates,
            "six_daowei_status": unit_six.get("status") if unit_six else "skipped",
            "r08_status": unit_r08.get("status") if unit_r08 else "skipped",
        })

    hard_to_service = _hard_to_service_v2(final_units, source_by_id)
    if hard_to_service:
        risk_levels.append("high")
        for flag in hard_to_service:
            final = next((item for item in final_units if item.get("id") == flag.get("unit_id")), {})
            evidence_items.extend(_unit_material_refs(final, flag["required_material_ids"], "硬转服务核查"))

    active_modes = list(dict.fromkeys(item["mode"] for item in decisions))
    summary_mode = active_modes[0] if len(active_modes) == 1 else "mixed"
    listing_mode = {
        "schema_version": 2,
        "mode": summary_mode,
        "mode_label": _MODE_LABEL.get(summary_mode, "混合列收模式"),
        "full_listing": bool(decisions) and all(item["listing_result"] == "full" for item in decisions),
        "basis": "按最终核算单元分别判断；项目级金额、占比和整体利润率按整个 BPM 项目计算，不互相连带改写单元结论。",
        "ratios": {
            "service_integration_pct": metrics["service_integration_pct"],
            "single_fulfillment_pct": metrics["single_fulfillment_pct"],
        },
        "gates": [],
        "blockers": [],
        "softs": [],
        "unit_decisions": decisions,
        "whitelist_version": WHITELIST_VERSION,
    }
    accounting_units = [
        {
            "id": item["unit_id"], "name": item["unit_name"],
            "declared_type": item["declared_type"], "amount": item["amount"],
            "listed": item["listed"], "listing_intent": item["listing_intent"],
            "listing_result_status": item["listing_result_status"],
        }
        for item in decisions
    ]
    return {
        "accounting_structure": structure,
        "accounting_units": accounting_units,
        "listing_mode": listing_mode,
        "six_daowei_checks": six_checks,
        "r08_checks": r08_checks,
        "hard_to_service": hard_to_service,
        "evidence_items": evidence_items,
        "risk_levels": risk_levels,
    }


def run_diagnosis(project_type: str | list | None, fields: dict, accounting_units: list | dict | None = None) -> dict:
    triggered = []
    tips = []
    manual_check_rules = []

    if isinstance(project_type, list):
        type_set = [t for t in project_type if t]
    elif project_type:
        type_set = [project_type]
    else:
        type_set = []

    for rule in sorted(RULES, key=lambda r: r["layer"]):
        applies_to = rule.get("applies_to", ["all"])
        if "all" not in applies_to:
            if not type_set or not any(t in applies_to for t in type_set):
                continue

        risk_level = rule["risk_level"]
        clause_sources = _get_clause_text(rule["clause_id"])

        item = {
            "rule_id": rule["id"],
            "rule_name": rule["name"],
            "layer": rule["layer"],
            "risk_level": risk_level,
            "risk_label": RISK_LABEL.get(risk_level, risk_level),
            "high_risk_type": rule.get("high_risk_type"),
            "risk_description": rule["risk_description"],
            "remediation": rule["remediation"],
            "optimization_direction": rule["optimization_direction"],
            "clause_sources": clause_sources,
            "audit_materials": rule.get("audit_materials", []),
        }

        if rule["trigger"].get("logic") == "MANUAL":
            manual_check_rules.append(item)
            continue

        if not _eval_trigger(rule["trigger"], fields):
            continue

        if risk_level == "tip":
            tips.append(item)
        else:
            triggered.append(item)

    # 抑制（27 号文重构后，见 docs/adr/0004 决策13）：切分了核算单元时——
    #   · R24/R25「硬件/施工包装为服务」是**误申报轴**，让位单元级硬转服务检测（#9），抑制；
    #   · R26「设备物流非主控」是**物权轴**，27 号文全额恰恰要求三流合一——保留为真实风险，
    #     并升格为 classify_listing_mode 内的单元级全额否决闸（供应商直发→该硬件没资格全额）。
    # 旧逻辑「硬件恒净额故 R24/R25/R26 一律误报抑制」作废（硬件现在可合法全额列收）。
    suppressed = []
    if accounting_units:
        _MISDECLARATION_RULES = {"R24", "R25"}
        suppressed = [it for it in triggered if it["rule_id"] in _MISDECLARATION_RULES]
        triggered = [it for it in triggered if it["rule_id"] not in _MISDECLARATION_RULES]

    # 软警告：本应切分核算单元的项目类型却未切分，意味着硬件排除（#8）与硬转服务检测（#9）
    # 都没跑——诊断退化为项目级单值，结论可能偏严。不阻断提交，只在结果里标记、报告显著提示。
    unit_warning = None
    if not accounting_units and any(t in _UNIT_EXPECTED_TYPES for t in type_set):
        unit_warning = {
            "level": "warn",
            "message": (
                "本次诊断未切分核算单元，硬件/施工的「铁律不列收」排除与「硬转服务」"
                "举证式检测均未生效，结论按项目级单值给出、可能偏严。建议返回"
                "「信息解析」面板切分并确认核算单元后重新提交诊断。"
            ),
        }

    # 新会话按最终核算单元分别判断。这里直接返回 v2 结果，旧数组继续走下方历史兼容路径，
    # 从而保证存量报告不会因为规则模型升级而被追溯改写。
    if is_v2_structure(accounting_units):
        unit_result = evaluate_accounting_structure(accounting_units, fields)
        risk_levels = [item["risk_level"] for item in triggered] + unit_result["risk_levels"]
        overall_risk = max(risk_levels, key=lambda r: RISK_ORDER.get(r, 0)) if risk_levels else "low"

        audit_set: dict[str, dict] = {}
        for item in triggered + tips + manual_check_rules:
            item_risk = "tip" if item in manual_check_rules else item["risk_level"]
            for material in item["audit_materials"]:
                _merge_audit_material(audit_set, material, item_risk, rule=item)
        for ref in unit_result["evidence_items"]:
            material = _material_from_id(ref["material_id"])
            _merge_audit_material(
                audit_set,
                material,
                "high",
                unit_name=ref.get("unit_name"),
                purpose=ref.get("purpose"),
            )

        return {
            "overall_risk": overall_risk,
            "overall_risk_label": RISK_LABEL.get(overall_risk, overall_risk),
            "triggered_rules": triggered,
            "tips": tips,
            "manual_check_rules": manual_check_rules,
            "audit_checklist": list(audit_set.values()),
            "suppressed_rules": suppressed,
            "accounting_structure": unit_result["accounting_structure"],
            "accounting_units": unit_result["accounting_units"],
            "hard_to_service": unit_result["hard_to_service"],
            "unit_warning": unit_warning,
            "control_roles_check": None,
            "six_daowei_check": None,
            "six_daowei_checks": unit_result["six_daowei_checks"],
            "r08_checks": unit_result["r08_checks"],
            "listing_mode": unit_result["listing_mode"],
            "rule_version": RULE_VERSION,
            "material_version": MATERIAL_VERSION,
            "advisory_only": True,
        }

    # 六到位关键角色自查（项目级共性证据，见 docs/adr/0003）——计算式，不进 rules.json
    # hardware_construction 字段定义为 bool（options: [True, False]），不是 "yes"/"no" 字符串
    _has_hardware = (fields.get("hardware_construction") is True) or any(
        u.get("declared_type") in _HW_UNIT_TYPES for u in (accounting_units or [])
    )
    # 「想全额」信号（跨项目类型）：R21 触发（系统集成/软件开发能力够主要责任人）
    # 或 服务自有/混合交付（服务类奔全额；全外包已被 R31 判差额，不算）
    _r21_fired = any(it["rule_id"] == "R21" for it in triggered)
    _wants_full = _r21_fired or fields.get("service_delivery_mode") in {"all_telecom", "mixed"}
    raw_control_roles_check = assess_control_roles(
        fields.get("control_roles"), _has_hardware, wants_full=_wants_full,
    )
    six_daowei_check = assess_six_daowei(
        fields,
        has_hardware=_has_hardware,
        wants_full=_wants_full,
        role_check=raw_control_roles_check,
    )
    control_roles_check = raw_control_roles_check
    # R09 纯外采已报「无控制权」时，抑制本检查的「资格不成立」，避免对同一项目重复报两条无控制权
    _r09_fired = any(it["rule_id"] == "R09" for it in triggered)
    if control_roles_check and control_roles_check["status"] == "ineligible" and _r09_fired:
        control_roles_check = None

    # 列收模式分类（27 号文重构，见 docs/adr/0004）——控制权是所有全额模式的总闸门。
    # control_roles_check 被 R09 置 None 时控制权实为不成立，按非 eligible 传入。
    _control_status = control_roles_check["status"] if control_roles_check else ("ineligible" if _r09_fired else None)
    _six_gate = six_daowei_check.get("listing_gate") or {}
    _six_gate_passed = _six_gate.get("passed")
    listing_mode = classify_listing_mode(
        type_set,
        fields,
        accounting_units,
        _control_status,
        six_daowei_passed=_six_gate_passed,
    )

    # 六到位未通过时服务也只能净额；标品保持既有“始终全额”独立口径，不由本闸门改写。
    if _six_gate_passed is False:
        for unit in accounting_units or []:
            if unit.get("declared_type") == "服务":
                unit["listed"] = False

    # #9：仅对最终仍奔全额的服务单元检查硬转服务；六到位已落净额的服务不重复检测。
    hard_to_service = detect_hard_to_service(accounting_units)

    risk_levels = (
        [it["risk_level"] for it in triggered]
        + [f["suspicion_level"] for f in hard_to_service]
    )
    # 资格不成立(high) 或 奔全额但未自证(medium) 计入整体风险；普通未填(tip)/成立(low) 不抬高
    if control_roles_check and control_roles_check["status"] in ("ineligible", "unfilled_wants_full"):
        risk_levels.append(control_roles_check["level"])
    if _six_gate_passed is False:
        risk_levels.append("high" if six_daowei_check.get("confirmed_level") == "none" else "medium")
    overall_risk = max(risk_levels, key=lambda r: RISK_ORDER.get(r, 0)) if risk_levels else "low"

    # 汇总材料：按材料编号去重，并保留全部用途、来源规则和四类目录元数据。
    audit_set: dict[str, dict] = {}
    for item in triggered + tips + manual_check_rules:
        item_risk = "tip" if item in manual_check_rules else item["risk_level"]
        for mat in item["audit_materials"]:
            _merge_audit_material(audit_set, mat, item_risk, rule=item)

    return {
        "overall_risk": overall_risk,
        "overall_risk_label": RISK_LABEL.get(overall_risk, overall_risk),
        "triggered_rules": triggered,
        "tips": tips,
        "manual_check_rules": manual_check_rules,
        "audit_checklist": list(audit_set.values()),
        "suppressed_rules": suppressed,
        "accounting_units": accounting_units or [],
        "hard_to_service": hard_to_service,
        "unit_warning": unit_warning,
        "control_roles_check": control_roles_check,
        "six_daowei_check": six_daowei_check,
        "listing_mode": listing_mode,
        "rule_version": RULE_VERSION,
        "material_version": MATERIAL_VERSION,
    }
