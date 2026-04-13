# -*- coding: utf-8 -*-
"""
Multi-source data ingestion script.

This module fetches remote data concurrently, normalizes the response into
record dictionaries, and writes the result into Kingbase/PostgreSQL tables.
It supports direct execution via ``main()`` and platform execution via
``run(context)``.
"""
import os
import copy
import re
import json
import time
import logging
from typing import Any, Dict, List, Optional, Tuple
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from uuid import uuid4

# Kingbase is PostgreSQL-compatible, so psycopg2 is used for database writes.
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values
from autotask_api.services.time_utils import now_shanghai

def get_end_of_day() -> str:
    """Return today's date formatted as YYYY-MM-DD."""
    return now_shanghai().strftime("%Y-%m-%d")

def get_begin_of_day(days_ago: int = 0) -> str:
    """Return the date N days ago formatted as YYYY-MM-DD."""
    date = now_shanghai() - timedelta(days=days_ago)
    return date.strftime("%Y-%m-%d")
def get_login_cookie(login_url: str, username: str, password: str) -> str:
    """Authenticate and return the Cookie header value."""
    login_data = {
        'username': username,
        'password': password,
        'rememberMe': True,
        'isPkiLogin': False,
        'isAccLogin': True,
        'isSmsLogin': False
    }
    response = requests.post(login_url, data=login_data)
    response.raise_for_status()
    cookies = response.cookies.get_dict()
    # Convert the cookie mapping into a standard Cookie header.
    return "; ".join([f"{k}={v}" for k, v in cookies.items()])

def get_end_of_day() -> str:
    """Return today's date formatted as YYYY-MM-DD."""
    return now_shanghai().strftime("%Y-%m-%d")

def get_begin_of_day(days_ago: int = 0) -> str:
    """Return the date N days ago formatted as YYYY-MM-DD."""
    date = now_shanghai() - timedelta(days=days_ago)
    return date.strftime("%Y-%m-%d")

def iter_dates(start: str, end: str, fmt: str = "%Y-%m-%d"):
    """Yield every date string between start and end, inclusive."""
    start_dt = datetime.strptime(start, fmt)
    end_dt = datetime.strptime(end, fmt)
    cur = start_dt
    while cur <= end_dt:
        yield cur.strftime(fmt)
        cur += timedelta(days=1)


def build_params_by_date_range(
    base_params: Dict[str, Any],
    date_key: str,
    start: str,
    end: str,
    fmt: str = "%Y-%m-%d"
) -> List[Dict[str, Any]]:
    """Clone base_params across a date range and fill date_key per day."""
    result: List[Dict[str, Any]] = []
    for d in iter_dates(start, end, fmt):
        p = dict(base_params)
        p[date_key] = d
        result.append(p)
    return result

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

CONFIG = {
    # Runtime behavior.
    "mode": "append",  # Supported values: "replace" or "append".
    "max_workers": 31,
    "request_timeout": 180,

    # Shared HTTP session settings.
    "session": {
        "headers": {
           "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.146 Safari/537.36",
            "Accept": "application/json, text/plain, */*;q=0.01",
            "X-Requested-With":"XMLHttpRequest",
            # The authenticated Cookie header is injected at runtime.
        },
        "cookies": {
            # "sessionid": "your_session_id"
        },
        "proxies": None,  # Example: {"http": "http://127.0.0.1:8080", "https": "http://127.0.0.1:8080"}
        "verify": True,
        "retry": {
            "enabled": True,
            "retries": 2,
            "backoff": 1.0,
        }
    },

    # Source task definitions.
    "tasks": [
        {
            "name": "duty_schedule",  # task name for logging
            "request": {
                "method": "POST",
                "url": "http://68.253.2.107/zhksh/dutySchedule/crossDayList",
                # The platform expands one request payload per day.
                "params_list": build_params_by_date_range(
                    {
                        'keywords': '',
                        'deploymentType': '',
                        'deploymentId': '',
                        'deploymentName': '',
                        'deploymentTypeCode': '',
                        'scheduleDate': '',
                        'params[beginTime]': '',
                        'params[endTime]': '',
                        'deptId': '',
                        'deptName': '鍏ㄩ儴',
                        'schemeId': '',
                        'shiftId': '',
                        'userTypeCode': '',
                        'dutyTypeCode': '',
                        'dutyTypeName': '',
                        'dutyLevelCode': '',
                        'policeCategory': '',
                        'userId': '',
                        'userName': '',
                        'reportState': '',
                        'pageSize': '99999',
                        'pageNum': '1',
                        'orderByColumn': 'startTime',
                        'isAsc': 'asc'
                    },
                    date_key="scheduleDate",
                    start=get_begin_of_day(9),
                    end=get_end_of_day(),
                    fmt="%Y-%m-%d"
                ),
                "json_list": None,
                "data_list": None,
            },
            "table": {
                "schema": "ywdata",
                "name": "zq_kshddpt_zxzgl",
                "unique_key": "scheduleId"
            }
        },
    ],

    # Database connection settings.
    "db": {
        "host": "",
        "port": 0,
        "dbname": "",
        "user": "",
        "password": "",
        "sslmode": "disable",
    },
}

def build_session(cfg: Dict[str, Any]) -> requests.Session:
    s = requests.Session()
    headers = cfg.get("headers") or {}
    cookies = cfg.get("cookies") or {}
    proxies = cfg.get("proxies")
    verify = cfg.get("verify", True)

    s.headers.update(headers)
    if cookies:
        s.cookies.update(cookies)
    if proxies:
        s.proxies.update(proxies)
    s.verify = verify
    return s


def do_request(
    s: requests.Session,
    method: str,
    url: str,
    timeout: int,
    params: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    retry_cfg: Optional[Dict[str, Any]] = None
) -> Tuple[Optional[requests.Response], Optional[Exception]]:
    retries = 0
    max_retries = retry_cfg.get("retries", 0) if retry_cfg else 0
    backoff = retry_cfg.get("backoff", 1.0) if retry_cfg else 1.0
    enabled = retry_cfg.get("enabled", False) if retry_cfg else False

    while True:
        try:
            resp = s.request(
                method=method.upper(),
                url=url,
                params=params,
                data=data,
                json=json_body,
                timeout=timeout
            )
            return resp, None
        except Exception as e:
            if enabled and retries < max_retries:
                retries += 1
                time.sleep(backoff * retries)
                continue
            return None, e


def fetch_all_for_task(cfg: Dict[str, Any], task_cfg: Dict[str, Any]) -> List[requests.Response]:
    """Fetch all pages for one task config."""
    session_cfg = cfg["session"]
    req_cfg = task_cfg["request"]
    max_workers = cfg["max_workers"]
    timeout = cfg["request_timeout"]

    s = build_session(session_cfg)
    method = req_cfg.get("method", "GET").upper()
    url = req_cfg["url"]

    # Build one concurrent request job per payload.
    tasks = []
    params_list = req_cfg.get("params_list")
    json_list = req_cfg.get("json_list")
    data_list = req_cfg.get("data_list")

    if params_list:
        for p in params_list:
            tasks.append(("params", p))
    elif json_list:
        for j in json_list:
            tasks.append(("json", j))
    elif data_list:
        for d in data_list:
            tasks.append(("data", d))
    else:
        # Fall back to a single request when no payload list is provided.
        tasks.append(("none", None))

    responses = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_args = {}
        for tag, payload in tasks:
            if tag == "params":
                future = executor.submit(
                    do_request, s, method, url, timeout, params=payload, retry_cfg=session_cfg.get("retry")
                )
            elif tag == "json":
                future = executor.submit(
                    do_request, s, method, url, timeout, json_body=payload, retry_cfg=session_cfg.get("retry")
                )
            elif tag == "data":
                future = executor.submit(
                    do_request, s, method, url, timeout, data=payload, retry_cfg=session_cfg.get("retry")
                )
            else:
                future = executor.submit(
                    do_request, s, method, url, timeout, retry_cfg=session_cfg.get("retry")
                )
            future_to_args[future] = payload

        for future in as_completed(future_to_args):
            resp, err = future.result()
            if err:
                logging.error(f"request failed: {err} | payload={future_to_args[future]}")
                continue
            if resp is None:
                continue
            if resp.status_code != 200:
                logging.warning(f"non-200 response: {resp.status_code} | payload={future_to_args[future]}")
            responses.append(resp)

    return responses



def fetch_all(cfg: Dict[str, Any]) -> List[requests.Response]:
    """Compatibility wrapper for legacy config layout."""
    # Support the older single-request config structure.
    if "request" in cfg:
        task_cfg = {
            "name": "compat_task",
            "request": cfg["request"]
        }
        return fetch_all_for_task(cfg, task_cfg)
    else:
        raise ValueError("invalid config format: expected tasks[] or request")


def process_single_task(cfg: Dict[str, Any], task_cfg: Dict[str, Any], conn) -> Dict[str, Any]:
    """Fetch, parse, deduplicate and upsert records for one task."""
    task_name = task_cfg.get("name", "unnamed_task")
    table_cfg = task_cfg["table"]
    unique_key = table_cfg["unique_key"]
    mode = cfg["mode"]
    started_at = now_shanghai()

    logging.info(f"start task: {task_name}")
    
    # Fetch remote payloads first, then normalize them into records.
    responses = fetch_all_for_task(cfg, task_cfg)
    logging.info(f"task[{task_name}] fetched responses: {len(responses)}")

    # Parse every response into flat text records.
    all_records: List[Dict[str, str]] = []
    for resp in responses:
        try:
            part = parse_response(resp)
            all_records.extend(part)
        except Exception as e:
            logging.exception(f"task[{task_name}] failed: {e}")

    # Deduplicate by the configured unique key.
    dedup_map: Dict[str, Dict[str, str]] = {}
    for r in all_records:
        cno = r.get(unique_key)
        if not cno:
            continue
        dedup_map[str(cno)] = {k: ("" if v is None else str(v)) for k, v in r.items()}

    final_rows = list(dedup_map.values())
    logging.info(f"task[{task_name}] records after dedup: {len(final_rows)}")

    summary = {
        "event_id": f"multi_{task_name}_{uuid4().hex}",
        "task_name": task_name,
        "target_table": f"{table_cfg.get('schema', '')}.{table_cfg['name']}".strip("."),
        "mode": mode,
        "status": "success",
        "fetched_response_count": len(responses),
        "parsed_record_count": len(all_records),
        "written_record_count": len(final_rows),
        "unique_key": unique_key,
        "message_vars": {
            "task_name": task_name,
            "target_table": f"{table_cfg.get('schema', '')}.{table_cfg['name']}".strip("."),
            "written_record_count": len(final_rows),
            "parsed_record_count": len(all_records),
            "mode": mode,
        },
        "message_text": "",
        "error_message": "",
        "start_time": started_at.isoformat(),
        "end_time": "",
    }

    if not final_rows:
        logging.warning(f"task[{task_name}] no records to write")
        summary["status"] = "success_no_data"
        summary["message_text"] = f"导数任务完成: {task_name}, 无可写入数据"
        summary["end_time"] = now_shanghai().isoformat()
        return summary

    # Create the table or missing columns before writing rows.
    try:
        ensure_table_and_columns(conn, table_cfg, unique_key, final_rows[:50])

        if mode == "replace":
            logging.info(f"task[{task_name}] run replace mode")
            replace_records(conn, table_cfg, final_rows)
        else:
            logging.info(f"task[{task_name}] run append mode")
            upsert_records(conn, table_cfg, unique_key, final_rows)

        logging.info(f"task[{task_name}] database write complete")
        summary["message_text"] = (
            f"导数任务完成: {task_name}, 目标表 {summary['target_table']}, "
            f"写入 {len(final_rows)} 条"
        )
        summary["end_time"] = now_shanghai().isoformat()
        return summary
    except Exception as e:
        logging.exception(f"task[{task_name}] database write failed: {e}")
        conn.rollback()
        summary["status"] = "failed"
        summary["error_message"] = str(e)
        summary["message_text"] = (
            f"导数任务失败: {task_name}, 目标表 {summary['target_table']}, 错误: {e}"
        )
        summary["end_time"] = now_shanghai().isoformat()
        raise RuntimeError(json.dumps(summary, ensure_ascii=False)) from e




def try_to_json(resp: requests.Response) -> Optional[Any]:
    ct = resp.headers.get("Content-Type", "")
    if "application/json" in ct.lower():
        try:
            return resp.json()
        except Exception:
            return None
    # Some endpoints return JSON with an incorrect Content-Type header.
    try:
        return resp.json()
    except Exception:
        return None


def flatten_dict(d: Dict[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, str]:
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else str(k)
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            # Store nested lists as JSON text.
            items.append((new_key, json.dumps(v, ensure_ascii=False)))
        else:
            items.append((new_key, "" if v is None else str(v)))
    return dict(items)


def extract_case_no(record: Dict[str, Any]) -> Optional[str]:
    # Try common case number keys first.
    for key in ["caseNo", "caseno", "case_no", "case_no_str", "caseNO", "CaseNo"]:
        if key in record and record[key]:
            return str(record[key])

    # Fall back to pattern matching across all string values.
    pattern = re.compile(r"[A-Za-z]{0,4}\d{3,}[-/]?\d*")
    for v in record.values():
        if isinstance(v, str):
            m = pattern.search(v)
            if m:
                return m.group(0)
    return None


def _parse_rows_value(rows_val) -> List[Dict[str, Any]]:
    """
    Normalize a ``rows`` value into ``list[dict]``.

    Strings are parsed as JSON first, then ``ast.literal_eval`` as a
    fallback. Lists are kept as-is, and scalar items are wrapped into
    ``{"raw": ...}``.
    """
    if isinstance(rows_val, list):
        return [x if isinstance(x, dict) else {"raw": str(x)} for x in rows_val]
    if isinstance(rows_val, str):
        s = rows_val.strip()
        try:
            data = json.loads(s)
        except Exception:
            try:
                import ast
                data = ast.literal_eval(s)
            except Exception:
                logging.warning("failed to parse rows as JSON/list, raw_len=%d", len(s))
                return []
        if isinstance(data, list):
            return [x if isinstance(x, dict) else {"raw": str(x)} for x in data]
        if isinstance(data, dict):
            return [data]
        return []
    if isinstance(rows_val, dict):
        return [rows_val]
    return []


def parse_response(resp: requests.Response) -> List[Dict[str, str]]:
    """Parse one response into normalized record dictionaries."""
    results: List[Dict[str, str]] = []

    data = try_to_json(resp)

    # Prefer payloads that expose a top-level rows field.
    if data is not None:
        # Handle list payloads such as [{"rows": [...]}].
        if isinstance(data, list) and data and isinstance(data[0], dict) and "rows" in data[0]:
            rows_list = _parse_rows_value(data[0].get("rows"))
            for obj in rows_list:
                if not isinstance(obj, dict):
                    obj = {"raw": str(obj)}
                # Ensure each record has a stable key for deduplication.
                if not obj.get("caseNo"):
                    cno = extract_case_no({k: ("" if v is None else str(v)) for k, v in obj.items()})
                    if not cno:
                        continue
                    obj["caseNo"] = cno
                # Persist all values as strings for dynamic text columns.
                results.append({k: ("" if v is None else str(v)) for k, v in obj.items()})
            return results

        # Handle dict payloads such as {"rows": [...]} .
        if isinstance(data, dict) and "rows" in data:
            rows_list = _parse_rows_value(data.get("rows"))
            for obj in rows_list:
                if not isinstance(obj, dict):
                    obj = {"raw": str(obj)}
                if not obj.get("caseNo"):
                    cno = extract_case_no({k: ("" if v is None else str(v)) for k, v in obj.items()})
                    if not cno:
                        continue
                    obj["caseNo"] = cno
                results.append({k: ("" if v is None else str(v)) for k, v in obj.items()})
            return results

    # Fall back to simple text parsing for non-JSON responses.
    text = resp.text or ""
    # Split by paragraph and keep the first recognizable case number.
    for i, para in enumerate(re.split(r"\n{2,}", text)):
        para = para.strip()
        if not para:
            continue
        cno_match = re.search(r"[A-Za-z]{0,4}\d{3,}[-/]?\d*", para)
        if not cno_match:
            continue
        record = {
            "caseNo": cno_match.group(0),
            "content": para[:2000]
        }
        results.append(record)

    return results


def db_connect(db_cfg: Dict[str, Any]):
    conn = psycopg2.connect(**db_cfg)
    conn.autocommit = False
    return conn

# Build SQL-safe identifiers for an optionally schema-qualified table.
def get_table_ident(table_cfg: Dict[str, Any]):
    """
    Return a SQL-safe table identifier tuple.

    The tuple contains the qualified SQL identifier, the plain table name,
    and the schema name if one is configured.
    """
    schema = table_cfg.get("schema")
    name = table_cfg["name"]
    if schema:
        qualified = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(name))
    else:
        qualified = sql.Identifier(name)
    return qualified, name, schema


def ensure_table_and_columns(conn, table_cfg: Dict[str, Any], unique_key: str, sample_rows: List[Dict[str, str]]):
    """Ensure the table, required columns, and unique constraint exist."""
    all_keys = set([unique_key])
    for r in sample_rows:
        all_keys.update(r.keys())

    tbl_ident, tbl_simple, schema = get_table_ident(table_cfg)

    with conn.cursor() as cur:
        # Create the schema on demand when one is configured.
        if schema:
            cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))

        # Create the table with the unique key column first.
        cols_sql = sql.SQL(", ").join([
            sql.SQL("{} TEXT").format(sql.Identifier(unique_key))
        ])
        create_sql = sql.SQL("CREATE TABLE IF NOT EXISTS {} ( {} )").format(
            tbl_ident,
            cols_sql
        )
        cur.execute(create_sql)

        # Add the unique constraint only when it does not already exist.
        # Constraint names cannot contain dots, so only the table name is used.
        idx_name = f"{tbl_simple}_{unique_key}_key"
        cur.execute(
            sql.SQL("DO $$ BEGIN "
                    "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = %s) THEN "
                    "ALTER TABLE {} ADD CONSTRAINT {} UNIQUE ({}); "
                    "END IF; END $$;").format(
                tbl_ident,
                sql.Identifier(idx_name),
                sql.Identifier(unique_key)
            ),
            (idx_name,)
        )

        # Add any missing columns discovered from the current batch.
        for k in sorted(all_keys):
            cur.execute(
                sql.SQL("ALTER TABLE {} ADD COLUMN IF NOT EXISTS {} TEXT")
                .format(tbl_ident, sql.Identifier(k))
            )
    conn.commit()


def upsert_records(conn, table_cfg: Dict[str, Any], unique_key: str, rows: List[Dict[str, str]]):
    if not rows:
        return

    tbl_ident, _, _ = get_table_ident(table_cfg)

    # Build a complete ordered column list for the batch.
    all_keys = sorted(set().union(*[row.keys() for row in rows]))
    if unique_key not in all_keys:
        raise ValueError(f"upsert rows must include unique key: {unique_key}")

    columns_ident = [sql.Identifier(k) for k in all_keys]
    values = []
    for r in rows:
        values.append([("" if v is None else str(v)) for v in (r.get(k) for k in all_keys)])

    set_assignments = [
        sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(k), sql.Identifier(k))
        for k in all_keys if k != unique_key
    ]

    insert_sql = sql.SQL("INSERT INTO {} ({}) VALUES %s ON CONFLICT ({}) DO UPDATE SET {}").format(
        tbl_ident,
        sql.SQL(", ").join(columns_ident),
        sql.Identifier(unique_key),
        sql.SQL(", ").join(set_assignments) if set_assignments else sql.SQL("/* no update */")
    )

    with conn.cursor() as cur:
        execute_values(cur, insert_sql, values)
    conn.commit()


def replace_records(conn, table_cfg: Dict[str, Any], rows: List[Dict[str, str]]):
    tbl_ident, _, _ = get_table_ident(table_cfg)

    if not rows:
        # Replace mode with an empty batch means truncating the table.
        with conn.cursor() as cur:
            cur.execute(sql.SQL("TRUNCATE TABLE {}").format(tbl_ident))
        conn.commit()
        return

    # Replace mode truncates first, then bulk-inserts the full batch.
    all_keys = sorted(set().union(*[row.keys() for row in rows]))
    columns_ident = [sql.Identifier(k) for k in all_keys]
    values = []
    for r in rows:
        values.append([("" if v is None else str(v)) for v in (r.get(k) for k in all_keys)])

    with conn.cursor() as cur:
        cur.execute(sql.SQL("TRUNCATE TABLE {}").format(tbl_ident))
        insert_sql = sql.SQL("INSERT INTO {} ({}) VALUES %s").format(
            tbl_ident,
            sql.SQL(", ").join(columns_ident)
        )
        execute_values(cur, insert_sql, values)
    conn.commit()


def _bool_env(name: str, default: bool = False) -> bool:
    value = (os.environ.get(name) or "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    value = (os.environ.get(name) or "").strip()
    if not value:
        return default
    return int(value)


def _require_env(name: str, default: Optional[str] = None) -> str:
    value = (os.environ.get(name) or "").strip()
    if value:
        return value
    if default is not None:
        return str(default)
    raise RuntimeError(f"missing env var: {name}")


def _first_env(names: List[str], default: Optional[str] = None) -> str:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    if default is not None:
        return str(default)
    raise RuntimeError(f"missing env var(s): {'/'.join(names)}")


def _config_value(runtime_config: Dict[str, Any], name: str) -> Optional[str]:
    value = runtime_config.get(name)
    if value in (None, ""):
        return None
    return str(value).strip()


def _bool_setting(runtime_config: Dict[str, Any], name: str, default: bool = False) -> bool:
    value = _config_value(runtime_config, name)
    if value is not None:
        return value.lower() in {"1", "true", "yes", "on"}
    return _bool_env(name, default)


def _int_setting(runtime_config: Dict[str, Any], name: str, default: int) -> int:
    value = _config_value(runtime_config, name)
    if value is not None:
        return int(value)
    return _int_env(name, default)


def _require_setting(
    runtime_config: Dict[str, Any],
    names: List[str],
    default: Optional[str] = None
) -> str:
    for name in names:
        value = _config_value(runtime_config, name)
        if value:
            return value
    if len(names) == 1:
        return _require_env(names[0], default)
    return _first_env(names, default)


def build_runtime_config(runtime_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    runtime_config = runtime_config or {}
    cfg = copy.deepcopy(CONFIG)

    cfg["mode"] = _require_setting(runtime_config, ["multi_mode", "MULTI_MODE"], cfg.get("mode", "append"))
    cfg["max_workers"] = _int_setting(
        runtime_config,
        "multi_max_workers",
        int(cfg.get("max_workers", 31))
    )
    cfg["request_timeout"] = _int_setting(
        runtime_config,
        "multi_request_timeout",
        int(cfg.get("request_timeout", 180))
    )

    cfg["db"]["host"] = _require_setting(runtime_config, ["multi_db_host", "MULTI_DB_HOST", "KINGBASE_HOST"])
    cfg["db"]["port"] = int(_require_setting(runtime_config, ["multi_db_port", "MULTI_DB_PORT", "KINGBASE_PORT"]))
    cfg["db"]["dbname"] = _require_setting(runtime_config, ["multi_db_name", "MULTI_DB_NAME", "KINGBASE_DBNAME"])
    cfg["db"]["user"] = _require_setting(runtime_config, ["multi_db_user", "MULTI_DB_USER", "KINGBASE_USER"])
    cfg["db"]["password"] = _require_setting(runtime_config, ["multi_db_password", "MULTI_DB_PASSWORD", "KINGBASE_PASSWORD"])
    cfg["db"]["sslmode"] = _require_setting(
        runtime_config,
        ["multi_db_sslmode", "MULTI_DB_SSLMODE"],
        cfg["db"].get("sslmode", "disable")
    )

    if not _bool_setting(runtime_config, "data_multi_task_enabled", True):
        cfg["tasks"] = []
        return cfg

    if cfg.get("tasks"):
        duty_task = cfg["tasks"][0]
        duty_task["request"]["url"] = _require_setting(
            runtime_config,
            ["multi_api_url_duty", "MULTI_API_URL_DUTY"],
            duty_task["request"].get("url", "")
        )

        begin_days_ago = _int_setting(runtime_config, "multi_begin_days_ago", 9)
        end_days_ago = _int_setting(runtime_config, "multi_end_days_ago", 0)
        start_date = (now_shanghai() - timedelta(days=begin_days_ago)).strftime("%Y-%m-%d")
        end_date = (now_shanghai() - timedelta(days=end_days_ago)).strftime("%Y-%m-%d")

        template_params = {}
        params_list = duty_task["request"].get("params_list") or []
        if params_list:
            template_params = dict(params_list[0])
        template_params["scheduleDate"] = ""

        duty_task["request"]["params_list"] = build_params_by_date_range(
            template_params,
            date_key="scheduleDate",
            start=start_date,
            end=end_date,
            fmt="%Y-%m-%d"
        )

    return cfg


def run(context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    context = context or {}
    runtime_config = context.get("runtime_config")
    if not isinstance(runtime_config, dict):
        runtime_config = {}

    cfg = build_runtime_config(runtime_config)
    login_url = _require_setting(runtime_config, ["multi_login_url", "MULTI_LOGIN_URL"])
    username = _require_setting(
        runtime_config,
        ["multi_login_username", "MULTI_LOGIN_USERNAME", "LOGIN_USERNAME"]
    )
    password = _require_setting(
        runtime_config,
        ["multi_login_password", "MULTI_LOGIN_PASSWORD", "LOGIN_PASSWORD"]
    )

    try:
        cookie = get_login_cookie(login_url, username, password)
        cfg["session"]["headers"]["Cookie"] = cookie
    except Exception as e:
        logging.error(f"failed to get login cookie: {e}")
        raise RuntimeError(f"failed to get login cookie: {e}") from e

    tasks = cfg.get("tasks", [])
    
    if not tasks:
        raise RuntimeError("no tasks configured")

    # Reuse a single database connection for all configured tasks.
    conn = None
    results: List[Dict[str, Any]] = []
    try:
        conn = db_connect(cfg["db"])
        
        # Execute each configured task independently.
        for task_cfg in tasks:
            try:
                results.append(process_single_task(cfg, task_cfg, conn))
            except Exception as e:
                error_summary: Dict[str, Any]
                try:
                    error_summary = json.loads(str(e))
                    if not isinstance(error_summary, dict):
                        raise ValueError("error summary is not dict")
                except Exception:
                    error_summary = {
                        "event_id": f"multi_{task_cfg.get('name', 'unnamed_task')}_{uuid4().hex}",
                        "task_name": task_cfg.get("name", "unnamed_task"),
                        "target_table": (
                            f"{task_cfg.get('table', {}).get('schema', '')}."
                            f"{task_cfg.get('table', {}).get('name', '')}"
                        ).strip("."),
                        "mode": cfg.get("mode", "append"),
                        "status": "failed",
                        "fetched_response_count": 0,
                        "parsed_record_count": 0,
                        "written_record_count": 0,
                        "unique_key": task_cfg.get("table", {}).get("unique_key", ""),
                        "message_vars": {
                            "task_name": task_cfg.get("name", "unnamed_task"),
                            "target_table": (
                                f"{task_cfg.get('table', {}).get('schema', '')}."
                                f"{task_cfg.get('table', {}).get('name', '')}"
                            ).strip("."),
                            "written_record_count": 0,
                            "parsed_record_count": 0,
                            "mode": cfg.get("mode", "append"),
                        },
                        "message_text": (
                            f"导数任务失败: {task_cfg.get('name', 'unnamed_task')}, 错误: {e}"
                        ),
                        "error_message": str(e),
                        "start_time": now_shanghai().isoformat(),
                        "end_time": now_shanghai().isoformat(),
                    }
                logging.error(
                    f"task failed: {task_cfg.get('name', 'unnamed_task')} | error: {e}"
                )
                results.append(error_summary)
                # Continue with the remaining tasks after a single-task failure.

        logging.info("all tasks finished")
        return results
    except Exception as e:
        logging.exception(f"database connection or processing failed: {e}")
        raise
    finally:
        if conn:
            conn.close()


def main():
    results = run({"runtime_config": {}})
    logging.info("multi task summaries: %s", json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()

