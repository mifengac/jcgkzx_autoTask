#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monitor script for mental-illness-related case notifications.

Behavior:
1. Login and query recent case records from monitor API.
2. Filter records whose caseContents or replies contains mental-health keywords.
3. Resolve recipient mobiles (Kingbase first, optional SMS_MOBILES fallback).
4. Deduplicate by caseNo + mobile and send SMS through Oracle.
"""

import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests


DEFAULT_LOGIN_URL = "http://68.253.2.111/dsjfx/login"
DEFAULT_API_URL = "http://68.253.2.111/dsjfx/case/list"
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 2
DEFAULT_PAGE_SIZE = 500
MOBILE_PATTERN = re.compile(r"^1[3-9]\d{9}$")
MENTAL_CASE_PATTERN = re.compile(r"精神病|精神障碍|精神异常|精神发病|犯病|肇事肇祸")

CASE_SOURCE_CODE = (
    "0100,0101,0102,0103,0199,0200,0201,0202,0299,0400,0401,0402,0403,0404,"
    "0405,0499,0500,0600,0601,0602,0603,0604,0800,0801,0802,0900,0901,0902,"
    "0903,0904,0999,9900"
)
CASE_SOURCE_NAME = (
    "电话报警,110报警,122报警,5G视频报警,其他电话报警,亲临报警,亲临到所,扭送现行,"
    "其他亲临报警,物联报警,终端报警,技防报警,校园报警,公交报警,地铁报警,"
    "其他物联报警,短信报警,网络报警,视频报警,网语报警,自助报警,其他网络报警,"
    "异地转警,省内,省外,其他部门移送,12345推送,119推送,120推送,心理关爱热线,"
    "其他部门,其他报警方式"
)

BASE_PARAMS = {
    "params[startTime]": "",
    "params[endTime]": "",
    "caseSourceCode": CASE_SOURCE_CODE,
    "caseSourceName": CASE_SOURCE_NAME,
    "caseNo": "",
    "dutyDeptNo": "",
    "dutyDeptName": "全部",
    "callerPhone": "",
    "occurAddress": "",
    "charaNo": "",
    "chara": "全部",
    "callerPeopleName": "",
    "phoneAddress": "",
    "callerAddress": "",
    "oriCharaNo": "",
    "oriChara": "全部",
    "iniCharaNo": "",
    "iniChara": "全部",
    "fixCharaNo": "",
    "fixChara": "全部",
    "caseLevelName": "",
    "operatorName": "",
    "callerPeopleIdcard": "",
    "uploadAreaNo": "",
    "fixCaseSourceCode": "",
    "fixCaseSourceName": "全部",
    "dossierNo": "",
    "caseMarkNo": "",
    "caseMark": "",
    "firstOriCharaNo": "",
    "firstOriChara": "全部",
    "firstCharaNo": "",
    "firstChara": "全部",
    "handleResultNo": "",
    "pageSize": str(DEFAULT_PAGE_SIZE),
    "pageNum": "1",
    "orderByColumn": "alarmTime",
    "isAsc": "desc",
}


@dataclass
class Config:
    login_username: str
    login_password: str
    monitor_login_url: str
    monitor_api_url: str
    oracle_dsn: str
    oracle_user: str
    oracle_password: str
    oracle_client_lib_dir: Optional[str] = None
    sms_mobiles: List[str] = field(default_factory=list)
    sms_userid: str = ""
    sms_password: str = ""
    sms_userport: str = ""
    kg_target_xqdm: str = "445300"
    kg_target_rwzt: str = "涉精神病人"
    query_page_size: int = DEFAULT_PAGE_SIZE
    kingbase_host: Optional[str] = None
    kingbase_port: Optional[int] = None
    kingbase_dbname: Optional[str] = None
    kingbase_user: Optional[str] = None
    kingbase_password: Optional[str] = None

    def has_kingbase_config(self) -> bool:
        return all(
            [
                self.kingbase_host,
                self.kingbase_port is not None,
                self.kingbase_dbname,
                self.kingbase_user,
                self.kingbase_password,
            ]
        )


def _split_mobile_candidates(raw: Any) -> List[str]:
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    return [x.strip() for x in re.split(r"[,\s，；;]+", text) if x.strip()]


def normalize_mobile_list(raw_values: List[Any]) -> List[str]:
    mobiles: List[str] = []
    seen = set()
    for raw in raw_values:
        for candidate in _split_mobile_candidates(raw):
            if not MOBILE_PATTERN.fullmatch(candidate):
                continue
            if candidate in seen:
                continue
            seen.add(candidate)
            mobiles.append(candidate)
    return mobiles


def setup_logging() -> logging.Logger:
    log_dir = "/app/logs"
    os.makedirs(log_dir, exist_ok=True)

    today = datetime.now().strftime("%Y%m%d")
    log_file = os.path.join(log_dir, f"0306jsbrjq_monitor_{today}.log")

    logger = logging.getLogger("0306jsbrjq_monitor")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    console_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


def load_config_from_env() -> Config:
    mobiles = normalize_mobile_list([os.environ.get("SMS_MOBILES", "")])

    kingbase_host = (os.environ.get("KINGBASE_HOST") or "").strip() or None
    kingbase_dbname = (os.environ.get("KINGBASE_DBNAME") or "").strip() or None
    kingbase_user = (os.environ.get("KINGBASE_USER") or "").strip() or None
    kingbase_password = (os.environ.get("KINGBASE_PASSWORD") or "").strip() or None

    kingbase_port = None
    kingbase_port_raw = (os.environ.get("KINGBASE_PORT") or "").strip()
    if kingbase_port_raw:
        try:
            kingbase_port = int(kingbase_port_raw)
        except ValueError:
            kingbase_port = None

    page_size = DEFAULT_PAGE_SIZE
    page_size_raw = (
        os.environ.get("JSBRJQ_PAGE_SIZE")
        or os.environ.get("MONITOR_PAGE_SIZE")
        or ""
    ).strip()
    if page_size_raw:
        try:
            parsed_page_size = int(page_size_raw)
            if parsed_page_size > 0:
                page_size = parsed_page_size
        except ValueError:
            page_size = DEFAULT_PAGE_SIZE

    return Config(
        login_username=(
            os.environ.get("JSBRJQ_LOGIN_USERNAME")
            or os.environ.get("LOGIN_USERNAME")
            or ""
        ).strip(),
        login_password=(
            os.environ.get("JSBRJQ_LOGIN_PASSWORD")
            or os.environ.get("LOGIN_PASSWORD")
            or ""
        ).strip(),
        monitor_login_url=(
            os.environ.get("JSBRJQ_LOGIN_URL")
            or os.environ.get("MONITOR_LOGIN_URL")
            or DEFAULT_LOGIN_URL
        ).strip(),
        monitor_api_url=(
            os.environ.get("JSBRJQ_API_URL")
            or os.environ.get("MONITOR_API_URL")
            or DEFAULT_API_URL
        ).strip(),
        oracle_dsn=(os.environ.get("ORACLE_DSN") or "").strip(),
        oracle_user=(os.environ.get("ORACLE_USER") or "").strip(),
        oracle_password=(os.environ.get("ORACLE_PASSWORD") or "").strip(),
        oracle_client_lib_dir=(os.environ.get("ORACLE_CLIENT_LIB_DIR") or "").strip() or None,
        sms_mobiles=mobiles,
        sms_userid=(os.environ.get("SMS_USERID") or "").strip(),
        sms_password=(os.environ.get("SMS_PASSWORD") or "").strip(),
        sms_userport=(os.environ.get("SMS_USERPORT") or "").strip(),
        kg_target_xqdm=(os.environ.get("KG_TARGET_XQDM") or "445300").strip() or "445300",
        kg_target_rwzt=(
            os.environ.get("JSBRJQ_KG_TARGET_RWZT")
            or os.environ.get("KG_TARGET_RWZT")
            or "涉精神病人"
        ).strip()
        or "涉精神病人",
        query_page_size=page_size,
        kingbase_host=kingbase_host,
        kingbase_port=kingbase_port,
        kingbase_dbname=kingbase_dbname,
        kingbase_user=kingbase_user,
        kingbase_password=kingbase_password,
    )


def get_dynamic_date_range() -> Tuple[str, str]:
    now = datetime.now()
    start_time = now - timedelta(hours=24)
    return start_time.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d %H:%M:%S")


class JsbrJqMonitor:
    def __init__(self, config: Config, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.session = requests.Session()
        self.use_thick_mode = False

        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/91.0.4472.124 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "X-Requested-With": "XMLHttpRequest",
            }
        )

        self.use_thick_mode = self._init_oracle_client()

    def _init_oracle_client(self) -> bool:
        if not self.config.oracle_client_lib_dir:
            self.logger.info("未配置Oracle Client路径，使用Thin模式(纯Python)")
            return False

        try:
            import oracledb

            oracledb.init_oracle_client(lib_dir=self.config.oracle_client_lib_dir)
            self.logger.info(
                "Oracle Instant Client已初始化(Thick模式): %s",
                self.config.oracle_client_lib_dir,
            )
            return True
        except Exception as exc:
            self.logger.warning("Oracle Instant Client初始化失败，将使用Thin模式: %s", exc)
            return False

    def _retry_request(self, method: str, url: str, **kwargs) -> Optional[requests.Response]:
        for attempt in range(MAX_RETRIES):
            try:
                return self.session.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
            except requests.RequestException as exc:
                self.logger.warning(
                    "请求失败 (尝试 %d/%d): %s",
                    attempt + 1,
                    MAX_RETRIES,
                    exc,
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    self.logger.error("请求最终失败: %s", url)
        return None

    def login(self) -> bool:
        login_data = {
            "username": self.config.login_username,
            "password": self.config.login_password,
            "rememberMe": "true",
        }
        login_headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }

        self.logger.info("开始登录: %s", self.config.monitor_login_url)
        response = self._retry_request(
            "POST",
            self.config.monitor_login_url,
            data=login_data,
            headers=login_headers,
        )
        if response is None:
            return False

        try:
            result = response.json()
        except json.JSONDecodeError:
            if response.status_code in {200, 302}:
                self.logger.info("登录成功（非JSON响应）")
                return True
            self.logger.error("登录失败，状态码: %s", response.status_code)
            return False

        self.logger.info("登录响应: %s", result)
        if (
            result.get("code") in {0, 200}
            or result.get("success") is True
            or result.get("msg") == "操作成功"
        ):
            self.logger.info("登录成功")
            if "token" in result:
                self.session.headers["Authorization"] = f"Bearer {result['token']}"
            return True

        self.logger.error("登录失败: %s", result.get("msg", "未知错误"))
        return False

    def _fetch_page(self, params: Dict[str, Any], page_num: int) -> Tuple[List[Dict[str, Any]], int]:
        response = self._retry_request("POST", self.config.monitor_api_url, data=params)
        if response is None:
            self.logger.error("查询数据失败(page=%d): 请求无响应", page_num)
            return [], 0

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            self.logger.error("解析响应失败(page=%d): %s", page_num, exc)
            return [], 0

        if data.get("code") != 0:
            self.logger.error(
                "查询失败(page=%d): code=%s, msg=%s",
                page_num,
                data.get("code"),
                data.get("msg"),
            )
            return [], 0

        rows = data.get("rows", [])
        total = data.get("total", 0)
        if not isinstance(rows, list):
            rows = []

        self.logger.info(
            "查询成功(page=%d): total=%s, rows=%d",
            page_num,
            total,
            len(rows),
        )
        return rows, int(total or 0)

    @staticmethod
    def _parse_record_time(record: Dict[str, Any]) -> datetime:
        value = record.get("alarmTime") or record.get("callTime")
        if value is None:
            return datetime.min
        text = str(value).strip()
        if not text:
            return datetime.min
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return datetime.min

    @staticmethod
    def _contains_mental_keyword(record: Dict[str, Any]) -> bool:
        case_contents = str(record.get("caseContents") or "").strip()
        replies = str(record.get("replies") or "").strip()
        return bool(
            MENTAL_CASE_PATTERN.search(case_contents)
            or MENTAL_CASE_PATTERN.search(replies)
        )

    @classmethod
    def _dedup_records(cls, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged_by_case: Dict[str, Dict[str, Any]] = {}
        no_case_records: List[Dict[str, Any]] = []

        def pick_better_text(old: Any, new: Any) -> Any:
            old_s = ("" if old is None else str(old)).strip()
            new_s = ("" if new is None else str(new)).strip()
            if not old_s and new_s:
                return new
            if old_s and new_s and len(new_s) > len(old_s):
                return new
            return old

        for record in records:
            case_no = str(record.get("caseNo") or "").strip()
            if not case_no:
                no_case_records.append(record)
                continue

            if case_no not in merged_by_case:
                merged_by_case[case_no] = dict(record)
                continue

            target = merged_by_case[case_no]
            for key, value in record.items():
                if key not in target or target.get(key) in (None, ""):
                    if value not in (None, ""):
                        target[key] = value
                    continue
                if key in {"caseContents", "replies", "occurAddress"}:
                    target[key] = pick_better_text(target.get(key), value)

        merged = list(merged_by_case.values()) + no_case_records
        merged.sort(key=cls._parse_record_time, reverse=True)
        return merged

    def fetch_data(self) -> List[Dict[str, Any]]:
        start_time, end_time = get_dynamic_date_range()
        self.logger.info(
            "开始查询数据: params[startTime]=%s, params[endTime]=%s, pageSize=%d",
            start_time,
            end_time,
            self.config.query_page_size,
        )

        page_num = 1
        total = 0
        raw_count = 0
        matched_records: List[Dict[str, Any]] = []

        while True:
            params = BASE_PARAMS.copy()
            params["params[startTime]"] = start_time
            params["params[endTime]"] = end_time
            params["pageSize"] = str(self.config.query_page_size)
            params["pageNum"] = str(page_num)

            rows, page_total = self._fetch_page(params, page_num)
            total = max(total, page_total)
            if not rows:
                break

            raw_count += len(rows)
            matched = [row for row in rows if self._contains_mental_keyword(row)]
            matched_records.extend(matched)
            self.logger.info(
                "第%d页过滤完成: 原始=%d, 命中涉精神病人警情=%d",
                page_num,
                len(rows),
                len(matched),
            )

            if len(rows) < self.config.query_page_size:
                break
            if total and raw_count >= total:
                break
            page_num += 1

        deduped = self._dedup_records(matched_records)
        self.logger.info(
            "查询完成: 原始总数=%d, 命中数=%d, 去重后=%d",
            raw_count,
            len(matched_records),
            len(deduped),
        )
        return deduped

    def _fetch_kingbase_mobiles(self) -> Tuple[Optional[List[str]], str]:
        if not self.config.has_kingbase_config():
            return None, "kingbase_config_incomplete"

        try:
            import psycopg2
        except ModuleNotFoundError:
            self.logger.error("Kingbase驱动缺失: 请安装 psycopg2-binary")
            return None, "kingbase_driver_missing"

        sql = """
            SELECT lxdh
            FROM ywdata.b_dxpt_mdjfyj
            WHERE xqdm = %s
              AND rwzt = %s
              AND lxdh IS NOT NULL
        """

        for attempt in range(MAX_RETRIES):
            conn = None
            try:
                conn = psycopg2.connect(
                    host=self.config.kingbase_host,
                    port=self.config.kingbase_port,
                    dbname=self.config.kingbase_dbname,
                    user=self.config.kingbase_user,
                    password=self.config.kingbase_password,
                )
                with conn.cursor() as cur:
                    cur.execute(sql, (self.config.kg_target_xqdm, self.config.kg_target_rwzt))
                    rows = cur.fetchall()

                mobiles = normalize_mobile_list([row[0] for row in rows])
                self.logger.info(
                    "号码来源=kingbase, xqdm=%s, rwzt=%s, 查询行数=%d, 清洗后号码数=%d",
                    self.config.kg_target_xqdm,
                    self.config.kg_target_rwzt,
                    len(rows),
                    len(mobiles),
                )
                if not mobiles:
                    return [], "kingbase_empty_result"
                return mobiles, "kingbase_success"
            except Exception as exc:
                self.logger.warning(
                    "Kingbase查询失败 (尝试 %d/%d): %s",
                    attempt + 1,
                    MAX_RETRIES,
                    exc,
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
            finally:
                if conn:
                    conn.close()

        self.logger.error("Kingbase查询最终失败")
        return None, "kingbase_query_failed"

    def resolve_target_mobiles(self) -> Tuple[List[str], str, str]:
        kingbase_mobiles, reason = self._fetch_kingbase_mobiles()
        if kingbase_mobiles is not None:
            if kingbase_mobiles:
                return kingbase_mobiles, "kingbase", reason
            self.logger.warning("号码来源=none, reason=%s, 不使用SMS_MOBILES回退", reason)
            return [], "none", reason

        if self.config.sms_mobiles:
            self.logger.warning(
                "号码来源=fallback_sms_mobiles, reason=%s, 清洗后号码数=%d",
                reason,
                len(self.config.sms_mobiles),
            )
            return self.config.sms_mobiles, "fallback_sms_mobiles", reason

        self.logger.warning("号码来源=none, reason=%s, no fallback mobiles", reason)
        return [], "none", reason

    def build_sms_content(self, record: Dict[str, Any]) -> str:
        alarm_time = str(record.get("alarmTime") or record.get("callTime") or "").strip()
        duty_dept = str(record.get("dutyDeptName") or "").strip()
        occur_address = str(record.get("occurAddress") or "").strip()
        case_contents = str(record.get("caseContents") or "").strip()
        replies = str(record.get("replies") or "").strip()

        detail_parts: List[str] = []
        if case_contents:
            detail_parts.append(case_contents)
        if replies and replies not in case_contents:
            detail_parts.append(f"回复:{replies}")
        detail = "；".join(detail_parts) if detail_parts else "内容为空"

        return (
            f"【涉精神病人警情】{alarm_time},{duty_dept}接报:"
            f"{detail}地址:{occur_address}【基础管控中心】"
        )

    def check_duplicate(self, conn: Any, case_no: str, mobile: str) -> bool:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM yfgadb.dfsdl
                    WHERE eid = :eid
                      AND mobile = :mobile
                    """,
                    {"eid": case_no, "mobile": mobile},
                )
                count = cur.fetchone()[0]
                return count > 0
        except Exception as exc:
            self.logger.error("去重检查失败: %s", exc)
            return False

    def send_sms(self, conn: Any, mobile: str, content: str, case_no: str) -> bool:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO yfgadb.dfsdl(
                        id, mobile, content, deadtime, status, eid,
                        userid, password, userport
                    ) VALUES (
                        yfgadb.seq_sendsms.nextval,
                        :mobile, :content, SYSDATE, '0', :eid,
                        :sms_userid, :sms_password, :sms_userport
                    )
                    """,
                    {
                        "mobile": mobile,
                        "content": content,
                        "eid": case_no,
                        "sms_userid": self.config.sms_userid,
                        "sms_password": self.config.sms_password,
                        "sms_userport": self.config.sms_userport,
                    },
                )
                return True
        except Exception as exc:
            self.logger.error("短信发送失败: %s", exc)
            return False

    def process_records(
        self,
        records: List[Dict[str, Any]],
        target_mobiles: List[str],
    ) -> Dict[str, int]:
        stats = {"total": len(records), "sent": 0, "skipped": 0, "failed": 0}
        if not records:
            return stats
        if not target_mobiles:
            self.logger.warning("本轮无可用接收号码，跳过短信发送")
            return stats

        conn = None
        for attempt in range(MAX_RETRIES):
            try:
                import oracledb

                conn = oracledb.connect(
                    user=self.config.oracle_user,
                    password=self.config.oracle_password,
                    dsn=self.config.oracle_dsn,
                )
                mode_str = "Thick" if self.use_thick_mode else "Thin"
                self.logger.info("Oracle连接成功 (%s模式)", mode_str)
                break
            except Exception as exc:
                self.logger.warning(
                    "Oracle连接失败 (尝试 %d/%d): %s",
                    attempt + 1,
                    MAX_RETRIES,
                    exc,
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    self.logger.error("Oracle连接最终失败")
                    return stats

        try:
            for record in records:
                case_no = str(record.get("caseNo") or "").strip()
                if not case_no:
                    self.logger.warning("记录缺少caseNo，跳过")
                    stats["skipped"] += 1
                    continue

                content = self.build_sms_content(record)
                for mobile in target_mobiles:
                    if self.check_duplicate(conn, case_no, mobile):
                        self.logger.info("跳过(已发送): caseNo=%s, mobile=%s", case_no, mobile)
                        stats["skipped"] += 1
                        continue

                    if self.send_sms(conn, mobile, content, case_no):
                        self.logger.info("短信已发送: caseNo=%s, mobile=%s", case_no, mobile)
                        stats["sent"] += 1
                    else:
                        stats["failed"] += 1

            conn.commit()
        except Exception as exc:
            self.logger.error("处理记录异常: %s", exc)
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

        return stats

    def run(self) -> int:
        self.logger.info("=" * 60)
        self.logger.info("开始执行涉精神病人警情监控任务")

        if not self.login():
            self.logger.error("登录失败，任务终止")
            return 1

        records = self.fetch_data()
        target_mobiles, mobile_source, mobile_reason = self.resolve_target_mobiles()
        self.logger.info(
            "号码来源=%s, reason=%s, 可用号码数=%d",
            mobile_source,
            mobile_reason,
            len(target_mobiles),
        )

        if not records:
            self.logger.info("未查询到涉精神病人警情")
            return 0

        if not target_mobiles:
            self.logger.warning("无可用号码，本轮不发送短信")
            return 0

        stats = self.process_records(records, target_mobiles)
        self.logger.info("=" * 60)
        self.logger.info(
            "任务完成: 命中%d条, 发送%d条, 跳过%d条, 失败%d条, 号码来源=%s",
            stats["total"],
            stats["sent"],
            stats["skipped"],
            stats["failed"],
            mobile_source,
        )
        self.logger.info("=" * 60)
        return 0


def main() -> int:
    logger = setup_logging()
    try:
        config = load_config_from_env()

        if not config.login_username or not config.login_password:
            logger.error(
                "缺少登录凭证，请设置 LOGIN_USERNAME/LOGIN_PASSWORD "
                "或 JSBRJQ_LOGIN_USERNAME/JSBRJQ_LOGIN_PASSWORD"
            )
            return 1

        if not config.oracle_dsn or not config.oracle_user or not config.oracle_password:
            logger.error("缺少Oracle配置，请设置 ORACLE_DSN, ORACLE_USER, ORACLE_PASSWORD")
            return 1

        if not config.sms_userid or not config.sms_password or not config.sms_userport:
            logger.error("缺少短信网关配置，请设置 SMS_USERID, SMS_PASSWORD, SMS_USERPORT")
            return 1

        if not config.has_kingbase_config() and not config.sms_mobiles:
            logger.error(
                "缺少可用号码来源：请配置完整Kingbase环境变量"
                "(KINGBASE_HOST/KINGBASE_PORT/KINGBASE_DBNAME/KINGBASE_USER/KINGBASE_PASSWORD)"
                " 或提供 SMS_MOBILES 作为兜底"
            )
            return 1

        if not config.has_kingbase_config():
            logger.warning("Kingbase配置不完整，将仅在Kingbase不可用场景使用 SMS_MOBILES 兜底")

        monitor = JsbrJqMonitor(config, logger)
        return monitor.run()
    except Exception as exc:
        logger.exception("程序异常: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
