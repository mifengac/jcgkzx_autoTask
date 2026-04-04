from __future__ import annotations

import re
from typing import Any


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


def matches_filter_expr(record: dict[str, Any], expr: Any) -> bool:
    if expr in (None, "", {}):
        return True
    if not isinstance(expr, dict):
        return False

    if "all" in expr:
        items = expr.get("all") or []
        return all(matches_filter_expr(record, item) for item in items)
    if "any" in expr:
        items = expr.get("any") or []
        return any(matches_filter_expr(record, item) for item in items)
    if "not" in expr:
        return not matches_filter_expr(record, expr.get("not"))

    field = str(expr.get("field") or "").strip()
    op = str(expr.get("op") or "eq").strip().lower()
    actual = _resolve_field_value(record, field)
    expected = expr.get("value")
    return _compare(actual, expected, op)
