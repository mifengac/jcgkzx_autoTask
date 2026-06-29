#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
打架斗殴语义特征提取 - 历史回溯版(内网手动执行)

用于一次性补提历史区间(如 2025-01-01 ~ 2026-06-28)的打架斗殴警情特征。
与平台实时增量任务 dajia_feature_extract.py 共用同一套清洗 / Prompt / 枚举 / 落库
逻辑(直接 import 复用, 保证打标完全一致), 但针对"几万条 + 大模型耗时数小时"的
回填场景做了三件实时任务没有的事:

  1. 显式日期区间(--begin/--end), 不走水位线 —— 实时任务空表只回溯3天, 刷不到历史。
  2. 服务端游标流式读源表(itersize), 内存恒定, 不怕源表大。
  3. 断点续跑 + 分批落库 ——
       - 每攒够 --batch-size 条警情就并发抽取并 UPSERT 一次, 崩溃最多丢一批;
       - --resume(默认开)跳过目标表里已 extract_status='ok' 的 caseno,
         重跑时只补未完成/失败的, 不重复烧共享 key 配额。

用法:
  python3 dajia_feature_extract_backfill.py \
    --begin 2025-01-01 --end 2026-06-28 \
    --src-url "host=127.0.0.1 port=54321 dbname=ywdata user=postgres password=xxx" \
    --dst-url "host=127.0.0.1 port=54321 dbname=jcgkzx_monitor user=postgres password=xxx" \
    --concurrency 3 --batch-size 200

  RUIZHI_API_KEY 从环境变量读, 不传命令行。源/目标库也可用环境变量(同实时任务回退链)。

依赖: psycopg2 (其余仅标准库 + 同目录 dajia_feature_extract.py)。
"""

from __future__ import annotations

import argparse
import concurrent.futures
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import execute_values

# 复用实时任务的核心逻辑(同目录), 保证清洗/Prompt/枚举/列顺序完全一致
import dajia_feature_extract as core

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ── 单条抽取(并发调用; 退避重试, 复用 core 的客户端与解析) ──────────
def extract_one(
    client: "core.RuizhiClient",
    cjqk_cleaned: str,
    occuraddress: str,
    retries: int,
    max_tokens: int,
    temperature: float,
) -> Dict[str, Any]:
    last_error = ""
    raw_answer = ""
    for attempt in range(retries + 1):
        try:
            resp = client.chat(
                core.build_messages(cjqk_cleaned, occuraddress), max_tokens, temperature
            )
            raw_answer = core._model_content(resp)
            parsed = core.extract_json_object(raw_answer)
            feats = core.map_features(parsed)
            feats.update(extract_status="ok", extract_error="", raw_answer=raw_answer)
            return feats
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                sleep_s = min(30, 2 ** attempt)
                if isinstance(exc, core.ApiError) and exc.status_code == 429:
                    sleep_s = max(sleep_s, 8)
                time.sleep(sleep_s)
    return {"extract_status": "failed", "extract_error": last_error, "raw_answer": raw_answer}


def _build_upsert_sql(dst_schema: str) -> str:
    set_clause = ",\n            ".join(f"{c} = EXCLUDED.{c}" for c in core._UPDATE_COLUMNS)
    return f"""
        INSERT INTO {dst_schema}.zq_dajia_feature_extract (
            {', '.join(core.INSERT_COLUMNS)}
        )
        VALUES %s
        ON CONFLICT (caseno) DO UPDATE SET
            {set_clause},
            updated_at = CURRENT_TIMESTAMP
    """


def _fetch_subclass_codes(dst_conn, config_schema: str, case_type: str) -> List[str]:
    """jcgkzx_monitor.case_type_config 里 leixing=case_type 的 newcharasubclass_list。"""
    sql = (
        f"SELECT unnest(newcharasubclass_list) "
        f"FROM {config_schema}.case_type_config WHERE leixing = %s"
    )
    with dst_conn.cursor() as cur:
        cur.execute(sql, (case_type,))
        codes = [r[0] for r in cur.fetchall() if r[0] is not None]
    if not codes:
        raise ValueError(
            f"{config_schema}.case_type_config 中 leixing='{case_type}' 未取到代码，请核对配置表。"
        )
    logger.info(f"case_type_config: leixing='{case_type}' 匹配 {len(codes)} 个叶子代码")
    return codes


def _load_done_casenos(dst_conn, dst_schema: str, begin: str, end: str) -> set:
    """已成功(extract_status='ok')的 caseno, 断点续跑时跳过。"""
    done: set = set()
    sql = (
        f"SELECT caseno FROM {dst_schema}.zq_dajia_feature_extract "
        f"WHERE extract_status = 'ok' AND calltime >= %s AND calltime < %s"
    )
    try:
        with dst_conn.cursor() as cur:
            cur.execute(sql, (begin, end))
            for (cn,) in cur:
                if cn:
                    done.add(cn)
    except Exception as exc:
        # 目标表不存在或无数据时, 当作无已完成项
        logger.warning(f"读取已完成 caseno 失败(忽略, 全量重跑): {exc}")
    logger.info(f"断点续跑: 已完成 {len(done)} 条, 将跳过")
    return done


def _process_batch(
    incidents: List[Dict],
    client: "core.RuizhiClient",
    helper: "core.DajiaFeatureTask",
    done: set,
    resume: bool,
    concurrency: int,
    retries: int,
    max_tokens: int,
    temperature: float,
    now: datetime,
) -> tuple:
    """对一批警情: 清洗 -> 有效案情并发抽取 -> 组装行。返回 (rows, 计数dict)。"""
    cleaned = [core.clean_one(r.get("replies")) for r in incidents]

    to_model = [
        i for i, c in enumerate(cleaned)
        if c.get("data_quality_flag") == "有效案情"
        and not (resume and (incidents[i].get("caseno") or "").strip() in done)
    ]
    feats_by_idx: Dict[int, Dict[str, Any]] = {}
    if to_model:
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            fut_to_idx = {
                pool.submit(
                    extract_one,
                    client,
                    cleaned[i].get("cjqk_cleaned", ""),
                    incidents[i].get("occuraddress", "") or "",
                    retries,
                    max_tokens,
                    temperature,
                ): i
                for i in to_model
            }
            for fut in concurrent.futures.as_completed(fut_to_idx):
                feats_by_idx[fut_to_idx[fut]] = fut.result()

    rows: List[tuple] = []
    cnt = {"ok": 0, "failed": 0, "skipped": 0, "resume_skip": 0}
    for i, rec in enumerate(incidents):
        caseno = (rec.get("caseno") or "").strip()
        if resume and caseno in done:
            cnt["resume_skip"] += 1
            continue  # 已完成, 不重写、不调模型
        feats = feats_by_idx.get(i)
        if feats is None:
            feats = {"extract_status": "skipped", "extract_error": "", "raw_answer": ""}
            cnt["skipped"] += 1
        elif feats.get("extract_status") == "ok":
            cnt["ok"] += 1
        else:
            cnt["failed"] += 1
        rows.append(helper._assemble_row(rec, cleaned[i], feats, now))
    return rows, cnt


def run_backfill(
    src_url: str,
    dst_url: str,
    begin: str,
    end: str,
    api_key: str,
    src_schema: str = "ywdata",
    dst_schema: str = "jcgkzx_monitor",
    case_type: str = "打架斗殴",
    config_schema: str = "jcgkzx_monitor",
    batch_size: int = 200,
    concurrency: int = 3,
    retries: int = 2,
    max_tokens: int = 700,
    temperature: float = 0.1,
    timeout: float = 120.0,
    resume: bool = True,
):
    logger.info(
        f"回填区间 [{begin} ~ {end})  源={src_schema}.zq_kshddpt_dsjfx_jq  "
        f"目标={dst_schema}.zq_dajia_feature_extract  并发={concurrency}  批={batch_size}"
    )
    src_conn = psycopg2.connect(src_url)
    src_conn.autocommit = False  # 命名游标需在事务中
    dst_conn = psycopg2.connect(dst_url)
    dst_conn.autocommit = True
    client = core.RuizhiClient(core.RUIZHI_BASE_URL, api_key, timeout)
    helper = core.DajiaFeatureTask.__new__(core.DajiaFeatureTask)  # 仅借用 _assemble_row
    upsert_sql = _build_upsert_sql(dst_schema)

    codes = _fetch_subclass_codes(dst_conn, config_schema, case_type)
    done = _load_done_casenos(dst_conn, dst_schema, begin, end) if resume else set()

    # 用代码列 neworicharasubclass(原始)/newcharasubclass(确认) 匹配 case_type_config 代码集
    select_sql = f"""
        SELECT {', '.join(core.BASE_COLUMNS)}
        FROM {src_schema}.zq_kshddpt_dsjfx_jq
        WHERE calltime >= %s AND calltime < %s AND calltime IS NOT NULL
          AND (neworicharasubclass = ANY(%s) OR newcharasubclass = ANY(%s))
        ORDER BY calltime
    """
    cur_name = f"cur_dajia_backfill_{os.getpid()}"
    tot = {"read": 0, "ok": 0, "failed": 0, "skipped": 0, "resume_skip": 0, "written": 0}
    now = datetime.now()
    try:
        with src_conn.cursor(name=cur_name) as src_cur:
            src_cur.itersize = max(batch_size, 1000)
            src_cur.execute(select_sql, (begin, end, codes, codes))
            cols = None
            buf: List[Dict] = []
            while True:
                rows = src_cur.fetchmany(batch_size)
                if not rows:
                    break
                if cols is None:
                    cols = [d[0] for d in src_cur.description]
                buf = [dict(zip(cols, r)) for r in rows]
                tot["read"] += len(buf)

                out_rows, cnt = _process_batch(
                    buf, client, helper, done, resume,
                    concurrency, retries, max_tokens, temperature, now,
                )
                for k in ("ok", "failed", "skipped", "resume_skip"):
                    tot[k] += cnt[k]
                if out_rows:
                    with dst_conn.cursor() as dc:
                        execute_values(dc, upsert_sql, out_rows, page_size=batch_size)
                    tot["written"] += len(out_rows)
                logger.info(
                    f"进度: 读 {tot['read']} | 成功 {tot['ok']} 失败 {tot['failed']} "
                    f"跳过(非有效) {tot['skipped']} 续跑跳过 {tot['resume_skip']} | 写入 {tot['written']}"
                )
        logger.info("=" * 60)
        logger.info(
            f"回填完成 [{begin}~{end}): 读 {tot['read']} 条; 抽取成功 {tot['ok']}, "
            f"失败 {tot['failed']}, 非有效跳过 {tot['skipped']}, 续跑跳过 {tot['resume_skip']}; "
            f"写入 {tot['written']} 行。"
        )
        if tot["failed"]:
            logger.info("提示: 有失败行(extract_status='failed'), 直接重跑本命令即可只补失败/未完成项。")
    except Exception as exc:
        logger.error(f"回填异常: {exc}", exc_info=True)
        raise
    finally:
        src_conn.close()
        dst_conn.close()
        logger.info("连接已关闭。")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="打架斗殴特征提取 - 历史回溯版(内存安全+断点续跑)")
    p.add_argument("--begin", required=True, help="起始日期(含), 如 2025-01-01")
    p.add_argument("--end", default="2026-06-28", help="结束日期(不含), 默认 2026-06-28")
    p.add_argument("--src-url", help="源库 DSN/URL, 缺省读环境变量")
    p.add_argument("--dst-url", help="目标库 DSN/URL, 缺省读环境变量")
    p.add_argument("--src-schema", default="ywdata")
    p.add_argument("--dst-schema", default="jcgkzx_monitor")
    p.add_argument("--case-type", default="打架斗殴", help="case_type_config.leixing 值")
    p.add_argument("--config-schema", default="jcgkzx_monitor", help="case_type_config 所在 schema")
    p.add_argument("--batch-size", type=int, default=200, help="每批警情数(也是落库刷新粒度)")
    p.add_argument("--concurrency", type=int, default=3, help="锐智并发(共享key建议<=4)")
    p.add_argument("--retries", type=int, default=2)
    p.add_argument("--max-tokens", type=int, default=700)
    p.add_argument("--temperature", type=float, default=0.1)
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--no-resume", action="store_true", help="关闭断点续跑(默认开启)")
    args = p.parse_args(argv)

    src_url = (
        args.src_url
        or os.environ.get("DJ_SRC_DB_URL") or os.environ.get("DJ_DB_URL")
        or os.environ.get("NE_SRC_DB_URL") or os.environ.get("NE_DB_URL")
        or os.environ.get("DATABASE_URL")
    )
    dst_url = (
        args.dst_url
        or os.environ.get("DJ_DST_DB_URL") or os.environ.get("DJ_DB_URL")
        or os.environ.get("NE_DST_DB_URL") or os.environ.get("NE_DB_URL")
        or os.environ.get("DATABASE_URL")
    )
    api_key = os.environ.get("RUIZHI_API_KEY")
    if not src_url or not dst_url:
        print("错误: 请提供 --src-url/--dst-url 或设置库连接环境变量", file=sys.stderr)
        return 2
    if not api_key:
        print("错误: 缺少环境变量 RUIZHI_API_KEY", file=sys.stderr)
        return 2
    if args.concurrency > 4:
        print(f"拒绝并发 {args.concurrency}: 共享 key 上限建议 4。", file=sys.stderr)
        return 2

    run_backfill(
        src_url=core._clean_url(src_url),
        dst_url=core._clean_url(dst_url),
        begin=args.begin,
        end=args.end,
        api_key=api_key,
        src_schema=args.src_schema,
        dst_schema=args.dst_schema,
        case_type=args.case_type,
        config_schema=args.config_schema,
        batch_size=args.batch_size,
        concurrency=args.concurrency,
        retries=args.retries,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        timeout=args.timeout,
        resume=not args.no_resume,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
