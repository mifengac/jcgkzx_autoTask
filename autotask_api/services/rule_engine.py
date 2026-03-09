from __future__ import annotations

import json
import re
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload

from autotask_api.models import OrgContact, OrgContactPhone, TaskRule


MOBILE_PATTERN = re.compile(r"^1[3-9]\d{9}$")
VALID_MATCH_FIELDS = {"sspcsdm", "xqdm", "city_code", "county_code"}


def parse_json_text(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def dump_json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def normalize_mobile(raw: Any) -> str | None:
    if raw is None:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if MOBILE_PATTERN.fullmatch(digits):
        return digits
    return None


def normalize_mobile_list(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    mobiles: list[str] = []
    for value in values:
        mobile = normalize_mobile(value)
        if not mobile or mobile in seen:
            continue
        seen.add(mobile)
        mobiles.append(mobile)
    return mobiles


def build_match_codes(
    raw_code: Any,
    target_field: str,
    include_self: bool,
    include_county: bool,
    include_city: bool,
) -> list[str]:
    text = re.sub(r"\D", "", str(raw_code or ""))
    if not text:
        return []

    codes: list[str] = []
    if target_field == "sspcsdm":
        if len(text) == 12 and include_self:
            codes.append(text)
        if len(text) >= 6 and include_county:
            codes.append(text[:6] + "000000")
        if len(text) >= 4 and include_city:
            codes.append(text[:4] + "00000000")
    elif target_field == "xqdm":
        if len(text) >= 6 and (include_self or include_county):
            codes.append(text[:6])
        if len(text) >= 4 and include_city:
            codes.append(text[:4] + "00")
    else:
        if include_self:
            codes.append(text)

    deduped: list[str] = []
    seen: set[str] = set()
    for code in codes:
        if code and code not in seen:
            seen.add(code)
            deduped.append(code)
    return deduped


def apply_contact_filters(stmt: Select[tuple[OrgContact]], rule: TaskRule) -> Select[tuple[OrgContact]]:
    filters = parse_json_text(rule.filter_json, {})
    if not isinstance(filters, dict):
        return stmt

    for field_name, expected in filters.items():
        if not hasattr(OrgContact, field_name):
            continue
        column = getattr(OrgContact, field_name)
        if isinstance(expected, list):
            stmt = stmt.where(column.in_(expected))
        else:
            stmt = stmt.where(column == expected)
    return stmt


def contact_query_for_codes(rule: TaskRule, codes: list[str]) -> Select[tuple[OrgContact]]:
    if rule.target_match_field not in VALID_MATCH_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported target_match_field: {rule.target_match_field}",
        )
    column = getattr(OrgContact, rule.target_match_field)
    stmt = (
        select(OrgContact)
        .options(joinedload(OrgContact.phones))
        .where(OrgContact.status == "active")
        .where(column.in_(codes))
    )
    return apply_contact_filters(stmt, rule)


def resolve_rule_targets(db: Session, rule: TaskRule, sample_row: dict[str, Any]) -> tuple[list[str], list[OrgContact]]:
    if not rule.enabled:
        return [], []

    if rule.rule_type == "fixed_receivers":
        return [], []

    if not rule.source_field:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rule source_field is required for match rules.",
        )

    source_value = sample_row.get(rule.source_field)
    if source_value in (None, ""):
        return [], []

    if rule.rule_type == "field_match":
        codes = [str(source_value).strip()]
    elif rule.rule_type == "field_match_with_ancestors":
        codes = build_match_codes(
            raw_code=source_value,
            target_field=rule.target_match_field,
            include_self=rule.include_self,
            include_county=rule.include_county,
            include_city=rule.include_city,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported rule_type: {rule.rule_type}",
        )

    if not codes:
        return [], []

    contacts = list(db.scalars(contact_query_for_codes(rule, codes)).unique())
    return codes, contacts


def resolve_rule_mobiles(db: Session, rule: TaskRule, sample_row: dict[str, Any]) -> tuple[list[str], list[str], list[OrgContact]]:
    if rule.rule_type == "fixed_receivers":
        mobiles = normalize_mobile_list(parse_json_text(rule.fixed_receivers_json, []))
        return [], mobiles, []

    codes, contacts = resolve_rule_targets(db, rule, sample_row)
    raw_mobiles: list[str] = []
    for contact in contacts:
        for phone in contact.phones:
            if phone.status != "active":
                continue
            raw_mobiles.append(phone.mobile)
    return codes, normalize_mobile_list(raw_mobiles), contacts


class SafeFormatDict(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def render_template(content: str, variables: dict[str, Any]) -> str:
    return content.format_map(SafeFormatDict(variables))
