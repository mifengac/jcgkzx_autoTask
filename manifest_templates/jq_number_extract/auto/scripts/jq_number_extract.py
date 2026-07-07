#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
警情文本号码提取脚本 v1
来源表: ywdata.zq_kshddpt_dsjfx_jq（报警内容 casecontents / 处警情况 replies）
目标表: jcgkzx_monitor.zq_jingqing_number_extract
提取类型: 身份证、手机号、固话、车牌（含新能源）、银行卡、社会信用代码、护照、QQ
增量策略: MAX(source_updatetime) 水位线 - NE_LOOKBACK_MIN 分钟 buffer，防止边界漏行
"""

import json
import logging
import os
import re
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

import psycopg2
from psycopg2.extras import execute_values
from zoneinfo import ZoneInfo

try:
    from autotask_api.services.time_utils import now_shanghai
except ModuleNotFoundError:
    _SH = ZoneInfo("Asia/Shanghai")

    def now_shanghai() -> datetime:
        return datetime.now(_SH)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

BATCH_SIZE = 500
CTX_WIN = 20  # 上下文窗口：号码前后各取 20 字


# ══════════════════════════════════════════════════════
#  1. 号码校验
# ══════════════════════════════════════════════════════

_ID_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
_ID_CHECK_CHARS = "10X98765432"

# 工信部公示手机号段（可按需补充）
_MOBILE_PREFIXES = {
    "130", "131", "132", "133", "134", "135", "136", "137", "138", "139",
    "141", "144", "145", "146", "147", "148", "149",
    "150", "151", "152", "153", "155", "156", "157", "158", "159",
    "162", "165", "166",
    "170", "171", "172", "173", "174", "175", "176", "177", "178",
    "180", "181", "182", "183", "184", "185", "186", "187", "188", "189",
    "190", "191", "192", "193", "195", "196", "197", "198", "199",
}


def _valid_id(s: str) -> bool:
    s = s.upper()
    if len(s) != 18 or not s[:17].isdigit():
        return False
    total = sum(int(s[i]) * _ID_WEIGHTS[i] for i in range(17))
    return _ID_CHECK_CHARS[total % 11] == s[-1]


def _valid_mobile(s: str) -> bool:
    return len(s) == 11 and s[:3] in _MOBILE_PREFIXES


def _luhn(s: str) -> bool:
    """Luhn 算法校验银行卡号"""
    digits = [int(c) for c in s]
    odd = sum(digits[-1::-2])
    even = sum(d * 2 - 9 if d * 2 > 9 else d * 2 for d in digits[-2::-2])
    return (odd + even) % 10 == 0


# ══════════════════════════════════════════════════════
#  2. 脱敏
# ══════════════════════════════════════════════════════


def _mask(s: str, head: int, tail: int, fill: str = "****") -> str:
    if len(s) <= head + tail:
        return s
    return s[:head] + fill + s[len(s) - tail :]


def _mask_id(s: str) -> str:
    return _mask(s, 6, 4, "********")  # 110101********1234


def _mask_mobile(s: str) -> str:
    return _mask(s, 3, 4)  # 138****8888


def _mask_plate(s: str) -> str:
    return s[:2] + "****" + s[-1] if len(s) >= 4 else s  # 粤A****5


def _mask_bank(s: str) -> str:
    return _mask(s, 4, 4)  # 6222****1234


def _mask_default(s: str) -> str:
    return _mask(s, 2, 2, "***")


# ══════════════════════════════════════════════════════
#  3. 正则规则表
#     每条规则 pattern 含且仅含 1 个捕获组（号码本体）
# ══════════════════════════════════════════════════════

_PV = r"[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤川青藏琼宁夏]"

RULES: List[Dict] = [
    # ── 居民身份证（18位，含校验位） ────────────────────────────
    dict(
        typ="ID_CARD",
        pat=re.compile(
            r"(?<!\d)([1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx])(?!\d)"
        ),
        validate=_valid_id,
        mask=_mask_id,
        conf_ok=95,
        conf_fail=30,   # 不过校验位，基本是误命中
        pid="ID_CARD_V1",
    ),
    # ── 手机号（11位，号段校验） ────────────────────────────────
    dict(
        typ="PHONE_MOBILE",
        pat=re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)"),
        validate=_valid_mobile,
        mask=_mask_mobile,
        conf_ok=92,
        conf_fail=45,   # 格式对但号段不在表中，可能是企业号/虚拟号
        pid="PHONE_MOBILE_V1",
    ),
    # ── 固定电话（含区号，支持连字符/空格分隔） ────────────────
    dict(
        typ="PHONE_LANDLINE",
        pat=re.compile(r"(?<!\d)(0\d{2,3}[-\s]?\d{7,8})(?!\d)"),
        validate=lambda s: True,
        mask=_mask_default,
        conf_ok=75,
        conf_fail=75,   # 无深度校验，置信度统一中等
        pid="PHONE_LANDLINE_V1",
    ),
    # ── 普通机动车号牌 ──────────────────────────────────────────
    dict(
        typ="PLATE_NUMBER",
        pat=re.compile(
            r"(" + _PV + r"[A-Z][A-HJ-NP-Z0-9]{4}[A-HJ-NP-Z0-9挂学警港澳])"
        ),
        validate=lambda s: True,
        mask=_mask_plate,
        conf_ok=88,
        conf_fail=88,
        pid="PLATE_STD_V1",
    ),
    # ── 新能源车牌（6位，末位/首位 D/F） ──────────────────────
    dict(
        typ="PLATE_NUMBER",
        pat=re.compile(
            r"(" + _PV + r"[A-Z](?:[0-9]{5}[DF]|[DF][A-HJ-NP-Z0-9][0-9]{4}))"
        ),
        validate=lambda s: True,
        mask=_mask_plate,
        conf_ok=88,
        conf_fail=88,
        pid="PLATE_NEV_V1",
    ),
    # ── 银行卡号（需上下文关键词，高置信） ─────────────────────
    dict(
        typ="BANK_CARD",
        pat=re.compile(
            r"(?:银行卡|卡号|储蓄卡|信用卡|借记卡)[：:\s]*([3-9]\d{15,18})(?!\d)"
        ),
        validate=_luhn,
        mask=_mask_bank,
        conf_ok=90,
        conf_fail=55,   # 有上下文但 Luhn 不过，仍有一定可信度
        pid="BANK_CARD_CTX_V1",
    ),
    # ── 银行卡号（无上下文，Luhn 校验是主要依据） ──────────────
    dict(
        typ="BANK_CARD",
        pat=re.compile(r"(?<!\d)([3-9]\d{15,18})(?!\d)"),
        validate=_luhn,
        mask=_mask_bank,
        conf_ok=80,
        conf_fail=15,   # 无上下文且 Luhn 不过，基本确认是误命中，几乎不存储
        pid="BANK_CARD_V1",
    ),
    # ── 统一社会信用代码（18位，字母+数字混合） ────────────────
    dict(
        typ="SOCIAL_CREDIT",
        pat=re.compile(
            r"(?<!\w)([0-9A-HJ-NP-RT-UW-Y]{2}\d{6}[0-9A-HJ-NP-RT-UW-Y]{10})(?!\w)"
        ),
        validate=lambda s: True,
        mask=_mask_default,
        conf_ok=72,
        conf_fail=72,
        pid="SOCIAL_CREDIT_V1",
    ),
    # ── 护照（G/E 开头 + 8位数字，中国大陆护照） ───────────────
    dict(
        typ="PASSPORT",
        pat=re.compile(r"(?<!\w)([EeGg]\d{8})(?!\w)"),
        validate=lambda s: True,
        mask=_mask_default,
        conf_ok=80,
        conf_fail=80,
        pid="PASSPORT_V1",
    ),
    # ── QQ号（需上下文关键词，group(1) 才是号码） ──────────────
    dict(
        typ="QQ",
        pat=re.compile(r"(?:QQ|qq|扣扣|Q号)[：:\s]*(\d{5,12})"),
        validate=lambda s: True,
        mask=_mask_default,
        conf_ok=82,
        conf_fail=82,
        pid="QQ_CTX_V1",
    ),
]


# ══════════════════════════════════════════════════════
#  4. 文本提取
# ══════════════════════════════════════════════════════


def extract_from_text(text: str) -> List[Dict[str, Any]]:
    """对单段文本跑所有规则，返回去重后的提取结果"""
    if not text:
        return []
    results: List[Dict] = []
    seen: set = set()

    for rule in RULES:
        for m in rule["pat"].finditer(text):
            raw = m.group(1)
            # 固话可能含空格/连字符，清洗后作为存储值
            cleaned = re.sub(r"[-\s]", "", raw)

            key = (rule["typ"], cleaned)
            if key in seen:
                continue
            seen.add(key)

            ok = rule["validate"](cleaned)
            conf = rule["conf_ok"] if ok else rule["conf_fail"]

            # 置信度太低（如无上下文的银行卡号 Luhn 不过）直接丢弃
            if conf < 20:
                continue

            s, e = m.start(), m.end()
            snippet = text[max(0, s - CTX_WIN) : min(len(text), e + CTX_WIN)].strip()

            results.append(
                dict(
                    number_type=rule["typ"],
                    number_value=cleaned,
                    number_masked=rule["mask"](cleaned),
                    is_valid=ok,
                    confidence=conf,
                    match_pattern=rule["pid"],
                    context_snippet=snippet,
                )
            )
    return results


# ══════════════════════════════════════════════════════
#  5. 主任务
# ══════════════════════════════════════════════════════


def _parse_dt(v: Any) -> Optional[datetime]:
    """将 TEXT 类型的时间字符串安全地解析为 datetime"""
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).strip().replace("/", "-"))
    except (ValueError, TypeError):
        return None


class NumberExtractTask:
    def __init__(
        self,
        src_dsn: str,
        dst_dsn: str,
        src_schema: str = "ywdata",
        dst_schema: str = "jcgkzx_monitor",
        lookback_min: int = 10,
    ):
        self.src_dsn = src_dsn
        self.dst_dsn = dst_dsn
        self.src_schema = src_schema
        self.dst_schema = dst_schema
        self.lookback_min = lookback_min
        self._src: Optional[psycopg2.extensions.connection] = None
        self._dst: Optional[psycopg2.extensions.connection] = None

    def connect(self):
        self._src = psycopg2.connect(self.src_dsn)
        self._src.autocommit = True
        self._dst = psycopg2.connect(self.dst_dsn)
        self._dst.autocommit = True
        logger.info("DB 连接就绪")

    def close(self):
        for c in (self._src, self._dst):
            try:
                if c:
                    c.close()
            except Exception:
                pass

    # ── 水位线 ─────────────────────────────────────────
    def _watermark(self) -> datetime:
        with self._dst.cursor() as cur:
            cur.execute(
                f"SELECT MAX(source_updatetime) "
                f"FROM {self.dst_schema}.zq_jingqing_number_extract"
            )
            row = cur.fetchone()
        if row and row[0]:
            wm = row[0] - timedelta(minutes=self.lookback_min)
            logger.info(f"水位线: {wm}（MAX source_updatetime - {self.lookback_min}min buffer）")
            return wm
        # 目标表为空，回溯 3 天
        fallback = now_shanghai() - timedelta(days=3)
        logger.info(f"目标表为空，回溯至 {fallback}")
        return fallback

    # ── 拉源数据 ────────────────────────────────────────
    def _fetch_src(self, since: datetime) -> List[Dict]:
        columns = [
            "caseno", "updatetime", "calltime", "cmdid", "cmdname", "callerphone", "callername", 
            "occuraddress", "casecontents", "replies", "dutydeptno", "dutydeptname", "callway", 
            "newrecvtype", "newrecvtypename", "neworicharacategory", "neworicharacategoryname", 
            "neworicharatype", "neworicharatypename", "neworicharasubcategory", "neworicharasubcategoryname", 
            "neworicharasubclass", "neworicharasubclassname", "newcharacategory", "newcharacategoryname", 
            "newcharatype", "newcharatypename", "newcharasubcategory", "newcharasubcategoryname", 
            "newcharasubclass", "newcharasubclassname", "lngofcriterion", "latofcriterion", 
            "casemark", "casemarkno", "casemarkok", "casemarkokno", "standardcaseno"
        ]
        sql = (
            f"SELECT {', '.join(columns)} "
            f"FROM {self.src_schema}.zq_kshddpt_dsjfx_jq "
            f"WHERE updatetime IS NOT NULL AND updatetime >= %s "
            f"ORDER BY updatetime"
        )
        with self._src.cursor() as cur:
            cur.execute(sql, (since,))
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        logger.info(f"源表读取 {len(rows)} 条（updatetime >= {since}）")
        return rows

    # ── 构建写入行 ──────────────────────────────────────
    def _build_rows(self, records: List[Dict]) -> List[tuple]:
        rows: List[tuple] = []
        now = now_shanghai()
        for rec in records:
            caseno = (rec.get("caseno") or "").strip()
            if not caseno:
                continue
            src_ut = _parse_dt(rec.get("updatetime"))
            calltime = _parse_dt(rec.get("calltime"))

            for field in ("casecontents", "replies"):
                text = rec.get(field) or ""
                for item in extract_from_text(text):
                    rows.append(
                        (
                            caseno,
                            src_ut,
                            calltime,
                            rec.get("cmdid"),
                            rec.get("cmdname"),
                            rec.get("callerphone"),
                            rec.get("callername"),
                            rec.get("occuraddress"),
                            rec.get("casecontents"),
                            rec.get("replies"),
                            rec.get("dutydeptno"),
                            rec.get("dutydeptname"),
                            rec.get("callway"),
                            rec.get("newrecvtype"),
                            rec.get("newrecvtypename"),
                            rec.get("neworicharacategory"),
                            rec.get("neworicharacategoryname"),
                            rec.get("neworicharatype"),
                            rec.get("neworicharatypename"),
                            rec.get("neworicharasubcategory"),
                            rec.get("neworicharasubcategoryname"),
                            rec.get("neworicharasubclass"),
                            rec.get("neworicharasubclassname"),
                            rec.get("newcharacategory"),
                            rec.get("newcharacategoryname"),
                            rec.get("newcharatype"),
                            rec.get("newcharatypename"),
                            rec.get("newcharasubcategory"),
                            rec.get("newcharasubcategoryname"),
                            rec.get("newcharasubclass"),
                            rec.get("newcharasubclassname"),
                            rec.get("lngofcriterion"),
                            rec.get("latofcriterion"),
                            rec.get("casemark"),
                            rec.get("casemarkno"),
                            rec.get("casemarkok"),
                            rec.get("casemarkokno"),
                            rec.get("standardcaseno"),
                            field,
                            item["number_type"],
                            item["number_value"],
                            item["number_masked"],
                            item["is_valid"],
                            item["confidence"],
                            item["match_pattern"],
                            item["context_snippet"],
                            now,  # extracted_at
                        )
                    )
        return rows

    # ── upsert ─────────────────────────────────────────
    def _upsert(self, rows: List[tuple]) -> int:
        if not rows:
            return 0
        sql = f"""
            INSERT INTO {self.dst_schema}.zq_jingqing_number_extract (
                caseno, source_updatetime, calltime, cmdid, cmdname, callerphone, callername, 
                occuraddress, casecontents, replies, dutydeptno, dutydeptname, callway, 
                newrecvtype, newrecvtypename, neworicharacategory, neworicharacategoryname, 
                neworicharatype, neworicharatypename, neworicharasubcategory, neworicharasubcategoryname, 
                neworicharasubclass, neworicharasubclassname, newcharacategory, newcharacategoryname, 
                newcharatype, newcharatypename, newcharasubcategory, newcharasubcategoryname, 
                newcharasubclass, newcharasubclassname, lngofcriterion, latofcriterion, 
                casemark, casemarkno, casemarkok, casemarkokno, standardcaseno,
                extract_field, number_type, number_value, number_masked, is_valid, confidence, 
                match_pattern, context_snippet, extracted_at
            )
            VALUES %s
            ON CONFLICT (caseno, extract_field, number_type, number_value)
            DO UPDATE SET
                source_updatetime           = EXCLUDED.source_updatetime,
                calltime                    = EXCLUDED.calltime,
                cmdid                       = EXCLUDED.cmdid,
                cmdname                     = EXCLUDED.cmdname,
                callerphone                 = EXCLUDED.callerphone,
                callername                  = EXCLUDED.callername,
                occuraddress                = EXCLUDED.occuraddress,
                casecontents                = EXCLUDED.casecontents,
                replies                     = EXCLUDED.replies,
                dutydeptno                  = EXCLUDED.dutydeptno,
                dutydeptname                = EXCLUDED.dutydeptname,
                callway                     = EXCLUDED.callway,
                newrecvtype                 = EXCLUDED.newrecvtype,
                newrecvtypename             = EXCLUDED.newrecvtypename,
                neworicharacategory         = EXCLUDED.neworicharacategory,
                neworicharacategoryname     = EXCLUDED.neworicharacategoryname,
                neworicharatype             = EXCLUDED.neworicharatype,
                neworicharatypename         = EXCLUDED.neworicharatypename,
                neworicharasubcategory      = EXCLUDED.neworicharasubcategory,
                neworicharasubcategoryname  = EXCLUDED.neworicharasubcategoryname,
                neworicharasubclass         = EXCLUDED.neworicharasubclass,
                neworicharasubclassname     = EXCLUDED.neworicharasubclassname,
                newcharacategory            = EXCLUDED.newcharacategory,
                newcharacategoryname        = EXCLUDED.newcharacategoryname,
                newcharatype                = EXCLUDED.newcharatype,
                newcharatypename            = EXCLUDED.newcharatypename,
                newcharasubcategory         = EXCLUDED.newcharasubcategory,
                newcharasubcategoryname     = EXCLUDED.newcharasubcategoryname,
                newcharasubclass            = EXCLUDED.newcharasubclass,
                newcharasubclassname        = EXCLUDED.newcharasubclassname,
                lngofcriterion              = EXCLUDED.lngofcriterion,
                latofcriterion              = EXCLUDED.latofcriterion,
                casemark                    = EXCLUDED.casemark,
                casemarkno                  = EXCLUDED.casemarkno,
                casemarkok                  = EXCLUDED.casemarkok,
                casemarkokno                = EXCLUDED.casemarkokno,
                standardcaseno              = EXCLUDED.standardcaseno,
                number_masked               = EXCLUDED.number_masked,
                is_valid                    = EXCLUDED.is_valid,
                confidence                  = EXCLUDED.confidence,
                match_pattern               = EXCLUDED.match_pattern,
                context_snippet             = EXCLUDED.context_snippet,
                extracted_at                = EXCLUDED.extracted_at,
                updated_at                  = CURRENT_TIMESTAMP
        """
        written = 0
        with self._dst.cursor() as cur:
            for i in range(0, len(rows), BATCH_SIZE):
                chunk = rows[i : i + BATCH_SIZE]
                execute_values(cur, sql, chunk, page_size=BATCH_SIZE)
                written += len(chunk)
        logger.info(f"upsert {written} 行完成")
        return written

    def run(self) -> Dict[str, Any]:
        wm = self._watermark()
        records = self._fetch_src(wm)
        rows = self._build_rows(records)
        logger.info(f"提取号码 {len(rows)} 行（来自 {len(records)} 条警情）")
        written = self._upsert(rows)
        return {
            "source_records": len(records),
            "extracted_rows": len(rows),
            "written_rows": written,
            "watermark": wm.isoformat(),
        }


# ══════════════════════════════════════════════════════
#  6. 环境变量 / runtime_config
# ══════════════════════════════════════════════════════


def _env(name: str, default: Optional[str] = None) -> str:
    v = (os.environ.get(name) or "").strip()
    if v:
        return v
    if default is not None:
        return default
    raise ValueError(f"缺少环境变量 {name}")


def _first(*names: str, default: Optional[str] = None) -> str:
    for n in names:
        v = (os.environ.get(n) or "").strip()
        if v:
            return v
    if default is not None:
        return default
    raise ValueError(f"缺少环境变量: {'/'.join(names)}")


def _build_dsn(host_keys, port_keys, db_keys, user_keys, pwd_keys) -> str:
    h = _first(*host_keys)
    p = _first(*port_keys, default="5432")
    d = _first(*db_keys)
    u = _first(*user_keys)
    w = _first(*pwd_keys)
    return f"host={h} port={p} dbname={d} user={u} password={w}"


def _clean_url(url: str) -> str:
    if not url:
        return url
    if "postgresql+psycopg2://" in url:
        return url.replace("postgresql+psycopg2://", "postgresql://")
    if "postgresql+pg8000://" in url:
        return url.replace("postgresql+pg8000://", "postgresql://")
    return url


def _src_dsn() -> str:
    url = _first("NE_SRC_DB_URL", "NE_DB_URL", "DATABASE_URL", default="")
    if url:
        return _clean_url(url)
    return _build_dsn(
        ["NE_SRC_HOST", "NE_DB_HOST", "ZQ_DB_HOST", "KINGBASE_HOST"],
        ["NE_SRC_PORT", "NE_DB_PORT", "ZQ_DB_PORT", "KINGBASE_PORT"],
        ["NE_SRC_DB", "NE_DB_NAME", "ZQ_DB_NAME", "KINGBASE_DBNAME"],
        ["NE_SRC_USER", "NE_DB_USER", "ZQ_DB_USER", "KINGBASE_USER"],
        ["NE_SRC_PASSWORD", "NE_DB_PASSWORD", "ZQ_DB_PASSWORD", "KINGBASE_PASSWORD"],
    )


def _dst_dsn() -> str:
    url = _first("NE_DST_DB_URL", "NE_DB_URL", "DATABASE_URL", default="")
    if url:
        return _clean_url(url)
    return _build_dsn(
        ["NE_DST_HOST", "NE_DB_HOST", "ZQ_DB_HOST", "KINGBASE_HOST"],
        ["NE_DST_PORT", "NE_DB_PORT", "ZQ_DB_PORT", "KINGBASE_PORT"],
        ["NE_DST_DB", "NE_DB_NAME", "ZQ_DB_NAME", "KINGBASE_DBNAME"],
        ["NE_DST_USER", "NE_DB_USER", "ZQ_DB_USER", "KINGBASE_USER"],
        ["NE_DST_PASSWORD", "NE_DB_PASSWORD", "ZQ_DB_PASSWORD", "KINGBASE_PASSWORD"],
    )


# runtime_config key → 环境变量名 映射
_ENV_MAP = {
    "ne_src_db_url":   "NE_SRC_DB_URL",
    "ne_dst_db_url":   "NE_DST_DB_URL",
    "ne_db_url":       "NE_DB_URL",
    "ne_src_host":     "NE_SRC_HOST",
    "ne_src_port":     "NE_SRC_PORT",
    "ne_src_db":       "NE_SRC_DB",
    "ne_src_user":     "NE_SRC_USER",
    "ne_src_password": "NE_SRC_PASSWORD",
    "ne_dst_host":     "NE_DST_HOST",
    "ne_dst_port":     "NE_DST_PORT",
    "ne_dst_db":       "NE_DST_DB",
    "ne_dst_user":     "NE_DST_USER",
    "ne_dst_password": "NE_DST_PASSWORD",
    "ne_src_schema":   "NE_SRC_SCHEMA",
    "ne_dst_schema":   "NE_DST_SCHEMA",
    "ne_lookback_min": "NE_LOOKBACK_MIN",
}


def _runtime_to_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, tuple, set)):
        return ",".join(str(i) for i in v if i not in (None, ""))
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


# ══════════════════════════════════════════════════════
#  7. 平台入口 run(context)
# ══════════════════════════════════════════════════════


def run(context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    context = context or {}
    rc = context.get("runtime_config") or {}
    started = now_shanghai()

    with _tmp_env(rc):
        task = NumberExtractTask(
            src_dsn=_src_dsn(),
            dst_dsn=_dst_dsn(),
            src_schema=_env("NE_SRC_SCHEMA", "ywdata"),
            dst_schema=_env("NE_DST_SCHEMA", "jcgkzx_monitor"),
            lookback_min=int(_env("NE_LOOKBACK_MIN", "10")),
        )
        try:
            task.connect()
            stats = task.run()
        finally:
            task.close()

    ended = now_shanghai()
    return [
        {
            "event_id": f"ne_{uuid4().hex}",
            "task_name": "jq_number_extract",
            "status": "success",
            "source_records": stats["source_records"],
            "extracted_rows": stats["extracted_rows"],
            "written_rows": stats["written_rows"],
            "watermark": stats["watermark"],
            "message_text": (
                f"号码提取完成: 处理警情 {stats['source_records']} 条，"
                f"提取 {stats['extracted_rows']} 行，"
                f"写入 {stats['written_rows']} 行"
            ),
            "start_time": started.isoformat(),
            "end_time": ended.isoformat(),
        }
    ]


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
