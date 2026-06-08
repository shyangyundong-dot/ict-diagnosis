import json
import os

# 加载规则库和条款原文库
_RULES_PATH = os.path.join(os.path.dirname(__file__), "rules.json")
_CLAUSES_PATH = os.path.join(os.path.dirname(__file__), "clauses.json")

with open(_RULES_PATH, encoding="utf-8") as f:
    _RULES_DATA = json.load(f)

with open(_CLAUSES_PATH, encoding="utf-8") as f:
    _CLAUSES_DATA = json.load(f)

RULES = _RULES_DATA["rules"]
CLAUSES = _CLAUSES_DATA["clauses"]
RULE_VERSION = _RULES_DATA.get("version", "v1.0")

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


# ── 控制权角色自查（总额法资格，见 docs/adr/0003）──
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


def assess_control_roles(control_roles, has_hardware: bool, wants_full: bool = False) -> dict | None:
    """控制权角色自查：判总额法资格（项目级，见 docs/adr/0003）。

    control_roles: 电信占据的关键角色编号列表（字符串/数字皆可）。
    has_hardware: 项目是否涉硬件（决定角色 16 是否必选）。
    wants_full: 项目从字段上看是否「明显奔全额列收」（R21 触发或服务自有/混合交付）。
                影响 unfilled 时的严重度：奔全额 → medium「控制权未自证」；否则 tip 不打扰。
    返回 None 表示无需呈现；否则 dict（status / level / message / missing）。
    举证式：资格不成立给 high + 举证路，不自动定性。high 仅在已填角色时落。
    """
    if not control_roles:
        if wants_full:
            return {
                "status": "unfilled_wants_full", "level": "medium", "missing": [],
                "message": (
                    "本项目从字段上看明显奔全额列收，但尚未通过官方 19 角色/8 情形框架自查控制权。"
                    "请在「信息解析」面板填写电信占据的关键角色，否则全额列收资格未自证。"
                ),
            }
        return {
            "status": "unfilled", "level": "tip", "missing": [],
            "message": "尚未填写控制权关键角色，未参与总额法资格判定。如需自证，请在「信息解析」面板补充。",
        }
    held = {str(r).strip() for r in control_roles if str(r).strip()}
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


def run_diagnosis(project_type: str | list | None, fields: dict, accounting_units: list | None = None) -> dict:
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

    # #8（见 docs/adr/0002）：硬件/施工 单元铁律不列收，正确归类即合规排除——
    # 此时 R24/R25/R26 的「列收违规」是误报，予以抑制。
    # （#9 会让 R24/R25 改按服务单元的「硬转服务」实质触发，而非项目含硬件即触发。）
    suppressed = []
    if accounting_units:
        hw_types = {"设备", "施工"}
        has_listed_hardware = any(
            (u.get("declared_type") in hw_types) and (u.get("listed") is not False)
            for u in accounting_units
        )
        if not has_listed_hardware:
            _HW_LISTING_RULES = {"R24", "R25", "R26"}
            suppressed = [it for it in triggered if it["rule_id"] in _HW_LISTING_RULES]
            triggered = [it for it in triggered if it["rule_id"] not in _HW_LISTING_RULES]

    # #9：硬转服务检测（举证式）——申报服务且列收的单元呈现硬件/施工实质即标记嫌疑，计入整体风险。
    hard_to_service = detect_hard_to_service(accounting_units)

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

    # 控制权角色自查（总额法资格，见 docs/adr/0003）——计算式，不进 rules.json
    _has_hardware = (fields.get("hardware_construction") == "yes") or any(
        u.get("declared_type") in {"设备", "施工"} for u in (accounting_units or [])
    )
    # 「想全额」信号（跨项目类型）：R21 触发（系统集成/软件开发能力够主要责任人）
    # 或 服务自有/混合交付（服务类奔全额；全外包已被 R31 判差额，不算）
    _r21_fired = any(it["rule_id"] == "R21" for it in triggered)
    _wants_full = _r21_fired or fields.get("service_delivery_mode") in {"all_telecom", "mixed"}
    control_roles_check = assess_control_roles(
        fields.get("control_roles"), _has_hardware, wants_full=_wants_full,
    )
    # R09 纯外采已报「无控制权」时，抑制本检查的「资格不成立」，避免对同一项目重复报两条无控制权
    _r09_fired = any(it["rule_id"] == "R09" for it in triggered)
    if control_roles_check and control_roles_check["status"] == "ineligible" and _r09_fired:
        control_roles_check = None

    risk_levels = (
        [it["risk_level"] for it in triggered]
        + [f["suspicion_level"] for f in hard_to_service]
    )
    # 资格不成立(high) 或 奔全额但未自证(medium) 计入整体风险；普通未填(tip)/成立(low) 不抬高
    if control_roles_check and control_roles_check["status"] in ("ineligible", "unfilled_wants_full"):
        risk_levels.append(control_roles_check["level"])
    overall_risk = max(risk_levels, key=lambda r: RISK_ORDER.get(r, 0)) if risk_levels else "low"

    # 汇总审计材料：同时覆盖风险项和操作提示，合并同名材料的多条用途和来源规则
    audit_set: dict[str, dict] = {}
    for item in triggered + tips:
        item_risk = item["risk_level"]
        for mat in item["audit_materials"]:
            key = mat["item"]
            if key not in audit_set:
                audit_set[key] = {
                    "item": mat["item"],
                    "purposes": [mat["purpose"]],
                    "rule_ids": [item["rule_id"]],
                    "rule_names": [item["rule_name"]],
                    # 取所有来源中最高的风险等级
                    "risk_level": item_risk,
                }
            else:
                entry = audit_set[key]
                if mat["purpose"] not in entry["purposes"]:
                    entry["purposes"].append(mat["purpose"])
                if item["rule_id"] not in entry["rule_ids"]:
                    entry["rule_ids"].append(item["rule_id"])
                    entry["rule_names"].append(item["rule_name"])
                # 升级风险等级（high > medium > low > tip）
                if RISK_ORDER.get(item_risk, 0) > RISK_ORDER.get(entry["risk_level"], 0):
                    entry["risk_level"] = item_risk

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
        "rule_version": RULE_VERSION,
    }

