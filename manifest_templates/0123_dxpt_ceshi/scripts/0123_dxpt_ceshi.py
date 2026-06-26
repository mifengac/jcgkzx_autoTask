from __future__ import annotations

import logging
import os
import re
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha1
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4
from zoneinfo import ZoneInfo

try:
    from autotask_api.services.time_utils import to_shanghai_naive
except ModuleNotFoundError:
    SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

    def to_shanghai_naive(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value
        return value.astimezone(SHANGHAI_TZ).replace(tzinfo=None)


LOGGER = logging.getLogger("0123_dxpt_ceshi")


TRANSFER_STATUS_CODES = {
    "12小时内未移交": "u12",
    "24小时内未移交": "u24",
    "36小时内未移交": "u36",
    "48小时内未移交": "u48",
    "72小时内未移交": "u72",
    "超出72小时仍未移交": "u72plus",
    "超出72小时未移交": "u72plus",
    "超出12小时未移交": "over12",
    "超出24小时未移交": "over24",
    "超出36小时未移交": "over36",
    "超出48小时未移交": "over48",
    "48小时内移交": "done48",
    "72小时内移交": "done72",
    "超出72小时移交": "done72plus",
}


KINGBASE_SQL = r"""
SELECT DISTINCT ON (a.systemid)
    a.systemid AS systemid,
    a.ywlsh AS business_no,
    a.jfmc AS dispute_name,
    c.detail AS dispute_type,
    a.jyqk AS summary,
    a.fssj AS happened_at,
    CASE
        WHEN a.sssj = '445300000000' THEN '云浮市公安局'
        ELSE a.sssj
    END AS city_bureau,
    CASE
        WHEN substring(a.ssfj, 1, 6) = '445302' THEN '云城分局'
        WHEN substring(a.ssfj, 1, 6) = '445303' THEN '云安分局'
        WHEN substring(a.ssfj, 1, 6) = '445321' THEN '新兴县公安局'
        WHEN substring(a.ssfj, 1, 6) = '445381' THEN '罗定市公安局'
        WHEN substring(a.ssfj, 1, 6) = '445322' THEN '郁南县公安局'
        ELSE a.ssfj
    END AS branch_name,
    e.sspcsdm AS station_code,
    e.sspcs AS station_name,
    d.detail AS flow_status,
    a.djsj AS registered_at,
    a.djdw_mc AS register_unit_name,
    a.xgsj AS updated_at,
    b.yjqqsj AS transfer_requested_at,
    g.detail AS feedback_status,
    CASE
        WHEN b.tczt = '1' THEN '已化解'
        WHEN b.tczt = '0' THEN '未化解'
        ELSE b.tczt
    END AS dispose_status,
    b.rksj AS imported_at,
    CASE
        WHEN b.orderstate = '2' THEN '已登记/已分发待确认'
        WHEN b.orderstate = '5' THEN '处理中/其他'
        WHEN b.orderstate = '6' THEN '已结案'
        WHEN b.orderstate = '4' THEN '处理中/业务系统已受理'
        ELSE b.orderstate
    END AS workflow_node_status,
    b.processtime AS workflow_node_time,
    round((EXTRACT(epoch FROM (b.yjqqsj - a.djsj)) / 86400 * 24), 2) AS transfer_hours,
    CASE
        WHEN round((EXTRACT(epoch FROM (now() - a.djsj)) / 86400 * 24), 2) <= 12
            AND (b.yjqqsj IS NULL OR g.detail = '粤平安退回' OR d.detail = '移交失败' OR d.detail <> '已移交')
            THEN '12小时内未移交'
        WHEN round((EXTRACT(epoch FROM (now() - a.djsj)) / 86400 * 24), 2) <= 24
            AND (b.yjqqsj IS NULL OR g.detail = '粤平安退回' OR d.detail = '移交失败' OR d.detail <> '已移交')
            THEN '24小时内未移交'
        WHEN round((EXTRACT(epoch FROM (now() - a.djsj)) / 86400 * 24), 2) <= 36
            AND (b.yjqqsj IS NULL OR g.detail = '粤平安退回' OR d.detail = '移交失败' OR d.detail <> '已移交')
            THEN '36小时内未移交'
        WHEN round((EXTRACT(epoch FROM (now() - a.djsj)) / 86400 * 24), 2) <= 48
            AND (b.yjqqsj IS NULL OR g.detail = '粤平安退回' OR d.detail = '移交失败' OR d.detail <> '已移交')
            THEN '48小时内未移交'
        WHEN round((EXTRACT(epoch FROM (now() - a.djsj)) / 86400 * 24), 2) <= 72
            AND (b.yjqqsj IS NULL OR g.detail = '粤平安退回' OR d.detail = '移交失败' OR d.detail <> '已移交')
            THEN '72小时内未移交'
        WHEN round((EXTRACT(epoch FROM (now() - a.djsj)) / 86400 * 24), 2) > 72
            AND (b.yjqqsj IS NULL OR g.detail = '粤平安退回' OR d.detail = '移交失败' OR d.detail <> '已移交')
            THEN '超出72小时仍未移交'
        WHEN round((EXTRACT(epoch FROM (b.yjqqsj - a.djsj)) / 86400 * 24), 2) <= 48
            AND (b.yjqqsj IS NOT NULL OR g.detail <> '粤平安退回' OR d.detail <> '移交失败')
            THEN '48小时内移交'
        WHEN round((EXTRACT(epoch FROM (b.yjqqsj - a.djsj)) / 86400 * 24), 2) <= 72
            AND (b.yjqqsj IS NOT NULL OR g.detail <> '粤平安退回' OR d.detail <> '移交失败')
            THEN '72小时内移交'
        ELSE '超出72小时移交'
    END AS transfer_status
FROM (
    SELECT *
    FROM stdata.b_per_mdjfjfsjgl
    WHERE deleteflag = '0'
      AND sfgazzfw = '0'
      AND djsj >= %s
) a
LEFT JOIN (
    SELECT *
    FROM stdata.b_per_mdjfypafhsj
    WHERE deleteflag = '0'
) b ON a.systemid = b.systemid
LEFT JOIN (
    SELECT code, detail
    FROM stdata.s_sg_dict
    WHERE kind_code = 'SQRY_XGNMK_MDJF_JFLX'
) c ON a.jflx = c.code
LEFT JOIN (
    SELECT code, detail
    FROM stdata.s_sg_dict
    WHERE kind_code = 'SQRY_XGNMK_MDJF_LCZT'
) d ON a.lczt = d.code
LEFT JOIN (
    SELECT code, detail
    FROM stdata.s_sg_dict
    WHERE kind_code = 'SQRY_XGNMK_MDJF_YJFKZT'
) g ON b.yjfkzt = g.code
LEFT JOIN stdata.b_dic_zzjgdm e ON a.sspcs = e.sspcsdm
WHERE a.lczt <> '6'
"""


@dataclass(frozen=True)
class KingbaseConfig:
    host: str
    port: int
    dbname: str
    user: str
    password: str


def _runtime_to_env_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set)):
        return ",".join(str(item) for item in value if item not in (None, ""))
    return str(value)


@contextmanager
def _temporary_runtime_env(runtime_config: Dict[str, Any], mapping: Dict[str, str]):
    original: Dict[str, Optional[str]] = {}
    try:
        for runtime_key, env_key in mapping.items():
            if runtime_key not in runtime_config:
                continue
            original[env_key] = os.environ.get(env_key)
            value = runtime_config.get(runtime_key)
            if value in (None, ""):
                os.environ.pop(env_key, None)
            else:
                os.environ[env_key] = _runtime_to_env_value(value)
        yield
    finally:
        for env_key, value in original.items():
            if value is None:
                os.environ.pop(env_key, None)
            else:
                os.environ[env_key] = value


def _require_env(name: str, default: Optional[str] = None) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        if default is not None and str(default).strip():
            return str(default).strip()
        raise RuntimeError(f"缺少环境变量 {name}，请在任务运行配置中填写。")
    return value.strip()


def _runtime_bool(runtime_config: Dict[str, Any], name: str, default: bool = False) -> bool:
    value = runtime_config.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def load_kingbase_config_from_env() -> KingbaseConfig:
    return KingbaseConfig(
        host=_require_env("KINGBASE_HOST"),
        port=int(_require_env("KINGBASE_PORT")),
        dbname=_require_env("KINGBASE_DBNAME"),
        user=_require_env("KINGBASE_USER"),
        password=_require_env("KINGBASE_PASSWORD"),
    )


def _format_dt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return to_shanghai_naive(value).strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def build_sms_content(row: Dict[str, Any]) -> str:
    return (
        f"基础管控中心提醒{row.get('branch_name') or ''}{row.get('station_name') or ''}"
        f"【纠纷名称】：{row.get('dispute_name') or ''}；"
        f"{row.get('transfer_status') or ''}；"
        f"【纠纷登记时间】：{_format_dt(row.get('registered_at'))}；"
        f"【纠纷类型】：{row.get('dispute_type') or ''}；"
        f"【发生时间】：{_format_dt(row.get('happened_at'))}"
    )


def should_emit(row: Dict[str, Any], *, only_untransferred: bool) -> bool:
    if not only_untransferred:
        return True
    transfer_status = row.get("transfer_status")
    return transfer_status is None or "未移交" in str(transfer_status)


def compute_event_ids(rows: List[Dict[str, Any]]) -> List[str]:
    business_numbers = [str(row.get("business_no") or "").strip() for row in rows]
    counts = Counter([value for value in business_numbers if value])
    event_ids: List[str] = []
    for row, business_no in zip(rows, business_numbers):
        systemid = str(row.get("systemid") or "").strip()
        if not business_no or counts.get(business_no, 0) > 1:
            event_ids.append(systemid)
        else:
            event_ids.append(business_no)
    return event_ids


def transfer_status_code(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "unknown"
    mapped = TRANSFER_STATUS_CODES.get(text)
    if mapped:
        return mapped
    return "s" + sha1(text.encode("utf-8")).hexdigest()[:10]


def build_dedup_event_key(source_event_id: str, transfer_status: Any) -> str:
    return f"DXPT:{source_event_id}:{transfer_status_code(transfer_status)}"


def fetch_kingbase_rows(cfg: KingbaseConfig, start_date: str) -> List[Dict[str, Any]]:
    try:
        import psycopg2
        import psycopg2.extras
    except ModuleNotFoundError as exc:
        raise RuntimeError("缺少依赖 psycopg2，无法连接人大金仓。") from exc

    LOGGER.info("connect kingbase: %s:%s/%s", cfg.host, cfg.port, cfg.dbname)
    conn = psycopg2.connect(
        host=cfg.host,
        port=cfg.port,
        dbname=cfg.dbname,
        user=cfg.user,
        password=cfg.password,
    )
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(KINGBASE_SQL, (start_date,))
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def iter_targets(rows: List[Dict[str, Any]], *, only_untransferred: bool) -> Iterable[Dict[str, Any]]:
    for row in rows:
        if should_emit(row, only_untransferred=only_untransferred):
            yield row


def normalize_result_row(
    row: Dict[str, Any],
    event_id: str,
    index: int,
    *,
    dedup_with_transfer_status: bool,
) -> Dict[str, Any]:
    systemid = str(row.get("systemid") or "").strip()
    business_no = str(row.get("business_no") or "").strip()
    station_code = str(row.get("station_code") or "").strip()
    source_event_id = event_id or systemid or business_no or f"dxpt_{uuid4().hex}"
    status_code = transfer_status_code(row.get("transfer_status"))
    resolved_event_id = (
        build_dedup_event_key(source_event_id, row.get("transfer_status"))
        if dedup_with_transfer_status
        else source_event_id
    )

    result = dict(row)
    result.update(
        {
            "event_id": resolved_event_id,
            "event_key": resolved_event_id,
            "source_event_id": source_event_id,
            "dedup_status_code": status_code,
            "dedup_key": resolved_event_id,
            "case_no": business_no or systemid or f"dxpt_case_{index}",
            "dwdm": station_code,
            "sspcsdm": station_code,
            "message_text": build_sms_content(row),
            "message_vars": {
                "business_no": business_no,
                "systemid": systemid,
                "source_event_id": source_event_id,
                "dedup_status_code": status_code,
                "station_code": station_code,
                "branch_name": row.get("branch_name") or "",
                "station_name": row.get("station_name") or "",
                "dispute_name": row.get("dispute_name") or "",
                "dispute_type": row.get("dispute_type") or "",
                "transfer_status": row.get("transfer_status") or "",
                "registered_at": _format_dt(row.get("registered_at")),
                "happened_at": _format_dt(row.get("happened_at")),
            },
        }
    )
    return result


def run(context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    context = context or {}
    runtime_config = context.get("runtime_config")
    if not isinstance(runtime_config, dict):
        runtime_config = {}

    env_mapping = {
        "kingbase_host": "KINGBASE_HOST",
        "kingbase_port": "KINGBASE_PORT",
        "kingbase_dbname": "KINGBASE_DBNAME",
        "kingbase_user": "KINGBASE_USER",
        "kingbase_password": "KINGBASE_PASSWORD",
        "dxpt_start_date": "DXPT_START_DATE",
    }

    with _temporary_runtime_env(runtime_config, env_mapping):
        start_date = _require_env("DXPT_START_DATE", "2026-01-01")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", start_date):
            raise RuntimeError("DXPT_START_DATE must be in YYYY-MM-DD format.")

        rows = fetch_kingbase_rows(load_kingbase_config_from_env(), start_date)
        targets = list(
            iter_targets(
                rows,
                only_untransferred=_runtime_bool(
                    runtime_config, "only_untransferred", default=True
                ),
            )
        )

        limit = int(runtime_config.get("limit") or runtime_config.get("dxpt_limit") or 0)
        if limit > 0:
            targets = targets[:limit]

        event_ids = compute_event_ids(targets)
        dedup_with_transfer_status = _runtime_bool(
            runtime_config, "dedup_with_transfer_status", default=True
        )
        return [
            normalize_result_row(
                row,
                event_id,
                index,
                dedup_with_transfer_status=dedup_with_transfer_status,
            )
            for index, (row, event_id) in enumerate(zip(targets, event_ids), start=1)
        ]
