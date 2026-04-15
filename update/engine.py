import json
import os
from typing import Any

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
        return False  # 人工判断规则，不自动触发
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


def run_diagnosis(project_type: str, fields: dict) -> dict:
    triggered = []
    tips = []

    # 按层顺序处理规则
    for rule in sorted(RULES, key=lambda r: r["layer"]):
        # 检查项目类型适用性
        applies_to = rule.get("applies_to", ["all"])
        if "all" not in applies_to and project_type not in applies_to:
            continue

        if not _eval_trigger(rule["trigger"], fields):
            continue

        risk_level = rule["risk_level"]
        clause_sources = _get_clause_text(rule["clause_id"])

        item = {
            "rule_id": rule["id"],
            "rule_name": rule["name"],
            "layer": rule["layer"],
            "risk_level": risk_level,
            "risk_label": RISK_LABEL.get(risk_level, risk_level),
            "high_risk_type": rule.get("high_risk_type"),   # forbidden | no_full_revenue | no_revenue | None
            "risk_description": rule["risk_description"],
            "remediation": rule["remediation"],
            "optimization_direction": rule["optimization_direction"],
            "clause_sources": clause_sources,
            "audit_materials": rule.get("audit_materials", []),
        }

        if risk_level == "tip":
            tips.append(item)
        else:
            triggered.append(item)

    # 计算总体风险等级
    if triggered:
        max_risk = max(triggered, key=lambda r: RISK_ORDER.get(r["risk_level"], 0))
        overall_risk = max_risk["risk_level"]
    else:
        overall_risk = "low"

    # 汇总审计材料（去重）
    audit_set = {}
    for item in triggered:
        for mat in item["audit_materials"]:
            key = mat["item"]
            if key not in audit_set:
                audit_set[key] = mat

    return {
        "overall_risk": overall_risk,
        "overall_risk_label": RISK_LABEL.get(overall_risk, overall_risk),
        "triggered_rules": triggered,
        "tips": tips,
        "audit_checklist": list(audit_set.values()),
        "rule_version": RULE_VERSION,
    }
