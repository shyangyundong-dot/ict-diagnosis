# ============================================================
# ai_chat.py 字段补丁 — v1.3（服务类交付模式单字段）
# 插入位置：FIELD_DEFINITIONS 字典末尾，has_advance_funding 之后，字典闭合 } 之前
# 说明：六必要等级（service_capability_level）与「招标前实质确定」已改为系统推导/下线，勿再插入。
# ============================================================

    # 服务类专属：交付模式三档（与规则 R31/R32/R34 的 service_delivery_mode 对齐）
    "service_delivery_mode": {
        "label": "服务交付是否由电信自有团队执行",
        "required": True,
        "applies_to": ["service"],
        "options": ["all_telecom", "mixed", "all_external"],
        "options_label": ["全部自有团队", "混合（自有+外包）", "全部外包/供应商执行"],
        "hint": "判断电信在交付中的实际角色——影响主要责任人/代理人认定；「六必要」能力等级由系统依据本项自动推导"
    },
