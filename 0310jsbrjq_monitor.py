#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for validating login and case query against the dsjfx system.

Purpose:
1. Login to the monitor system.
2. Query case data from /case/list using the same payload shape as the browser request.
3. Filter records whose case_contents/caseContents or replies contains mental keywords.
4. Save raw query summary and matched records to local JSON files for offline verification.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import json
import logging
import os
from pathlib import Path
import re
import sys
import time
from typing import Any

import requests


DEFAULT_LOGIN_URL = "http://68.253.2.111/dsjfx/login"
DEFAULT_API_URL = "http://68.253.2.111/dsjfx/case/list"
DEFAULT_PAGE_SIZE = 15
DEFAULT_HOURS_BACK = 24
DEFAULT_MAX_PAGES = 10
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2

MENTAL_CASE_PATTERN = re.compile(r"精神病|精神障碍|精神异常|精神发病|犯病|肇事肇祸")

BASE_PARAMS = {
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
    "pageSize": str(DEFAULT_PAGE_SIZE),
    "pageNum": "1",
    "orderByColumn": "callTime",
    "isAsc": "desc",
}


@dataclass(frozen=True)
class Config:
    login_username: str
    login_password: str
    login_url: str = DEFAULT_LOGIN_URL
    api_url: str = DEFAULT_API_URL
    page_size: int = DEFAULT_PAGE_SIZE
    hours_back: int = DEFAULT_HOURS_BACK
    max_pages: int = DEFAULT_MAX_PAGES
    output_dir: str = "."


def _runtime_to_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("0310jsbrjq_monitor")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    return logger


def load_config_from_env(args: argparse.Namespace) -> Config:
    username = (
        args.username
        or os.environ.get("JSBRJQ_LOGIN_USERNAME")
        or os.environ.get("LOGIN_USERNAME")
        or ""
    ).strip()
    password = (
        args.password
        or os.environ.get("JSBRJQ_LOGIN_PASSWORD")
        or os.environ.get("LOGIN_PASSWORD")
        or ""
    ).strip()

    return Config(
        login_username=username,
        login_password=password,
        login_url=(args.login_url or DEFAULT_LOGIN_URL).strip(),
        api_url=(args.api_url or DEFAULT_API_URL).strip(),
        page_size=max(1, int(args.page_size or DEFAULT_PAGE_SIZE)),
        hours_back=max(1, int(args.hours_back or DEFAULT_HOURS_BACK)),
        max_pages=max(1, int(args.max_pages or DEFAULT_MAX_PAGES)),
        output_dir=args.output_dir or ".",
    )


def load_config_from_runtime_config(runtime_config: dict[str, Any]) -> Config:
    username = _runtime_to_string(
        runtime_config.get("jsbrjq_login_username")
        or runtime_config.get("login_username")
        or runtime_config.get("username")
        or os.environ.get("JSBRJQ_LOGIN_USERNAME")
        or os.environ.get("LOGIN_USERNAME")
    )
    password = _runtime_to_string(
        runtime_config.get("jsbrjq_login_password")
        or runtime_config.get("login_password")
        or runtime_config.get("password")
        or os.environ.get("JSBRJQ_LOGIN_PASSWORD")
        or os.environ.get("LOGIN_PASSWORD")
    )
    login_url = _runtime_to_string(
        runtime_config.get("jsbrjq_login_url")
        or runtime_config.get("monitor_login_url")
        or runtime_config.get("login_url")
        or DEFAULT_LOGIN_URL
    ) or DEFAULT_LOGIN_URL
    api_url = _runtime_to_string(
        runtime_config.get("jsbrjq_api_url")
        or runtime_config.get("monitor_api_url")
        or runtime_config.get("api_url")
        or DEFAULT_API_URL
    ) or DEFAULT_API_URL
    page_size = int(runtime_config.get("jsbrjq_page_size") or runtime_config.get("page_size") or DEFAULT_PAGE_SIZE)
    hours_back = int(runtime_config.get("jsbrjq_hours_back") or runtime_config.get("hours_back") or DEFAULT_HOURS_BACK)
    max_pages = int(runtime_config.get("jsbrjq_max_pages") or runtime_config.get("max_pages") or DEFAULT_MAX_PAGES)
    output_dir = _runtime_to_string(runtime_config.get("output_dir") or ".") or "."
    return Config(
        login_username=username,
        login_password=password,
        login_url=login_url,
        api_url=api_url,
        page_size=max(1, page_size),
        hours_back=max(1, hours_back),
        max_pages=max(1, max_pages),
        output_dir=output_dir,
    )


def build_time_range(hours_back: int) -> tuple[str, str]:
    now = datetime.now()
    start_time = now - timedelta(hours=hours_back)
    begin_date = start_time.strftime("%Y-%m-%d 00:00:00")
    end_date = now.strftime("%Y-%m-%d 23:59:59")
    return begin_date, end_date


class JsbrJqQueryTester:
    def __init__(self, config: Config, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.session = requests.Session()
        self.session.headers.update(
            {
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
        )

    def _request(self, method: str, url: str, **kwargs) -> requests.Response | None:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return self.session.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
            except requests.RequestException as exc:
                self.logger.warning("Request failed (%d/%d): %s", attempt, MAX_RETRIES, exc)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY_SECONDS * attempt)
        return None

    def login(self) -> tuple[bool, dict[str, Any]]:
        payload = {
            "username": self.config.login_username,
            "password": self.config.login_password,
            "rememberMe": "true",
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }

        self.logger.info("Login request: %s", self.config.login_url)
        response = self._request("POST", self.config.login_url, data=payload, headers=headers)
        if response is None:
            return False, {"error": "no_response"}

        result: dict[str, Any] = {
            "status_code": response.status_code,
            "cookies": self.session.cookies.get_dict(),
        }
        try:
            body = response.json()
            result["body"] = body
        except json.JSONDecodeError:
            body = None
            result["body_text_preview"] = response.text[:500]

        if body is not None:
            if body.get("token"):
                self.session.headers["Authorization"] = f"Bearer {body['token']}"
            success = (
                body.get("code") in {0, 200}
                or body.get("success") is True
                or body.get("msg") == "操作成功"
            )
            return success, result

        return response.status_code in {200, 302}, result

    def fetch_page(self, page_num: int, begin_date: str, end_date: str) -> dict[str, Any]:
        params = BASE_PARAMS.copy()
        params["beginDate"] = begin_date
        params["endDate"] = end_date
        params["pageSize"] = str(self.config.page_size)
        params["pageNum"] = str(page_num)

        self.logger.info(
            "Query page=%d beginDate=%s endDate=%s pageSize=%d",
            page_num,
            begin_date,
            end_date,
            self.config.page_size,
        )
        response = self._request("POST", self.config.api_url, data=params)
        if response is None:
            return {
                "ok": False,
                "page_num": page_num,
                "error": "no_response",
                "request_params": params,
            }

        try:
            body = response.json()
        except json.JSONDecodeError:
            return {
                "ok": False,
                "page_num": page_num,
                "status_code": response.status_code,
                "error": "invalid_json",
                "body_text_preview": response.text[:1000],
                "request_params": params,
            }

        rows = body.get("rows", [])
        total = body.get("total", 0)
        return {
            "ok": body.get("code") == 0,
            "page_num": page_num,
            "status_code": response.status_code,
            "code": body.get("code"),
            "msg": body.get("msg"),
            "total": int(total or 0),
            "row_count": len(rows) if isinstance(rows, list) else 0,
            "rows": rows if isinstance(rows, list) else [],
            "request_params": params,
        }

    @staticmethod
    def _record_case_text(record: dict[str, Any]) -> str:
        return str(record.get("case_contents") or record.get("caseContents") or "").strip()

    @staticmethod
    def _record_replies_text(record: dict[str, Any]) -> str:
        return str(record.get("replies") or "").strip()

    @staticmethod
    def build_message_text(record: dict[str, Any]) -> str:
        call_time = str(record.get("callTime") or record.get("occurTime") or "").strip()
        duty_dept_name = str(record.get("dutyDeptName") or "").strip()
        occur_address = str(record.get("occurAddress") or "").strip()
        case_text = str(record.get("case_contents") or record.get("caseContents") or "").strip()
        detail = case_text or "无警情正文"
        return f"【涉精神警情】{call_time} {duty_dept_name} {detail} 地址:{occur_address}【基础管控中心】".strip()

    def filter_records(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        matched: list[dict[str, Any]] = []
        for record in rows:
            case_text = self._record_case_text(record)
            replies_text = self._record_replies_text(record)
            if MENTAL_CASE_PATTERN.search(case_text) or MENTAL_CASE_PATTERN.search(replies_text):
                matched.append(record)
        return matched

    def run(self) -> int:
        output_dir = Path(self.config.output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        login_ok, login_result = self.login()
        summary: dict[str, Any] = {
            "config": asdict(self.config),
            "login_ok": login_ok,
            "login_result": login_result,
            "query_pages": [],
            "matched_count": 0,
            "raw_count": 0,
        }

        if not login_ok:
            self.logger.error("Login failed.")
            summary_path = output_dir / "0310jsbrjq_monitor_summary.json"
            summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            self.logger.info("Saved summary: %s", summary_path)
            return 1

        begin_date, end_date = build_time_range(self.config.hours_back)
        all_rows: list[dict[str, Any]] = []
        matched_rows: list[dict[str, Any]] = []

        for page_num in range(1, self.config.max_pages + 1):
            page_result = self.fetch_page(page_num, begin_date, end_date)
            summary["query_pages"].append({key: value for key, value in page_result.items() if key != "rows"})

            if not page_result.get("ok"):
                self.logger.error("Query failed on page=%d: %s", page_num, page_result)
                break

            rows = page_result["rows"]
            if not rows:
                self.logger.info("No rows returned on page=%d.", page_num)
                break

            all_rows.extend(rows)
            matched = self.filter_records(rows)
            matched_rows.extend(matched)
            self.logger.info(
                "Page=%d raw_rows=%d matched_rows=%d",
                page_num,
                len(rows),
                len(matched),
            )

            if len(rows) < self.config.page_size:
                break
            if page_result.get("total") and len(all_rows) >= int(page_result["total"]):
                break

        summary["raw_count"] = len(all_rows)
        summary["matched_count"] = len(matched_rows)
        summary["sample_case_numbers"] = [
            str(item.get("caseNo") or item.get("case_no") or "").strip()
            for item in matched_rows[:20]
        ]

        summary_path = output_dir / "0310jsbrjq_monitor_summary.json"
        matched_path = output_dir / "0310jsbrjq_monitor_matched.json"
        raw_path = output_dir / "0310jsbrjq_monitor_raw_preview.json"

        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        matched_path.write_text(json.dumps(matched_rows, ensure_ascii=False, indent=2), encoding="utf-8")
        raw_path.write_text(json.dumps(all_rows[:200], ensure_ascii=False, indent=2), encoding="utf-8")

        self.logger.info("Saved summary: %s", summary_path)
        self.logger.info("Saved matched rows: %s", matched_path)
        self.logger.info("Saved raw preview rows: %s", raw_path)
        self.logger.info("Finished: raw_count=%d matched_count=%d", len(all_rows), len(matched_rows))
        return 0


def _platform_result_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        case_no = _runtime_to_string(record.get("caseNo") or record.get("case_no"))
        call_time = _runtime_to_string(record.get("callTime") or record.get("occurTime"))
        duty_dept_no = _runtime_to_string(record.get("dutyDeptNo") or record.get("brigadeNo"))
        duty_dept_name = _runtime_to_string(record.get("dutyDeptName"))
        event_id = case_no or f"jsbrjq_{index}_{int(time.time())}"

        row = dict(record)
        row.update(
            {
                "event_id": event_id,
                "event_key": event_id,
                "case_no": case_no or event_id,
                "event_time": call_time,
                "dwdm": duty_dept_no,
                "sspcsdm": duty_dept_no,
                "message_text": JsbrJqQueryTester.build_message_text(record),
                "message_vars": {
                    "case_no": case_no or event_id,
                    "call_time": call_time,
                    "duty_dept_name": duty_dept_name,
                    "occur_address": _runtime_to_string(record.get("occurAddress")),
                    "case_contents": _runtime_to_string(
                        record.get("case_contents") or record.get("caseContents")
                    ),
                    "replies": _runtime_to_string(record.get("replies")),
                },
            }
        )
        results.append(row)
    return results


def run(context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    context = context or {}
    runtime_config = context.get("runtime_config")
    if not isinstance(runtime_config, dict):
        runtime_config = {}

    logger = setup_logger()
    config = load_config_from_runtime_config(runtime_config)
    if not config.login_username or not config.login_password:
        raise RuntimeError("Missing login credentials in runtime_config.")

    tester = JsbrJqQueryTester(config, logger)
    login_ok, login_result = tester.login()
    if not login_ok:
        raise RuntimeError(f"Login failed: {json.dumps(login_result, ensure_ascii=False)}")

    begin_date, end_date = build_time_range(config.hours_back)
    all_rows: list[dict[str, Any]] = []
    matched_rows: list[dict[str, Any]] = []

    for page_num in range(1, config.max_pages + 1):
        page_result = tester.fetch_page(page_num, begin_date, end_date)
        if not page_result.get("ok"):
            raise RuntimeError(
                f"Query failed on page {page_num}: "
                f"{json.dumps({k: v for k, v in page_result.items() if k != 'rows'}, ensure_ascii=False)}"
            )

        rows = page_result["rows"]
        if not rows:
            break

        all_rows.extend(rows)
        matched_rows.extend(tester.filter_records(rows))

        if len(rows) < config.page_size:
            break
        if page_result.get("total") and len(all_rows) >= int(page_result["total"]):
            break

    return _platform_result_rows(matched_rows)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="0310jsbrjq_monitor.py",
        description="Test login and query for mental-related cases without SMS sending.",
    )
    parser.add_argument("--username", default="", help="Login username")
    parser.add_argument("--password", default="", help="Login password")
    parser.add_argument("--login-url", default=DEFAULT_LOGIN_URL, help="Login endpoint URL")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Case list endpoint URL")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, help="Query page size")
    parser.add_argument("--hours-back", type=int, default=DEFAULT_HOURS_BACK, help="Lookback hours")
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES, help="Maximum pages")
    parser.add_argument("--output-dir", default=".", help="Directory for JSON outputs")
    return parser


def main() -> int:
    logger = setup_logger()
    args = build_arg_parser().parse_args()
    config = load_config_from_env(args)

    if not config.login_username or not config.login_password:
        logger.error(
            "Missing login credentials. Set LOGIN_USERNAME/LOGIN_PASSWORD "
            "or JSBRJQ_LOGIN_USERNAME/JSBRJQ_LOGIN_PASSWORD, "
            "or pass --username/--password."
        )
        return 1

    tester = JsbrJqQueryTester(config, logger)
    try:
        return tester.run()
    except Exception as exc:
        logger.exception("Script failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
