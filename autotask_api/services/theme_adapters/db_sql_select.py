from __future__ import annotations

from datetime import date, datetime, time as time_value, timedelta
import os
import re
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import create_engine, text

from autotask_api.services.theme_adapters.base import (
    ThemeSourceAdapter,
    ThemeSourceLike,
    register_theme_source_adapter,
)
from autotask_api.services.time_utils import to_shanghai_naive


DEFAULT_CHUNK_SIZE = 500
DEFAULT_MAX_ROWS = 5000
READ_ONLY_QUERY_PREFIXES = ("select", "with")
FORBIDDEN_QUERY_KEYWORDS = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|merge|call|exec)\b",
    re.IGNORECASE,
)
DEFAULT_FIELD_ALIASES: dict[str, list[str]] = {
    "event_key": ["event_key", "event_id", "id", "caseNo", "case_no", "systemid"],
    "case_no": ["case_no", "caseNo"],
    "alarmTime": ["alarmTime", "alarm_time"],
    "callTime": ["callTime", "call_time", "occurTime", "occur_time"],
    "dwdm": ["dwdm", "sspcsdm", "dutyDeptNo", "duty_dept_no", "dept_code"],
    "sspcsdm": ["sspcsdm", "dwdm", "dutyDeptNo", "duty_dept_no", "dept_code"],
    "xqdm": ["xqdm"],
    "dutyDeptName": ["dutyDeptName", "duty_dept_name", "dept_name"],
    "caseContents": ["caseContents", "case_contents", "content"],
    "replies": ["replies", "reply", "feedback"],
    "occurAddress": ["occurAddress", "occur_address", "address"],
    "message_text": ["message_text", "content", "sms_content"],
}


def _safe_str(value: Any) -> str:
    return str(value or "").strip()


def _normalize_scalar(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, time_value):
        return value.strftime("%H:%M:%S")
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _resolve_env_value(name: str) -> str:
    if not name:
        return ""
    return str(os.environ.get(name) or "").strip()


def _coerce_str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple)):
        values: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                values.append(text)
        return values
    return []


class DbSqlSelectThemeAdapter(ThemeSourceAdapter):
    source_type = "db_sql_select"

    def fetch(
        self,
        *,
        source: ThemeSourceLike,
        source_config: dict[str, Any],
        now: datetime,
        dry_run: bool,
    ) -> list[dict[str, Any]]:
        del dry_run

        database_url = self._resolve_database_url(source_config)
        query = self._resolve_query(source_config, source.source_code)
        begin_time, end_time = self._build_time_range(source_config, now)
        params = self._build_query_params(
            source=source,
            source_config=source_config,
            begin_time=begin_time,
            end_time=end_time,
        )
        field_map = (
            source_config.get("field_map")
            if isinstance(source_config.get("field_map"), dict)
            else {}
        )
        fetch_profile = (
            source_config.get("fetch_profile")
            if isinstance(source_config.get("fetch_profile"), dict)
            else {}
        )
        chunk_size = max(1, int(fetch_profile.get("chunk_size") or DEFAULT_CHUNK_SIZE))
        max_rows = max(1, int(fetch_profile.get("max_rows") or DEFAULT_MAX_ROWS))

        engine = create_engine(database_url, pool_pre_ping=True, future=True)
        rows: list[dict[str, Any]] = []
        try:
            with engine.connect() as connection:
                result = connection.execution_options(stream_results=True).execute(
                    text(query),
                    params,
                )
                index = 0
                while True:
                    batch = result.fetchmany(chunk_size)
                    if not batch:
                        break
                    for row in batch:
                        index += 1
                        rows.append(
                            self._normalize_row(
                                raw_row=dict(row._mapping),
                                source_code=source.source_code,
                                index=index,
                                field_map=field_map,
                            )
                        )
                        if len(rows) >= max_rows:
                            return rows
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Theme source {source.source_code} database query failed: {exc}",
            ) from exc
        finally:
            engine.dispose()
        return rows

    def _resolve_database_url(self, source_config: dict[str, Any]) -> str:
        credential_ref = (
            source_config.get("credential_ref")
            if isinstance(source_config.get("credential_ref"), dict)
            else {}
        )
        database_url = _resolve_env_value(_safe_str(credential_ref.get("url_env")))
        if not database_url:
            database_url = _safe_str(source_config.get("database_url"))
        if database_url:
            return database_url
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Theme source database URL is missing. "
                "Set credential_ref.url_env or source_config.database_url."
            ),
        )

    def _resolve_query(self, source_config: dict[str, Any], source_code: str) -> str:
        query = str(source_config.get("query") or "").strip()
        if not query:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Theme source {source_code} query is empty.",
            )

        normalized = query.rstrip().rstrip(";").strip()
        lowered = normalized.lower()
        if ";" in normalized or not lowered.startswith(READ_ONLY_QUERY_PREFIXES):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    f"Theme source {source_code} query must be a single read-only "
                    "SELECT statement."
                ),
            )
        if FORBIDDEN_QUERY_KEYWORDS.search(lowered):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Theme source {source_code} query contains forbidden keywords.",
            )
        return normalized

    def _build_time_range(
        self,
        source_config: dict[str, Any],
        now: datetime,
    ) -> tuple[datetime, datetime]:
        time_range = (
            source_config.get("time_range")
            if isinstance(source_config.get("time_range"), dict)
            else {}
        )
        mode = _safe_str(time_range.get("mode") or "rolling_hours") or "rolling_hours"
        current_time = to_shanghai_naive(now)
        if mode == "rolling_days":
            days_back = max(1, int(time_range.get("days_back") or 1))
            begin_time = current_time - timedelta(days=days_back)
        else:
            hours_back = max(1, int(time_range.get("hours_back") or 24))
            begin_time = current_time - timedelta(hours=hours_back)
        return begin_time, current_time

    def _build_query_params(
        self,
        *,
        source: ThemeSourceLike,
        source_config: dict[str, Any],
        begin_time: datetime,
        end_time: datetime,
    ) -> dict[str, Any]:
        query_params = (
            source_config.get("query_params")
            if isinstance(source_config.get("query_params"), dict)
            else {}
        )
        fetch_profile = (
            source_config.get("fetch_profile")
            if isinstance(source_config.get("fetch_profile"), dict)
            else {}
        )
        max_rows = max(1, int(fetch_profile.get("max_rows") or DEFAULT_MAX_ROWS))
        params = dict(query_params)
        params.update(
            {
                "begin_time": begin_time,
                "end_time": end_time,
                "begin_date": begin_time,
                "end_date": end_time,
                "begin_time_text": begin_time.strftime("%Y-%m-%d %H:%M:%S"),
                "end_time_text": end_time.strftime("%Y-%m-%d %H:%M:%S"),
                "begin_date_text": begin_time.strftime("%Y-%m-%d %H:%M:%S"),
                "end_date_text": end_time.strftime("%Y-%m-%d %H:%M:%S"),
                "now_time": end_time,
                "now_time_text": end_time.strftime("%Y-%m-%d %H:%M:%S"),
                "limit": max_rows,
                "source_code": source.source_code,
            }
        )
        return params

    def _resolve_field_value(
        self,
        raw_row: dict[str, Any],
        field_map: dict[str, Any],
        target_field: str,
    ) -> Any:
        candidates: list[str] = _coerce_str_list(field_map.get(target_field))
        if not candidates:
            candidates = DEFAULT_FIELD_ALIASES.get(target_field, [target_field])

        for candidate in candidates:
            current: Any = raw_row
            found = True
            for part in candidate.split("."):
                if isinstance(current, dict) and part in current:
                    current = current.get(part)
                    continue
                found = False
                break
            if found and current is not None:
                return current
        return None

    def _normalize_row(
        self,
        *,
        raw_row: dict[str, Any],
        source_code: str,
        index: int,
        field_map: dict[str, Any],
    ) -> dict[str, Any]:
        raw = {key: _normalize_scalar(value) for key, value in dict(raw_row).items()}
        case_no = _safe_str(self._resolve_field_value(raw, field_map, "case_no"))
        mapped_event_key = _safe_str(self._resolve_field_value(raw, field_map, "event_key"))
        event_key = mapped_event_key or case_no or f"{source_code}_{index}"
        alarm_time = _safe_str(self._resolve_field_value(raw, field_map, "alarmTime"))
        call_time = _safe_str(self._resolve_field_value(raw, field_map, "callTime")) or alarm_time
        dept_code = _safe_str(self._resolve_field_value(raw, field_map, "sspcsdm"))
        if not dept_code:
            dept_code = _safe_str(self._resolve_field_value(raw, field_map, "dwdm"))
        xqdm = _safe_str(self._resolve_field_value(raw, field_map, "xqdm"))
        if not xqdm and len(dept_code) >= 6:
            xqdm = dept_code[:6]

        case_contents = _safe_str(self._resolve_field_value(raw, field_map, "caseContents"))
        replies = _safe_str(self._resolve_field_value(raw, field_map, "replies"))
        occur_address = _safe_str(self._resolve_field_value(raw, field_map, "occurAddress"))
        duty_dept_name = _safe_str(self._resolve_field_value(raw, field_map, "dutyDeptName"))
        message_text = self._resolve_field_value(raw, field_map, "message_text")

        normalized = dict(raw)
        normalized.update(
            {
                "source_code": source_code,
                "event_id": event_key,
                "event_key": event_key,
                "case_no": case_no or event_key,
                "event_time": call_time or alarm_time,
                "dwdm": dept_code,
                "sspcsdm": dept_code,
                "xqdm": xqdm,
                "dutyDeptName": duty_dept_name,
                "caseContents": case_contents,
                "case_contents": case_contents,
                "replies": replies,
                "occurAddress": occur_address,
                "raw_fields": raw,
                "message_vars": {
                    "case_no": case_no or event_key,
                    "alarmTime": alarm_time,
                    "alarm_time": alarm_time,
                    "callTime": call_time,
                    "call_time": call_time,
                    "duty_dept_name": duty_dept_name,
                    "occur_address": occur_address,
                    "case_contents": case_contents,
                    "replies": replies,
                },
            }
        )
        if message_text not in (None, ""):
            normalized["message_text"] = message_text
        return normalized


register_theme_source_adapter(DbSqlSelectThemeAdapter())
