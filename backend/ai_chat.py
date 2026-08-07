import asyncio
import json
import os
import re
import httpx
from dotenv import load_dotenv

from guided_intake import SECTION_DEFINITIONS, SECTION_KEYS

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# 大模型请求：网络抖动或偶发 5xx/429 时重试
DEEPSEEK_MAX_RETRIES = int(os.getenv("DEEPSEEK_MAX_RETRIES", "3"))


# 所有需要收集的字段定义
FIELD_DEFINITIONS = {
    # 通用字段
    "bpm_id": {
        "label": "BPM商机编号",
        "required": True,
        "applies_to": "all",
        "hint": "测试阶段可填任意编号或占位文字；正式环境建议与 BPM 系统一致（如 BPM2024XXXXX）",
    },
    "project_type": {
        "label": "项目类型",
        "required": True,
        "applies_to": "all",
        "options": ["system_integration", "software_development", "equipment_sales", "service", "other"],
        "options_label": ["系统集成", "软件开发", "设备销售", "服务类", "其他"],
        "hint": "系统集成/软件开发/设备销售/服务类/其他"
    },
    "control_roles": {
        "label": "六到位关键角色（电信占据哪些）",
        "required": False,
        "applies_to": "all",
        "multi": True,
        "options": ["3", "4", "6", "7", "9", "10", "11", "13", "14", "16"],
        "options_label": [
            "3 解决方案设计者", "4 解决方案整合确定者",
            "6 应标与签约统筹者", "7 软硬件采购决策者",
            "9 全流程交付管理与质量责任者",
            "10 交付实施方案设计者", "11 交付实施方案确定及责任者",
            "13 项目实施/技术开发/联调实施者", "14 项目实施/技术开发主导与联调实操责任者",
            "16 到货验收及设备管理者（涉硬件）",
        ],
        "hint": "六到位自查（见 docs/adr/0003）：勾选电信在本项目实际占据的关键主导/决策/责任角色（非配合）。判定=必选6/7/9（涉硬件加16）+ 方案{3|4}/交付实施{10|11}/实施开发{13|14}各占一个。多为售中/执行信息，对话常缺，通常需手动确认。",
    },
    "six_daowei_facts_confirmed": {
        "label": "六到位基础事实已核对",
        "required": False,
        "applies_to": "all",
        "manual_confirmation": True,
        "options": [True],
        "options_label": ["已核对交付模式与关键角色"],
        "hint": "即使未勾选任何关键角色，也必须明确确认已经核对过；角色、交付模式或项目适用范围变化后需重新确认。",
    },
    # 六到位逐项结论由系统根据既有事实给建议、用户在右侧逐项确认；AI 不直接填写。
    "six_daowei_customer_insight": {
        "label": "客情掌握到位",
        "required": False,
        "applies_to": "all",
        "manual_confirmation": True,
        "options": ["in_place", "not_in_place", "pending_evidence"],
        "options_label": ["到位", "不到位", "待补证据"],
    },
    "six_daowei_solution_control": {
        "label": "方案总控到位",
        "required": False,
        "applies_to": "all",
        "manual_confirmation": True,
        "options": ["in_place", "not_in_place", "pending_evidence"],
        "options_label": ["到位", "不到位", "待补证据"],
    },
    "six_daowei_bid_autonomy": {
        "label": "谈判/应标自主到位",
        "required": False,
        "applies_to": "all",
        "manual_confirmation": True,
        "options": ["in_place", "not_in_place", "pending_evidence"],
        "options_label": ["到位", "不到位", "待补证据"],
    },
    "six_daowei_procurement_autonomy": {
        "label": "采购自主到位",
        "required": False,
        "applies_to": "all",
        "manual_confirmation": True,
        "options": ["in_place", "not_in_place", "pending_evidence", "not_applicable"],
        "options_label": ["到位", "不到位", "待补证据", "不适用（无外部采购）"],
    },
    "six_daowei_project_management": {
        "label": "项目强管理到位",
        "required": False,
        "applies_to": "all",
        "manual_confirmation": True,
        "options": ["in_place", "not_in_place", "pending_evidence"],
        "options_label": ["到位", "不到位", "待补证据"],
    },
    "six_daowei_operations_autonomy": {
        "label": "运维自主到位",
        "required": False,
        "applies_to": "all",
        "manual_confirmation": True,
        "options": ["in_place", "not_in_place", "pending_evidence", "not_applicable"],
        "options_label": ["到位", "不到位", "待补证据", "不适用（无运维/售后义务）"],
    },
    "six_daowei_level": {
        "label": "六到位综合结论",
        "required": False,
        "applies_to": "all",
        "manual_confirmation": True,
        "options": ["strong", "medium", "none"],
        "options_label": ["强", "中", "无"],
        "hint": "系统根据六维确认、关键角色和服务交付事实给出建议；最终以本项人工确认为准。只有基础事实已核对、六维全部到位、关键角色齐备且最终确认为强，才通过全额列收前置闸门；中或无均只能净额。通过后仍需继续判断 R08 及其他全额条件。",
    },
    "customer_type": {
        "label": "前向客户类型",
        "required": True,
        "applies_to": "all",
        "options": ["state_owned", "private", "institution", "government", "other"],
        "options_label": ["国企", "民企", "事业单位", "政府机关", "其他"]
    },
    "supplier_confirmed": {
        "label": "后向供应商是否已确定",
        "required": True,
        "applies_to": "all",
        "options": [True, False],
        "options_label": ["是", "否"]
    },
    "procurement_method": {
        "label": "后向采购方式",
        "required": True,
        "applies_to": "all",
        "options": ["open_bid", "sole_source", "comparison", "collective"],
        "options_label": ["公开招标", "单一来源", "比选", "集采"]
    },
    "forward_bidding_type": {
        "label": "前向客户的采购方式",
        "required": True,
        "applies_to": "all",
        "options": ["public_bid", "negotiation", "other"],
        "options_label": ["公开招标", "谈判/议标", "其他"],
        "hint": "前向客户对电信的采购方式（区别于电信对供应商的后向采购）。若为公开招标，需准备招标公告、应标文件、中标公告等投标材料备查。"
    },
    "contract_matches_bpm": {
        "label": "前向合同客户与BPM商机客户是否一致",
        "required": True,
        "applies_to": "all",
        "options": ["yes", "no", "uncertain"],
        "options_label": ["是（一致 / 计划保持一致）", "否（不一致）", "不确定 / 尚未签订"],
        "hint": "六到位「谈判/应标自主」核查要点：合同客户必须与BPM商机录入客户保持一致，否则可能涉及商机录错或借名走账风险。"
    },
    "related_party": {
        "label": "前后向是否存在关联关系",
        "required": True,
        "applies_to": "all",
        "options": ["yes", "no", "uncertain"],
        "options_label": ["是", "否", "不确定"]
    },
    "gross_margin": {
        "label": "毛利率估算（应列收/服务侧）",
        "required": True,
        "applies_to": "all",
        "options": ["lte_0", "lte_3", "pct_3_4", "pct_4_5", "pct_5_6", "pct_6_10", "gt_10"],
        "options_label": ["≤0%", "1%-3%", "3%-4%", "4%-5%", "5%-6%", "6%-10%", "10%以上"]
    },
    # ── 27 号文列收模式重构新增（见 docs/adr/0004）──
    "overall_margin": {
        "label": "项目整体税前利润率（含硬件，喂列收模式门槛）",
        "required": False,
        "applies_to": "all",
        "options": ["lte_0", "lte_3", "pct_3_4", "pct_4_5", "pct_5_6", "pct_6_10", "gt_10"],
        "options_label": ["≤0%", "1%-3%", "3%-4%", "4%-5%", "5%-6%", "6%-10%", "10%以上"],
        "hint": "与服务侧毛利率不同：这是项目整体（含硬件）的税前利润率，按新政「剔除非项目型 ICT 收支（云/小微/基础业务）」口径，填已剔除后的值。只喂列收模式门槛（服务整合≥10%/单一履约≥5%），不喂三零/过手检测。口径不较真，按填报估算。"
    },
    "major_integration": {
        "label": "是否为重大整合（单一组合产出）",
        "required": False,
        "applies_to": "all",
        "options": ["yes", "no", "uncertain"],
        "options_label": ["是（深度耦合/重大定制/交付单一功能完整系统）", "否（分别提供商品+服务）", "不确定"],
        "hint": "区分服务整合 vs 单一履约的分水岭：硬件与服务深度耦合、电信做了重大修改/定制、交付的是一个功能完整的单一系统，才算重大整合。AI 只在明确说「深度定制/重大修改/系统级集成」才抽，否则请手动勾选并举证，绝不臆测笼统的「提供了集成服务」。"
    },
    "payment_terms": {
        "label": "前向付款节点",
        "required": False,
        "applies_to": "all",
        "options": ["standard", "other"],
        "options_label": ["首付款 + 到货验收尾款（全额准入硬条件）", "其他（分期/账期等）"],
        "hint": "全额列收准入硬条件：前向付款方式须为「首付款 + 到货验收尾款」，按到货验收时点确认收入，确保产权实质性转移。非此方式则不符合全额准入。"
    },
    "ownership_transfer": {
        "label": "硬件产权是否验收后转移客户",
        "required": False,
        "applies_to": "all",
        "options": ["yes", "no", "uncertain"],
        "options_label": ["是", "否", "不确定/时点未到"],
        "hint": "全额列收要求验收后硬件所有权转移给客户。软提示：填报时点常未发生，不一票否决，但需举证产权实质性转移。"
    },
    "collective_procurement_ratio": {
        "label": "后向集采比例",
        "required": False,
        "applies_to": "all",
        "options": ["gte_60", "lt_60", "unknown"],
        "options_label": ["≥60%", "<60%", "不确定"],
        "hint": "单一履约后向采购建议集采比例 ≥60%（软建议，省采购是否授权市采购待定）。<60% 给黄字提示，不一票否决。"
    },
    "is_capital_investment": {
        "label": "是否为电信自投资设备打包（资本投资模式）",
        "required": False,
        "applies_to": "all",
        "options": [True, False],
        "options_label": ["是", "否"],
        "hint": "电信自投资、设备打包进资产、按收投比评估的模式。本工具仅打标识别，收投比 1.2 门槛走线下投资流程、不在此判定。"
    },
    "revenue_recognition": {
        "label": "收入确认方式",
        "required": True,
        "applies_to": "all",
        "options": ["point_in_time", "over_time", "mixed", "uncertain"],
        "options_label": ["时点法（一次性交付）", "时段法（周期性服务）", "混合", "不确定"]
    },
    "is_end_user": {
        "label": "前向客户是否为服务最终用户",
        "required": False,
        "applies_to": "all",
        "options": [True, False],
        "options_label": ["是", "否"]
    },
    # 系统集成/软件开发附加字段
    "has_telecom_capability": {
        "label": "是否有电信自有产品或能力融入",
        "required": True,
        "applies_to": ["system_integration", "software_development"],
        "options": ["yes", "no", "partial"],
        "options_label": ["是", "否", "部分有"]
    },
    "capability_ratio": {
        "label": "自有能力占比估算",
        "required": True,
        "applies_to": ["system_integration", "software_development"],
        "options": ["all_external", "very_low", "medium", "high"],
        "options_label": ["0%（全外采）", "极低（少量融入）", "中等", "较高"]
    },
    "contract_content_same": {
        "label": "前后向合同内容是否高度一致",
        "required": True,
        "applies_to": ["system_integration", "software_development", "equipment_sales"],
        "options": ["yes", "no", "uncertain"],
        "options_label": ["是", "否", "不确定"]
    },
    "acceptance_content_same": {
        "label": "是否计划直接使用供应商验收材料向客户交验",
        "required": True,
        "applies_to": ["system_integration", "software_development", "service"],
        "options": ["yes", "no", "uncertain"],
        "options_label": ["是（直接转交，不做二次加工）", "否（电信独立编制客户验收报告）", "不确定"],
        "hint": "前瞻性风险提示：若计划将供应商提供的验收材料原样转给客户，验收交付自主性缺失，审计时会被视为「空转走单」证据。建议：电信基于供应商交付物独立编制面向客户的验收报告。同时确保后向验收（供应商交付确认）早于前向验收（客户签收）完成，避免倒签风险。"
    },
    "project_location": {
        "label": "项目实施地点",
        "required": True,
        "applies_to": ["system_integration", "software_development", "service"],
        "options": ["local", "remote_with_capability", "remote_without_capability"],
        "options_label": ["本地", "异地（电信有实施能力）", "异地（电信无实施能力）"]
    },
    "scheme_reviewed": {
        "label": "方案是否经过中台把关/评审",
        "required": True,
        "applies_to": ["system_integration", "software_development"],
        "options": ["yes", "no", "planned"],
        "options_label": ["是", "否", "计划中"]
    },
    "hardware_construction": {
        "label": "是否含硬件/施工类内容",
        "required": True,
        "applies_to": ["system_integration", "software_development", "service", "equipment_sales"],
        "options": [True, False],
        "options_label": ["是", "否"]
    },
    # 设备销售附加字段
    "logistics_control": {
        "label": "物流是否由电信主控",
        "required": True,
        "applies_to": ["equipment_sales"],
        "options": ["telecom_controlled", "supplier_direct"],
        "options_label": ["是（电信采购-仓储-交付）", "否（供应商直发客户）"]
    },
    "related_party_checked": {
        "label": "三方关联关系是否已核查",
        "required": False,
        "applies_to": ["equipment_sales"],
        "options": ["yes", "no", "na"],
        "options_label": ["是", "否", "不适用"]
    },
    # 服务类附加字段（交付模式统一为 v1.2 三档，见 service_delivery_mode）
    "service_period": {
        "label": "服务周期",
        "required": True,
        "applies_to": ["service"],
        "options": ["lte_3m", "3m_12m", "gt_12m"],
        "options_label": ["≤3个月", "3-12个月", ">12个月"]
    },
    # 资金相关
    "has_prepayment": {
        "label": "我方采购是否含预付款",
        "required": True,
        "applies_to": "all",
        "options": [True, False],
        "options_label": ["是", "否"]
    },
    "has_advance_funding": {
        "label": "我方是否存在垫资",
        "required": True,
        "applies_to": "all",
        "options": [True, False],
        "options_label": ["是", "否"]
    },
    # 服务类专属补丁字段（v1.2新增）
    "service_delivery_mode": {
        "label": "服务交付是否由电信自有团队执行",
        "required": True,
        "applies_to": ["service"],
        "options": ["all_telecom", "mixed", "all_external"],
        "options_label": ["全部自有团队", "混合（自有+外包）", "全部外包/供应商执行"],
        "hint": "六到位服务场景证据：记录电信自有团队与外包团队的实际交付关系，供 R31/R32/R34 与关键角色证据共同判断"
    },
    # 历史兼容字段：2026-07-18 起不再按交付模式自动生成，新诊断不展示。
    "service_capability_level": {
        "label": "六到位服务能力等级（历史自动推导）",
        "required": False,
        "applies_to": ["service"],
        "deprecated": True,
        "options": ["strong", "medium", "weak", "none"],
        "options_label": [
            "强（N1-N6全部具备，有充分留痕）",
            "中（N1-N6部分具备，部分需补充）",
            "弱（仅具备1-3项，难以全额列收）",
            "无（无法举证任何六到位能力）",
        ],
    },
}


def _required_keys_for_project_types(types: list[str]) -> list[str]:
    """按 FIELD_DEFINITIONS 顺序，合并多种项目类型下的必填字段键（去重）。"""
    keys: list[str] = []
    for key, defn in FIELD_DEFINITIONS.items():
        applies = defn.get("applies_to", "all")
        if applies == "all":
            keys.append(key)
        elif isinstance(applies, list) and any(t in applies for t in types):
            keys.append(key)
    return keys


def project_types_from_fields(fields: dict) -> list[str] | None:
    """project_type 支持字符串（兼容旧数据）或多选列表。"""
    pt = fields.get("project_type")
    if pt is None:
        return None
    if isinstance(pt, list):
        out = [x for x in pt if x]
        return out if out else None
    if isinstance(pt, str) and pt.strip():
        return [pt.strip()]
    return None


def normalize_project_type_field(fields: dict) -> None:
    """将模型返回的单个类型规范为列表，便于多选存储。"""
    pt = fields.get("project_type")
    if pt is None:
        return
    if isinstance(pt, str) and pt.strip():
        fields["project_type"] = [pt.strip()]
    elif isinstance(pt, list):
        fields["project_type"] = [x for x in pt if x]


def strip_deprecated_input_fields(fields: dict) -> None:
    """移除已下线或只供历史记录读取的字段。"""
    fields.pop("supplier_confirmed_early", None)
    fields.pop("service_capability_level", None)
    fields.pop("major_integration", None)
    for key in (
        "six_daowei_facts_confirmed",
        "six_daowei_customer_insight",
        "six_daowei_solution_control",
        "six_daowei_bid_autonomy",
        "six_daowei_procurement_autonomy",
        "six_daowei_project_management",
        "six_daowei_operations_autonomy",
        "six_daowei_level",
    ):
        fields.pop(key, None)


def apply_derived_fields_for_diagnosis(fields: dict) -> None:
    """提交诊断入库前执行兼容迁移，并清除已停用的派生等级。"""
    migrate_legacy_service_fields(fields)
    strip_deprecated_input_fields(fields)


def migrate_legacy_service_fields(fields: dict) -> None:
    """旧版 service_by_telecom（yes/no/mixed）→ service_delivery_mode（v1.2 三档），并移除旧键。"""
    if fields.get("service_delivery_mode") is not None:
        fields.pop("service_by_telecom", None)
        return
    old = fields.get("service_by_telecom")
    if old is None:
        return
    m = {"yes": "all_telecom", "mixed": "mixed", "no": "all_external"}
    if old in m:
        fields["service_delivery_mode"] = m[old]
    fields.pop("service_by_telecom", None)


def get_missing_fields(fields: dict) -> list[str]:
    """返回还缺少的必填字段（依赖 project_type 多选并集）。"""
    migrate_legacy_service_fields(fields)
    strip_deprecated_input_fields(fields)
    types = project_types_from_fields(fields)
    if not types:
        return ["project_type"]

    needed = _required_keys_for_project_types(types)
    missing: list[str] = []
    for key in needed:
        defn = FIELD_DEFINITIONS.get(key, {})
        if not defn.get("required", False):
            continue
        val = fields.get(key)
        if key == "bpm_id":
            if val is None or (isinstance(val, str) and not val.strip()):
                missing.append(key)
            continue
        if key == "project_type":
            if not types:
                missing.append(key)
            continue
        if key == "six_daowei_facts_confirmed":
            if val is not True:
                missing.append(key)
            continue
        if val is None:
            missing.append(key)
    return missing


def format_field_value_for_display(key: str, val, defn: dict):
    """将存储值转为右侧展示用中文（含 project_type 多选）。"""
    if val is None:
        return None
    if key == "project_type" and isinstance(val, list):
        options = defn.get("options", [])
        options_label = defn.get("options_label", [])
        parts = []
        for v in val:
            if v in options:
                idx = options.index(v)
                parts.append(options_label[idx] if idx < len(options_label) else v)
            else:
                parts.append(str(v))
        return "、".join(parts) if parts else None
    options = defn.get("options", [])
    options_label = defn.get("options_label", [])
    if val in options:
        idx = options.index(val)
        return options_label[idx] if idx < len(options_label) else val
    if val is True:
        return "是"
    if val is False:
        return "否"
    return val


def build_fields_display(current_fields: dict) -> list[dict]:
    """构建字段展示列表（供前端与编辑态同步）。"""
    fields_display = []
    for key, val in current_fields.items():
        defn = FIELD_DEFINITIONS.get(key, {})
        label = defn.get("label", key)
        display_val = format_field_value_for_display(key, val, defn)
        fields_display.append({"key": key, "label": label, "value": display_val, "raw": val})
    return fields_display


def parse_json_payload_from_ai(content: str) -> dict:
    """从模型回复中解析含 extracted 的 JSON；兼容 ```json 代码块、正文中的裸 JSON 对象。"""
    for m in re.finditer(r"```(?:json)?\s*([\s\S]*?)\s*```", content, re.IGNORECASE):
        raw = m.group(1).strip()
        if not raw.startswith("{"):
            continue
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict) and (
                "extracted" in obj or "missing_required" in obj or "is_complete" in obj
            ):
                return obj
        except json.JSONDecodeError:
            continue
    decoder = json.JSONDecoder()
    for i, ch in enumerate(content):
        if ch != "{":
            continue
        try:
            obj, _end = decoder.raw_decode(content, i)
            if isinstance(obj, dict) and (
                "extracted" in obj or "missing_required" in obj or "is_complete" in obj
            ):
                return obj
        except ValueError:
            continue
    # 兜底：模型直接输出整段 JSON（无代码块、未被 raw_decode 命中时）
    s = (content or "").strip()
    if s.startswith("{") and s.endswith("}"):
        try:
            obj = json.loads(s)
            if isinstance(obj, dict) and (
                "extracted" in obj or "missing_required" in obj or "is_complete" in obj
            ):
                return obj
        except json.JSONDecodeError:
            pass
    return {}


def clip_messages_for_api(messages: list[dict], max_chars: int = 10000) -> list[dict]:
    """单条对话过长时截断，避免第二轮超长输入撑爆上下文或拖垮请求。"""
    out: list[dict] = []
    for m in messages:
        role = m.get("role") or "user"
        c = m.get("content") or ""
        if len(c) > max_chars:
            c = (
                c[:max_chars]
                + "\n\n…（本条过长已截断发送给模型，关键信息请拆成多条发送）"
            )
        out.append({"role": role, "content": c})
    return out


def build_reply_text(clean_content: str, extracted_data: dict) -> str:
    """去掉 JSON 后若正文为空，用 next_question 或默认提示，避免出现空白回复。"""
    t = (clean_content or "").strip()
    if t:
        return t
    nq = (extracted_data.get("next_question") or "").strip()
    if nq:
        return nq
    return (
        "已根据你的描述更新解析结果，请查看右侧「已解析并确认的信息」与「待补充信息」。"
        "若你刚发送的内容较长，已将部分正文截断后发给模型，重要信息可分多条补充说明。"
    )


SYSTEM_PROMPT = """你是广州电信云中台的ICT项目合规诊断助手。你的任务是通过对话，逐步收集用户项目的关键信息，用于后续的合规风险诊断。

## 你的工作方式
1. 用户用自然语言描述项目，你负责从中提取结构化字段
2. 每轮对话后，判断哪些字段还缺失，继续追问
3. 追问时要自然、友好，像一个有经验的业务顾问，不要像填表机器人
4. 每次只追问1-2个最重要的缺失信息，不要一次性抛出太多问题
5. 如果用户的描述模糊，要帮助澄清，举例说明

## 字段提取规则
每轮对话结束时，你必须输出一个JSON块，格式如下：
```json
{
  "extracted": {
    "字段名": "字段值"
  },
  "missing_required": ["字段名列表"],
  "next_question": "下一个要问的问题（自然语言）",
  "is_complete": false
}
```

## 字段名和合法值说明
- project_type: **数组**，可多项。每项为："system_integration"（系统集成）| "software_development"（软件开发）| "equipment_sales"（设备销售）| "service"（服务类）| "other"。若用户只描述了一种，也可用单字符串，系统会转为单元素数组。
- customer_type: "state_owned"（国企）| "private"（民企）| "institution"（事业单位）| "government"（政府机关，如民政局、各级政府行政部门）| "other"
- supplier_confirmed: true | false
- procurement_method: 电信对实施方/供应商的后向采购。"open_bid"（公开招标）| "sole_source"（单一来源）| "comparison"（比选）| "collective"（集采）
- forward_bidding_type: 前向客户对电信的采购方式（不要与 procurement_method 混淆）。"public_bid"（公开招标）| "negotiation"（谈判/议标）| "other"（其他）
- contract_matches_bpm: 前向合同客户与BPM商机客户是否一致。"yes"（一致或计划保持一致）| "no"（不一致）| "uncertain"（不确定/尚未签订）
- related_party: "yes" | "no" | "uncertain"
- gross_margin: "lte_0"（≤0%）| "lte_3"（1-3%）| "pct_3_4"（3-4%）| "pct_4_5"（4-5%）| "pct_5_6"（5-6%）| "pct_6_10"（6-10%）| "gt_10"（10%以上）。**只取服务侧毛利**，绝不要把设备、成品软件或施工毛利混算进来。项目整体利润率另填 overall_margin。
- revenue_recognition: "point_in_time"（时点法）| "over_time"（时段法）| "mixed" | "uncertain"
- is_end_user: true | false
- has_telecom_capability: "yes" | "no" | "partial"
- capability_ratio: "all_external"（全外采）| "very_low"（极低）| "medium"（中等）| "high"（较高）
- contract_content_same: "yes" | "no" | "uncertain"
- acceptance_content_same: "yes"（计划直接用供应商验收材料交客户）| "no"（电信独立编制客户验收报告）| "uncertain"
- project_location: "local"（本地）| "remote_with_capability"（异地有实施能力）| "remote_without_capability"（异地无实施能力）
- scheme_reviewed: "yes" | "no" | "planned"
- hardware_construction: true | false
- logistics_control: "telecom_controlled" | "supplier_direct"
- service_period: "lte_3m" | "3m_12m" | "gt_12m"
- has_prepayment: true | false
- has_advance_funding: true | false
- service_delivery_mode: "all_telecom"（全部自有团队）| "mixed"（混合（自有+外包））| "all_external"（全部外包/供应商执行）。仅 service 类型必填，是六到位在服务场景下的客观证据之一。
- bpm_id: 字符串。测试阶段可为任意占位编号；正式环境建议与 BPM 一致（如 BPM2024XXXXX）
- control_roles: **数组**，电信在本项目占据的关键角色编号（字符串）。取值：
  - 必选区："6"（应标与签约统筹）| "7"（软硬件采购决策）| "9"（全流程交付管理与质量责任）| "16"（到货验收及设备管理，涉硬件时）
  - 方案二选一："3"（解决方案设计者）| "4"（解决方案整合确定者）
  - 交付实施方案二选一："10"（交付实施方案设计者）| "11"（交付实施方案确定及责任者）
  - 实施开发二选一："13"（项目实施/技术开发/联调实施者）| "14"（项目实施/技术开发主导与联调实操责任者）
  提取规则：**只抽取用户明确说出的角色**，不要从"自有能力"/"主要责任人"等抽象描述推断。
  示例：用户说"电信主导方案设计、自主采购、负责全流程交付管理" → ["3","7","9"]；用户说"电信自主投标签约、设备由电信负责验收" → ["6","16"]；用户只说项目金额/客户/范围/毛利 → **不输出该字段**（让用户自己手填，绝不臆测）。

- six_daowei_facts_confirmed / six_daowei_customer_insight / six_daowei_solution_control / six_daowei_bid_autonomy /
  six_daowei_procurement_autonomy / six_daowei_project_management /
  six_daowei_operations_autonomy / six_daowei_level：均为右侧面板人工确认字段。
  **不要输出、不要代替用户确认，也不要在对话里逐项重复追问**。新诊断会在用户确认组合关系和最终核算单元列收意图后，对每个拟全额单元分别完成六到位与 R08 自查。
- service_capability_level：历史兼容字段，**不要输出**。

### 27 号文列收模式字段（全额资格判定，见 docs/adr/0004）——均非必填，**只抽用户明确说出的，拿不准就不输出，让用户手填**：
- overall_margin: 项目**整体**税前利润率（**含硬件**，区别于服务侧 gross_margin）。同一套分桶："lte_0"|"lte_3"|"pct_3_4"|"pct_4_5"|"pct_5_6"|"pct_6_10"|"gt_10"。喂列收模式门槛（服务整合≥10%/单一履约≥5%）。用户明确说整体利润率才抽。
- major_integration：历史字段，**不要输出**。新诊断在核算单元面板按四项履约关系事实逐组合确认，不再使用项目级重大整合单值。
- payment_terms: 前向付款节点。"standard"（首付款+到货验收尾款）| "other"（分期/账期等）。明确说付款方式才抽。
- ownership_transfer: 硬件产权是否验收后转移客户。"yes" | "no" | "uncertain"。
- collective_procurement_ratio: 后向集采比例。"gte_60"（≥60%）| "lt_60"（<60%）| "unknown"。
- is_capital_investment: 是否电信自投资设备打包（资本投资模式）。true | false。明确说"电信自投资/资本投资"才抽 true。

## 重要规则
- 你只做事实提取，**绝不输出风险等级、列收结论、合规结论或任何规则命中判断**；正式诊断只会在用户确认表单后由规则引擎执行。
- is_complete只有在所有必填字段（根据project_type**数组**所覆盖类型的并集）都已收集完毕时才设为true
- 追问要有温度，要体现你理解业务，不是机械地问清单
- 如果用户表达的信息和某个选项不完全匹配，选最接近的，但在next_question里请用户确认
- bpm_id如果用户没提，要问；如果用户说"还没有"，可记为"待录入"等占位
- **只输出 JSON 对象，不要输出 JSON 外的自然语言、Markdown 或代码块。**
"""


FIELD_HELP_SYSTEM_PROMPT = """你是 ICT 项目事实填报助手。用户正在填写一个明确字段；你只能解释该字段的含义、根据用户明确说出的事实给出合法选项建议，或提出一个澄清问题。

严格边界：不要判断项目合规性、风险等级、能否全额列收、是否触发规则，也不要说“通过/不通过”。这些结论只能由用户提交后运行规则库得出。

只输出以下 JSON 对象，不要输出 Markdown 或额外文字：
{
  "explanation": "简短字段解释",
  "suggested_value": "合法选项值或 null",
  "reason": "建议依据；不确定时说明缺少什么事实",
  "follow_up": "必要时的一个澄清问题，否则为空字符串"
}
"""


def _parse_any_json_object(content: str) -> dict:
    """从模型内容中尽力提取第一个 JSON 对象。"""
    for m in re.finditer(r"```(?:json)?\s*([\s\S]*?)\s*```", content or "", re.IGNORECASE):
        try:
            value = json.loads(m.group(1).strip())
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            continue
    decoder = json.JSONDecoder()
    for index, char in enumerate(content or ""):
        if char != "{":
            continue
        try:
            value, _end = decoder.raw_decode(content, index)
            if isinstance(value, dict):
                return value
        except ValueError:
            continue
    return {}


def _build_deepseek_payload(
    api_messages: list[dict],
    max_tokens: int,
    *,
    model: str | None = None,
    json_output: bool = False,
    disable_thinking: bool = True,
) -> dict:
    """构造结构化调用载荷；V4 默认关闭思考，避免推理耗尽输出预算。"""
    selected_model = model or DEEPSEEK_MODEL
    payload = {
        "model": selected_model,
        "messages": api_messages,
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }
    if disable_thinking and str(selected_model).startswith("deepseek-v4"):
        payload["thinking"] = {"type": "disabled"}
    if json_output:
        payload["response_format"] = {"type": "json_object"}
    return payload


async def _call_deepseek_messages(
    api_messages: list[dict],
    max_tokens: int = 4096,
    *,
    json_output: bool = False,
    disable_thinking: bool = True,
) -> tuple[str, str, str | None]:
    """统一处理 DeepSeek 请求、重试和可展示错误。"""
    if not (DEEPSEEK_API_KEY or "").strip():
        return "", "", "系统未配置 DEEPSEEK_API_KEY，暂时无法使用 AI 助填。"

    timeout = httpx.Timeout(connect=30.0, read=120.0, write=120.0, pool=30.0)
    payload = _build_deepseek_payload(
        api_messages,
        max_tokens,
        json_output=json_output,
        disable_thinking=disable_thinking,
    )
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    data = None
    last_error: Exception | None = None

    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(DEEPSEEK_MAX_RETRIES):
            try:
                resp = await client.post(DEEPSEEK_URL, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                last_error = None
                break
            except httpx.HTTPStatusError as e:
                last_error = e
                code = e.response.status_code
                retriable = code in (429, 500, 502, 503, 504)
                if retriable and attempt < DEEPSEEK_MAX_RETRIES - 1:
                    await asyncio.sleep(1.5 * (2**attempt))
                    continue
                return "", "", f"调用 DeepSeek 失败：HTTP {code}。"
            except httpx.RequestError as e:
                last_error = e
                if attempt < DEEPSEEK_MAX_RETRIES - 1:
                    await asyncio.sleep(1.5 * (2**attempt))
                    continue
                return "", "", f"调用 AI 网络异常（已重试 {DEEPSEEK_MAX_RETRIES} 次）。"
            except Exception as e:
                return "", "", f"调用 AI 时出错：{e!s}"

    if data is None:
        msg = f"{last_error!s}" if last_error else "未知错误"
        return "", "", f"调用 AI 失败：{msg}"

    choice = data["choices"][0]
    content = (choice.get("message") or {}).get("content") or ""
    finish_reason = choice.get("finish_reason") or ""
    if not content.strip():
        if finish_reason == "length":
            return "", finish_reason, "AI 输出预算已用尽，未返回可解析内容。"
        return "", finish_reason, "AI 未返回可解析内容，请稍后重试。"
    return content, finish_reason, None


async def chat_with_ai(messages: list[dict], current_fields: dict, project_type: str = None) -> dict:
    """从整段项目描述提取可预填字段；不产生诊断结论。"""
    context_msg = f"""
当前已收集到的字段：
{json.dumps(current_fields, ensure_ascii=False, indent=2)}

项目类型：{project_type or "未确定"}

请根据对话历史，提取新信息并判断下一步要问什么。
"""
    api_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": context_msg},
    ] + clip_messages_for_api(messages)
    content, finish_reason, error = await _call_deepseek_messages(api_messages, json_output=True)
    if error:
        return {"reply": error, "extracted": {}, "missing_required": [], "next_question": "", "is_complete": False}

    extracted_data = parse_json_payload_from_ai(content)
    reply_text = build_reply_text("", extracted_data)
    if finish_reason == "length":
        reply_text += "（模型输出已达长度上限，若 JSON 不完整请缩短描述后重试。）"

    return {
        "reply": reply_text,
        "extracted": extracted_data.get("extracted", {}),
        "missing_required": extracted_data.get("missing_required", []),
        "next_question": extracted_data.get("next_question", ""),
        "is_complete": extracted_data.get("is_complete", False),
    }


def _legal_field_suggestion(field_key: str, value):
    definition = FIELD_DEFINITIONS.get(field_key) or {}
    options = definition.get("options") or []
    if value is None or not options:
        return None
    if field_key == "project_type":
        values = value if isinstance(value, list) else [value]
        if values and all(item in options for item in values):
            return values
        return None
    return value if value in options else None


async def help_with_field(field_key: str, question: str, current_fields: dict) -> dict:
    """返回单字段解释与可选建议，不写入会话字段。"""
    definition = FIELD_DEFINITIONS.get(field_key)
    if not definition:
        return {"explanation": "未找到该字段定义。", "suggested_value": None, "reason": "", "follow_up": ""}

    context = {
        "field_key": field_key,
        "label": definition.get("label"),
        "hint": definition.get("hint", ""),
        "options": definition.get("options", []),
        "options_label": definition.get("options_label", []),
        "current_value": current_fields.get(field_key),
        "known_fields": current_fields,
        "user_question": question,
    }
    api_messages = [
        {"role": "system", "content": FIELD_HELP_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
    ]
    content, _finish_reason, error = await _call_deepseek_messages(
        api_messages, max_tokens=900, json_output=True,
    )
    if error:
        return {
            "explanation": definition.get("hint") or "请按项目实际事实选择。",
            "suggested_value": None,
            "reason": error,
            "follow_up": "",
        }

    data = _parse_any_json_object(content)
    return {
        "explanation": str(data.get("explanation") or definition.get("hint") or "请按项目实际事实选择。"),
        "suggested_value": _legal_field_suggestion(field_key, data.get("suggested_value")),
        "reason": str(data.get("reason") or ""),
        "follow_up": str(data.get("follow_up") or ""),
    }


# ── 六块引导式项目说明 ──────────────────────────────────────

GUIDED_INTAKE_SYSTEM_PROMPT = """你是广州电信云中台的 ICT 项目事实整理助手。用户会按六块模板描述项目，你负责整理事实、判断信息覆盖、规划集中追问，并形成原始核算单元草稿。

严格边界：
1. 只做事实提取和缺口识别，绝不输出风险等级、规则命中、列收结果、合规结论或整改建议。
2. 不要把“电信参与/协调”臆测成“电信主导/决策/承担责任”。
3. 不确定的字段不要猜；用户明确说不知道时记录为 unknown_confirmed。
4. 每轮最多给 5 个追问，按同一主题集中组织；已回答或明确不知道的内容不要重复问。
5. 只输出 JSON 对象，不要输出 Markdown、代码块或 JSON 外文字。

六块键固定为：basic、delivery、responsibilities、acceptance、commercial、financial。
每块必须返回：
- status: covered | partial | missing | not_applicable | unknown_confirmed
- summary: 2-5 句事实摘要，不得含风险或列收结论
- missing_topics: 尚缺主题数组
- contradictions: 前后冲突数组
- evidence: 支撑摘要的用户原文逐字短句数组

原始核算单元 source_units 的每项字段：
- name
- declared_type: 设备 | 成品软件 | 施工 | 服务 | 标品 | 其他
- amount: 元，不确定为 null
- tax_rate: 如 13%，不确定为 null
- gross: 毛利额或毛利率原文，不确定为 null
- logistics: self | supplier_direct | unknown
- has_self_capability: true | false | unknown
- whitelisted: 仅设备/成品软件使用 true | false | unknown，其他类型为 null
- suggested_group: 可能构成同一组合产出时使用相同组名，否则 null
- reason: 业务实质分类依据
- evidence: 对象，至少包含 type；可包含 amount、tax_rate、gross、logistics、capability、whitelist。
  每项必须逐字摘自用户原文；没有直接证据时对应值必须填 null/unknown。

最小拆分要求：同一报价项或描述同时包含可独立识别的设备和施工（如设备供货 + 安装/布放/调试）时，必须拆成设备、施工两个原始单元；总金额不能可靠拆分时，两项 amount 均填 null，并用相同 suggested_group 关联。
每个有独立名称或金额的标段/报价块都必须保留一个原始单元；即使其内部设备、施工、服务金额尚未拆清，也先用“其他”占位并保留该标段总额，不得因资料不完整而漏掉整块业务。

特别注意：gross_margin 只表示应列收/服务侧毛利；overall_margin 才表示包含硬件的项目整体利润率，二者严禁互串。

返回结构：
{
  "sections": {
    "basic": {"status":"...","summary":"...","missing_topics":[],"contradictions":[],"evidence":[]},
    "delivery": {}, "responsibilities": {}, "acceptance": {}, "commercial": {}, "financial": {}
  },
  "extracted": {"合法字段键": {"value": "合法字段值", "evidence": "用户原文逐字短句"}},
  "source_units": [],
  "blocking_topics": [],
  "simple_fact_gaps": [],
  "contradictions": [],
  "follow_up_questions": []
}
"""


def _guided_field_contract() -> dict:
    contract = {}
    for key, definition in FIELD_DEFINITIONS.items():
        if definition.get("deprecated") or definition.get("manual_confirmation"):
            continue
        if key in {"control_roles", "major_integration", "service_capability_level"}:
            continue
        contract[key] = {
            "label": definition.get("label"),
            "options": definition.get("options"),
            "multi": definition.get("multi", False),
        }
    return contract


_UNCERTAIN_EVIDENCE = re.compile(r"暂不清楚|尚不清楚|不清楚|未说明|未明确|未知|待确认|材料未提供|无法确认|不确定")


def _normalized_evidence_text(value) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def _evidence_is_grounded(evidence, source_text: str) -> bool:
    needle = _normalized_evidence_text(evidence)
    haystack = _normalized_evidence_text(source_text)
    return len(needle) >= 2 and needle in haystack


def _field_evidence_is_semantically_sufficient(key: str, field_value, evidence: str) -> bool:
    """给容易把前后向、未知和业务动作混淆的字段加最小语义闸门。"""
    if key == "payment_terms" and field_value == "standard":
        return bool(
            re.search(r"首付|预付款", evidence)
            and "到货" in evidence
            and "验收" in evidence
            and "尾款" in evidence
        )
    if key == "has_prepayment":
        return bool(
            "预付" in evidence
            and re.search(r"我方|电信", evidence)
            and re.search(r"采购|后向|供应商", evidence)
        )
    if key == "has_advance_funding":
        return "垫资" in evidence
    if key == "is_capital_investment":
        return bool(re.search(r"自投|自投资|资本投资", evidence))
    return True


def sanitize_guided_extracted_fields(value, *, source_text: str | None = None) -> dict:
    """只保留字段契约允许、且能回指用户原文的 AI 提取结果。"""
    raw = value if isinstance(value, dict) else {}
    sanitized = {}
    for key, raw_entry in raw.items():
        definition = FIELD_DEFINITIONS.get(key)
        if (
            not definition
            or definition.get("deprecated")
            or definition.get("manual_confirmation")
            or key in {"control_roles", "major_integration", "service_capability_level"}
        ):
            continue
        if source_text is not None:
            if not isinstance(raw_entry, dict) or "value" not in raw_entry:
                continue
            field_value = raw_entry.get("value")
            evidence = str(raw_entry.get("evidence") or "").strip()
            if field_value is None or not _evidence_is_grounded(evidence, source_text):
                continue
            is_unknown_value = isinstance(field_value, str) and field_value in {"uncertain", "unknown"}
            if _UNCERTAIN_EVIDENCE.search(evidence) and not is_unknown_value:
                continue
            if not _field_evidence_is_semantically_sufficient(key, field_value, evidence):
                continue
        else:
            field_value = raw_entry
            if field_value is None:
                continue
        options = definition.get("options") or []
        if options:
            if key == "project_type":
                values = field_value if isinstance(field_value, list) else [field_value]
                if values and all(item in options for item in values):
                    sanitized[key] = values
            elif field_value in options:
                sanitized[key] = field_value
            continue
        if isinstance(field_value, (str, int, float, bool, list)):
            sanitized[key] = field_value
    return sanitized


_UNIT_TYPES = {"设备", "成品软件", "施工", "服务", "标品", "其他"}
_DEVICE_TERMS = re.compile(r"设备|硬件|天线|馈线|功分器|耦合器|poi|机柜|服务器|存储|交换机", re.IGNORECASE)
_CONSTRUCTION_TERMS = re.compile(r"施工|安装|布放|布线|工程|调试|装修")


def _unit_evidence_value(evidence: dict, key: str, source_text: str) -> str:
    value = str(evidence.get(key) or "").strip() if isinstance(evidence, dict) else ""
    return value if _evidence_is_grounded(value, source_text) else ""


def _normalized_unit_amount(value, evidence: str):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not evidence:
        return None
    amount = float(value)
    if "亿元" in evidence and abs(amount) < 10_000_000:
        amount *= 100_000_000
    elif "万元" in evidence and abs(amount) < 100_000:
        amount *= 10_000
    return round(amount, 2)


def sanitize_guided_source_units(value, *, source_text: str) -> list[dict]:
    """把核算单元草稿压回可举证事实，并对设备+施工混合描述做最小拆分。"""
    raw_units = value if isinstance(value, list) else []
    sanitized: list[dict] = []
    for index, raw in enumerate(raw_units, 1):
        if not isinstance(raw, dict):
            continue
        declared_type = raw.get("declared_type")
        evidence = raw.get("evidence") if isinstance(raw.get("evidence"), dict) else {}
        type_evidence = _unit_evidence_value(evidence, "type", source_text)
        if declared_type not in _UNIT_TYPES or not type_evidence or _UNCERTAIN_EVIDENCE.search(type_evidence):
            continue

        name = str(raw.get("name") or f"{declared_type}单元{index}").strip()[:120]
        amount_evidence = _unit_evidence_value(evidence, "amount", source_text)
        amount = _normalized_unit_amount(raw.get("amount"), amount_evidence)
        tax_evidence = _unit_evidence_value(evidence, "tax_rate", source_text)
        tax_rate = str(raw.get("tax_rate"))[:30] if tax_evidence and raw.get("tax_rate") is not None else None
        gross_evidence = _unit_evidence_value(evidence, "gross", source_text)
        gross = str(raw.get("gross"))[:120] if gross_evidence and raw.get("gross") is not None else None

        logistics_evidence = _unit_evidence_value(evidence, "logistics", source_text)
        logistics = raw.get("logistics")
        if logistics not in {"self", "supplier_direct"} or not logistics_evidence or _UNCERTAIN_EVIDENCE.search(logistics_evidence):
            logistics = "unknown"

        capability_evidence = _unit_evidence_value(evidence, "capability", source_text)
        if re.search(r"无法.*(?:电信)?自维|不可自维|全部外包|供应商负责.*(?:实施|运维)", capability_evidence):
            has_self_capability = False
        elif re.search(r"可自维|电信直接运维|自有团队.*(?:执行|实施|运维)", capability_evidence):
            has_self_capability = True
        else:
            has_self_capability = "unknown"

        whitelist_evidence = _unit_evidence_value(evidence, "whitelist", source_text)
        whitelisted = raw.get("whitelisted")
        if declared_type not in {"设备", "成品软件"}:
            whitelisted = None
        elif (
            whitelisted not in {True, False}
            or not whitelist_evidence
            or "白名单" not in whitelist_evidence
            or _UNCERTAIN_EVIDENCE.search(whitelist_evidence)
        ):
            whitelisted = "unknown"

        reason = f"用户原文提到“{type_evidence[:120]}”，暂按{declared_type}拆分；业务类型和金额需人工确认。"
        unit = {
            "name": name,
            "declared_type": declared_type,
            "amount": amount,
            "tax_rate": tax_rate,
            "gross": gross,
            "logistics": logistics,
            "has_self_capability": has_self_capability,
            "whitelisted": whitelisted,
            "suggested_group": str(raw.get("suggested_group") or "").strip()[:80] or None,
            "reason": reason,
        }
        fact_blob = f"{name} {type_evidence}"
        already_split = bool(re.search(
            r"(?:^|[-_（(])(?:设备|施工)部分(?:[）)]|$)", name,
        ))
        if (
            declared_type in {"设备", "施工", "其他"}
            and not already_split
            and _DEVICE_TERMS.search(fact_blob)
            and _CONSTRUCTION_TERMS.search(fact_blob)
        ):
            group = unit["suggested_group"] or f"设备施工拆分组{index}"
            for split_type in ("设备", "施工"):
                split_unit = dict(unit)
                split_unit.update({
                    "name": f"{name}（{split_type}部分）",
                    "declared_type": split_type,
                    "amount": None,
                    "tax_rate": None,
                    "gross": None,
                    "whitelisted": "unknown" if split_type == "设备" else None,
                    "suggested_group": group,
                    "reason": (
                        f"用户原文同时提到设备与施工内容，先拆为{split_type}原始单元；"
                        "分项业务类型和金额需人工确认。"
                    ),
                })
                sanitized.append(split_unit)
        else:
            sanitized.append(unit)

    existing_types = {unit.get("declared_type") for unit in sanitized}
    source_sentences = [
        sentence.strip() for sentence in re.split(r"[。！？\n]+", source_text or "") if sentence.strip()
    ]
    mixed_evidence = next((
        sentence for sentence in source_sentences
        if _DEVICE_TERMS.search(sentence) and _CONSTRUCTION_TERMS.search(sentence)
    ), "")
    if mixed_evidence:
        group = "设备施工待拆组"
        for split_type in ("设备", "施工"):
            if split_type in existing_types:
                continue
            sanitized.append({
                "name": f"{split_type}部分（待确认）",
                "declared_type": split_type,
                "amount": None,
                "tax_rate": None,
                "gross": None,
                "logistics": "unknown",
                "has_self_capability": "unknown",
                "whitelisted": "unknown" if split_type == "设备" else None,
                "suggested_group": group,
                "reason": (
                    f"用户原文同时提到设备与施工：“{mixed_evidence[:100]}”；"
                    f"先补充{split_type}占位单元，分项类型和金额需人工确认。"
                ),
            })
            existing_types.add(split_type)

    lot_pattern = re.compile(
        r"([\u4e00-\u9fa5A-Za-z0-9_-]{2,12}标段)\s*(?:约|为|：|:)?\s*(\d+(?:\.\d+)?)\s*万"
    )
    existing_names = [str(unit.get("name") or "") for unit in sanitized]
    for lot_name, amount_text in lot_pattern.findall(source_text or ""):
        if lot_name in {"每个标段", "两个标段", "各个标段"}:
            continue
        if any(lot_name in name for name in existing_names):
            continue
        sanitized.append({
            "name": f"{lot_name}（待拆分）",
            "declared_type": "其他",
            "amount": round(float(amount_text) * 10000, 2),
            "tax_rate": None,
            "gross": None,
            "logistics": "unknown",
            "has_self_capability": "unknown",
            "whitelisted": None,
            "suggested_group": None,
            "reason": f"用户给出{lot_name}总额，但内部构成尚未拆清；先保留整块业务并由用户确认。",
        })
        existing_names.append(lot_name)
    return sanitized


def _guided_source_text(guided_input: dict, messages: list[dict]) -> str:
    chunks = [
        str(item.get("text") or "")
        for item in (guided_input.get("sections") or {}).values()
        if isinstance(item, dict) and item.get("text")
    ]
    chunks.extend(
        str(message.get("content") or "")
        for message in messages
        if message.get("role") == "user"
    )
    return "\n".join(chunks)


_UNKNOWN_FIELD_PATTERNS = {
    "bpm_id": re.compile(r"BPM", re.IGNORECASE),
    "supplier_confirmed": re.compile(r"后向供应商|供应商是否.*确定"),
    "procurement_method": re.compile(r"后向采购方式|供应商.*采购方式"),
    "related_party": re.compile(r"关联关系|三方关联"),
    "has_prepayment": re.compile(r"我方.*预付|后向.*预付|采购.*预付"),
    "has_advance_funding": re.compile(r"垫资"),
    "acceptance_content_same": re.compile(r"验收报告.*编制|供应商材料.*整理|验收材料.*整理"),
}
_UNKNOWN_STATEMENT = re.compile(r"暂不清楚|尚不清楚|不清楚|未说明|未明确|未知|待确认|未提供|尚未提供|无法确认|不确定")


def infer_acknowledged_unknown_fields(source_text: str) -> list[str]:
    """识别用户已明确承认未知的简单表单事实，后续不再重复追问。"""
    found: list[str] = []
    for sentence in re.split(r"[。！？\n]+", source_text or ""):
        if not _UNKNOWN_STATEMENT.search(sentence):
            continue
        for key, pattern in _UNKNOWN_FIELD_PATTERNS.items():
            if pattern.search(sentence) and key not in found:
                found.append(key)
    return found


def _margin_bucket(percent: float) -> str:
    if percent <= 0:
        return "lte_0"
    if percent <= 3:
        return "lte_3"
    if percent < 4:
        return "pct_3_4"
    if percent < 5:
        return "pct_4_5"
    if percent < 6:
        return "pct_5_6"
    if percent <= 10:
        return "pct_6_10"
    return "gt_10"


def derive_safe_guided_fields(source_text: str) -> dict:
    """对少量高确定性事实做服务端兜底，弥补模型偶发漏提。"""
    derived: dict = {}
    sentences = [
        sentence.strip() for sentence in re.split(r"[。！？\n]+", source_text or "") if sentence.strip()
    ]
    for sentence in sentences:
        if (
            re.search(r"服务|ICT成本", sentence, re.IGNORECASE)
            and "利润率" in sentence
            and not re.search(r"全项目|项目整体|整体利润率", sentence)
        ):
            match = re.search(r"利润率(?:约为|约|为)?\s*(\d+(?:\.\d+)?)\s*%", sentence)
            if match:
                derived["gross_margin"] = _margin_bucket(float(match.group(1)))
                break

    payment_sentence = next((
        sentence for sentence in sentences
        if re.search(r"前向付款|付款方式", sentence) and re.search(r"进度款|分期|质保金|按年|每月", sentence)
    ), "")
    if payment_sentence and not (
        re.search(r"首付|预付款", payment_sentence)
        and "到货" in payment_sentence
        and "验收" in payment_sentence
        and "尾款" in payment_sentence
    ):
        derived["payment_terms"] = "other"

    positive_delivery = any(
        re.search(r"可自维部分|电信直接运维|电信自维|自有团队.*(?:执行|实施|运维)", sentence)
        and not re.search(r"无法|不可自维", sentence)
        for sentence in sentences
    )
    external_delivery = bool(re.search(
        r"无法.*(?:电信)?自维|不可自维部分|合作方代维|采用合作方代维|合作方负责.*(?:运维|实施|施工)|供应商负责.*(?:现场施工|运维|维保)",
        source_text or "",
    ))
    if positive_delivery and external_delivery:
        derived["service_delivery_mode"] = "mixed"
    elif external_delivery:
        derived["service_delivery_mode"] = "all_external"
    if re.search(r"BPM[^。；\n]{0,20}(?:未提供|暂未提供|不清楚|未知)", source_text or "", re.IGNORECASE):
        derived["contract_matches_bpm"] = "uncertain"
    return derived


def augment_project_types_from_units(fields: dict, source_units: list[dict]) -> bool:
    """用已举证的单元组成补足多选项目类型，不覆盖用户已有类型。"""
    types = fields.get("project_type")
    types = list(types) if isinstance(types, list) else ([types] if isinstance(types, str) else [])
    unit_types = {
        unit.get("declared_type") for unit in source_units if isinstance(unit, dict)
    }
    changed = False
    if "服务" in unit_types and (unit_types & {"设备", "成品软件", "施工"}):
        for project_type in ("system_integration", "service"):
            if project_type not in types:
                types.append(project_type)
                changed = True
    elif unit_types == {"设备"} and "equipment_sales" not in types:
        types.append("equipment_sales")
        changed = True
    if changed:
        fields["project_type"] = types
    return changed


def _guided_unit_identity(unit: dict) -> str:
    name = str(unit.get("name") or "").strip().lower()
    name = re.sub(r"(?:[-_（(])(?:设备|施工)部分(?:[）)]|$)", "", name)
    name = re.sub(r"\s+", "", name)
    return f"{unit.get('declared_type') or ''}|{name}"


def merge_guided_source_units(previous: list[dict], incoming: list[dict]) -> list[dict]:
    """按业务名+类型合并跨轮草稿，容忍“（设备部分）/-设备部分”等表述变化。"""
    merged: list[dict] = []
    index_by_identity: dict[str, int] = {}
    for unit in previous:
        if not isinstance(unit, dict):
            continue
        identity = _guided_unit_identity(unit)
        if identity in index_by_identity:
            continue
        index_by_identity[identity] = len(merged)
        merged.append(unit)
    for unit in incoming:
        if not isinstance(unit, dict):
            continue
        identity = _guided_unit_identity(unit)
        if identity in index_by_identity:
            merged[index_by_identity[identity]] = unit
        else:
            index_by_identity[identity] = len(merged)
            merged.append(unit)
    return merged


async def analyze_guided_intake(
    guided_input: dict,
    messages: list[dict],
    current_fields: dict,
    *,
    known_coverage: dict | None = None,
    known_source_units: list[dict] | None = None,
) -> dict:
    """分析六块项目说明并规划下一轮追问；不运行任何诊断规则。"""
    context = {
        "section_definitions": {
            key: {"title": value["title"], "prompt": value["prompt"]}
            for key, value in SECTION_DEFINITIONS.items()
        },
        "guided_input": guided_input,
        "known_fields": current_fields,
        "known_coverage": known_coverage or {},
        "known_source_units": known_source_units or [],
        "field_contract": _guided_field_contract(),
        "conversation": clip_messages_for_api([
            message for message in messages
            if message.get("role") == "user"
            and not str(message.get("content") or "").startswith("【六块引导式项目说明】")
        ], max_chars=8000),
    }
    api_messages = [
        {"role": "system", "content": GUIDED_INTAKE_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
    ]
    content, finish_reason, error = await _call_deepseek_messages(
        api_messages, max_tokens=7000, json_output=True,
    )
    if error:
        return {
            "sections": {},
            "extracted": {},
            "source_units": [],
            "blocking_topics": ["AI 暂时无法完成覆盖评估"],
            "simple_fact_gaps": [],
            "contradictions": [],
            "follow_up_questions": [],
            "error": error,
        }

    data = _parse_any_json_object(content)
    questions = data.get("follow_up_questions")
    if not isinstance(questions, list):
        questions = []
    source_units = data.get("source_units")
    if not isinstance(source_units, list):
        source_units = []
    source_text = _guided_source_text(guided_input, messages)
    extracted = sanitize_guided_extracted_fields(data.get("extracted"), source_text=source_text)
    for key, field_value in derive_safe_guided_fields(source_text).items():
        extracted.setdefault(key, field_value)
    result = {
        "sections": data.get("sections") if isinstance(data.get("sections"), dict) else {},
        "extracted": extracted,
        "source_units": sanitize_guided_source_units(source_units, source_text=source_text),
        "acknowledged_unknown_fields": infer_acknowledged_unknown_fields(source_text),
        "blocking_topics": data.get("blocking_topics") if isinstance(data.get("blocking_topics"), list) else [],
        "simple_fact_gaps": data.get("simple_fact_gaps") if isinstance(data.get("simple_fact_gaps"), list) else [],
        "contradictions": data.get("contradictions") if isinstance(data.get("contradictions"), list) else [],
        "follow_up_questions": questions[:5],
        "error": None,
    }
    if finish_reason == "length":
        result["error"] = "AI 输出达到长度上限，请缩短单块描述后重试。"
        result["extracted"] = {}
        result["source_units"] = []
    # 契约完整性由 guided_intake.normalize_coverage / evaluate_readiness 再校验。
    return result


# ── 核算单元切分（#7，见 docs/adr/0002）──
UNIT_SEGMENT_PROMPT = """你是电信 ICT 项目财务核算助手。请先把项目描述切分成最小的原始业务单元，并给出可能需要组合判断的草稿建议。最终分类和组合关系由用户确认。

对每个核算单元输出字段：
- name: 单元名称
- declared_type: 申报业务类型，取值之一：设备 | 成品软件 | 施工 | 服务 | 标品 | 其他
- amount: 收入金额（数字，单位元；不确定填 null）
- tax_rate: 税率（字符串如 "13%"/"6%"；不确定 null）
- gross: 毛利额或毛利率（字符串描述；不确定 null）
- logistics: 物流是否电信主控，取值：self | supplier_direct | unknown
- has_self_capability: 是否融入电信自有能力，取值：true | false | unknown
- whitelisted: 是否属于集团白名单（仅设备/成品软件有意义），取值：true | false | unknown
- suggested_group: 若多个原始单元可能构成同一组合产出，填写相同的简短候选组名；明显分别交付或拿不准时填 null
- reason: declared_type / whitelisted 的简短理由

规则：
- 标品专指电信自有产品，例如电话、宽带、天翼云；标品固定全额，不判断白名单，也不参与组合。
- 成品软件指 Oracle、Windows 等可独立交付的成品授权软件。declared_type=设备/成品软件 时才判 whitelisted；施工、服务、标品均填 null。
  白名单大类：硬件=计算存储/网络/安全/无线/终端/AI机器人/机房配套/低空经济；软件=基础/通用/行业/安全软件（成品授权）。
  室分/综合布线/弱电/LED屏/机房装修=施工本质，whitelisted=false。拿不准填 "unknown"（系统保守按非白名单处理）。
- 按业务实质分类，不要只靠关键词。例如客户交付的服务器/存储通常是设备；布线、安装、弱电施工通常是施工；电信自投资设备打包另由项目事实进入资本投资提示。
- 不要输出 listed 字段。列收意图由用户在组合关系确认后，对最终核算单元逐一确认。
宁可把不确定的值填 null，也不要编造。只输出一个 JSON 数组，不要任何解释文字。"""


async def segment_accounting_units(messages: list[dict]) -> list[dict]:
    """把对话切分成核算单元草稿（AI 生成，供用户确认）。失败返回空列表。"""
    if not (DEEPSEEK_API_KEY or "").strip():
        return []

    convo = "\n\n".join(
        (m.get("content") or "") for m in messages if m.get("role") == "user"
    ).strip()
    if not convo:
        return []

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": UNIT_SEGMENT_PROMPT},
            {"role": "user", "content": convo},
        ],
        "temperature": 0.2,
        "max_tokens": 3000,
    }
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    timeout = httpx.Timeout(connect=30.0, read=120.0, write=120.0, pool=30.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(DEEPSEEK_MAX_RETRIES):
                try:
                    resp = await client.post(DEEPSEEK_URL, headers=headers, json=payload)
                    resp.raise_for_status()
                    break
                except (httpx.HTTPStatusError, httpx.RequestError):
                    if attempt < DEEPSEEK_MAX_RETRIES - 1:
                        await asyncio.sleep(1.5 * (2**attempt))
                        continue
                    return []
        content = (resp.json()["choices"][0].get("message") or {}).get("content") or ""
        m = re.search(r"\[[\s\S]*\]", content)
        if not m:
            return []
        units = json.loads(m.group(0))
        return units if isinstance(units, list) else []
    except Exception:
        return []
