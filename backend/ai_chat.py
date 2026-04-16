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
    "customer_type": {
        "label": "前向客户类型",
        "required": True,
        "applies_to": "all",
        "options": ["state_owned", "private", "institution", "other"],
        "options_label": ["国企", "民企", "事业单位", "其他"]
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
    "related_party": {
        "label": "前后向是否存在关联关系",
        "required": True,
        "applies_to": "all",
        "options": ["yes", "no", "uncertain"],
        "options_label": ["是", "否", "不确定"]
    },
    "gross_margin": {
        "label": "毛利率估算",
        "required": True,
        "applies_to": "all",
        "options": ["lte_0", "lte_3", "pct_4_5", "pct_6_10", "gt_10"],
        "options_label": ["≤0%", "1%-3%", "4%-5%", "6%-10%", "10%以上"]
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
- customer_type: "state_owned"（国企）| "private"（民企）| "institution"（事业单位）| "other"
- supplier_confirmed: true | false
- procurement_method: 电信对实施方/供应商的后向采购。"open_bid"（公开招标）| "sole_source"（单一来源）| "comparison"（比选）| "collective"（集采）
- related_party: "yes" | "no" | "uncertain"
- gross_margin: "lte_0"（≤0%）| "lte_3"（1-3%）| "pct_4_5"（4-5%）| "pct_6_10"（6-10%）| "gt_10"（10%以上）
- revenue_recognition: "point_in_time"（时点法）| "over_time"（时段法）| "mixed" | "uncertain"
- is_end_user: true | false
- has_telecom_capability: "yes" | "no" | "partial"
- capability_ratio: "all_external"（全外采）| "very_low"（极低）| "medium"（中等）| "high"（较高）
- contract_content_same: "yes" | "no" | "uncertain"
- project_location: "local"（本地）| "remote_with_capability"（异地有实施能力）| "remote_without_capability"（异地无实施能力）
- scheme_reviewed: "yes" | "no" | "planned"
- hardware_construction: true | false
- logistics_control: "telecom_controlled" | "supplier_direct"
- service_period: "lte_3m" | "3m_12m" | "gt_12m"
- has_prepayment: true | false
- has_advance_funding: true | false
- service_delivery_mode: "all_telecom"（全部自有团队）| "mixed"（混合（自有+外包））| "all_external"（全部外包/供应商执行）。仅 service 类型必填。（勿输出 service_capability_level，该等级由系统根据本字段推导）
- bpm_id: 字符串。测试阶段可为任意占位编号；正式环境建议与 BPM 一致（如 BPM2024XXXXX）

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
