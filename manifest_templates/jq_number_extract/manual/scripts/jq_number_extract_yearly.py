#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
警情文本号码提取脚本 - 年份历史回溯版
用于内网手动执行历史年份的数据归档提取
用法:
  python3 jq_number_extract_yearly.py --year 2024 --src-url "postgresql://..." --dst-url "postgresql://..."
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════
#  1. 号码校验与脱敏规则 (与生产脚本保持完全一致)
# ══════════════════════════════════════════════════════

_ID_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
_ID_CHECK_CHARS = "10X98765432"

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
    digits = [int(c) for c in s]
    odd = sum(digits[-1::-2])
    even = sum(d * 2 - 9 if d * 2 > 9 else d * 2 for d in digits[-2::-2])
    return (odd + even) % 10 == 0

def _mask(s: str, head: int, tail: int, fill: str = "****") -> str:
    if len(s) <= head + tail:
        return s
    return s[:head] + fill + s[len(s) - tail :]

def _mask_id(s: str) -> str:
    return _mask(s, 6, 4, "********")

def _mask_mobile(s: str) -> str:
    return _mask(s, 3, 4)

def _mask_plate(s: str) -> str:
    return s[:2] + "****" + s[-1] if len(s) >= 4 else s

def _mask_bank(s: str) -> str:
    return _mask(s, 4, 4)

def _mask_default(s: str) -> str:
    return _mask(s, 2, 2, "***")

_PV = r"[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤川青藏琼宁夏]"

RULES: List[Dict] = [
    dict(
        typ="ID_CARD",
        pat=re.compile(r"(?<!\d)([1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx])(?!\d)"),
        validate=_valid_id,
        mask=_mask_id,
        conf_ok=95,
        conf_fail=30,
        pid="ID_CARD_V1",
    ),
    dict(
        typ="PHONE_MOBILE",
        pat=re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)"),
        validate=_valid_mobile,
        mask=_mask_mobile,
        conf_ok=92,
        conf_fail=45,
        pid="PHONE_MOBILE_V1",
    ),
    dict(
        typ="PHONE_LANDLINE",
        pat=re.compile(r"(?<!\d)(0\d{2,3}[-\s]?\d{7,8})(?!\d)"),
        validate=lambda s: True,
        mask=_mask_default,
        conf_ok=75,
        conf_fail=75,
        pid="PHONE_LANDLINE_V1",
    ),
    dict(
        typ="PLATE_NUMBER",
        pat=re.compile(r"(" + _PV + r"[A-Z][A-HJ-NP-Z0-9]{4}[A-HJ-NP-Z0-9挂学警港澳])"),
        validate=lambda s: True,
        mask=_mask_plate,
        conf_ok=88,
        conf_fail=88,
        pid="PLATE_STD_V1",
    ),
    dict(
        typ="PLATE_NUMBER",
        pat=re.compile(r"(" + _PV + r"[A-Z](?:[0-9]{5}[DF]|[DF][A-HJ-NP-Z0-9][0-9]{4}))"),
        validate=lambda s: True,
        mask=_mask_plate,
        conf_ok=88,
        conf_fail=88,
        pid="PLATE_NEV_V1",
    ),
    dict(
        typ="BANK_CARD",
        pat=re.compile(r"(?:银行卡|卡号|储蓄卡|信用卡|借记卡)[：:\s]*([3-9]\d{15,18})(?!\d)"),
        validate=_luhn,
        mask=_mask_bank,
        conf_ok=90,
        conf_fail=55,
        pid="BANK_CARD_CTX_V1",
    ),
    dict(
        typ="BANK_CARD",
        pat=re.compile(r"(?<!\d)([3-9]\d{15,18})(?!\d)"),
        validate=_luhn,
        mask=_mask_bank,
        conf_ok=80,
        conf_fail=15,
        pid="BANK_CARD_V1",
    ),
    dict(
        typ="SOCIAL_CREDIT",
        pat=re.compile(r"(?<!\w)([0-9A-HJ-NP-RT-UW-Y]{2}\d{6}[0-9A-HJ-NP-RT-UW-Y]{10})(?!\w)"),
        validate=lambda s: True,
        mask=_mask_default,
        conf_ok=72,
        conf_fail=72,
        pid="SOCIAL_CREDIT_V1",
    ),
    dict(
        typ="PASSPORT",
        pat=re.compile(r"(?<!\w)([EeGg]\d{8})(?!\w)"),
        validate=lambda s: True,
        mask=_mask_default,
        conf_ok=80,
        conf_fail=80,
        pid="PASSPORT_V1",
    ),
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

CTX_WIN = 20

def extract_from_text(text: str) -> List[Dict[str, Any]]:
    if not text:
        return []
    results: List[Dict] = []
    seen: set = set()
    for rule in RULES:
        for m in rule["pat"].finditer(text):
            raw = m.group(1)
            cleaned = re.sub(r"[-\s]", "", raw)
            key = (rule["typ"], cleaned)
            if key in seen:
                continue
            seen.add(key)
            ok = rule["validate"](cleaned)
            conf = rule["conf_ok"] if ok else rule["conf_fail"]
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
#  2. 数据抽取与逐行处理 (基于 Server-side Cursor 防止内存溢出)
# ══════════════════════════════════════════════════════

SRC_COLUMNS = [
    "caseno", "updatetime", "calltime", "cmdid", "cmdname", "callerphone", "callername", 
    "occuraddress", "casecontents", "replies", "dutydeptno", "dutydeptname", "callway", 
    "newrecvtype", "newrecvtypename", "neworicharacategory", "neworicharacategoryname", 
    "neworicharatype", "neworicharatypename", "neworicharasubcategory", "neworicharasubcategoryname", 
    "neworicharasubclass", "neworicharasubclassname", "newcharacategory", "newcharacategoryname", 
    "newcharatype", "newcharatypename", "newcharasubcategory", "newcharasubcategoryname", 
    "newcharasubclass", "newcharasubclassname", "lngofcriterion", "latofcriterion", 
    "casemark", "casemarkno", "casemarkok", "casemarkokno", "standardcaseno"
]

def run_yearly_extract(
    src_url: str,
    dst_url: str,
    year: int,
    src_schema: str = "ywdata",
    dst_schema: str = "jcgkzx_monitor",
    batch_size: int = 500
):
    logger.info(f"开始提取年份 {year} 的历史数据，源库模式: {src_schema}，目标库模式: {dst_schema}")
    
    # 建立连接
    try:
        src_conn = psycopg2.connect(src_url)
        src_conn.autocommit = False # 使用事务
        dst_conn = psycopg2.connect(dst_url)
        dst_conn.autocommit = True
        logger.info("数据库连接成功")
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        sys.exit(1)

    start_date = f"{year}-01-01 00:00:00"
    end_date = f"{year+1}-01-01 00:00:00"

    # 使用服务器端游标 (Server-side Cursor)，避免一次性把百万条记录拉进 Python 内存
    server_cursor_name = f"cur_yearly_{year}_{uuid4().hex[:8]}"
    
    select_sql = f"""
        SELECT {", ".join(SRC_COLUMNS)}
        FROM {src_schema}.zq_kshddpt_dsjfx_jq
        WHERE updatetime >= %s AND updatetime < %s
          AND updatetime IS NOT NULL
    """

    upsert_sql = f"""
        INSERT INTO {dst_schema}.zq_jingqing_number_extract (
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
        ) VALUES %s
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

    try:
        # 使用命名游标启用 Server-side Streaming
        with src_conn.cursor(name=server_cursor_name) as src_cur:
            src_cur.itersize = 2000  # 每次从数据库预取 2000 行
            logger.info("正在执行源表查询...")
            src_cur.execute(select_sql, (start_date, end_date))
            
            write_buffer = []
            total_processed_cases = 0
            total_extracted_rows = 0
            total_written_rows = 0
            now = datetime.now()

            while True:
                rows = src_cur.fetchmany(batch_size)
                if not rows:
                    break
                
                # 获取列字段映射关系
                cols = [d[0] for d in src_cur.description]
                
                for r in rows:
                    rec = dict(zip(cols, r))
                    caseno = (rec.get("caseno") or "").strip()
                    if not caseno:
                        continue
                    
                    total_processed_cases += 1
                    
                    # 针对报警内容 casecontents 和 处警情况 replies 两个文本字段提取号码
                    for field in ("casecontents", "replies"):
                        text = rec.get(field) or ""
                        extractions = extract_from_text(text)
                        for item in extractions:
                            val_tuple = (
                                caseno,
                                rec.get("updatetime"),
                                rec.get("calltime"),
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
                                now
                            )
                            write_buffer.append(val_tuple)
                            total_extracted_rows += 1

                # 缓存区达到 batch_size 后刷盘写入目标库
                if len(write_buffer) >= batch_size:
                    with dst_conn.cursor() as dst_cur:
                        execute_values(dst_cur, upsert_sql, write_buffer, page_size=batch_size)
                    total_written_rows += len(write_buffer)
                    logger.info(f"已处理 {total_processed_cases} 条警情，提取并写入 {total_written_rows} 行号码数据...")
                    write_buffer.clear()

            # 处理剩余的数据
            if write_buffer:
                with dst_conn.cursor() as dst_cur:
                    execute_values(dst_cur, upsert_sql, write_buffer, page_size=batch_size)
                total_written_rows += len(write_buffer)
                write_buffer.clear()

        logger.info(f"年份 {year} 历史数据提取完成！")
        logger.info(f"总结: 共读取警情 {total_processed_cases} 条，提取号码 {total_extracted_rows} 个，成功插入/更新目标表 {total_written_rows} 行。")

    except Exception as e:
        logger.error(f"处理数据时发生异常: {e}", exc_info=True)
    finally:
        src_conn.close()
        dst_conn.close()
        logger.info("数据库连接已关闭。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="警情号码历史年提取脚本 (Server-side Cursor 内存安全版)")
    parser.add_argument("--year", type=int, required=True, help="要提取的历史年份 (如 2024)")
    parser.add_argument("--src-url", type=str, help="源数据库 PostgreSQL/Kingbase URL 连接串")
    parser.add_argument("--dst-url", type=str, help="目标数据库 PostgreSQL/Kingbase URL 连接串")
    parser.add_argument("--src-schema", type=str, default="ywdata", help="源数据 Schema 名称")
    parser.add_argument("--dst-schema", type=str, default="jcgkzx_monitor", help="目标数据 Schema 名称")
    parser.add_argument("--batch-size", type=int, default=500, help="单批次提交数量")
    
    args = parser.parse_args()

    # 从命令行参数或环境变量读取连接串
    src_url = args.src_url or os.environ.get("NE_SRC_DB_URL") or os.environ.get("DATABASE_URL")
    dst_url = args.dst_url or os.environ.get("NE_DST_DB_URL") or os.environ.get("DATABASE_URL")

    if not src_url:
        print("错误: 请提供源数据库连接参数 (--src-url 或设置环境变量 DATABASE_URL/NE_SRC_DB_URL)", file=sys.stderr)
        sys.exit(1)
    if not dst_url:
        print("错误: 请提供目标数据库连接参数 (--dst-url 或设置环境变量 DATABASE_URL/NE_DST_DB_URL)", file=sys.stderr)
        sys.exit(1)

    run_yearly_extract(
        src_url=src_url,
        dst_url=dst_url,
        year=args.year,
        src_schema=args.src_schema,
        dst_schema=args.dst_schema,
        batch_size=args.batch_size
    )
