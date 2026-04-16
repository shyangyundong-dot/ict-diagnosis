"""
AI个性化报告生成模块

核心思路：
- 规则引擎负责"判断触发了哪些规则"（客观、可追溯）
- 本模块负责"针对这个具体项目，写有针对性的分析文字"（个性化）
- 两者分工明确：引擎保证合规逻辑正确，AI保证报告有温度、有针对性
"""

import asyncio
import json
import os
import re
import httpx
from dotenv import load_dotenv

from ai_chat import migrate_legacy_service_fields

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MAX_RETRIES = int(os.getenv("DEEPSEEK_MAX_RETRIES", "3"))

# 字段值 → 中文映射（与 ai_chat.py 保持一致）
FIELD_VALUE_LABELS = {
    "project_type": {
        "system_integration": "系统集成",
        "software_development": "软件开发",
        "equipment_sales": "设备销售",
        "service": "服务类",
        "other": "其他",
    },
    "customer_type": {
        "state_owned": "国企",
        "private": "民企",
        "institution": "事业单位",
        "other": "其他",
    },
    "procurement_method": {
        "open_bid": "公开招标",
        "sole_source": "单一来源",
        "comparison": "比选",
        "collective": "集采",
    },
    "related_party": {"yes": "是", "no": "否", "uncertain": "不确定"},
    "gross_margin": {
        "lte_0": "≤0%",
        "lte_3": "1%-3%",
        "pct_4_5": "4%-5%",
        "pct_6_10": "6%-10%",
        "gt_10": "10%以上",
    },
    "revenue_recognition": {
        "point_in_time": "时点法（一次性交付）",
        "over_time": "时段法（周期性服务）",
        "mixed": "混合",
        "uncertain": "不确定",
    },
    "has_telecom_capability": {"yes": "是", "no": "否", "partial": "部分有"},
    "capability_ratio": {
        "all_external": "0%（全外采）",
        "very_low": "极低（少量融入）",
        "medium": "中等",
        "high": "较高",
    },
    "contract_content_same": {"yes": "是", "no": "否", "uncertain": "不确定"},
    "project_location": {
        "local": "本地",
        "remote_with_capability": "异地（电信有实施能力）",
        "remote_without_capability": "异地（电信无实施能力）",
    },
    "scheme_reviewed": {"yes": "是", "no": "否", "planned": "计划中"},
    "logistics_control": {
        "telecom_controlled": "是（电信采购-仓储-交付）",
        "supplier_direct": "否（供应商直发客户）",
    },
    "service_delivery_mode": {
        "all_telecom": "全部自有团队",
        "mixed": "混合（自有+外包）",
        "all_external": "全部外包/供应商执行",
    },
    "service_capability_level": {
        "strong": "强（N1-N6全部具备，有充分留痕）",
        "medium": "中（N1-N6大部分具备，部分需补充）",
        "weak": "弱（仅具备1-3项，难以全额列收）",
        "none": "无（无法举证任何六必要能力）",
    },
    "service_period": {
        "lte_3m": "≤3个月",
        "3m_12m": "3-12个月",
        "gt_12m": ">12个月",
    },
}

FIELD_LABELS = {
    "bpm_id": "BPM商机编号",
    "project_type": "项目类型",
    "customer_type": "前向客户类型",
    "supplier_confirmed": "后向供应商是否已确定",
    "procurement_method": "后向采购方式",
    "related_party": "前后向是否存在关联关系",
    "gross_margin": "毛利率估算",
    "revenue_recognition": "收入确认方式",
    "is_end_user": "前向客户是否为最终用户",
    "has_telecom_capability": "是否有电信自有产品或能力融入",
    "capability_ratio": "自有能力占比估算",
    "contract_content_same": "前后向合同内容是否高度一致",
    "project_location": "项目实施地点",
    "scheme_reviewed": "方案是否经过中台把关/评审",
    "hardware_construction": "是否含硬件/施工类内容",
    "logistics_control": "物流是否由电信主控",
    "service_delivery_mode": "服务交付是否由电信自有团队执行",
    "service_capability_level": "电信自有服务能力等级（六必要，系统依据交付模式推导）",
    "service_period": "服务周期",
    "has_prepayment": "是否含预付款",
    "has_advance_funding": "是否存在电信垫资",
    "related_party_checked": "三方关联关系是否已核查",
}


def _field_to_chinese(key: str, val) -> str:
    """将字段值转换为中文描述"""
    if val is True:
        return "是"
    if val is False:
        return "否"
    mapping = FIELD_VALUE_LABELS.get(key, {})
    if isinstance(val, list):
        return "、".join(mapping.get(v, str(v)) for v in val)
    return mapping.get(str(val), str(val))


def build_project_summary(fields: dict, chat_history: list[dict] | None = None) -> str:
    """将结构化字段 + 对话历史拼成项目描述文本，供 AI 参考"""
    fields = dict(fields or {})
    migrate_legacy_service_fields(fields)
    lines = ["【项目基本信息（结构化字段）】"]
    for key, label in FIELD_LABELS.items():
        val = fields.get(key)
        if val is None:
            continue
        lines.append(f"  {label}：{_field_to_chinese(key, val)}")

    # 提取对话中的用户原始描述（最多取前3条用户消息）
    if chat_history:
        user_msgs = [m["content"] for m in chat_history if m.get("role") == "user"][:3]
        if user_msgs:
            lines.append("\n【用户原始描述（对话摘要）】")
            for i, msg in enumerate(user_msgs, 1):
                # 截断过长消息
                truncated = msg[:500] + "…" if len(msg) > 500 else msg
                lines.append(f"  第{i}轮：{truncated}")

    return "\n".join(lines)


def _split_by_type(project_types: list[str]) -> tuple[list[str], list[str]]:
    """
    将项目类型拆分为"硬件/设备"板块 和 "服务/集成"板块
    返回 (hardware_types, service_types)
    """
    hw = [t for t in project_types if t in ("equipment_sales",)]
    svc = [t for t in project_types if t in ("system_integration", "software_development", "service", "other")]
    return hw, svc


async def _call_deepseek(prompt: str, system: str) -> str:
    """调用 DeepSeek，返回纯文本回复"""
    if not (DEEPSEEK_API_KEY or "").strip():
        return "（未配置 DEEPSEEK_API_KEY，跳过 AI 个性化分析）"

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 2000,
    }
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(connect=30.0, read=90.0, write=30.0, pool=30.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(DEEPSEEK_MAX_RETRIES):
            try:
                resp = await client.post(DEEPSEEK_URL, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
            except Exception as e:
                if attempt < DEEPSEEK_MAX_RETRIES - 1:
                    await asyncio.sleep(1.5 * (2 ** attempt))
                    continue
                return f"（AI分析生成失败：{e!s}）"
    return "（AI分析生成失败）"


ANALYSIS_SYSTEM_PROMPT = """你是广州电信云中台的ICT项目合规顾问，擅长结合具体项目情况给出有针对性的合规分析。

你的分析必须：
1. 结合项目的具体信息（前向客户类型、后向采购方式、毛利率、能力情况等），而不是泛泛而谈
2. 使用第二人称"您的项目"、"该项目"，让分析有代入感
3. 措辞专业但易懂，避免过于学术化
4. 每段分析控制在100-200字，简洁有力
5. 不要重复规则的定义，重点说"为什么这个项目会有这个问题"和"针对这个项目应该怎么做"

输出格式：纯文本，不要使用 markdown 标题，可以使用「」『』等符号强调关键词。"""


async def generate_rule_analysis(
    rule: dict,
    fields: dict,
    project_summary: str,
    segment_label: str = "",
) -> dict:
    """
    为单条触发规则生成个性化分析文字
    返回包含 ai_risk_analysis, ai_remediation, ai_optimization 的字典
    """
    rule_id = rule["rule_id"]
    rule_name = rule["rule_name"]
    hrt = rule.get("high_risk_type", "")
    hrt_labels = {
        "forbidden": "🚫 禁止做",
        "no_revenue": "❌ 不可列收",
        "no_full_revenue": "⚠️ 不可全额列收",
    }
    hrt_label = hrt_labels.get(hrt, "")

    segment_ctx = f"（分析范围：{segment_label}）" if segment_label else ""

    prompt = f"""请根据以下项目信息和触发规则，为该规则生成三段个性化分析文字。

{project_summary}

触发规则：{rule_id} - {rule_name} {hrt_label} {segment_ctx}
规则说明：{rule["risk_description"]}
标准整改建议：{rule["remediation"]}
标准模式优化：{rule["optimization_direction"]}

请生成以下三段文字（每段之间用 [SEP] 分隔）：
1. 风险分析（结合这个项目说明为什么会触发这条规则，有什么具体风险）
2. 整改建议（针对这个项目的具体可操作建议，比通用建议更有针对性）
3. 模式优化（结合这个项目的实际情况给出转型路径）

直接输出三段内容，用[SEP]分隔，不要加编号或标题。"""

    response = await _call_deepseek(prompt, ANALYSIS_SYSTEM_PROMPT)

    parts = response.split("[SEP]")
    if len(parts) >= 3:
        return {
            "ai_risk_analysis": parts[0].strip(),
            "ai_remediation": parts[1].strip(),
            "ai_optimization": parts[2].strip(),
        }
    else:
        # 分隔失败，整段作为风险分析
        return {
            "ai_risk_analysis": response.strip(),
            "ai_remediation": "",
            "ai_optimization": "",
        }


async def generate_segment_overview(
    segment_label: str,
    segment_types: list[str],
    triggered_rules: list[dict],
    fields: dict,
    project_summary: str,
) -> str:
    """为每个业务板块生成总体概述"""
    if not triggered_rules:
        return f"该板块（{segment_label}）未触发风险规则。"

    rule_list = "\n".join(
        f"- {r['rule_id']} {r['rule_name']}（{r.get('risk_label', '')}）"
        for r in triggered_rules
    )
    prompt = f"""请为以下业务板块生成一段总体合规概述（100字以内）：

项目信息：
{project_summary}

业务板块：{segment_label}
该板块触发的风险规则：
{rule_list}

请简明说明该板块整体合规状况和最核心的风险点，不要列举每条规则，重点给整体结论。"""

    return await _call_deepseek(prompt, ANALYSIS_SYSTEM_PROMPT)


async def enrich_diagnosis_with_ai(
    result: dict,
    fields: dict,
    chat_history: list[dict] | None = None,
) -> dict:
    """
    主入口：为规则引擎输出的诊断结果注入AI个性化分析
    支持混合型项目按板块分节
    """
    triggered = result.get("triggered_rules", [])
    tips = result.get("tips", [])

    key_ok = bool((DEEPSEEK_API_KEY or "").strip())

    if not triggered and not tips:
        result["segments"] = []
        result["ai_enriched"] = False
        return result

    # 获取项目类型列表
    pt = fields.get("project_type")
    if isinstance(pt, list):
        project_types = [t for t in pt if t]
    elif pt:
        project_types = [pt]
    else:
        project_types = []

    project_summary = build_project_summary(fields, chat_history)

    # 判断是否需要分板块
    hw_types, svc_types = _split_by_type(project_types)
    is_mixed = bool(hw_types and svc_types)

    if is_mixed:
        # 混合项目：按板块分类规则
        segments = await _build_mixed_segments(
            hw_types, svc_types, triggered, tips, fields, project_summary
        )
    else:
        # 单一类型：统一处理
        segments = await _build_single_segment(
            project_types, triggered, tips, fields, project_summary
        )

    result["segments"] = segments
    result["ai_enriched"] = key_ok
    result["is_mixed_project"] = is_mixed
    return result


# 强制归属硬件板块的规则ID（设备销售专属逻辑）
_HW_ONLY_RULES = {"R26"}
# 强制归属服务板块的规则ID（收入确认/控制权类）
_SVC_ONLY_RULES = {"R17", "R18", "R19", "R20", "R21", "R22", "R23", "R06", "R07", "R08"}

def _classify_rule_to_segment(rule: dict, hw_types: list, svc_types: list) -> str:
    """
    判断规则属于哪个板块（混合项目下避免重复）
    - 设备销售专属规则 → 硬件板块
    - 收入确认/控制权规则 → 服务板块
    - 其他通用规则 → 硬件板块（贸易合规重点）
    - 服务专属规则 → 服务板块
    """
    rule_id = rule.get("rule_id", "")
    applies_to = rule.get("applies_to", ["all"])

    if rule_id in _HW_ONLY_RULES:
        return "hardware"
    if rule_id in _SVC_ONLY_RULES:
        return "service"

    has_hw = "equipment_sales" in applies_to if "all" not in applies_to else True
    has_svc = any(t in applies_to for t in ["system_integration", "software_development", "service"])               if "all" not in applies_to else True

    if has_hw and not has_svc:
        return "hardware"
    if has_svc and not has_hw:
        return "service"

    # 通用规则（all）：根据规则层级分配
    # 第1-3层（禁止/控制权/业务真实性）→ 硬件板块（贸易合规）
    # 第4-7层（收入确认/采购）→ 服务板块
    layer = rule.get("layer", 3)
    return "hardware" if layer <= 3 else "service"


async def _build_mixed_segments(
    hw_types, svc_types, triggered, tips, fields, project_summary
) -> list[dict]:
    """构建混合项目的分板块结构"""
    hw_label = "设备/硬件销售部分"
    svc_label = "系统集成/服务部分"

    hw_rules, svc_rules = [], []
    for rule in triggered:
        seg = _classify_rule_to_segment(rule, hw_types, svc_types)
        if seg == "hardware":
            hw_rules.append(rule)
        else:
            svc_rules.append(rule)

    # 并发生成各板块总述
    hw_all = hw_rules
    svc_all = svc_rules

    hw_overview_task = generate_segment_overview(hw_label, hw_types, hw_all, fields, project_summary)
    svc_overview_task = generate_segment_overview(svc_label, svc_types, svc_all, fields, project_summary)
    hw_overview, svc_overview = await asyncio.gather(hw_overview_task, svc_overview_task)

    # 并发为每条规则生成AI分析
    async def enrich_rule(rule, seg_label):
        ai = await generate_rule_analysis(rule, fields, project_summary, seg_label)
        return {**rule, **ai}

    hw_tasks = [enrich_rule(r, hw_label) for r in hw_all]
    svc_tasks = [enrich_rule(r, svc_label) for r in svc_all]
    hw_enriched, svc_enriched = await asyncio.gather(
        asyncio.gather(*hw_tasks),
        asyncio.gather(*svc_tasks),
    )

    # 操作提示统一放最后，不分板块
    tips_tasks = [enrich_rule(r, "") for r in tips]
    tips_enriched = await asyncio.gather(*tips_tasks) if tips_tasks else []

    segments = []
    if hw_all or not svc_all:
        segments.append({
            "segment_id": "hardware",
            "segment_label": hw_label,
            "segment_types": hw_types,
            "overview": hw_overview,
            "triggered_rules": list(hw_enriched),
            "tips": [],
        })
    if svc_all:
        segments.append({
            "segment_id": "service",
            "segment_label": svc_label,
            "segment_types": svc_types,
            "overview": svc_overview,
            "triggered_rules": list(svc_enriched),
            "tips": [],
        })
    if tips_enriched:
        segments.append({
            "segment_id": "tips",
            "segment_label": "操作提示",
            "segment_types": [],
            "overview": "",
            "triggered_rules": [],
            "tips": list(tips_enriched),
        })

    return segments


async def _build_single_segment(
    project_types, triggered, tips, fields, project_summary
) -> list[dict]:
    """单一业务类型，所有规则放一个板块"""
    type_label_map = {
        "system_integration": "系统集成",
        "software_development": "软件开发",
        "equipment_sales": "设备销售",
        "service": "服务类",
        "other": "其他",
    }
    label = "、".join(type_label_map.get(t, t) for t in project_types) if project_types else "ICT项目"

    overview = await generate_segment_overview(label, project_types, triggered, fields, project_summary)

    async def enrich_rule(rule):
        ai = await generate_rule_analysis(rule, fields, project_summary)
        return {**rule, **ai}

    all_tasks = [enrich_rule(r) for r in triggered + tips]
    all_enriched = await asyncio.gather(*all_tasks) if all_tasks else []

    enriched_triggered = all_enriched[:len(triggered)]
    enriched_tips = all_enriched[len(triggered):]

    return [{
        "segment_id": "main",
        "segment_label": label,
        "segment_types": project_types,
        "overview": overview,
        "triggered_rules": list(enriched_triggered),
        "tips": list(enriched_tips),
    }]
