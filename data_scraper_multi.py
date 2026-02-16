# -*- coding: utf-8 -*-
"""
鏁版嵁鎶撳彇鑴氭湰锛坮equests + 绾跨▼姹犲苟鍙?+ Kingbase 鍐欏叆锛?
- 骞跺彂鎶撳彇锛氫娇鐢?ThreadPoolExecutor + requests.Session
- 瑙ｆ瀽锛氫紭鍏?JSON锛岄檷绾х畝鍗?HTML 瑙ｆ瀽锛涗骇鍑轰负 List[dict]锛岄渶瑕佸寘鍚?caseNo 瀛楁
- 鍏ュ簱锛氫汉澶ч噾浠擄紙PostgreSQL 鍗忚鍏煎锛夛紝鎵€鏈夊瓧娈典繚瀛樹负 TEXT
- 鏇存柊妯″紡锛?
  - mode='replace' 鍏ㄩ噺锛氬厛娓呯┖琛ㄥ啀鎻掑叆
  - mode='append' 澧為噺锛氭寜 caseNo 鍋氬敮涓€鏍￠獙锛屽瓨鍦ㄥ垯鏇存柊锛屽惁鍒欐彃鍏?
浣跨敤鍓嶈淇敼 CONFIG 涓殑 session銆乺equest銆乨b銆乼able 绛夐厤缃?

娉ㄦ剰锛氳鍦?main 鍑芥暟涓厤缃疄闄呯殑鐧诲綍URL銆佺敤鎴峰悕鍜屽瘑鐮?
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

# 濡傛灉鐜涓病鏈?psycopg2锛岃鍦ㄦ湰鍦扮绾跨幆澧冨噯澶囧ソ锛圞ingbase 閫氬父鍏煎 psycopg2锛?
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values

def get_end_of_day() -> str:
    """
    鑾峰彇褰撴棩鐨勭粨鏉熸椂闂达紝鏍煎紡涓?'YYYY-MM-DD'
    """
    return datetime.now().strftime("%Y-%m-%d")

def get_begin_of_day(days_ago: int = 0) -> str:
    """
    鑾峰彇鎸囧畾澶╂暟鍓嶇殑寮€濮嬫椂闂达紝鏍煎紡涓?'YYYY-MM-DD'
    """
    date = datetime.now() - timedelta(days=days_ago)
    return date.strftime("%Y-%m-%d")
def get_login_cookie(login_url: str, username: str, password: str) -> str:
    """
    鐧诲綍骞惰幏鍙朇ookie
    """
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
    # 灏嗗瓧鍏歌浆鎹负瀛楃涓?
    return "; ".join([f"{k}={v}" for k, v in cookies.items()])

def get_end_of_day() -> str:
    """
    鑾峰彇褰撴棩鐨勭粨鏉熸椂闂达紝鏍煎紡涓?'YYYY-MM-DD 23:59:59'
    """
    return datetime.now().strftime("%Y-%m-%d")

def get_begin_of_day(days_ago: int = 0) -> str:
    """
    鑾峰彇鎸囧畾澶╂暟鍓嶇殑寮€濮嬫椂闂达紝鏍煎紡涓?'YYYY-MM-DD 00:00:00'
    """
    date = datetime.now() - timedelta(days=days_ago)
    return date.strftime("%Y-%m-%d")

def iter_dates(start: str, end: str, fmt: str = "%Y-%m-%d"):
    """鐢熸垚浠?start 鍒?end锛堝寘鍚級鐨勬棩鏈熷瓧绗︿覆搴忓垪"""
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
    """澶嶅埗 base_params 澶氫唤锛屾寜鏃ユ湡鍖洪棿濉厖 date_key"""
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
    # 骞跺彂涓庢ā寮?
    "mode": "append",  # 鍙€? "replace" 鎴?"append"
    "max_workers": 31,  # 骞跺彂绾跨▼鏁?
    "request_timeout": 180,  # 鍗曡姹傝秴鏃剁

    # Session 鍩虹閰嶇疆锛堟寜闇€淇敼锛?
    "session": {
        "headers": {
           "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.146 Safari/537.36",
            "Accept": "application/json, text/plain, */*;q=0.01",
            "X-Requested-With":"XMLHttpRequest",
            # 绉婚櫎浜嗗啓姝荤殑Cookie
        },
        "cookies": {
            # "sessionid": "your_session_id"
        },
        "proxies": None,  # 渚嬪: {"http": "http://127.0.0.1:8080", "https": "http://127.0.0.1:8080"}
        "verify": True,   # 鍏抽棴璇佷功楠岃瘉鍙涓?False锛堝唴缃戣嚜绛惧満鏅級
        "retry": {
            "enabled": True,
            "retries": 2,
            "backoff": 1.0,  # 绉?
        }
    },

    # 澶氫釜鏁版嵁婧愰厤缃?
    "tasks": [
#         {
#             "name": "璀︽儏鏁版嵁",  # 浠诲姟鍚嶇О锛岀敤浜庢棩蹇楁爣璇?
#             "request": {
#                 "method": "POST",  # "GET" 鎴?"POST"
#                 "url": "http://68.253.2.107/zhksh/case/list",  # 鐩爣 URL锛堢ず渚嬩负鏈湴鏈嶅姟锛?
#                 # 濡傛灉鏄?GET锛氫紶鍏ュ涓?params 鍋氬苟鍙戯紱濡傛灉鏄?POST锛氬彲鐢?json_list 鎴?data_list
#                 "params_list": [
#                     {'beginTime': get_begin_of_day(3), 'endTime': get_end_of_day(), 'callerPhone': '', 'caseNo': '', 'dutyDeptNos': '', 'dutyDeptName': '鍏ㄩ儴', 'charaNoNew': 
# '', 'chara': '鍏ㄩ儴', 'relationInfoNo': '', 'caseStageNew': '', 'oriCharaNoNew': '01000000,02000000,06000000,07000000,08000000,09000000', 'oriChara': '鍒戜簨绫昏鎯?琛屾斂锛堟不瀹夛級绫昏鎯?缇や紬绱ф€ユ眰鍔╃被璀︽儏,鑱斿姩娴佽浆绫昏鎯?绾犵悍绫昏鎯?涓炬姤绫昏鎯?, 'caseSourceNo': '', 'caseSource': '鍏ㄩ儴', 'operatorNo': '', 'policeArea': '', 'policeAreaName': '鍏ㄩ儴', 'keywords': '', 'caseKeywords': '', 'pageSize': '99999', 'pageNum': '1', 'orderByColumn': '', 'isAsc': 'asc'},
#                 ],
#                 "json_list": None,  # 渚嬪: [{"q": "abc"}, {"q": "def"}]
#                 "data_list": None,  # 琛ㄥ崟: [{"k": "v"}]
#             },
#             "table": {
#                 "schema": "ywdata",          # schema锛堟ā寮忓悕锛?
#                 "name": "zq_kshddpt_jq",        # 浠呰〃鍚嶏紝涓嶈鍖呭惈鐐?
#                 "unique_key": "caseNo"
#             }
#         },
        {
            "name": "duty_schedule",  # task name for logging
            "request": {
                "method": "POST",  # "GET" 鎴?"POST"
                "url": "http://68.253.2.107/zhksh/dutySchedule/crossDayList",  # 鐩爣 URL锛堢ず渚嬩负鏈湴鏈嶅姟锛?
                # 濡傛灉鏄?GET锛氫紶鍏ュ涓?params 鍋氬苟鍙戯紱濡傛灉鏄?POST锛氬彲鐢?json_list 鎴?data_list
                "params_list": build_params_by_date_range(
                    {
                        'keywords': '',
                        'deploymentType': '',
                        'deploymentId': '',
                        'deploymentName': '',
                        'deploymentTypeCode': '',
                        'scheduleDate': '',  # 灏嗚鏃ユ湡鍖洪棿瑕嗙洊
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
                "json_list": None,  # 渚嬪: [{"q": "abc"}, {"q": "def"}]
                "data_list": None,  # 琛ㄥ崟: [{"k": "v"}]
            },
            "table": {
                "schema": "ywdata",          # schema锛堟ā寮忓悕锛?
                "name": "zq_kshddpt_zxzgl",        # 浠呰〃鍚嶏紝涓嶈鍖呭惈鐐?
                "unique_key": "scheduleId"
            }
        },        
        # 鍙互娣诲姞鏇村浠诲姟
        # {
        #     "name": "鍏朵粬鏁版嵁婧?,
        #     "request": {
        #         "method": "GET",
        #         "url": "http://example.com/api/data",
        #         "params_list": [
        #             {"page": 1, "size": 100},
        #             {"page": 2, "size": 100},
        #         ],
        #     },
        #     "table": {
        #         "schema": "ywdata",
        #         "name": "other_table",
        #         "unique_key": "id"
        #     }
        # }
    ],

    # 鏁版嵁搴撻厤缃紙Kingbase/PG 鍗忚锛?
    "db": {
        "host": "",
        "port": 0,          # 鎸変綘鐨勪汉澶ч噾浠撶鍙ｄ慨鏀?
        "dbname": "",
        "user": "",
        "password": "",
        "sslmode": "disable",   # 濡傞渶 SSL锛岃鎸夐渶璋冩暣
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

    # 骞跺彂浠诲姟鏋勯€?
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
        # 娌℃湁鎵归噺鍙傛暟锛屽崟娆¤姹?
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
    # 濡傛灉浣跨敤鏃х殑閰嶇疆鏍煎紡锛岃浆鎹负鏂版牸寮?
    if "request" in cfg:
        task_cfg = {
            "name": "compat_task",
            "request": cfg["request"]
        }
        return fetch_all_for_task(cfg, task_cfg)
    else:
        raise ValueError("閰嶇疆鏍煎紡閿欒锛岃浣跨敤 tasks 鏁扮粍鎴?request 瀵硅薄")


def process_single_task(cfg: Dict[str, Any], task_cfg: Dict[str, Any], conn):
    """Fetch, parse, deduplicate and upsert records for one task."""
    task_name = task_cfg.get("name", "unnamed_task")
    table_cfg = task_cfg["table"]
    unique_key = table_cfg["unique_key"]
    mode = cfg["mode"]

    logging.info(f"start task: {task_name}")
    
    # 鎶撳彇鏁版嵁
    responses = fetch_all_for_task(cfg, task_cfg)
    logging.info(f"task[{task_name}] fetched responses: {len(responses)}")

    # 瑙ｆ瀽鏁版嵁
    all_records: List[Dict[str, str]] = []
    for resp in responses:
        try:
            part = parse_response(resp)
            all_records.extend(part)
        except Exception as e:
            logging.exception(f"task[{task_name}] failed: {e}")

    # 鍘婚噸
    dedup_map: Dict[str, Dict[str, str]] = {}
    for r in all_records:
        cno = r.get(unique_key)
        if not cno:
            continue
        dedup_map[str(cno)] = {k: ("" if v is None else str(v)) for k, v in r.items()}

    final_rows = list(dedup_map.values())
    logging.info(f"task[{task_name}] records after dedup: {len(final_rows)}")

    if not final_rows:
        logging.warning(f"task[{task_name}] no records to write")
        return

    # 鍐欏叆鏁版嵁搴?
    try:
        ensure_table_and_columns(conn, table_cfg, unique_key, final_rows[:50])

        if mode == "replace":
            logging.info(f"task[{task_name}] run replace mode")
            replace_records(conn, table_cfg, final_rows)
        else:
            logging.info(f"task[{task_name}] run append mode")
            upsert_records(conn, table_cfg, unique_key, final_rows)

        logging.info(f"task[{task_name}] database write complete")
    except Exception as e:
        logging.exception(f"task[{task_name}] database write failed: {e}")
        conn.rollback()
        raise




def try_to_json(resp: requests.Response) -> Optional[Any]:
    ct = resp.headers.get("Content-Type", "")
    if "application/json" in ct.lower():
        try:
            return resp.json()
        except Exception:
            return None
    # Content-Type 涓嶄竴瀹氭纭紝灏濊瘯 json 瑙ｆ瀽
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
            # 鍒楄〃搴忓垪鍖栦负 JSON 鏂囨湰
            items.append((new_key, json.dumps(v, ensure_ascii=False)))
        else:
            items.append((new_key, "" if v is None else str(v)))
    return dict(items)


def extract_case_no(record: Dict[str, Any]) -> Optional[str]:
    # 浼樺厛鐩存帴閿?
    for key in ["caseNo", "caseno", "case_no", "case_no_str", "caseNO", "CaseNo"]:
        if key in record and record[key]:
            return str(record[key])

    # 鍏滃簳锛氬湪鎵€鏈夊€奸噷姝ｅ垯灏濊瘯
    pattern = re.compile(r"[A-Za-z]{0,4}\d{3,}[-/]?\d*")
    for v in record.values():
        if isinstance(v, str):
            m = pattern.search(v)
            if m:
                return m.group(0)
    return None


def _parse_rows_value(rows_val) -> List[Dict[str, Any]]:
    """
    灏?rows 瀛楁瑙ｆ瀽涓?List[dict]锛?
    - 鑻ヤ负瀛楃涓诧細鍏?json.loads锛屽け璐ュ啀 ast.literal_eval 鍏滃簳
    - 鑻ヤ负鍒楄〃锛氱‘淇濆厓绱犱负 dict锛屼笉鏄垯鍖呬竴灞?{"raw": "..."}
    - 鑻ヤ负瀛楀吀锛氱洿鎺ヤ綔涓轰竴鏉¤褰?
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
    """
    灏嗗崟涓搷搴旇В鏋愪负璁板綍鍒楄〃锛屾瘡鏉¤褰曞寘鍚?caseNo 鍙婂叾浠栨枃鏈瓧娈?
    """
    results: List[Dict[str, str]] = []

    data = try_to_json(resp)

    # 鏂板锛氫紭鍏堝鐞嗗寘鍚?rows 鐨勭粨鏋勶紝鍙繑鍥?rows 涓殑璁板綍
    if data is not None:
        # 椤跺眰涓?list 涓旂涓€椤规槸 dict锛屼笖鍚?rows
        if isinstance(data, list) and data and isinstance(data[0], dict) and "rows" in data[0]:
            rows_list = _parse_rows_value(data[0].get("rows"))
            for obj in rows_list:
                if not isinstance(obj, dict):
                    obj = {"raw": str(obj)}
                # 纭繚瀛樺湪 caseNo
                if not obj.get("caseNo"):
                    cno = extract_case_no({k: ("" if v is None else str(v)) for k, v in obj.items()})
                    if not cno:
                        continue
                    obj["caseNo"] = cno
                # 缁熶竴杞?str
                results.append({k: ("" if v is None else str(v)) for k, v in obj.items()})
            return results

        # 椤跺眰涓?dict锛屼笖鍚?rows
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

    # 闈?JSON锛氱畝鍗曚粠 HTML/鏂囨湰涓尮閰嶏紝浜у嚭涓€鏉℃垨澶氭潯
    text = resp.text or ""
    # 绠€鍗曠ず渚嬶細鎸夋钀芥媶鍒嗭紝姣忔涓€涓褰?
    for i, para in enumerate(re.split(r"\n{2,}", text)):
        para = para.strip()
        if not para:
            continue
        cno_match = re.search(r"[A-Za-z]{0,4}\d{3,}[-/]?\d*", para)
        if not cno_match:
            continue
        record = {
            "caseNo": cno_match.group(0),
            "content": para[:2000]  # 鎴柇閬垮厤杩囬暱
        }
        results.append(record)

    return results


def db_connect(db_cfg: Dict[str, Any]):
    conn = psycopg2.connect(**db_cfg)
    conn.autocommit = False
    return conn

# 鏂板锛氭牴鎹?table 閰嶇疆鐢熸垚鍚堟垚鏍囪瘑绗︼紙鏀寔 schema锛?
def get_table_ident(table_cfg: Dict[str, Any]):
    """
    杩斿洖 (qualified_table_ident, simple_table_name, schema_name)
    - qualified_table_ident: 鍙敤浜?SQL 鐨勫悎鎴愭爣璇嗙锛堝彲鑳芥槸 schema.table锛?
    - simple_table_name: 绾〃鍚嶏紙鐢ㄤ簬鐢熸垚绾︽潫鍚嶇瓑涓嶅厑璁稿寘鍚偣鐨勫満鏅級
    - schema_name: schema 鍚嶏紙鍙兘涓?None锛?
    """
    schema = table_cfg.get("schema")
    name = table_cfg["name"]
    if schema:
        qualified = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(name))
    else:
        qualified = sql.Identifier(name)
    return qualified, name, schema


def ensure_table_and_columns(conn, table_cfg: Dict[str, Any], unique_key: str, sample_rows: List[Dict[str, str]]):
    """
    - 濡傛灉琛ㄤ笉瀛樺湪鍒欏垱寤?
    - 鏍规嵁 sample_rows 涓殑閿姩鎬佽ˉ榻愮己澶卞垪锛圱EXT锛?
    - 涓?unique_key 寤哄敮涓€绾︽潫锛堟垨浣滀负涓婚敭锛?
    """
    all_keys = set([unique_key])
    for r in sample_rows:
        all_keys.update(r.keys())

    tbl_ident, tbl_simple, schema = get_table_ident(table_cfg)

    with conn.cursor() as cur:
        # 鑻ラ厤缃簡 schema锛岀‘淇?schema 瀛樺湪
        if schema:
            cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))

        # 鍒涘缓琛紙濡傛灉涓嶅瓨鍦級
        cols_sql = sql.SQL(", ").join([
            sql.SQL("{} TEXT").format(sql.Identifier(unique_key))
        ])
        create_sql = sql.SQL("CREATE TABLE IF NOT EXISTS {} ( {} )").format(
            tbl_ident,
            cols_sql
        )
        cur.execute(create_sql)

        # 涓?unique_key 寤哄敮涓€绾︽潫锛堝鏋滀笉瀛樺湪锛?
        # 娉ㄦ剰锛氱害鏉熷悕涓嶈兘鍖呭惈鐐癸紝杩欓噷浣跨敤绾〃鍚嶆嫾鎺?
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

        # 鍔ㄦ€佽ˉ鍒?
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

    # 鎵€鏈夊垪锛堢‘淇濋兘涓?TEXT锛?
    all_keys = sorted(set().union(*[row.keys() for row in rows]))
    if unique_key not in all_keys:
        raise ValueError(f"澧為噺/鍐欏叆闇€瑕佸寘鍚敮涓€閿?{unique_key}")

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
        # 娓呯┖鍗冲彲
        with conn.cursor() as cur:
            cur.execute(sql.SQL("TRUNCATE TABLE {}").format(tbl_ident))
        conn.commit()
        return

    # 鍏ㄩ噺妯″紡锛氬厛娓呯┖琛紝鍐嶆壒閲忔彃鍏ワ紙鏃犻渶 ON CONFLICT锛?
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


def build_runtime_config() -> Dict[str, Any]:
    cfg = copy.deepcopy(CONFIG)

    cfg["mode"] = _require_env("MULTI_MODE", cfg.get("mode", "append"))
    cfg["max_workers"] = _int_env("MULTI_MAX_WORKERS", int(cfg.get("max_workers", 31)))
    cfg["request_timeout"] = _int_env("MULTI_REQUEST_TIMEOUT", int(cfg.get("request_timeout", 180)))

    cfg["db"]["host"] = _first_env(["MULTI_DB_HOST", "KINGBASE_HOST"])
    cfg["db"]["port"] = int(_first_env(["MULTI_DB_PORT", "KINGBASE_PORT"]))
    cfg["db"]["dbname"] = _first_env(["MULTI_DB_NAME", "KINGBASE_DBNAME"])
    cfg["db"]["user"] = _first_env(["MULTI_DB_USER", "KINGBASE_USER"])
    cfg["db"]["password"] = _first_env(["MULTI_DB_PASSWORD", "KINGBASE_PASSWORD"])
    cfg["db"]["sslmode"] = _require_env("MULTI_DB_SSLMODE", cfg["db"].get("sslmode", "disable"))

    if not _bool_env("DATA_MULTI_TASK_ENABLED", True):
        cfg["tasks"] = []
        return cfg

    if cfg.get("tasks"):
        duty_task = cfg["tasks"][0]
        duty_task["request"]["url"] = _require_env(
            "MULTI_API_URL_DUTY",
            duty_task["request"].get("url", "")
        )

        begin_days_ago = _int_env("MULTI_BEGIN_DAYS_AGO", 9)
        end_days_ago = _int_env("MULTI_END_DAYS_AGO", 0)
        start_date = (datetime.now() - timedelta(days=begin_days_ago)).strftime("%Y-%m-%d")
        end_date = (datetime.now() - timedelta(days=end_days_ago)).strftime("%Y-%m-%d")

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


def main():
    cfg = build_runtime_config()
    login_url = _require_env("MULTI_LOGIN_URL")
    username = _first_env(["MULTI_LOGIN_USERNAME", "LOGIN_USERNAME"])
    password = _first_env(["MULTI_LOGIN_PASSWORD", "LOGIN_PASSWORD"])

    try:
        cookie = get_login_cookie(login_url, username, password)
        cfg["session"]["headers"]["Cookie"] = cookie
    except Exception as e:
        logging.error(f"failed to get login cookie: {e}")
        return

    tasks = cfg.get("tasks", [])
    
    if not tasks:
        logging.error("no tasks configured")
        return

    # 寤虹珛鏁版嵁搴撹繛鎺?
    conn = None
    try:
        conn = db_connect(cfg["db"])
        
        # 澶勭悊姣忎釜浠诲姟
        for task_cfg in tasks:
            try:
                process_single_task(cfg, task_cfg, conn)
            except Exception as e:
                logging.error(
                    f"task failed: {task_cfg.get('name', 'unnamed_task')} | error: {e}"
                )
                # 缁х画澶勭悊涓嬩竴涓换鍔★紝涓嶄腑鏂暣涓祦绋?

        logging.info("all tasks finished")
    except Exception as e:
        logging.exception(f"database connection or processing failed: {e}")
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()

