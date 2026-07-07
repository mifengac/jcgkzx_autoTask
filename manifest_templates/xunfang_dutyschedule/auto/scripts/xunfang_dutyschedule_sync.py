#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
巡防排班 crossDayList 增量同步(平台自定义任务)
================================================

平台入口 run(context)。每次运行**重新拉取近端时间窗口**(默认 [今天-3, 今天+1] 天),
按天开窗 + pageSize 翻页, UPSERT 进 ywdata.zq_kshddpt_zxzgl(唯一键 scheduleId)。

为什么按天开窗 + 重拉近端窗口
------------------------------
- 压测证明接口卡死点是"单请求返回行数"(≈10ms/行), 时间范围本身很便宜;
  一天一窗口(约 1700 行)配 pageSize=500 翻页, 每页约 6s、offset 浅, 永不卡死。
- crossDayList 只能按排班时间(beginTime/endTime)过滤, 无法按 updateTime 增量,
  故每次重拉最近几天(覆盖新排班与被改动的排班), 靠 scheduleId UPSERT 去重刷新。

runtime_config / 环境变量(key -> env):
  xf_base                XF_BASE
  xf_username            XF_USERNAME
  xf_password_enc        XF_PASSWORD_ENC
  xf_cookie              XF_COOKIE            (可选, 覆盖登录)
  xf_lookback_days       XF_LOOKBACK_DAYS     (默认 3)
  xf_lookahead_days      XF_LOOKAHEAD_DAYS    (默认 1)
  xf_page_size           XF_PAGE_SIZE         (默认 500)
  xf_concurrency         XF_CONCURRENCY       (默认 4)
  xf_db_schema           XF_DB_SCHEMA         (默认 ywdata)
  xf_table               XF_TABLE             (默认 zq_kshddpt_zxzgl)
  DB: xf_db_host/port/name/user/password  (回退 KINGBASE_* / MULTI_DB_*)

依赖: requests + psycopg2。
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import requests
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values

try:
    from autotask_api.services.time_utils import now_shanghai
except ModuleNotFoundError:
    from zoneinfo import ZoneInfo

    def now_shanghai() -> datetime:
        return datetime.now(ZoneInfo("Asia/Shanghai"))


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOGGER = logging.getLogger("xunfang_sync")

DEFAULT_BASE = "http://68.253.2.107/zhksh"
DEFAULT_USERNAME = "270378"
DEFAULT_PASSWORD_ENC = "IIhlt+k0TQ06d6PUm4yV+Q=="
DEFAULT_SCHEMA = "ywdata"
DEFAULT_TABLE = "zq_kshddpt_zxzgl"
UNIQUE_KEY = "scheduleId"

REQUEST_TIMEOUT = 60
LOGIN_TIMEOUT = 30
MAX_RETRIES = 4
RETRY_BASE_DELAY = 3
DB_BATCH_SIZE = 500

DEFAULT_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
}


# ══════════════════════════════════════════════════════════════
#  环境变量解析
# ══════════════════════════════════════════════════════════════

def _env(name: str, default: Optional[str] = None) -> str:
    v = (os.environ.get(name) or "").strip()
    if v:
        return v
    if default is not None:
        return default
    raise ValueError(f"缺少环境变量 {name}")


def _env_first(*names: str, default: Optional[str] = None) -> str:
    for n in names:
        v = (os.environ.get(n) or "").strip()
        if v:
            return v
    if default is not None:
        return default
    raise ValueError(f"缺少环境变量: {'/'.join(names)}")


# runtime_config key -> 环境变量
_ENV_MAP = {
    "xf_base": "XF_BASE",
    "xf_username": "XF_USERNAME",
    "xf_password_enc": "XF_PASSWORD_ENC",
    "xf_cookie": "XF_COOKIE",
    "xf_lookback_days": "XF_LOOKBACK_DAYS",
    "xf_lookahead_days": "XF_LOOKAHEAD_DAYS",
    "xf_page_size": "XF_PAGE_SIZE",
    "xf_concurrency": "XF_CONCURRENCY",
    "xf_db_schema": "XF_DB_SCHEMA",
    "xf_table": "XF_TABLE",
    "xf_db_host": "XF_DB_HOST",
    "xf_db_port": "XF_DB_PORT",
    "xf_db_name": "XF_DB_NAME",
    "xf_db_user": "XF_DB_USER",
    "xf_db_password": "XF_DB_PASSWORD",
}


def _runtime_to_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


@contextmanager
def _tmp_env(rc: Dict[str, Any]):
    orig: Dict[str, Optional[str]] = {}
    try:
        for rk, ek in _ENV_MAP.items():
            if rk not in rc:
                continue
            orig[ek] = os.environ.get(ek)
            v = rc.get(rk)
            if v in (None, ""):
                os.environ.pop(ek, None)
            else:
                os.environ[ek] = _runtime_to_str(v)
        yield
    finally:
        for ek, v in orig.items():
            if v is None:
                os.environ.pop(ek, None)
            else:
                os.environ[ek] = v


# ══════════════════════════════════════════════════════════════
#  数据源: 登录 + 按天翻页  (与 manual/xunfang_backfill.py 同口径)
# ══════════════════════════════════════════════════════════════

def build_params(begin_time: str, end_time: str, page_size: int, page_num: int) -> Dict[str, str]:
    return {
        "pageSize": str(page_size), "pageNum": str(page_num),
        "orderByColumn": "startTime", "isAsc": "asc",
        "keywords": "", "deploymentType": "", "deploymentId": "", "deploymentName": "",
        "scheduleDate": "",
        "params[beginTime]": begin_time, "params[endTime]": end_time,
        "deptId": "", "deptName": "全部", "schemeId": "", "shiftId": "",
        "userTypeCode": "", "dutyTypeCode": "", "dutyTypeName": "",
        "policeCategory": "", "userId": "", "userName": "",
    }


def day_window(d: date) -> Tuple[str, str]:
    return (f"{d.isoformat()} 00:00:00", f"{d.isoformat()} 23:59:59")


class SourceClient:
    def __init__(self, base: str, username: str, password_enc: str, cookie: str):
        self.base = base.rstrip("/")
        self.username = username
        self.password_enc = password_enc
        self.cookie = (cookie or "").strip()
        origin = urllib.parse.urlsplit(self.base)
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.session.headers["Origin"] = f"{origin.scheme}://{origin.netloc}"
        self.session.headers["Referer"] = f"{self.base}/dutySchedule"
        if self.cookie:
            self.session.headers["Cookie"] = self.cookie

    def login(self):
        if self.cookie:
            LOGGER.info("使用 cookie 覆盖, 跳过账号登录")
            return
        try:
            self.session.get(f"{self.base}/login", timeout=LOGIN_TIMEOUT)
        except requests.RequestException as exc:
            LOGGER.info("GET /login 提示(可忽略): %s", exc)
        resp = self.session.post(
            f"{self.base}/login",
            data={"username": self.username, "password": self.password_enc,
                  "rememberMe": "true", "isPkiLogin": "false",
                  "isAccLogin": "true", "isSmsLogin": "false"},
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
            timeout=LOGIN_TIMEOUT)
        ok = resp.status_code == 200
        try:
            code = resp.json().get("code")
            if code is not None:
                ok = code in (0, 200)
        except ValueError:
            pass
        if not ok:
            raise RuntimeError(f"登录失败 (HTTP {resp.status_code}): {resp.text[:200]}")
        LOGGER.info("登录成功 (HTTP %s)", resp.status_code)

    def fetch_day(self, d: date, page_size: int, max_pages: int = 200) -> List[Dict[str, Any]]:
        begin, end = day_window(d)
        rows: List[Dict[str, Any]] = []
        page_num = 1
        while page_num <= max_pages:
            page = self._fetch_page(begin, end, page_size, page_num)
            batch = page["rows"]
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < page_size or (page["total"] and len(rows) >= page["total"]):
                break
            page_num += 1
        return rows

    def _fetch_page(self, begin, end, page_size, page_num) -> Dict[str, Any]:
        resp = self._request("POST", f"{self.base}/dutySchedule/crossDayList",
                             data=build_params(begin, end, page_size, page_num))
        try:
            body = resp.json()
        except ValueError as exc:
            raise RuntimeError(f"crossDayList 非 JSON(疑似掉登录): {resp.text[:200]}") from exc
        if not isinstance(body, dict) or ("rows" not in body and "total" not in body):
            raise RuntimeError(f"crossDayList 响应异常: {str(body)[:200]}")
        rows = body.get("rows") or []
        return {"rows": rows if isinstance(rows, list) else [],
                "total": int(body.get("total") or 0)}

    def _request(self, method, url, **kwargs) -> "requests.Response":
        last_exc: Optional[Exception] = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
                if resp.status_code >= 500:
                    raise RuntimeError(f"HTTP {resp.status_code}")
                return resp
            except (requests.RequestException, RuntimeError) as exc:
                last_exc = exc
                time.sleep(RETRY_BASE_DELAY * attempt)
        raise RuntimeError(f"重试 {MAX_RETRIES} 次仍失败: {last_exc}")


# ══════════════════════════════════════════════════════════════
#  目标库(camelCase 列, 全 TEXT, ON CONFLICT scheduleId)
# ══════════════════════════════════════════════════════════════

def _to_text(v: Any) -> str:
    return "" if v is None else str(v)


class TargetDB:
    def __init__(self, dsn: Dict[str, Any], schema: str, table: str, unique_key=UNIQUE_KEY):
        self.dsn = dsn
        self.schema, self.table, self.unique_key = schema, table, unique_key
        self.conn = None
        self._known: Optional[set] = None  # 已存在列缓存

    @property
    def _tbl(self):
        return sql.SQL("{}.{}").format(sql.Identifier(self.schema), sql.Identifier(self.table))

    def connect(self):
        self.conn = psycopg2.connect(**self.dsn)
        self.conn.autocommit = True

    def close(self):
        if self.conn:
            self.conn.close()

    def _load_columns(self) -> set:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s",
                (self.schema, self.table))
            return {r[0] for r in cur.fetchall()}

    def _ensure_base(self):
        with self.conn.cursor() as cur:
            cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(self.schema)))
            cur.execute(sql.SQL("CREATE TABLE IF NOT EXISTS {} ( {} TEXT )").format(
                self._tbl, sql.Identifier(self.unique_key)))
            idx = f"{self.table}_{self.unique_key}_key"
            cur.execute(
                sql.SQL("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint "
                        "WHERE conname = %s) THEN ALTER TABLE {} ADD CONSTRAINT {} "
                        "UNIQUE ({}); END IF; END $$;").format(
                    self._tbl, sql.Identifier(idx), sql.Identifier(self.unique_key)), (idx,))
        self._known = self._load_columns()

    def ensure_columns(self, keys) -> None:
        """确保 keys 每列都存在(只对缓存里没有的列 ALTER, 幂等)。"""
        if self._known is None:
            self._ensure_base()
        missing = [k for k in keys if k not in self._known]
        if not missing:
            return
        with self.conn.cursor() as cur:
            for k in missing:
                cur.execute(sql.SQL("ALTER TABLE {} ADD COLUMN IF NOT EXISTS {} TEXT")
                            .format(self._tbl, sql.Identifier(k)))
                self._known.add(k)
                LOGGER.info("新增列 %s", k)

    def upsert(self, rows: List[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        all_keys = sorted(set().union(*[r.keys() for r in rows]))
        if self.unique_key not in all_keys:
            return 0
        # 每批次补齐缺失列(缓存后只 ALTER 新列), 避免后到字段缺列报错
        self.ensure_columns(all_keys)
        cols = [sql.Identifier(k) for k in all_keys]
        set_clause = [sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(k), sql.Identifier(k))
                      for k in all_keys if k != self.unique_key]
        stmt = sql.SQL("INSERT INTO {} ({}) VALUES %s ON CONFLICT ({}) DO UPDATE SET {}").format(
            self._tbl, sql.SQL(", ").join(cols), sql.Identifier(self.unique_key),
            sql.SQL(", ").join(set_clause) if set_clause else sql.SQL("/* noop */"))
        values = [[_to_text(r.get(k)) for k in all_keys] for r in rows]
        written = 0
        with self.conn.cursor() as cur:
            for i in range(0, len(values), DB_BATCH_SIZE):
                chunk = values[i:i + DB_BATCH_SIZE]
                execute_values(cur, stmt, chunk, page_size=DB_BATCH_SIZE)
                written += len(chunk)
        return written


def _dsn_from_env() -> Dict[str, Any]:
    return {
        "host": _env_first("XF_DB_HOST", "KINGBASE_HOST", "MULTI_DB_HOST"),
        "port": int(_env_first("XF_DB_PORT", "KINGBASE_PORT", "MULTI_DB_PORT", default="54321")),
        "dbname": _env_first("XF_DB_NAME", "KINGBASE_DBNAME", "MULTI_DB_NAME"),
        "user": _env_first("XF_DB_USER", "KINGBASE_USER", "MULTI_DB_USER"),
        "password": _env_first("XF_DB_PASSWORD", "KINGBASE_PASSWORD", "MULTI_DB_PASSWORD"),
    }


def dedup_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        key = r.get(UNIQUE_KEY)
        if key is None or str(key).strip() == "":
            continue
        seen[str(key)] = r
    return list(seen.values())


# ══════════════════════════════════════════════════════════════
#  平台入口
# ══════════════════════════════════════════════════════════════

def run(context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    context = context or {}
    rc = context.get("runtime_config") or {}
    started = now_shanghai()

    with _tmp_env(rc):
        base = _env("XF_BASE", DEFAULT_BASE)
        username = _env("XF_USERNAME", DEFAULT_USERNAME)
        password_enc = _env("XF_PASSWORD_ENC", DEFAULT_PASSWORD_ENC)
        cookie = _env("XF_COOKIE", "")
        lookback = int(_env("XF_LOOKBACK_DAYS", "3"))
        lookahead = int(_env("XF_LOOKAHEAD_DAYS", "1"))
        page_size = int(_env("XF_PAGE_SIZE", "500"))
        concurrency = int(_env("XF_CONCURRENCY", "4"))
        schema = _env("XF_DB_SCHEMA", DEFAULT_SCHEMA)
        table = _env("XF_TABLE", DEFAULT_TABLE)
        dsn = _dsn_from_env()

        today = now_shanghai().date()
        days = [today - timedelta(days=n) for n in range(lookback, -lookahead - 1, -1)]
        LOGGER.info("增量窗口 %s ~ %s (%s 天), page_size=%s 并发=%s",
                    days[0], days[-1], len(days), page_size, concurrency)

        src = SourceClient(base, username, password_enc, cookie)
        src.login()
        db = TargetDB(dsn, schema, table)
        db.connect()

        total_fetched = 0
        total_written = 0
        failed: List[str] = []
        try:
            with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
                fut_to_day = {pool.submit(src.fetch_day, d, page_size): d for d in days}
                for fut in as_completed(fut_to_day):
                    d = fut_to_day[fut]
                    try:
                        raw = fut.result()
                    except Exception as exc:
                        LOGGER.error("天 %s 拉取失败: %s", d.isoformat(), exc)
                        failed.append(d.isoformat())
                        continue
                    rows = dedup_rows(raw)
                    written = db.upsert(rows)  # upsert 内部按批次补齐缺失列
                    total_fetched += len(raw)
                    total_written += written
                    LOGGER.info("天 %s: 拉取=%s 去重=%s 写入=%s",
                                d.isoformat(), len(raw), len(rows), written)
        finally:
            db.close()

    ended = now_shanghai()
    status = "success" if not failed else "partial_success"
    msg = (f"巡防排班增量同步完成: 窗口 {days[0]}~{days[-1]}, "
           f"拉取 {total_fetched} 条, 写入 {total_written} 条")
    if failed:
        msg += f", 失败 {len(failed)} 天({', '.join(failed)})"
    return [{
        "event_id": f"xf_{uuid4().hex}",
        "task_name": "xunfang_dutyschedule_sync",
        "target_table": f"{schema}.{table}",
        "status": status,
        "fetched_count": total_fetched,
        "written_count": total_written,
        "failed_days": failed,
        "window_start": days[0].isoformat(),
        "window_end": days[-1].isoformat(),
        "message_text": msg,
        "start_time": started.isoformat(),
        "end_time": ended.isoformat(),
    }]


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, default=str))
