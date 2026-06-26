import json
import os
import re

# 加载规则库和条款原文库
_RULES_PATH = os.path.join(os.path.dirname(__file__), "rules.json")
_CLAUSES_PATH = os.path.join(os.path.dirname(__file__), "clauses.json")
_WHITELIST_PATH = os.path.join(os.path.dirname(__file__), "whitelist.json")

with open(_RULES_PATH, encoding="utf-8") as f:
    _RULES_DATA = json.load(f)

with open(_CLAUSES_PATH, encoding="utf-8") as f:
    _CLAUSES_DATA = json.load(f)

with open(_WHITELIST_PATH, encoding="utf-8") as f:
    _WHITELIST_DATA = json.load(f)

RULES = _RULES_DATA["rules"]
CLAUSES = _CLAUSES_DATA["clauses"]
RULE_VERSION = _RULES_DATA.get("version", "v1.0")
WHITELIST_VERSION = _WHITELIST_DATA.get("version", "v1.0")

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
    返回 dict（status / level / message / missing）；R09 防撞置 None 在 run_diagnosis 内处理。
    举证式：资格不成立给 high + 举证路，不自动定性。high 仅在已填角色时落。
    """
    # AI 偶尔把数组误输出成字符串（如 "6,7,9"）——按分隔符拆开，绝不能逐字符迭代
    # （否则 "10"/"13" 等两位编号永远拆不出，给用户展示错误的缺失清单）
    if isinstance(control_roles, str):
        control_roles = [p for p in re.split(r"[,;/\s、，；]+", control_roles) if p]
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


def classify_listing_mode(type_set, fields: dict, units: list | None, control_status: str | None) -> dict:
    """27 号文列收模式级联分类（见 docs/adr/0004）。

    就地把合格全额单元的 `listed` 置 True（派生输出），返回 listing 结论 dict：
      mode/mode_label/full_listing/basis/ratios/gates/blockers/softs/unit_decisions/margin_ok。
    control_status: assess_control_roles 的 status（"eligible"=控制权成立，是所有全额模式的总闸门）。
    """
    units = units or []
    amt = {"设备": 0.0, "施工": 0.0, "服务": 0.0, "标品": 0.0, "其他": 0.0}
    amount_incomplete = False
    for u in units:
        t = u.get("declared_type")
        if u.get("amount") in (None, ""):
            amount_incomplete = True
        amt[t if t in amt else "其他"] += _unit_amount(u)

    total = sum(amt.values())
    hw_constr = amt["设备"] + amt["施工"]                 # 服务整合分子（含集成施工）
    hw_goods = amt["设备"] + amt["标品"]                  # 软硬件（白名单口径）
    single_denom = amt["设备"] + amt["标品"] + amt["服务"]  # 单一履约场景一分母（施工排除）

    has_hardware = any(u.get("declared_type") in _HW_UNIT_TYPES for u in units) or fields.get("hardware_construction") is True
    has_goods_unit = any(u.get("declared_type") in _WL_UNIT_TYPES for u in units)
    control_ok = control_status == "eligible"
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
    if not control_ok:
        blockers.append("控制权资格未成立/未自证（19 角色矩阵），全额列收总闸门未过")

    # 占比（派生比值，不破脱敏边界）
    ratio_si = (hw_constr / total) if total > 0 else None
    ratio_sf = (hw_goods / single_denom) if single_denom > 0 else None

    # ── 实质路由 ──
    # 纯服务/无硬件无标品 → 常规 ICT，本分类器不主导（列收按服务侧常规规则）
    if not has_hardware and not has_goods_unit:
        return {
            "mode": "regular", "mode_label": _MODE_LABEL["regular"],
            "full_listing": True, "basis": "项目无硬件/标品，按常规 ICT 服务列收，硬件列收模式不适用",
            "ratios": {}, "gates": [], "blockers": [], "softs": softs,
            "unit_decisions": [], "margin_ok": True,
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
        basis = "控制权资格未成立/未自证，全额总闸门未过 → 全部硬件落净额兜底"

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
    # hardware_construction 字段定义为 bool（options: [True, False]），不是 "yes"/"no" 字符串
    _has_hardware = (fields.get("hardware_construction") is True) or any(
        u.get("declared_type") in _HW_UNIT_TYPES for u in (accounting_units or [])
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

    # 列收模式分类（27 号文重构，见 docs/adr/0004）——控制权是所有全额模式的总闸门。
    # control_roles_check 被 R09 置 None 时控制权实为不成立，按非 eligible 传入。
    _control_status = control_roles_check["status"] if control_roles_check else ("ineligible" if _r09_fired else None)
    listing_mode = classify_listing_mode(type_set, fields, accounting_units, _control_status)

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
        "listing_mode": listing_mode,
        "rule_version": RULE_VERSION,
    }

