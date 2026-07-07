#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
巡防排班 crossDayList 全量回填(手动一次性执行)
================================================

在**内网**把「智慧可视化指挥调度平台」`dutySchedule/crossDayList` 的排班数据
从起始日期(默认 2024-12-01)回填到今天, UPSERT 进 `ywdata.zq_kshddpt_zxzgl`
(唯一键 `scheduleId`, 与 legacy/data_scraper_multi.py 写同一张表、同一格式)。

为什么按天开窗
--------------
压测(见 ../../docs/README.md)证明: 接口卡死的根因是**单请求返回行数太多**
(≈10ms/行, 5000 行 50s, 1 万行直接 504), 而**时间范围本身很便宜**。
所以这里**一天一个窗口**(begin=当天 00:00:00, end=当天 23:59:59, 单日约 1700 行),
每个窗口用 `pageSize=500` 翻页(每页约 6s、offset 浅), 永远不会超过一天 → 不卡死。
多天窗口并发拉取以缩短总时长; DB 写入串行在主线程、按天断点续跑。

用法
----
    python3 xunfang_backfill.py \
        --db-host 10.x.x.x --db-port 54321 --db-name yfywk \
        --db-user XXX --db-password XXX --db-schema ywdata \
        --start-date 2024-12-01

    # 崩溃/中断后原样重跑, 自动跳过已完成的天:
    python3 xunfang_backfill.py [同样参数] --resume

    # 只拉取落成 JSONL、先不写库:
    python3 xunfang_backfill.py --no-db --dump-jsonl ./xunfang_dump.jsonl --start-date 2024-12-01

认证复用抓包密文(见文件末 DEFAULT_PASSWORD_ENC), 无需明文; 也可 --cookie 覆盖。
依赖: requests + psycopg2(psycopg2-binary)。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterator, List, Optional, Tuple

try:
    import requests
except ImportError:
    sys.stderr.write("缺少依赖: requests (pip install requests)\n")
    raise

try:
    import psycopg2
    from psycopg2 import sql
    from psycopg2.extras import execute_values
except ImportError:
    sys.stderr.write("缺少依赖: psycopg2 (pip install psycopg2-binary)\n")
    raise


LOGGER = logging.getLogger("xunfang_backfill")

DEFAULT_BASE = "http://68.253.2.107/zhksh"
DEFAULT_USERNAME = "270378"
# 客户端加密后的口令密文(AES 单块, 对固定账号确定); 见 ../../docs/README.md
DEFAULT_PASSWORD_ENC = "IIhlt+k0TQ06d6PUm4yV+Q=="
DEFAULT_TABLE = "zq_kshddpt_zxzgl"
DEFAULT_SCHEMA = "ywdata"
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
#  CLI
# ══════════════════════════════════════════════════════════════

def parse_args(argv=None):
    p = argparse.ArgumentParser(description="巡防 crossDayList 全量回填")
    # 认证 / 接口
    p.add_argument("--base", default=os.environ.get("XF_BASE", DEFAULT_BASE),
                   help="站点根, 默认 %(default)s")
    p.add_argument("--username", default=os.environ.get("XF_USERNAME", DEFAULT_USERNAME))
    p.add_argument("--password-enc",
                   default=os.environ.get("XF_PASSWORD_ENC", DEFAULT_PASSWORD_ENC),
                   help="客户端加密后的口令密文")
    p.add_argument("--cookie", default=os.environ.get("XF_COOKIE", ""),
                   help="直接贴 Cookie 跳过登录(应急)")
    # 时间范围
    p.add_argument("--start-date", default=os.environ.get("XF_START_DATE", "2024-12-01"),
                   help="起始日期 YYYY-MM-DD(含), 默认 2024-12-01")
    p.add_argument("--end-date", default=os.environ.get("XF_END_DATE", ""),
                   help="结束日期 YYYY-MM-DD(含), 默认今天")
    # 抓取参数
    p.add_argument("--page-size", type=int,
                   default=int(os.environ.get("XF_PAGE_SIZE", "500")),
                   help="每页行数(压测建议<=500), 默认 %(default)s")
    p.add_argument("--concurrency", type=int,
                   default=int(os.environ.get("XF_CONCURRENCY", "8")),
                   help="并发拉取的天窗口数, 默认 %(default)s")
    p.add_argument("--max-pages-per-day", type=int, default=200,
                   help="单日翻页安全上限")
    p.add_argument("--timeout", type=int, default=REQUEST_TIMEOUT)
    # DB
    p.add_argument("--db-host", default=_env_first("XF_DB_HOST", "KINGBASE_HOST", "MULTI_DB_HOST"))
    p.add_argument("--db-port", type=int,
                   default=int(_env_first("XF_DB_PORT", "KINGBASE_PORT", "MULTI_DB_PORT", default="54321")))
    p.add_argument("--db-name", default=_env_first("XF_DB_NAME", "KINGBASE_DBNAME", "MULTI_DB_NAME"))
    p.add_argument("--db-user", default=_env_first("XF_DB_USER", "KINGBASE_USER", "MULTI_DB_USER"))
    p.add_argument("--db-password", default=_env_first("XF_DB_PASSWORD", "KINGBASE_PASSWORD", "MULTI_DB_PASSWORD"))
    p.add_argument("--db-schema", default=os.environ.get("XF_DB_SCHEMA", DEFAULT_SCHEMA))
    p.add_argument("--table-name", default=os.environ.get("XF_TABLE", DEFAULT_TABLE))
    # 运行控制
    p.add_argument("--no-db", action="store_true", help="不写库(配合 --dump-jsonl)")
    p.add_argument("--dump-jsonl", default="", help="同时把每行落成 JSONL 备份文件")
    p.add_argument("--resume", action="store_true", help="从进度文件断点续跑")
    p.add_argument("--progress-file", default="xunfang_backfill_progress.json")
    p.add_argument("--log-file", default="xunfang_backfill.log")
    p.add_argument("--dry-run", action="store_true", help="只拉取不写库、不落文件")
    return p.parse_args(argv)


def _env_first(*names: str, default: str = "") -> str:
    for n in names:
        v = (os.environ.get(n) or "").strip()
        if v:
            return v
    return default


def setup_logging(log_file: str):
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    except OSError as exc:
        sys.stderr.write(f"warn: 无法打开日志文件 {log_file}: {exc}\n")
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


# ══════════════════════════════════════════════════════════════
#  时间开窗(按天)
# ══════════════════════════════════════════════════════════════

def parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def iter_days(start: date, end: date) -> Iterator[date]:
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def day_window(d: date) -> Tuple[str, str]:
    return (f"{d.isoformat()} 00:00:00", f"{d.isoformat()} 23:59:59")


# ══════════════════════════════════════════════════════════════
#  进度文件(按天断点)
# ══════════════════════════════════════════════════════════════

class Progress:
    def __init__(self, path: str, data: Optional[Dict[str, Any]] = None):
        self.path = path
        data = data or {}
        self.started_at = data.get("started_at") or datetime.now().isoformat()
        self.completed_days = set(data.get("completed_days") or [])
        self.total_fetched = int(data.get("total_fetched") or 0)
        self.total_written = int(data.get("total_written") or 0)

    @classmethod
    def load_or_init(cls, path: str) -> "Progress":
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return cls(path, json.load(f))
        return cls(path)

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({
                "started_at": self.started_at,
                "completed_days": sorted(self.completed_days),
                "total_fetched": self.total_fetched,
                "total_written": self.total_written,
                "updated_at": datetime.now().isoformat(),
            }, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)


# ══════════════════════════════════════════════════════════════
#  数据源: 登录 + 按天翻页
# ══════════════════════════════════════════════════════════════

class SourceClient:
    def __init__(self, base: str, username: str, password_enc: str,
                 cookie: str, timeout: int):
        self.base = base.rstrip("/")
        self.username = username
        self.password_enc = password_enc
        self.cookie = cookie.strip()
        self.timeout = timeout
        origin = urllib.parse.urlsplit(self.base)
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.session.headers["Origin"] = f"{origin.scheme}://{origin.netloc}"
        self.session.headers["Referer"] = f"{self.base}/dutySchedule"
        if self.cookie:
            self.session.headers["Cookie"] = self.cookie

    def login(self):
        if self.cookie:
            LOGGER.info("使用 --cookie 覆盖, 跳过账号登录")
            return
        # 先 GET 登录页拿 JSESSIONID
        try:
            self.session.get(f"{self.base}/login", timeout=LOGIN_TIMEOUT)
        except requests.RequestException as exc:
            LOGGER.info("GET /login 提示(可忽略): %s", exc)
        LOGGER.info("login -> %s/login as %s", self.base, self.username)
        resp = self.session.post(
            f"{self.base}/login",
            data={
                "username": self.username,
                "password": self.password_enc,
                "rememberMe": "true",
                "isPkiLogin": "false",
                "isAccLogin": "true",
                "isSmsLogin": "false",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
            timeout=LOGIN_TIMEOUT,
        )
        ok = resp.status_code == 200
        try:
            body = resp.json()
            code = body.get("code")
            if code is not None:
                ok = code in (0, 200)
        except ValueError:
            pass  # 登录接口可能返回空体, 靠首个抓取验证
        if not ok:
            raise RuntimeError(
                f"登录疑似失败 (HTTP {resp.status_code}): {resp.text[:200]}; "
                f"请更新 --password-enc 或改用 --cookie")
        LOGGER.info("登录请求已提交 (HTTP %s)", resp.status_code)

    def fetch_day(self, d: date, page_size: int, max_pages: int) -> List[Dict[str, Any]]:
        """把某一天全部行翻页取回(list[dict])。异常向上抛, 由调用方决定重试/记录。"""
        begin, end = day_window(d)
        rows: List[Dict[str, Any]] = []
        page_num = 1
        while page_num <= max_pages:
            page = self._fetch_page(begin, end, page_size, page_num)
            batch = page["rows"]
            total = page["total"]
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < page_size:
                break
            if total and len(rows) >= total:
                break
            page_num += 1
        return rows

    def _fetch_page(self, begin: str, end: str, page_size: int,
                    page_num: int) -> Dict[str, Any]:
        params = build_params(begin, end, page_size, page_num)
        resp = self._request("POST", f"{self.base}/dutySchedule/crossDayList", data=params)
        try:
            body = resp.json()
        except ValueError as exc:
            raise RuntimeError(
                f"crossDayList 非 JSON(疑似掉登录): {resp.text[:200]}") from exc
        if not isinstance(body, dict) or ("rows" not in body and "total" not in body):
            raise RuntimeError(f"crossDayList 响应异常: {str(body)[:200]}")
        rows = body.get("rows") or []
        if not isinstance(rows, list):
            rows = []
        return {"rows": rows, "total": int(body.get("total") or 0)}

    def _request(self, method: str, url: str, **kwargs) -> "requests.Response":
        last_exc: Optional[Exception] = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.request(method, url, timeout=self.timeout, **kwargs)
                if resp.status_code >= 500:
                    raise RuntimeError(f"HTTP {resp.status_code}")
                return resp
            except (requests.RequestException, RuntimeError) as exc:
                last_exc = exc
                wait = RETRY_BASE_DELAY * attempt
                LOGGER.warning("请求失败 (%s/%s): %s, %ss 后重试", attempt, MAX_RETRIES, exc, wait)
                time.sleep(wait)
        raise RuntimeError(f"重试 {MAX_RETRIES} 次仍失败: {last_exc}")


def build_params(begin_time: str, end_time: str,
                 page_size: int, page_num: int) -> Dict[str, str]:
    """crossDayList 表单(字段照抄 HAR 默认)。"""
    return {
        "pageSize": str(page_size),
        "pageNum": str(page_num),
        "orderByColumn": "startTime",
        "isAsc": "asc",
        "keywords": "",
        "deploymentType": "",
        "deploymentId": "",
        "deploymentName": "",
        "scheduleDate": "",
        "params[beginTime]": begin_time,
        "params[endTime]": end_time,
        "deptId": "",
        "deptName": "全部",
        "schemeId": "",
        "shiftId": "",
        "userTypeCode": "",
        "dutyTypeCode": "",
        "dutyTypeName": "",
        "policeCategory": "",
        "userId": "",
        "userName": "",
    }


# ══════════════════════════════════════════════════════════════
#  目标库(与 legacy/data_scraper_multi.py 同格式: 保留 camelCase 列名, 全 TEXT)
# ══════════════════════════════════════════════════════════════

def _to_text(v: Any) -> str:
    """与 legacy/data_scraper_multi.py 一致: None -> "", 其余 str(v)(嵌套用 Python repr)。"""
    return "" if v is None else str(v)


class TargetDB:
    def __init__(self, host, port, dbname, user, password, schema, table,
                 unique_key=UNIQUE_KEY, dry_run=False):
        self.host, self.port, self.dbname = host, port, dbname
        self.user, self.password = user, password
        self.schema, self.table, self.unique_key = schema, table, unique_key
        self.dry_run = dry_run
        self.conn = None
        self._known: Optional[set] = None  # 已存在列缓存

    @property
    def _tbl(self):
        return sql.SQL("{}.{}").format(sql.Identifier(self.schema), sql.Identifier(self.table))

    def connect(self):
        if self.dry_run:
            LOGGER.info("[dry-run] 跳过连库")
            return
        LOGGER.info("连库 %s:%s/%s schema=%s table=%s",
                    self.host, self.port, self.dbname, self.schema, self.table)
        self.conn = psycopg2.connect(host=self.host, port=self.port, dbname=self.dbname,
                                     user=self.user, password=self.password)
        self.conn.autocommit = True

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def _load_columns(self) -> set:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s",
                (self.schema, self.table))
            return {r[0] for r in cur.fetchall()}

    def _ensure_base(self):
        """建 schema/表/唯一约束(幂等), 并载入已存在列到缓存。仅首次。"""
        with self.conn.cursor() as cur:
            cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(self.schema)))
            cur.execute(sql.SQL("CREATE TABLE IF NOT EXISTS {} ( {} TEXT )").format(
                self._tbl, sql.Identifier(self.unique_key)))
            idx_name = f"{self.table}_{self.unique_key}_key"
            cur.execute(
                sql.SQL("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint "
                        "WHERE conname = %s) THEN ALTER TABLE {} ADD CONSTRAINT {} "
                        "UNIQUE ({}); END IF; END $$;").format(
                    self._tbl, sql.Identifier(idx_name), sql.Identifier(self.unique_key)),
                (idx_name,))
        self._known = self._load_columns()

    def ensure_columns(self, keys) -> None:
        """确保 keys 里每一列都存在(只对缓存里没有的列执行 ALTER, 幂等)。"""
        if self.dry_run:
            return
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
        if self.dry_run:
            return len(rows)
        all_keys = sorted(set().union(*[r.keys() for r in rows]))
        if self.unique_key not in all_keys:
            LOGGER.warning("批次缺少 %s, 跳过", self.unique_key)
            return 0
        # 关键: 每批次都补齐缺失列(缓存后只 ALTER 新列), 避免后到的字段(如 userPostName)缺列报错
        self.ensure_columns(all_keys)
        cols_ident = [sql.Identifier(k) for k in all_keys]
        set_clause = [sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(k), sql.Identifier(k))
                      for k in all_keys if k != self.unique_key]
        insert_sql = sql.SQL(
            "INSERT INTO {} ({}) VALUES %s ON CONFLICT ({}) DO UPDATE SET {}").format(
            self._tbl, sql.SQL(", ").join(cols_ident), sql.Identifier(self.unique_key),
            sql.SQL(", ").join(set_clause) if set_clause else sql.SQL("/* noop */"))
        values = [[_to_text(r.get(k)) for k in all_keys] for r in rows]
        written = 0
        with self.conn.cursor() as cur:
            for i in range(0, len(values), DB_BATCH_SIZE):
                chunk = values[i:i + DB_BATCH_SIZE]
                execute_values(cur, insert_sql, chunk, page_size=DB_BATCH_SIZE)
                written += len(chunk)
        return written


def dedup_rows(rows: List[Dict[str, Any]], unique_key: str) -> List[Dict[str, Any]]:
    seen: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        key = r.get(unique_key)
        if key is None or str(key).strip() == "":
            continue
        seen[str(key)] = r
    return list(seen.values())


# ══════════════════════════════════════════════════════════════
#  主流程
# ══════════════════════════════════════════════════════════════

def _validate(args):
    if not args.no_db and not args.dry_run:
        missing = [n for n, v in [
            ("--db-host", args.db_host), ("--db-name", args.db_name),
            ("--db-user", args.db_user), ("--db-password", args.db_password),
        ] if not v]
        if missing:
            raise SystemExit(f"缺少必填参数: {', '.join(missing)} (或用 --no-db 只落文件)")


def main(argv=None) -> int:
    args = parse_args(argv)
    setup_logging(args.log_file)
    _validate(args)

    start = parse_iso_date(args.start_date)
    end = parse_iso_date(args.end_date) if args.end_date else datetime.now().date()
    if start > end:
        raise SystemExit(f"start-date {start} 晚于 end-date {end}")

    progress = Progress.load_or_init(args.progress_file)
    if not args.resume:
        # 非续跑: 忽略旧进度(但不删文件, 便于排查)
        progress.completed_days = set()
    all_days = [d for d in iter_days(start, end) if d.isoformat() not in progress.completed_days]
    LOGGER.info("范围 %s ~ %s, 待处理 %s 天(已完成 %s 天), page_size=%s 并发=%s",
                start, end, len(all_days), len(progress.completed_days),
                args.page_size, args.concurrency)

    src = SourceClient(args.base, args.username, args.password_enc, args.cookie, args.timeout)
    src.login()

    db = TargetDB(args.db_host, args.db_port, args.db_name, args.db_user, args.db_password,
                  args.db_schema, args.table_name, dry_run=(args.dry_run or args.no_db))
    db.connect()

    dump_fp = None
    if args.dump_jsonl and not args.dry_run:
        dump_fp = open(args.dump_jsonl, "a", encoding="utf-8")

    failed_days: List[str] = []
    try:
        with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
            fut_to_day = {
                pool.submit(src.fetch_day, d, args.page_size, args.max_pages_per_day): d
                for d in all_days
            }
            done = 0
            for fut in as_completed(fut_to_day):
                d = fut_to_day[fut]
                try:
                    raw = fut.result()
                except Exception as exc:
                    LOGGER.error("天 %s 拉取失败: %s", d.isoformat(), exc)
                    failed_days.append(d.isoformat())
                    continue

                rows = dedup_rows(raw, UNIQUE_KEY)
                # DB 写入串行在主线程; upsert 内部按批次补齐缺失列
                written = db.upsert(rows)

                if dump_fp:
                    for r in rows:
                        dump_fp.write(json.dumps(r, ensure_ascii=False) + "\n")

                progress.completed_days.add(d.isoformat())
                progress.total_fetched += len(raw)
                progress.total_written += written
                progress.save()

                done += 1
                LOGGER.info("天 %s 完成: 拉取=%s 去重=%s 写入=%s | 进度 %s/%s 累计写入=%s",
                            d.isoformat(), len(raw), len(rows), written,
                            done, len(all_days), progress.total_written)
    finally:
        if dump_fp:
            dump_fp.close()
        db.close()

    LOGGER.info("=" * 60)
    LOGGER.info("全部完成: 累计拉取=%s 累计写入=%s 完成天数=%s 失败天数=%s",
                progress.total_fetched, progress.total_written,
                len(progress.completed_days), len(failed_days))
    if failed_days:
        LOGGER.warning("以下天失败, 可加 --resume 重跑补齐: %s", ", ".join(sorted(failed_days)))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
