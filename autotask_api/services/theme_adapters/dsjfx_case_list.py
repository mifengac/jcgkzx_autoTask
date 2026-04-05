from __future__ import annotations

from datetime import datetime, timedelta
import os
import time
from typing import Any

from fastapi import HTTPException, status
import requests

from autotask_api.services.theme_adapters.base import ThemeSourceAdapter, ThemeSourceLike, register_theme_source_adapter


DEFAULT_LOGIN_URL = "http://68.253.2.111/dsjfx/login"
DEFAULT_API_URL = "http://68.253.2.111/dsjfx/case/list"
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/109.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "http://68.253.2.111",
    "Referer": "http://68.253.2.111/dsjfx/case",
}

DEFAULT_BASE_PARAMS = {
    "params[colArray]": "",
    "beginDate": "",
    "endDate": "",
    "newCaseSourceNo": "",
    "newCaseSource": "全部",
    "dutyDeptNo": "",
    "dutyDeptName": "全部",
    "newCharaSubclassNo": "",
    "newCharaSubclass": "全部",
    "newOriCharaSubclassNo": "",
    "newOriCharaSubclass": "全部",
    "caseNo": "",
    "callerName": "",
    "callerPhone": "",
    "phoneAddress": "",
    "callerIdentity": "",
    "operatorNo": "",
    "operatorName": "",
    "params[isInvalidCase]": "",
    "occurAddress": "",
    "caseMarkNo": "",
    "caseMark": "全部",
    "params[repetitionCase]": "",
    "params[originalDuplicateCase]": "",
    "params[startTimePeriod]": "",
    "params[endTimePeriod]": "",
    "caseContents": "",
    "replies": "",
    "params[sinceRecord]": "",
    "dossierResult": "",
    "params[isVideo]": "",
    "params[isConversation]": "",
    "pageSize": "100",
    "pageNum": "1",
    "orderByColumn": "callTime",
    "isAsc": "desc",
}


def _safe_str(value: Any) -> str:
    return str(value or "").strip()


def _resolve_env_value(name: str) -> str:
    if not name:
        return ""
    return str(os.environ.get(name) or "").strip()


class DsjfxCaseListThemeAdapter(ThemeSourceAdapter):
    source_type = "dsjfx_case_list"

    def fetch(
        self,
        *,
        source: ThemeSourceLike,
        source_config: dict[str, Any],
        now: datetime,
        dry_run: bool,
    ) -> list[dict[str, Any]]:
        del dry_run

        session = requests.Session()
        session.headers.update(DEFAULT_HEADERS)

        login_url = _safe_str(source_config.get("login_url") or DEFAULT_LOGIN_URL) or DEFAULT_LOGIN_URL
        api_url = _safe_str(source_config.get("api_url") or DEFAULT_API_URL) or DEFAULT_API_URL
        username, password = self._resolve_credentials(source_config)
        self._login(session, login_url, username, password, source.source_code)

        begin_date, end_date = self._build_time_range(source_config, now)
        fetch_profile = source_config.get("fetch_profile") if isinstance(source_config.get("fetch_profile"), dict) else {}
        page_size = max(1, int(fetch_profile.get("page_size") or DEFAULT_BASE_PARAMS["pageSize"]))
        page_num_start = max(1, int(fetch_profile.get("page_num_start") or 1))
        max_pages = max(1, int(fetch_profile.get("max_pages") or 10))

        all_rows: list[dict[str, Any]] = []
        for page_num in range(page_num_start, page_num_start + max_pages):
            params = self._build_query_params(
                source_config=source_config,
                begin_date=begin_date,
                end_date=end_date,
                page_size=page_size,
                page_num=page_num,
            )
            page = self._fetch_page(session, api_url, params, source.source_code)
            rows = page["rows"]
            if not rows:
                break
            all_rows.extend(rows)
            if len(rows) < page_size:
                break
            total = page.get("total") or 0
            if total and len(all_rows) >= int(total):
                break

        return [self._normalize_row(row, source.source_code, index) for index, row in enumerate(all_rows, start=1)]

    def _resolve_credentials(self, source_config: dict[str, Any]) -> tuple[str, str]:
        credential_ref = source_config.get("credential_ref")
        if isinstance(credential_ref, dict):
            username = _resolve_env_value(_safe_str(credential_ref.get("username_env")))
            password = _resolve_env_value(_safe_str(credential_ref.get("password_env")))
        else:
            username = ""
            password = ""

        username = username or _safe_str(source_config.get("login_username"))
        password = password or _safe_str(source_config.get("login_password"))

        if not username or not password:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Theme source credentials are incomplete.",
            )
        return username, password

    def _request(
        self,
        session: requests.Session,
        method: str,
        url: str,
        *,
        source_code: str,
        **kwargs: Any,
    ) -> requests.Response:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return session.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
            except requests.RequestException as exc:
                if attempt >= MAX_RETRIES:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"Theme source {source_code} request failed: {exc}",
                    ) from exc
                time.sleep(RETRY_DELAY_SECONDS * attempt)
        raise AssertionError("unreachable")

    def _login(
        self,
        session: requests.Session,
        login_url: str,
        username: str,
        password: str,
        source_code: str,
    ) -> None:
        response = self._request(
            session,
            "POST",
            login_url,
            source_code=source_code,
            data={
                "username": username,
                "password": password,
                "rememberMe": "true",
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
            },
        )

        try:
            body = response.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Theme source {source_code} login returned invalid JSON.",
            ) from exc

        success = (
            body.get("code") in {0, 200}
            or body.get("success") is True
            or body.get("msg") == "操作成功"
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Theme source {source_code} login failed: {body.get('msg') or body}",
            )
        token = body.get("token")
        if token:
            session.headers["Authorization"] = f"Bearer {token}"

    def _build_time_range(
        self,
        source_config: dict[str, Any],
        now: datetime,
    ) -> tuple[str, str]:
        time_range = source_config.get("time_range") if isinstance(source_config.get("time_range"), dict) else {}
        mode = _safe_str(time_range.get("mode") or "rolling_hours") or "rolling_hours"
        if mode == "rolling_days":
            days_back = max(1, int(time_range.get("days_back") or 1))
            begin_time = now - timedelta(days=days_back)
        else:
            hours_back = max(1, int(time_range.get("hours_back") or 24))
            begin_time = now - timedelta(hours=hours_back)
        begin_date = begin_time.strftime("%Y-%m-%d %H:%M:%S")
        end_date = now.strftime("%Y-%m-%d %H:%M:%S")
        return begin_date, end_date

    def _build_query_params(
        self,
        *,
        source_config: dict[str, Any],
        begin_date: str,
        end_date: str,
        page_size: int,
        page_num: int,
    ) -> dict[str, Any]:
        base_params = dict(DEFAULT_BASE_PARAMS)
        configured_params = source_config.get("base_params")
        if isinstance(configured_params, dict):
            base_params.update(configured_params)
        base_params["beginDate"] = begin_date
        base_params["endDate"] = end_date
        base_params["pageSize"] = str(page_size)
        base_params["pageNum"] = str(page_num)
        return base_params

    def _fetch_page(
        self,
        session: requests.Session,
        api_url: str,
        params: dict[str, Any],
        source_code: str,
    ) -> dict[str, Any]:
        response = self._request(
            session,
            "POST",
            api_url,
            source_code=source_code,
            data=params,
        )
        try:
            body = response.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Theme source {source_code} query returned invalid JSON.",
            ) from exc

        if body.get("code") != 0:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Theme source {source_code} query failed: {body.get('msg') or body}",
            )

        rows = body.get("rows")
        return {
            "rows": rows if isinstance(rows, list) else [],
            "total": int(body.get("total") or 0),
        }

    def _normalize_row(
        self,
        row: dict[str, Any],
        source_code: str,
        index: int,
    ) -> dict[str, Any]:
        raw = dict(row)
        case_no = _safe_str(raw.get("caseNo") or raw.get("case_no"))
        event_key = case_no or _safe_str(raw.get("id") or raw.get("systemid")) or f"{source_code}_{index}"
        duty_dept_no = _safe_str(raw.get("dutyDeptNo") or raw.get("brigadeNo"))
        xqdm = duty_dept_no[:6] if len(duty_dept_no) >= 6 else ""
        case_contents = _safe_str(raw.get("caseContents") or raw.get("case_contents"))
        replies = _safe_str(raw.get("replies"))
        occur_address = _safe_str(raw.get("occurAddress"))
        alarm_time = _safe_str(raw.get("alarmTime"))
        call_time = _safe_str(raw.get("callTime") or raw.get("occurTime"))
        if not alarm_time:
            alarm_time = call_time
        duty_dept_name = _safe_str(raw.get("dutyDeptName"))

        normalized = dict(raw)
        normalized.update(
            {
                "source_code": source_code,
                "event_id": event_key,
                "event_key": event_key,
                "case_no": case_no or event_key,
                "event_time": call_time,
                "dwdm": duty_dept_no,
                "sspcsdm": duty_dept_no,
                "xqdm": xqdm,
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
        return normalized


register_theme_source_adapter(DsjfxCaseListThemeAdapter())
