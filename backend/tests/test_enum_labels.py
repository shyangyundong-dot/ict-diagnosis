"""枚举映射完整性：ai_chat 给 AI 的每个字符串枚举，ai_report 都要有中文标签。

防回归：缺标签会让报告里漏出英文 key（如 government / pct_3_4 / pct_5_6 曾漏）。
"""

import ai_chat
import ai_report


def test_every_chat_enum_has_report_label():
    defs = ai_chat.FIELD_DEFINITIONS
    value_labels = ai_report.FIELD_VALUE_LABELS

    drift = []
    for field, spec in defs.items():
        str_opts = [o for o in spec.get("options", []) if isinstance(o, str)]
        if not str_opts:
            continue  # 纯布尔/数值字段无需值标签
        fmap = value_labels.get(field)
        if fmap is None:
            drift.append(f"{field}: 整个字段缺值标签映射")
            continue
        for opt in str_opts:
            if opt not in fmap:
                drift.append(f"{field}.{opt} 缺中文标签")

    assert not drift, "枚举映射漂移：\n" + "\n".join(drift)


def test_known_previously_missing_values_present():
    """显式锁定曾漏掉的三个值，作为人读的回归说明。"""
    vl = ai_report.FIELD_VALUE_LABELS
    assert vl["customer_type"].get("government")
    assert vl["gross_margin"].get("pct_3_4")
    assert vl["gross_margin"].get("pct_5_6")
