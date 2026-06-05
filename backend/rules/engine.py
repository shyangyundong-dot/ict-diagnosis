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

    risk_levels = (
        [it["risk_level"] for it in triggered]
        + [f["suspicion_level"] for f in hard_to_service]
    )
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
        "rule_version": RULE_VERSION,
    }

