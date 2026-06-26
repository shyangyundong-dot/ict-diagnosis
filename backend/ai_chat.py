import asyncio
import json
import os
import re
import httpx
from dotenv import load_dotenv

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
        "label": "控制权关键角色（电信占据哪些）",
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
        "hint": "总额法资格自查（见 docs/adr/0003）：勾选电信在本项目实际占据的关键主导/决策/责任角色（非配合）。判定=必选6/7/9（涉硬件加16）+ 方案{3|4}/交付实施{10|11}/实施开发{13|14}各占一个。多为售中/执行信息，对话常缺，通常需手动确认。",
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
        "hint": "判断电信在交付中的实际角色——影响主要责任人/代理人认定；「六必要」能力等级由系统依据本项自动推导"
    },
    # 系统依据 service_delivery_mode 推导入库；展示层需 label/options 以便前端与溯源页显示中文
    "service_capability_level": {
        "label": "电信自有服务能力等级（六必要，系统依据交付模式推导）",
        "required": False,
        "applies_to": ["service"],
        "options": ["strong", "medium", "weak", "none"],
        "options_label": [
            "强（N1-N6全部具备，有充分留痕）",
            "中（N1-N6部分具备，部分需补充）",
            "弱（仅具备1-3项，难以全额列收）",
            "无（无法举证任何六必要能力）",
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
    """已下线手填项：与 supplier_confirmed 语义重复、或改由系统推导。"""
    fields.pop("supplier_confirmed_early", None)
    fields.pop("service_capability_level", None)


_SERVICE_CAPABILITY_BY_DELIVERY = {
    "all_telecom": "strong",
    "mixed": "medium",
    "all_external": "none",
}


def apply_derived_fields_for_diagnosis(fields: dict) -> None:
    """
    提交诊断入库前：写入系统推导字段。
    六必要等级仅依据服务交付模式（与规则 R31/R32/R34 所依据维度一致），不再手填。
    """
    migrate_legacy_service_fields(fields)
    fields.pop("supplier_confirmed_early", None)
    types = project_types_from_fields(fields) or []
    if "service" in types:
        mode = fields.get("service_delivery_mode")
        derived = _SERVICE_CAPABILITY_BY_DELIVERY.get(mode)
        if derived is not None:
            fields["service_capability_level"] = derived
    else:
        fields.pop("service_capability_level", None)


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
- gross_margin: "lte_0"（≤0%）| "lte_3"（1-3%）| "pct_3_4"（3-4%）| "pct_4_5"（4-5%）| "pct_5_6"（5-6%）| "pct_6_10"（6-10%）| "gt_10"（10%以上）。**只取应列收（服务）侧的毛利**：设备/施工单元铁律不列收、其毛利与列收判断无关，绝不要把设备/施工的毛利混算或拖低进这个值。若项目含多块服务，取在问列收的那块服务的毛利（多服务单元的精确逐块判断是已知缺口，暂取主服务块）。
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
- service_delivery_mode: "all_telecom"（全部自有团队）| "mixed"（混合（自有+外包））| "all_external"（全部外包/供应商执行）。仅 service 类型必填。（勿输出 service_capability_level，该等级由系统根据本字段推导）
- bpm_id: 字符串。测试阶段可为任意占位编号；正式环境建议与 BPM 一致（如 BPM2024XXXXX）
- control_roles: **数组**，电信在本项目占据的关键角色编号（字符串）。取值：
  - 必选区："6"（应标与签约统筹）| "7"（软硬件采购决策）| "9"（全流程交付管理与质量责任）| "16"（到货验收及设备管理，涉硬件时）
  - 方案二选一："3"（解决方案设计者）| "4"（解决方案整合确定者）
  - 交付实施方案二选一："10"（交付实施方案设计者）| "11"（交付实施方案确定及责任者）
  - 实施开发二选一："13"（项目实施/技术开发/联调实施者）| "14"（项目实施/技术开发主导与联调实操责任者）
  提取规则：**只抽取用户明确说出的角色**，不要从"自有能力"/"主要责任人"等抽象描述推断。
  示例：用户说"电信主导方案设计、自主采购、负责全流程交付管理" → ["3","7","9"]；用户说"电信自主投标签约、设备由电信负责验收" → ["6","16"]；用户只说项目金额/客户/范围/毛利 → **不输出该字段**（让用户自己手填，绝不臆测）。

### 27 号文列收模式字段（全额资格判定，见 docs/adr/0004）——均非必填，**只抽用户明确说出的，拿不准就不输出，让用户手填**：
- overall_margin: 项目**整体**税前利润率（**含硬件**，区别于服务侧 gross_margin）。同一套分桶："lte_0"|"lte_3"|"pct_3_4"|"pct_4_5"|"pct_5_6"|"pct_6_10"|"gt_10"。喂列收模式门槛（服务整合≥10%/单一履约≥5%）。用户明确说整体利润率才抽。
- major_integration: 是否**重大整合（单一组合产出）**。"yes"（硬件与服务深度耦合、电信做了重大定制/修改、交付一个功能完整的单一系统）| "no"（分别提供商品+服务）| "uncertain"。**只在用户明确说"深度定制/重大修改/系统级集成"才抽 yes**，笼统的"提供了集成服务"**不算**、不要臆测。
- payment_terms: 前向付款节点。"standard"（首付款+到货验收尾款）| "other"（分期/账期等）。明确说付款方式才抽。
- ownership_transfer: 硬件产权是否验收后转移客户。"yes" | "no" | "uncertain"。
- collective_procurement_ratio: 后向集采比例。"gte_60"（≥60%）| "lt_60"（<60%）| "unknown"。
- is_capital_investment: 是否电信自投资设备打包（资本投资模式）。true | false。明确说"电信自投资/资本投资"才抽 true。

## 重要规则
- is_complete只有在所有必填字段（根据project_type**数组**所覆盖类型的并集）都已收集完毕时才设为true
- 追问要有温度，要体现你理解业务，不是机械地问清单
- 如果用户表达的信息和某个选项不完全匹配，选最接近的，但在next_question里请用户确认
- bpm_id如果用户没提，要问；如果用户说"还没有"，可记为"待录入"等占位
- **每次回复在 JSON 代码块之外，必须写至少 1～2 句自然语言**（小结或追问），不要只输出 JSON，否则用户界面会显示空白。
"""


async def chat_with_ai(messages: list[dict], current_fields: dict, project_type: str = None) -> dict:
    """
    与DeepSeek进行一轮对话，返回AI回复和提取的字段
    """
    if not (DEEPSEEK_API_KEY or "").strip():
        return {
            "reply": "（系统未配置 DEEPSEEK_API_KEY，无法调用大模型。请在 backend 目录的 .env 中设置 DEEPSEEK_API_KEY 后重启后端。）",
            "extracted": {},
            "missing_required": [],
            "next_question": "",
            "is_complete": False,
        }

    # 构建系统上下文
    context_msg = f"""
当前已收集到的字段：
{json.dumps(current_fields, ensure_ascii=False, indent=2)}

项目类型：{project_type or "未确定"}

请根据对话历史，提取新信息并判断下一步要问什么。
"""

    # 构建消息列表（截断过长单条，避免第二轮超长输入导致超时或空输出）
    clipped = clip_messages_for_api(messages)
    api_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": context_msg},
    ] + clipped

    timeout = httpx.Timeout(connect=30.0, read=120.0, write=120.0, pool=30.0)
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": api_messages,
        "temperature": 0.3,
        "max_tokens": 4096,
    }
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
                return {
                    "reply": f"（调用 DeepSeek 失败：HTTP {code}，请检查 DEEPSEEK_API_KEY 是否有效、网络是否正常。）",
                    "extracted": {},
                    "missing_required": [],
                    "next_question": "",
                    "is_complete": False,
                }
            except httpx.RequestError as e:
                last_error = e
                if attempt < DEEPSEEK_MAX_RETRIES - 1:
                    await asyncio.sleep(1.5 * (2**attempt))
                    continue
                return {
                    "reply": f"（调用 AI 网络异常（已重试 {DEEPSEEK_MAX_RETRIES} 次）：{e!s}）",
                    "extracted": {},
                    "missing_required": [],
                    "next_question": "",
                    "is_complete": False,
                }
            except Exception as e:
                return {
                    "reply": f"（调用 AI 时出错：{e!s}）",
                    "extracted": {},
                    "missing_required": [],
                    "next_question": "",
                    "is_complete": False,
                }

    if data is None:
        msg = f"{last_error!s}" if last_error else "未知错误"
        return {
            "reply": f"（调用 AI 失败：{msg}）",
            "extracted": {},
            "missing_required": [],
            "next_question": "",
            "is_complete": False,
        }

    choice = data["choices"][0]
    content = (choice.get("message") or {}).get("content") or ""
    finish_reason = choice.get("finish_reason") or ""

    extracted_data = parse_json_payload_from_ai(content)

    # 清理回复文本（去掉 JSON 代码块，只保留自然语言部分）
    clean_content = re.sub(r"```(?:json)?\s*[\s\S]*?```", "", content, flags=re.IGNORECASE).strip()
    reply_text = build_reply_text(clean_content, extracted_data)
    if finish_reason == "length":
        reply_text += "（模型输出已达长度上限，若 JSON 不完整请缩短描述后重试。）"

    return {
        "reply": reply_text,
        "extracted": extracted_data.get("extracted", {}),
        "missing_required": extracted_data.get("missing_required", []),
        "next_question": extracted_data.get("next_question", ""),
        "is_complete": extracted_data.get("is_complete", False),
    }


# ── 核算单元切分（#7，见 docs/adr/0002）──
UNIT_SEGMENT_PROMPT = """你是电信 ICT 项目财务核算助手。请把下面这段项目描述切分成「核算单元」——一笔合同里被分别核算的最小业务块。

对每个核算单元输出字段：
- name: 单元名称
- declared_type: 申报业务类型，取值之一：设备 | 施工 | 服务 | 标品 | 其他
- amount: 收入金额（数字，单位元；不确定填 null）
- tax_rate: 税率（字符串如 "13%"/"6%"；不确定 null）
- gross: 毛利额或毛利率（字符串描述；不确定 null）
- logistics: 物流是否电信主控，取值：self | supplier_direct | unknown
- has_self_capability: 是否融入电信自有能力，取值：true | false | unknown
- whitelisted: 是否属于集团白名单标准化硬件/成品软件（仅设备/标品有意义），取值：true | false | unknown
- reason: declared_type / whitelisted 的简短理由

规则：
- declared_type=设备/标品 时才判 whitelisted；施工恒非白名单(false)、服务不适用(填 null)。
  白名单大类：硬件=计算存储/网络/安全/无线/终端/AI机器人/机房配套/低空经济；软件=基础/通用/行业/安全软件（成品授权）。
  室分/综合布线/弱电/LED屏/机房装修=施工本质，whitelisted=false。拿不准填 "unknown"（系统保守按非白名单处理）。
- 不要输出 listed 字段——是否列收由系统按 27 号文列收模式（控制权+门槛+白名单）算出，不是你判定的。
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
