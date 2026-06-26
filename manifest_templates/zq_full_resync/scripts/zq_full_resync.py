#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""zq_kshddpt_dsjfx_jq quan-liang chong tong-bu (yi-ci-xing).

Production one-shot resync script for table zq_kshddpt_dsjfx_jq.

Workflow:
  1. Login http://68.253.2.111/dsjfx/login
  2. (Optional) TRUNCATE schema.zq_kshddpt_dsjfx_jq
  3. Iterate [start-date, end-date] window-by-window (monthly slices)
  4. For each window paginate /dsjfx/case/list with pageSize
  5. Bulk upsert into Kingbase via psycopg2 execute_values + ON CONFLICT
  6. Persist progress to a json file; supports --resume

Notes:
  - Standalone script: depends only on requests + psycopg2-binary.
  - Idempotent: safe to rerun. Use --resume to skip already finished windows.
  - Schema strategy mirrors examples/zq_kshddpt_dsjfx_jq.py: dynamic CREATE
    based on first row, ALTER TABLE to add missing columns. All TEXT,
    caseno is UNIQUE NOT NULL.

Usage (first run, wipe + reload):
  python zq_full_resync.py \
    --username XXX --password XXX \
    --db-host 10.45.x.x --db-port 54321 --db-name yfgxpt \
    --db-user XXX --db-password XXX --db-schema ywdata \
    --start-date 2020-01-01 --end-date 2026-06-17 \
    --truncate --confirm-truncate

Usage (resume after crash, do NOT pass --truncate again):
  python zq_full_resync.py [same args] --resume

Env vars (CLI takes precedence):
  ZQ_LOGIN_URL ZQ_API_URL ZQ_LOGIN_USERNAME ZQ_LOGIN_PASSWORD
  ZQ_DB_HOST ZQ_DB_PORT ZQ_DB_NAME ZQ_DB_USER ZQ_DB_PASSWORD ZQ_DB_SCHEMA
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Iterable

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    sys.stderr.write("missing dependency: psycopg2 (pip install psycopg2-binary)\n")
    raise

try:
    import requests
except ImportError:
    sys.stderr.write("missing dependency: requests (pip install requests)\n")
    raise


LOGGER = logging.getLogger("zq_full_resync")

DEFAULT_LOGIN_URL = "http://68.253.2.111/dsjfx/login"
DEFAULT_API_URL = "http://68.253.2.111/dsjfx/case/list"
DEFAULT_TABLE = "zq_kshddpt_dsjfx_jq"

REQUEST_TIMEOUT = 60
LOGIN_TIMEOUT = 30
MAX_RETRIES = 5
RETRY_BASE_DELAY = 3
DB_BATCH_SIZE = 500

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


# ---------- CLI ----------

def parse_args(argv=None):
    p = argparse.ArgumentParser(description="zq_kshddpt_dsjfx_jq full resync")

    p.add_argument("--login-url", default=os.environ.get("ZQ_LOGIN_URL", DEFAULT_LOGIN_URL))
    p.add_argument("--api-url", default=os.environ.get("ZQ_API_URL", DEFAULT_API_URL))
    p.add_argument("--username", default=os.environ.get("ZQ_LOGIN_USERNAME", ""))
    p.add_argument("--password", default=os.environ.get("ZQ_LOGIN_PASSWORD", ""))

    p.add_argument("--db-host", default=os.environ.get("ZQ_DB_HOST", ""))
    p.add_argument(
        "--db-port",
        type=int,
        default=int(os.environ.get("ZQ_DB_PORT", "54321") or "54321"),
    )
    p.add_argument("--db-name", default=os.environ.get("ZQ_DB_NAME", ""))
    p.add_argument("--db-user", default=os.environ.get("ZQ_DB_USER", ""))
    p.add_argument("--db-password", default=os.environ.get("ZQ_DB_PASSWORD", ""))
    p.add_argument("--db-schema", default=os.environ.get("ZQ_DB_SCHEMA", "ywdata"))
    p.add_argument("--table-name", default=DEFAULT_TABLE)

    p.add_argument(
        "--start-date",
        required=False,
        help="start date YYYY-MM-DD inclusive; required on first run, optional with --resume",
    )
    p.add_argument(
        "--end-date",
        required=False,
        help="end date YYYY-MM-DD inclusive; defaults to today",
    )
    p.add_argument("--page-size", type=int, default=2000)
    p.add_argument(
        "--max-pages-per-window",
        type=int,
        default=10000,
        help="safety cap to avoid infinite paging in one window",
    )
    p.add_argument(
        "--sleep-between-pages",
        type=float,
        default=0.0,
        help="seconds to sleep between page requests; default 0",
    )

    p.add_argument(
        "--truncate",
        action="store_true",
        help="TRUNCATE target table before sync (resets id sequence)",
    )
    p.add_argument(
        "--confirm-truncate",
        action="store_true",
        help="must be combined with --truncate to actually truncate (safety switch)",
    )

    p.add_argument(
        "--resume",
        action="store_true",
        help="resume from progress file; will not truncate",
    )
    p.add_argument(
        "--progress-file",
        default="zq_full_resync_progress.json",
    )
    p.add_argument(
        "--log-file",
        default="zq_full_resync.log",
    )

    p.add_argument(
        "--dry-run",
        action="store_true",
        help="print actions without writing DB or truncating",
    )

    return p.parse_args(argv)


def setup_logging(log_file):
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    handlers = [logging.StreamHandler(sys.stdout)]
    try:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    except OSError as exc:
        sys.stderr.write(f"warn: cannot open log file {log_file}: {exc}\n")
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


# ---------- time slicing ----------

def parse_iso_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def iter_month_windows(start, end):
    if start > end:
        return
    cursor = start.replace(day=1)
    while cursor <= end:
        if cursor.month == 12:
            next_first = date(cursor.year + 1, 1, 1)
        else:
            next_first = date(cursor.year, cursor.month + 1, 1)
        window_end = min(next_first - timedelta(days=1), end)
        window_start = max(cursor, start)
        yield window_start, window_end
        cursor = next_first


def fmt_begin(d):
    return f"{d.strftime('%Y-%m-%d')} 00:00:00"


def fmt_end(d):
    return f"{d.strftime('%Y-%m-%d')} 23:59:59"


def window_key(start, end):
    return f"{start.isoformat()}_{end.isoformat()}"


# ---------- progress file ----------

@dataclass
class Progress:
    path: str
    started_at: str
    completed_windows: list
    last_window: Any
    total_fetched: int
    total_written: int

    @classmethod
    def load_or_init(cls, path):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls(
                path=path,
                started_at=data.get("started_at") or datetime.now().isoformat(),
                completed_windows=list(data.get("completed_windows") or []),
                last_window=data.get("last_window"),
                total_fetched=int(data.get("total_fetched") or 0),
                total_written=int(data.get("total_written") or 0),
            )
        return cls(
            path=path,
            started_at=datetime.now().isoformat(),
            completed_windows=[],
            last_window=None,
            total_fetched=0,
            total_written=0,
        )

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "started_at": self.started_at,
                    "completed_windows": self.completed_windows,
                    "last_window": self.last_window,
                    "total_fetched": self.total_fetched,
                    "total_written": self.total_written,
                    "updated_at": datetime.now().isoformat(),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        os.replace(tmp, self.path)


# ---------- source: login + paging ----------

class SourceClient:
    def __init__(self, login_url, api_url, username, password):
        self.login_url = login_url
        self.api_url = api_url
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def login(self):
        LOGGER.info("login -> %s as %s", self.login_url, self.username)
        resp = self._request(
            "POST",
            self.login_url,
            timeout=LOGIN_TIMEOUT,
            data={
                "username": self.username,
                "password": self.password,
                "rememberMe": "true",
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
            },
        )
        try:
            body = resp.json()
        except ValueError as exc:
            raise RuntimeError(f"login response not json: {resp.text[:200]}") from exc
        ok = (
            body.get("code") in (0, 200)
            or body.get("success") is True
            or body.get("msg") == "操作成功"
            or "token" in body
        )
        if not ok:
            raise RuntimeError(f"login failed: {body}")
        token = body.get("token")
        if not token and isinstance(body.get("data"), dict):
            token = body["data"].get("token")
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
            LOGGER.info("login ok, token attached")
        else:
            LOGGER.info("login ok, cookie-based session")

    def fetch_window(self, begin_date, end_date, page_size, max_pages, sleep_between):
        page_num = 1
        total_in_window = 0
        while page_num <= max_pages:
            params = self._build_params(begin_date, end_date, page_size, page_num)
            LOGGER.info(
                "fetch %s ~ %s page=%s pageSize=%s",
                begin_date,
                end_date,
                page_num,
                page_size,
            )
            page = self._fetch_page(params)
            rows = page["rows"]
            total = page["total"]
            if not rows:
                LOGGER.info("empty page, window done")
                break
            yield rows
            total_in_window += len(rows)
            if len(rows) < page_size:
                break
            if total and total_in_window >= total:
                break
            page_num += 1
            if sleep_between > 0:
                time.sleep(sleep_between)
        LOGGER.info("window %s ~ %s fetched=%s", begin_date, end_date, total_in_window)

    def _build_params(self, begin_date, end_date, page_size, page_num):
        return {
            "params[colArray]": "",
            "beginDate": begin_date,
            "endDate": end_date,
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
            "pageSize": str(page_size),
            "pageNum": str(page_num),
            "orderByColumn": "callTime",
            "isAsc": "desc",
        }

    def _fetch_page(self, params):
        resp = self._request("POST", self.api_url, timeout=REQUEST_TIMEOUT, data=params)
        try:
            body = resp.json()
        except ValueError as exc:
            raise RuntimeError(f"case/list response not json: {resp.text[:200]}") from exc
        if body.get("code") != 0:
            raise RuntimeError(f"case/list failed: {body.get('msg') or body}")
        rows = body.get("rows") or []
        if not isinstance(rows, list):
            rows = []
        return {"rows": rows, "total": int(body.get("total") or 0)}

    def _request(self, method, url, **kwargs):
        last_exc = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return self.session.request(method, url, **kwargs)
            except requests.RequestException as exc:
                last_exc = exc
                wait = RETRY_BASE_DELAY * attempt
                LOGGER.warning("request failed (%s/%s): %s, retry in %ss", attempt, MAX_RETRIES, exc, wait)
                time.sleep(wait)
        raise RuntimeError(f"request failed after {MAX_RETRIES} retries: {last_exc}")


# ---------- target DB ----------

class TargetDB:
    def __init__(self, host, port, dbname, user, password, schema, table, dry_run=False):
        self.host = host
        self.port = port
        self.dbname = dbname
        self.user = user
        self.password = password
        self.schema = schema
        self.table = table
        self.dry_run = dry_run
        self.conn = None
        self._existing_columns = None

    def connect(self):
        if self.dry_run:
            LOGGER.info("[dry-run] skip db connect")
            return
        LOGGER.info("connect db %s:%s/%s schema=%s", self.host, self.port, self.dbname, self.schema)
        self.conn = psycopg2.connect(
            host=self.host,
            port=self.port,
            database=self.dbname,
            user=self.user,
            password=self.password,
            options=f"-c search_path={self.schema}",
        )
        self.conn.autocommit = True

    def close(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def truncate(self):
        if self.dry_run:
            LOGGER.warning("[dry-run] skip TRUNCATE %s.%s", self.schema, self.table)
            return
        LOGGER.warning("TRUNCATE %s.%s RESTART IDENTITY", self.schema, self.table)
        with self.conn.cursor() as cur:
            cur.execute(f'TRUNCATE TABLE "{self.schema}"."{self.table}" RESTART IDENTITY')
        self._existing_columns = None

    def ensure_table(self, sample_row):
        if self.dry_run:
            LOGGER.info("[dry-run] skip ensure_table; sample fields=%s", list(sample_row.keys()))
            return
        cols = []
        cols.append('"id" SERIAL PRIMARY KEY')
        seen_caseno = False
        for k in sample_row.keys():
            kl = k.lower()
            if kl == "id":
                continue
            if kl == "caseno":
                cols.append('"caseno" TEXT UNIQUE NOT NULL')
                seen_caseno = True
            else:
                cols.append(f'"{kl}" TEXT')
        if not seen_caseno:
            cols.append('"caseno" TEXT UNIQUE NOT NULL')
        cols.append('"created_at" TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        cols.append('"updated_at" TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        body = ",\n  ".join(cols)
        ddl = f'CREATE TABLE IF NOT EXISTS "{self.schema}"."{self.table}" (\n  {body}\n)'
        with self.conn.cursor() as cur:
            cur.execute(ddl)
            cur.execute(
                f'CREATE INDEX IF NOT EXISTS idx_{self.table}_caseno '
                f'ON "{self.schema}"."{self.table}"(caseno)'
            )
            cur.execute(
                f'CREATE INDEX IF NOT EXISTS idx_{self.table}_created_at '
                f'ON "{self.schema}"."{self.table}"(created_at)'
            )
        self._existing_columns = self._load_columns()
        LOGGER.info("ensure table ok, existing cols=%s", len(self._existing_columns))

    def ensure_columns(self, fields):
        if self.dry_run:
            return
        if self._existing_columns is None:
            self._existing_columns = self._load_columns()
        for raw in fields:
            f = raw.lower()
            if f in self._existing_columns:
                continue
            if f == "caseno":
                ddl = f'ALTER TABLE "{self.schema}"."{self.table}" ADD COLUMN IF NOT EXISTS "caseno" TEXT UNIQUE'
            else:
                ddl = f'ALTER TABLE "{self.schema}"."{self.table}" ADD COLUMN IF NOT EXISTS "{f}" TEXT'
            try:
                with self.conn.cursor() as cur:
                    cur.execute(ddl)
                self._existing_columns.add(f)
                LOGGER.info("added column %s", f)
            except Exception as exc:
                LOGGER.warning("add column %s failed: %s", f, exc)

    def _load_columns(self):
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                """,
                (self.schema, self.table),
            )
            return {row[0] for row in cur.fetchall()}

    def upsert_batch(self, rows):
        if not rows:
            return 0
        if self.dry_run:
            LOGGER.info("[dry-run] would upsert %s rows", len(rows))
            return len(rows)

        all_keys = []
        seen = set()
        for r in rows:
            for k in r.keys():
                kl = k.lower()
                if kl in ("id", "created_at", "updated_at"):
                    continue
                if kl not in seen:
                    seen.add(kl)
                    all_keys.append(kl)
        self.ensure_columns(all_keys)
        if "caseno" not in all_keys:
            LOGGER.warning("rows missing caseno field, skip")
            return 0

        col_list = ",".join(f'"{c}"' for c in all_keys)
        non_key_cols = [c for c in all_keys if c != "caseno"]
        set_exprs = [f'"{c}" = EXCLUDED."{c}"' for c in non_key_cols]
        set_exprs.append('"updated_at" = CURRENT_TIMESTAMP')
        update_clause = ",".join(set_exprs)

        if "updatetime" in all_keys:
            guard = (
                f'WHERE "{self.table}".updatetime IS NULL '
                f'OR EXCLUDED.updatetime >= "{self.table}".updatetime'
            )
        else:
            guard = ""

        sql = (
            f'INSERT INTO "{self.schema}"."{self.table}" ({col_list}) VALUES %s '
            f'ON CONFLICT (caseno) DO UPDATE SET {update_clause} {guard}'
        )

        values = []
        for r in rows:
            row_lower = {k.lower(): v for k, v in r.items()}
            case_no = row_lower.get("caseno")
            if not case_no:
                continue
            tup = tuple(_to_text(row_lower.get(c)) for c in all_keys)
            values.append(tup)

        if not values:
            return 0

        written = 0
        with self.conn.cursor() as cur:
            for i in range(0, len(values), DB_BATCH_SIZE):
                chunk = values[i : i + DB_BATCH_SIZE]
                execute_values(cur, sql, chunk, page_size=DB_BATCH_SIZE)
                written += len(chunk)
        return written


def _to_text(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


# ---------- main ----------

def _validate_args(args):
    missing = []
    for name, val in [
        ("--username", args.username),
        ("--password", args.password),
        ("--db-host", args.db_host),
        ("--db-name", args.db_name),
        ("--db-user", args.db_user),
        ("--db-password", args.db_password),
        ("--db-schema", args.db_schema),
    ]:
        if not val:
            missing.append(name)
    if missing:
        raise SystemExit(f"missing required args: {', '.join(missing)}")

    if args.truncate and not args.confirm_truncate:
        raise SystemExit("--truncate requires --confirm-truncate")

    if not args.start_date and not args.resume:
        raise SystemExit("--start-date is required on first run (or use --resume)")


def _resolve_date_range(args, progress):
    today = datetime.now().date()
    end = parse_iso_date(args.end_date) if args.end_date else today

    if args.start_date:
        start = parse_iso_date(args.start_date)
    else:
        # resume mode without explicit start: derive from last completed window
        if progress.completed_windows:
            last = progress.completed_windows[-1]
            # window keys look like "2024-01-01_2024-01-31"; use the start of that window
            try:
                start_str = last.split("_", 1)[0]
                start = parse_iso_date(start_str)
            except Exception:
                raise SystemExit(
                    "cannot infer --start-date from progress file, please pass it explicitly"
                )
        else:
            raise SystemExit("--start-date required when progress file is empty")
    return start, end


def main(argv=None):
    args = parse_args(argv)
    setup_logging(args.log_file)
    _validate_args(args)

    progress = Progress.load_or_init(args.progress_file)
    start, end = _resolve_date_range(args, progress)
    LOGGER.info(
        "config: range=%s~%s page_size=%s schema=%s table=%s dry_run=%s resume=%s",
        start,
        end,
        args.page_size,
        args.db_schema,
        args.table_name,
        args.dry_run,
        args.resume,
    )

    src = SourceClient(args.login_url, args.api_url, args.username, args.password)
    src.login()

    db = TargetDB(
        host=args.db_host,
        port=args.db_port,
        dbname=args.db_name,
        user=args.db_user,
        password=args.db_password,
        schema=args.db_schema,
        table=args.table_name,
        dry_run=args.dry_run,
    )
    db.connect()

    try:
        if args.truncate and not args.resume:
            db.truncate()
            # truncate invalidates progress; reset
            progress.completed_windows = []
            progress.last_window = None
            progress.save()
        elif args.truncate and args.resume:
            LOGGER.warning("--truncate ignored because --resume is set")

        ensured_table = False

        for wstart, wend in iter_month_windows(start, end):
            wkey = window_key(wstart, wend)
            if wkey in progress.completed_windows:
                LOGGER.info("skip window %s (already done)", wkey)
                continue

            progress.last_window = wkey
            progress.save()

            window_fetched = 0
            window_written = 0

            for batch in src.fetch_window(
                begin_date=fmt_begin(wstart),
                end_date=fmt_end(wend),
                page_size=args.page_size,
                max_pages=args.max_pages_per_window,
                sleep_between=args.sleep_between_pages,
            ):
                window_fetched += len(batch)
                if not ensured_table and not args.dry_run:
                    db.ensure_table(batch[0])
                    ensured_table = True
                written = db.upsert_batch(batch)
                window_written += written
                progress.total_fetched += len(batch)
                progress.total_written += written
                progress.save()

            progress.completed_windows.append(wkey)
            progress.save()
            LOGGER.info(
                "window %s done fetched=%s written=%s grand_total fetched=%s written=%s",
                wkey,
                window_fetched,
                window_written,
                progress.total_fetched,
                progress.total_written,
            )

        LOGGER.info(
            "ALL DONE. total_fetched=%s total_written=%s windows=%s",
            progress.total_fetched,
            progress.total_written,
            len(progress.completed_windows),
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
