from __future__ import annotations

import re
from typing import Any


FIELD_LABELS = {
    "caseContents": "报警内容",
    "case_contents": "报警内容",
    "occurAddress": "地点",
    "occur_address": "地点",
    "replies": "处警情况",
    "callTime": "时间",
    "occurTime": "时间",
    "caseNo": "警情编号",
    "case_no": "警情编号",
    "dutyDeptName": "派出所",
    "dutyDeptNo": "派出所代码",
}


def _coerce_iterable(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _resolve_field_value(record: dict[str, Any], field: str) -> Any:
    if not field:
        return None

    current: Any = record
    for part in field.split("."):
        if isinstance(current, dict) and part in current:
            current = current.get(part)
            continue
        current = None
        break
    if current is not None:
        return current

    raw_fields = record.get("raw_fields")
    if isinstance(raw_fields, dict):
        current = raw_fields
        for part in field.split("."):
            if isinstance(current, dict) and part in current:
                current = current.get(part)
                continue
            current = None
            break
        if current is not None:
            return current

    return record.get(field)


def _field_label(field: str, expr: Any) -> str:
    if isinstance(expr, dict):
        custom_label = str(expr.get("label") or expr.get("field_label") or "").strip()
        if custom_label:
            return custom_label
    if not field:
        return ""
    return FIELD_LABELS.get(field, field)


def _contains(actual: Any, expected: Any) -> bool:
    if isinstance(actual, (list, tuple, set)):
        return expected in actual
    return str(expected) in str(actual or "")


def _contains_any(actual: Any, expected: Any) -> bool:
    candidates = _coerce_iterable(expected)
    if isinstance(actual, (list, tuple, set)):
        actual_values = {str(item) for item in actual}
        return any(str(item) in actual_values for item in candidates)
    actual_text = str(actual or "")
    return any(str(item) in actual_text for item in candidates)


def _compare(actual: Any, expected: Any, op: str) -> bool:
    if op == "eq":
        return actual == expected
    if op == "ne":
        return actual != expected
    if op == "in":
        return actual in _coerce_iterable(expected)
    if op == "not_in":
        return actual not in _coerce_iterable(expected)
    if op == "contains":
        return _contains(actual, expected)
    if op == "contains_any":
        return _contains_any(actual, expected)
    if op == "regex":
        return re.search(str(expected or ""), str(actual or "")) is not None
    if op == "exists":
        return actual not in (None, "")
    if op == "not_exists":
        return actual in (None, "")
    if op == "gt":
        return actual > expected
    if op == "gte":
        return actual >= expected
    if op == "lt":
        return actual < expected
    if op == "lte":
        return actual <= expected
    raise ValueError(f"Unsupported filter op: {op}")


def _first_matching_candidate(actual: Any, expected: Any) -> str:
    candidates = [str(item) for item in _coerce_iterable(expected) if str(item)]
    if not candidates:
        return ""

    if isinstance(actual, (list, tuple, set)):
        actual_values = {str(item) for item in actual}
        for candidate in candidates:
            if candidate in actual_values:
                return candidate
        return ""

    actual_text = str(actual or "")
    for candidate in candidates:
        if candidate in actual_text:
            return candidate
    return ""


def _leaf_keyword(actual: Any, expected: Any, op: str) -> str:
    if op == "contains_any":
        return _first_matching_candidate(actual, expected)
    if op == "contains":
        if isinstance(expected, (list, tuple, set)):
            return _first_matching_candidate(actual, expected)
        return str(expected or "")
    if op == "eq":
        if expected not in (None, ""):
            return str(expected)
        if actual not in (None, ""):
            return str(actual)
        return ""
    if op == "in":
        if actual not in (None, ""):
            return str(actual)
        return _first_matching_candidate(actual, expected)
    if op == "regex":
        pattern = str(expected or "")
        try:
            match = re.search(pattern, str(actual or ""))
        except re.error:
            return ""
        if match:
            return match.group(0)
        return pattern
    return ""


def _match_expr(record: dict[str, Any], expr: Any) -> tuple[bool, str, str]:
    if expr in (None, "", {}):
        return True, "", ""
    if not isinstance(expr, dict):
        return False, "", ""

    if "all" in expr:
        label = ""
        keyword = ""
        items = expr.get("all") or []
        for item in items:
            matched, item_label, item_keyword = _match_expr(record, item)
            if not matched:
                return False, "", ""
            if not keyword and item_keyword:
                keyword = item_keyword
                label = item_label or label
            if not label and item_label:
                label = item_label
        return True, label, keyword
    if "any" in expr:
        items = expr.get("any") or []
        matched_any = False
        label = ""
        keyword = ""
        for item in items:
            matched, item_label, item_keyword = _match_expr(record, item)
            if not matched:
                continue
            matched_any = True
            if item_keyword:
                return True, item_label, item_keyword
            if not label and item_label:
                label = item_label
        return matched_any, label, keyword
    if "not" in expr:
        matched, _, _ = _match_expr(record, expr.get("not"))
        return not matched, "", ""

    field = str(expr.get("field") or "").strip()
    op = str(expr.get("op") or "eq").strip().lower()
    actual = _resolve_field_value(record, field)
    expected = expr.get("value")
    matched = _compare(actual, expected, op)
    if not matched:
        return False, "", ""
    return True, _field_label(field, expr), _leaf_keyword(actual, expected, op)


def matches_filter_expr(record: dict[str, Any], expr: Any) -> bool:
    return _match_expr(record, expr)[0]


def derive_hit_keyword(record: dict[str, Any], expr: Any) -> str:
    matched, label, keyword = _match_expr(record, expr)
    if not matched:
        return ""
    if label and keyword:
        return f"{label}→{keyword}"
    if keyword:
        return keyword
    return label
