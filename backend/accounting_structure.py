"""Accounting-unit structure v2.

The persisted JSON keeps source business blocks, candidate combination groups and
unit-level listing self-checks in one versioned envelope.  Old diagnosis records
remain plain lists and are deliberately not rewritten.
"""

from __future__ import annotations

import copy
import re


SCHEMA_VERSION = 2
SOURCE_TYPES = ("设备", "成品软件", "施工", "服务", "标品", "其他")
STANDARD_PRODUCT_TYPE = "标品"
WHITELIST_TYPES = {"设备", "成品软件"}
PO_KEYS = ("po1_independent_benefit", "po2_significant_integration", "po3_modification", "po4_interdependence")
SIX_DIMENSIONS = (
    "customer_insight",
    "solution_control",
    "bid_autonomy",
    "procurement_autonomy",
    "project_management",
    "operations_autonomy",
)
SIX_VALUES = {"in_place", "not_in_place", "pending_evidence", "not_applicable"}
R08_KEYS = ("ctrl1_control_before_transfer", "ctrl2_primary_responsibility", "ctrl3_inventory_delivery_risk", "ctrl4_pricing_autonomy")
R08_VALUES = {"yes", "no", "pending_evidence"}


def _slug(value, fallback: str) -> str:
    text = re.sub(r"[^0-9A-Za-z_-]+", "-", str(value or "").strip()).strip("-")
    return text or fallback


def _unique_id(raw, prefix: str, index: int, used: set[str]) -> str:
    base = _slug(raw, f"{prefix}-{index}")
    candidate = base
    serial = 2
    while candidate in used:
        candidate = f"{base}-{serial}"
        serial += 1
    used.add(candidate)
    return candidate


def _normalize_source(unit: dict, index: int, used: set[str]) -> dict:
    source = copy.deepcopy(unit) if isinstance(unit, dict) else {}
    source["id"] = _unique_id(source.get("id"), "src", index, used)
    if source.get("declared_type") not in SOURCE_TYPES:
        source["declared_type"] = "其他"
    if source["declared_type"] == STANDARD_PRODUCT_TYPE:
        source["whitelisted"] = None
    elif source["declared_type"] not in WHITELIST_TYPES:
        source["whitelisted"] = None
    elif source.get("whitelisted") not in (True, False, "unknown"):
        source["whitelisted"] = "unknown"
    source.pop("listed", None)
    return source


def _empty_decision(source_type: str | None = None) -> dict:
    standard = source_type == STANDARD_PRODUCT_TYPE
    return {
        "listing_intent": "full" if standard else None,
        "listing_intent_confirmed": standard,
        "six_daowei": {
            "facts_confirmed": False,
            "dimensions": {},
            "level": None,
            "confirmation_status": "confirmed" if standard else "draft",
            "no_external_procurement": False,
            "no_operations_obligation": False,
        },
        "r08": {
            "answers": {},
            "conclusion": None,
            "confirmation_status": "confirmed" if standard else "draft",
        },
    }


def relationship_suggestion(po_facts: dict | None) -> str | None:
    facts = po_facts or {}
    if any(facts.get(key) not in ("yes", "no") for key in PO_KEYS):
        return None
    if facts[PO_KEYS[0]] == "yes" and all(facts[key] == "no" for key in PO_KEYS[1:]):
        return "separate"
    return "combined"


def structure_from_units(units: list | None) -> dict:
    """Promote AI/legacy flat units into an editable v2 session draft."""
    used: set[str] = set()
    sources = [_normalize_source(unit, i + 1, used) for i, unit in enumerate(units or [])]

    suggested: dict[str, list[str]] = {}
    for source in sources:
        key = str(source.get("suggested_group") or "").strip()
        if key and source["declared_type"] != STANDARD_PRODUCT_TYPE:
            suggested.setdefault(key, []).append(source["id"])

    groups = []
    group_ids: set[str] = set()
    for index, (name, source_ids) in enumerate(suggested.items(), start=1):
        if len(source_ids) < 2:
            continue
        groups.append({
            "id": _unique_id(None, "grp", index, group_ids),
            "name": name,
            "source_unit_ids": source_ids,
            "po_facts": {key: None for key in PO_KEYS},
            "relationship_suggestion": "combined",
            "confirmed_relationship": None,
        })

    structure = {
        "schema_version": SCHEMA_VERSION,
        "source_units": sources,
        "groups": groups,
        "decisions": {},
        "archived_decisions": [],
    }
    return normalize_structure(structure)


def is_v2_structure(value) -> bool:
    return isinstance(value, dict) and value.get("schema_version") == SCHEMA_VERSION


def normalize_structure(value) -> dict:
    if not is_v2_structure(value):
        return structure_from_units(value if isinstance(value, list) else [])

    raw = copy.deepcopy(value)
    used: set[str] = set()
    sources = [
        _normalize_source(unit, i + 1, used)
        for i, unit in enumerate(raw.get("source_units") or [])
    ]
    source_ids = {source["id"] for source in sources}

    group_used: set[str] = set()
    groups = []
    for index, item in enumerate(raw.get("groups") or [], start=1):
        if not isinstance(item, dict):
            continue
        group = copy.deepcopy(item)
        group["id"] = _unique_id(group.get("id"), "grp", index, group_used)
        group["source_unit_ids"] = [
            source_id for source_id in dict.fromkeys(group.get("source_unit_ids") or [])
            if source_id in source_ids
        ]
        facts = group.get("po_facts") if isinstance(group.get("po_facts"), dict) else {}
        group["po_facts"] = {
            key: facts.get(key) if facts.get(key) in ("yes", "no") else None
            for key in PO_KEYS
        }
        group["relationship_suggestion"] = relationship_suggestion(group["po_facts"])
        if group.get("confirmed_relationship") not in ("combined", "separate"):
            group["confirmed_relationship"] = None
        groups.append(group)

    decisions = raw.get("decisions") if isinstance(raw.get("decisions"), dict) else {}
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "source_units": sources,
        "groups": groups,
        "decisions": copy.deepcopy(decisions),
        "archived_decisions": copy.deepcopy(raw.get("archived_decisions") or []),
    }
    for final_unit in derive_final_units(normalized, include_decisions=False):
        final_id = final_unit["id"]
        decision = normalized["decisions"].get(final_id)
        if not isinstance(decision, dict):
            decision = _empty_decision(final_unit.get("declared_type"))
        else:
            default = _empty_decision(final_unit.get("declared_type"))
            default.update(copy.deepcopy(decision))
            six = _empty_decision()["six_daowei"]
            six.update(copy.deepcopy(decision.get("six_daowei") or {}))
            six["dimensions"] = copy.deepcopy((decision.get("six_daowei") or {}).get("dimensions") or {})
            r08 = _empty_decision()["r08"]
            r08.update(copy.deepcopy(decision.get("r08") or {}))
            r08["answers"] = copy.deepcopy((decision.get("r08") or {}).get("answers") or {})
            default["six_daowei"] = six
            default["r08"] = r08
            decision = default
        if final_unit.get("declared_type") == STANDARD_PRODUCT_TYPE:
            decision["listing_intent"] = "full"
            decision["listing_intent_confirmed"] = True
        normalized["decisions"][final_id] = decision
    return normalized


def derive_final_units(structure: dict, include_decisions: bool = True) -> list[dict]:
    """Derive the user-facing accounting units after group confirmation."""
    sources = structure.get("source_units") or []
    source_by_id = {source.get("id"): source for source in sources if source.get("id")}
    combined_members: set[str] = set()
    finals: list[dict] = []

    for group in structure.get("groups") or []:
        member_ids = [source_id for source_id in group.get("source_unit_ids") or [] if source_id in source_by_id]
        if group.get("confirmed_relationship") != "combined" or len(member_ids) < 2:
            continue
        members = [source_by_id[source_id] for source_id in member_ids]
        combined_members.update(member_ids)
        types = list(dict.fromkeys(member.get("declared_type") for member in members))
        amount_values = [member.get("amount") for member in members]
        amount = sum(_amount(value) for value in amount_values) if any(value not in (None, "") for value in amount_values) else None
        final = {
            "id": group.get("id"),
            "name": group.get("name") or "组合核算单元",
            "source_unit_ids": member_ids,
            "declared_type": types[0] if len(types) == 1 else "组合",
            "declared_types": types,
            "amount": amount,
            "relationship": "combined",
        }
        if include_decisions:
            final["decision"] = (structure.get("decisions") or {}).get(final["id"], _empty_decision())
        finals.append(final)

    for source in sources:
        if source.get("id") in combined_members:
            continue
        final = {
            "id": source.get("id"),
            "name": source.get("name") or "未命名核算单元",
            "source_unit_ids": [source.get("id")],
            "declared_type": source.get("declared_type"),
            "declared_types": [source.get("declared_type")],
            "amount": source.get("amount"),
            "relationship": "separate",
        }
        if include_decisions:
            final["decision"] = (structure.get("decisions") or {}).get(final["id"], _empty_decision(source.get("declared_type")))
        finals.append(final)
    return finals


def _amount(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fingerprints(structure: dict) -> dict[str, tuple]:
    source_by_id = {u["id"]: u for u in structure.get("source_units") or []}
    result = {}
    for final in derive_final_units(structure, include_decisions=False):
        result[final["id"]] = (
            final.get("relationship"),
            tuple(sorted((source_id, source_by_id[source_id].get("declared_type")) for source_id in final["source_unit_ids"])),
        )
    return result


def prepare_structure_update(previous, incoming) -> dict:
    """Normalize an edit and stale only checks whose type/grouping changed."""
    old = normalize_structure(previous)
    new = normalize_structure(incoming)
    old_fingerprints = _fingerprints(old)
    new_fingerprints = _fingerprints(new)
    new_finals = {
        final["id"]: final
        for final in derive_final_units(new, include_decisions=False)
    }
    current_ids = set(new_fingerprints)

    for final_id, decision in list(new["decisions"].items()):
        if final_id not in current_ids:
            continue
        if old_fingerprints.get(final_id) == new_fingerprints.get(final_id):
            continue
        if new_finals[final_id].get("declared_type") != STANDARD_PRODUCT_TYPE:
            decision["listing_intent_confirmed"] = False
        for section in ("six_daowei", "r08"):
            check = decision.get(section)
            if isinstance(check, dict) and check.get("confirmation_status") == "confirmed":
                check["confirmation_status"] = "stale"

    removed = set(old_fingerprints) - current_ids
    archived = list(new.get("archived_decisions") or [])
    for final_id in removed:
        if final_id in old.get("decisions", {}):
            archived.append({"final_unit_id": final_id, "decision": old["decisions"][final_id], "reason": "核算单元组成或组合关系已变更"})
    new["archived_decisions"] = archived[-20:]
    return new


def invalidate_full_unit_checks(structure) -> dict:
    """Shared project-fact edits stale all currently full-intent unit checks."""
    normalized = normalize_structure(structure)
    for final in derive_final_units(normalized):
        decision = normalized["decisions"].get(final["id"], {})
        if decision.get("listing_intent") != "full" or final.get("declared_type") == STANDARD_PRODUCT_TYPE:
            continue
        for section in ("six_daowei", "r08"):
            check = decision.get(section)
            if isinstance(check, dict):
                check["confirmation_status"] = "stale"
    return normalized


def validate_structure(structure, for_submit: bool = False) -> list[str]:
    normalized = normalize_structure(structure)
    errors: list[str] = []
    sources = normalized["source_units"]
    source_by_id = {source["id"]: source for source in sources}
    if not sources:
        return ["请先建立至少一个原始核算单元"] if for_submit else []

    other_names = [source.get("name") or "未命名单元" for source in sources if source.get("declared_type") == "其他"]
    if for_submit and other_names:
        errors.append(f"正式诊断前必须将“其他”归入明确类别：{'、'.join(other_names)}")

    seen: set[str] = set()
    for group in normalized["groups"]:
        member_ids = group.get("source_unit_ids") or []
        if len(member_ids) < 2:
            errors.append(f"组合“{group.get('name') or group['id']}”至少需要两个原始单元")
        overlap = seen.intersection(member_ids)
        if overlap:
            errors.append("同一原始单元不能进入多个候选组合")
        seen.update(member_ids)
        if any(source_by_id[source_id].get("declared_type") == STANDARD_PRODUCT_TYPE for source_id in member_ids if source_id in source_by_id):
            errors.append("标品固定单独全额列收，不参与履约组合")
        if for_submit:
            if any(group.get("po_facts", {}).get(key) not in ("yes", "no") for key in PO_KEYS):
                errors.append(f"请完成组合“{group.get('name') or group['id']}”的四项履约关系判断")
            if group.get("confirmed_relationship") not in ("combined", "separate"):
                errors.append(f"请确认组合“{group.get('name') or group['id']}”最终是组合还是分别核算")

    if for_submit:
        for final in derive_final_units(normalized):
            if final.get("declared_type") == STANDARD_PRODUCT_TYPE:
                continue
            decision = normalized["decisions"].get(final["id"], {})
            if decision.get("listing_intent") not in ("full", "net") or decision.get("listing_intent_confirmed") is not True:
                errors.append(f"请确认核算单元“{final['name']}”拟全额列收或拟净额列收")
    return list(dict.fromkeys(errors))


def legal_six_value(dimension: str, value: str, six: dict) -> bool:
    if value != "not_applicable":
        return value in SIX_VALUES
    if dimension == "procurement_autonomy":
        return six.get("no_external_procurement") is True
    if dimension == "operations_autonomy":
        return six.get("no_operations_obligation") is True
    return False
