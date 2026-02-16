#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monitor script for juvenile case notifications.

Behavior:
1. Login and query case records from monitor API.
2. Resolve recipient mobiles (Kingbase first, optional SMS_MOBILES fallback).
3. Deduplicate by caseNo + mobile + DEDUP_HOURS and send SMS through Oracle.

Key environment variables:
- LOGIN_USERNAME / LOGIN_PASSWORD
- MONITOR_LOGIN_URL / MONITOR_API_URL
- ORACLE_DSN / ORACLE_USER / ORACLE_PASSWORD / ORACLE_CLIENT_LIB_DIR
- SMS_USERID / SMS_PASSWORD / SMS_USERPORT
- KINGBASE_HOST / KINGBASE_PORT / KINGBASE_DBNAME / KINGBASE_USER / KINGBASE_PASSWORD
- KG_TARGET_XQDM (default: 445300)
- SMS_MOBILES (fallback only when Kingbase is unavailable)
- DEDUP_HOURS (default: 12)
"""

import os
import re
import json
import time
import logging
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

import requests

# 甯搁噺瀹氫箟
DEFAULT_LOGIN_URL = "http://68.253.2.111/dsjfx/login"
DEFAULT_API_URL = "http://68.253.2.111/dsjfx/case/list"
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds
MOBILE_PATTERN = re.compile(r"^1[3-9]\d{9}$")

# 鍥哄畾璇锋眰鍙傛暟
BASE_PARAMS = {
    "params[colArray]": "selectItem,callTime,newRecvTypeName,newCaseSourceName,newComeTelephoneName,newOriCharaSubclassName,newCharaSubclassName,newCaseHandleStatusName,caseResultStateName,dutyDeptName,77,",
    "newCaseSourceNo": "",
    "newCaseSource": "鍏ㄩ儴",
    "dutyDeptNo": "",
    "dutyDeptName": "鍏ㄩ儴",
    "newCharaSubclassNo": "",
    "newCharaSubclass": "鍏ㄩ儴",
    "newOriCharaSubclassNo": "01,0101,010101,01010101,01010102,01010103,01010104,01010105,01010106,01010107,01010199,010102,01010201,01010202,01010299,010103,01010301,01010302,01010303,01010399,010104,010105,010199,0102,010201,010202,010203,010204,010205,010206,010207,01020701,01020702,01020703,01020704,01020705,01020799,010208,01020801,01020802,01020803,01020804,01020805,01020806,01020807,01020899,010209,01020901,01020902,01020903,01020904,01020999,010210,010211,010212,01021201,01021202,01021203,01021204,01021205,01021206,01021207,01021208,01021299,010213,01021301,01021302,01021303,01021304,01021305,01021306,01021307,01021399,010214,01021401,01021402,01021403,01021404,01021405,01021406,01021407,01021499,010215,01021501,01021502,01021503,01021504,01021505,01021599,010216,010299,0103,010301,010302,01030201,01030202,010303,010304,010305,01030501,01030502,01030503,01030504,010306,01030601,01030602,01030699,010307,010308,010309,01030901,01030902,01030903,01030904,01030999,010310,01031001,01031002,01031003,01031099,010311,010312,010313,010314,010315,010316,01031601,01031602,01031603,01031604,01031605,01031606,01031699,010317,01031701,01031702,01031703,01031704,01031799,010318,01031801,01031802,01031803,01031804,01031805,01031899,010319,010320,010321,010399,0104,010401,01040101,01040102,01040103,01040104,01040105,01040106,01040107,01040108,01040109,01040110,01040199,010402,01040201,01040202,01040299,010403,01040301,01040302,01040303,01040304,01040305,01040306,01040307,01040308,01040309,01040310,01040311,01040312,01040313,01040314,01040315,01040316,01040317,01040318,01040319,01040320,01040321,01040322,01040399,010404,01040401,01040402,01040403,01040404,01040405,01040406,01040407,01040408,01040409,01040410,01040411,01040412,01040413,01040414,01040415,01040416,01040417,01040418,01040419,01040420,01040421,01040422,01040423,01040424,01040425,01040499,010405,01040501,01040502,01040503,01040504,01040505,01040506,01040507,01040508,01040509,01040510,01040511,01040512,01040599,010406,01040601,01040602,01040603,01040699,010407,010408,010409,010410,010411,010412,010499,0105,010501,01050101,01050102,01050103,01050104,01050105,01050106,01050107,01050108,01050109,01050110,01050111,01050112,01050113,01050114,01050115,01050116,01050117,01050118,01050119,01050120,01050121,01050199,010502,01050201,01050299,010503,01050301,01050302,01050303,01050304,01050399,010504,01050401,01050402,01050403,01050404,01050405,01050499,010505,01050501,01050502,01050503,01050599,010506,01050601,01050602,01050603,01050604,01050605,01050699,010507,01050701,01050702,01050703,01050704,01050705,01050706,01050799,010508,01050801,01050802,01050803,01050804,01050805,01050806,01050807,01050808,01050809,01050899,010509,01050901,01050902,01050903,01050904,01050905,01050906,01050907,01050908,01050909,01050910,01050911,01050912,01050913,01050999,010510,01051001,01051002,01051003,01051004,01051005,01051006,01051007,01051008,01051009,01051099,010511,01051101,01051102,01051103,01051104,01051199,010512,010598,01059801,01059802,010599,0106,010601,01060101,01060102,01060103,01060104,01060105,01060106,01060107,01060108,01060199,010602,01060201,01060202,01060203,01060204,01060205,01060206,01060207,01060299,010603,01060301,01060302,01060303,01060304,01060305,01060399,010604,01060401,01060402,01060403,01060404,01060405,01060406,01060407,01060408,01060499,010605,01060501,01060502,01060503,01060504,01060505,01060506,01060507,01060598,01060599,010606,01060690,01060691,01060692,01060693,01060694,01060695,01060696,01060697,01060698,01060699,010607,010608,010699,0199,02,0201,020101,02010101,02010102,02010103,02010104,02010105,02010199,020102,020103,02010301,02010302,02010303,02010304,02010305,02010399,020104,02010401,02010402,02010403,02010404,02010499,020105,02010501,02010599,020106,02010601,02010602,02010699,020107,02010701,02010702,02010703,02010704,02010705,02010706,02010799,020108,02010801,02010802,02010803,02010899,020109,02010901,02010902,02010903,02010992,02010993,02010994,02010995,02010996,02010997,02010998,02010999,020110,02011001,02011002,02011003,02011099,020111,020112,020198,020199,0202,020201,02020101,02020102,02020103,02020104,02020199,020202,02020201,02020202,02020203,02020204,02020205,02020206,02020207,02020208,02020299,020203,02020301,02020302,02020303,02020399,020204,02020401,02020402,02020403,02020499,020205,02020501,02020502,02020503,02020504,02020505,02020506,02020599,020206,02020601,02020602,02020603,02020699,020207,020208,020209,020210,020211,020212,020213,020214,020215,020216,020217,020299,0203,020301,020302,02030201,02030202,02030203,02030204,02030205,02030299,020303,020304,020305,020306,020307,02030701,02030799,020308,020309,020310,020311,020312,020313,02031301,02031302,02031303,020314,02031401,02031402,02031403,02031404,02031499,020315,020316,020317,020318,020319,02031901,02031902,02031903,02031999,020320,020321,020399,0204,020401,020402,02040201,02040202,02040299,020403,02040301,02040302,02040303,02040399,020404,020405,02040501,02040502,02040503,02040504,02040505,02040506,02040507,02040508,02040509,02040510,02040511,02040512,02040513,02040514,02040515,02040516,02040517,02040599,020406,02040601,02040602,02040603,02040604,02040605,02040606,02040607,02040608,02040609,02040610,02040611,02040612,02040613,02040614,02040615,02040616,02040617,02040618,02040698,02040699,020407,02040701,02040702,02040703,02040704,02040705,02040706,02040707,02040708,02040709,02040710,02040711,02040793,02040794,02040795,02040796,02040797,02040798,02040799,020499,0205,020501,02050101,02050102,02050103,02050104,02050199,020502,020503,02050301,02050302,02050303,02050399,020504,020505,020506,020507,020508,02050801,02050802,02050803,02050898,02050899,020509,02050901,02050902,02050903,02050904,02050999,020510,020511,02051101,02051102,02051199,020512,02051201,02051202,02051203,02051297,02051298,02051299,020513,02051301,02051302,02051303,02051304,02051305,02051306,02051399,020514,02051401,02051402,02051403,02051499,020515,02051501,02051502,02051599,020516,02051601,02051602,02051699,020517,02051701,02051702,02051799,020518,02051801,02051802,02051803,02051804,02051805,02051806,02051807,02051808,02051809,02051899,020519,020520,02052001,02052002,02052003,02052004,02052099,020521,02052101,02052102,02052103,02052104,02052105,02052106,02052107,02052108,02052199,020522,02052201,02052202,02052203,02052299,020523,02052301,02052302,02052303,02052304,02052399,020524,02052497,02052498,02052499,020525,020526,020527,020528,02052897,02052898,02052899,020529,020530,020531,020532,020533,02053398,02053399,020534,020535,020536,020537,020538,020539,02053998,02053999,020540,020541,020596,02059601,02059602,02059603,02059604,02059605,02059606,02059607,02059608,02059609,02059610,02059611,02059612,02059613,02059614,02059615,02059616,02059617,02059618,02059699,020597,020598,020599,0299",
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
    "caseMarkNo": "01020201,0102020101,0102020102,0102020103",
    "caseMark": "鏈垚骞翠汉,鏈垚骞翠汉锛堝姞瀹虫柟锛?鏈垚骞翠汉锛堝彈瀹虫柟锛?鏈垚骞翠汉锛堝叾浠栵級",
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
    "pageSize": "99999",
    "pageNum": "1",
    "orderByColumn": "callTime",
    "isAsc": "desc"
}


@dataclass
class Config:
    """閰嶇疆绫?"""
    # 鐧诲綍閰嶇疆
    login_username: str
    login_password: str
    monitor_login_url: str
    monitor_api_url: str

    # Oracle閰嶇疆
    oracle_dsn: str
    oracle_user: str
    oracle_password: str
    oracle_client_lib_dir: Optional[str] = None

    # 鐭俊閰嶇疆
    sms_mobiles: List[str] = field(default_factory=list)
    dedup_hours: int = 12
    sms_userid: str = ""
    sms_password: str = ""
    sms_userport: str = ""
    kg_target_xqdm: str = "445300"

    # 浜哄ぇ閲戜粨閰嶇疆
    kingbase_host: Optional[str] = None
    kingbase_port: Optional[int] = None
    kingbase_dbname: Optional[str] = None
    kingbase_user: Optional[str] = None
    kingbase_password: Optional[str] = None

    def has_kingbase_config(self) -> bool:
        """妫€鏌ヤ汉澶ч噾浠撻厤缃槸鍚﹀畬鏁村彲鐢?"""
        return all([
            self.kingbase_host,
            self.kingbase_port is not None,
            self.kingbase_dbname,
            self.kingbase_user,
            self.kingbase_password
        ])


def _split_mobile_candidates(raw: Any) -> List[str]:
    """鎸夊父瑙佸垎闅旂鎷嗗垎鎵嬫満鍙峰€欓€?"""
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    return [x.strip() for x in re.split(r"[,\s锛岋紱;]+", text) if x.strip()]


def normalize_mobile_list(raw_values: List[Any]) -> List[str]:
    """娓呮礂骞跺幓閲嶆墜鏈哄彿锛屼粎淇濈暀鍚堟硶11浣嶆墜鏈哄彿"""
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
    """閰嶇疆鏃ュ織锛屾寜鏃ユ湡鍒嗗壊"""
    log_dir = "/app/logs"
    os.makedirs(log_dir, exist_ok=True)

    today = datetime.now().strftime("%Y%m%d")
    log_file = os.path.join(log_dir, f"monitor_wcnr_jq_{today}.log")

    logger = logging.getLogger("monitor_wcnr_jq")
    logger.setLevel(logging.INFO)

    # 娓呴櫎宸叉湁澶勭悊鍣?
    logger.handlers.clear()

    # 鏂囦欢澶勭悊鍣?
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)

    # 鎺у埗鍙板鐞嗗櫒
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    # 鏍煎紡鍖?
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def load_config_from_env() -> Config:
    """浠庣幆澧冨彉閲忓姞杞介厤缃?"""
    mobiles_str = os.environ.get("SMS_MOBILES", "")
    mobiles = normalize_mobile_list([mobiles_str])

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

    return Config(
        login_username=os.environ.get("LOGIN_USERNAME", ""),
        login_password=os.environ.get("LOGIN_PASSWORD", ""),
        monitor_login_url=(os.environ.get("MONITOR_LOGIN_URL") or DEFAULT_LOGIN_URL).strip(),
        monitor_api_url=(os.environ.get("MONITOR_API_URL") or DEFAULT_API_URL).strip(),
        oracle_dsn=os.environ.get("ORACLE_DSN", ""),
        oracle_user=os.environ.get("ORACLE_USER", ""),
        oracle_password=os.environ.get("ORACLE_PASSWORD", ""),
        oracle_client_lib_dir=os.environ.get("ORACLE_CLIENT_LIB_DIR"),
        sms_mobiles=mobiles,
        dedup_hours=int(os.environ.get("DEDUP_HOURS", "12")),
        sms_userid=(os.environ.get("SMS_USERID") or "").strip(),
        sms_password=(os.environ.get("SMS_PASSWORD") or "").strip(),
        sms_userport=(os.environ.get("SMS_USERPORT") or "").strip(),
        kg_target_xqdm=(os.environ.get("KG_TARGET_XQDM") or "445300").strip() or "445300",
        kingbase_host=kingbase_host,
        kingbase_port=kingbase_port,
        kingbase_dbname=kingbase_dbname,
        kingbase_user=kingbase_user,
        kingbase_password=kingbase_password
    )


def get_dynamic_date_range() -> Tuple[str, str]:
    """
    鑾峰彇鍔ㄦ€佹棩鏈熻寖鍥?
    endDate: 褰撳墠鏃堕棿
    beginDate: 褰撳墠鏃堕棿鍓?澶?
    杩斿洖: (beginDate, endDate) 鏍煎紡: YYYY-MM-DD HH:MM:SS
    """
    now = datetime.now()
    end_date = now.strftime("%Y-%m-%d %H:%M:%S")
    begin_date = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    return begin_date, end_date


class WcnrJqMonitor:
    """鏈垚骞翠汉璀︽儏鐩戞帶绫?"""

    def __init__(self, config: Config, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.session = requests.Session()
        self.use_thick_mode = False  # 鏍囪鏄惁浣跨敤Thick妯″紡

        # 璁剧疆璇锋眰澶?
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "X-Requested-With": "XMLHttpRequest"
        })

        # 鍒濆鍖朞racle瀹㈡埛绔?
        self.use_thick_mode = self._init_oracle_client()

    def _init_oracle_client(self) -> bool:
        """
        鍒濆鍖朞racle瀹㈡埛绔?
        濡傛灉閰嶇疆浜嗗鎴风璺緞涓斿垵濮嬪寲鎴愬姛锛屼娇鐢═hick妯″紡
        鍚﹀垯浣跨敤Thin妯″紡锛堢函Python锛屾棤闇€瀹㈡埛绔級
        杩斿洖: True琛ㄧず浣跨敤Thick妯″紡锛孎alse琛ㄧず浣跨敤Thin妯″紡
        """
        if self.config.oracle_client_lib_dir:
            try:
                import oracledb
                oracledb.init_oracle_client(lib_dir=self.config.oracle_client_lib_dir)
                self.logger.info(f"Oracle Instant Client宸插垵濮嬪寲(Thick妯″紡): {self.config.oracle_client_lib_dir}")
                return True
            except Exception as e:
                self.logger.warning(f"Oracle Instant Client鍒濆鍖栧け璐ワ紝灏嗕娇鐢═hin妯″紡: {e}")
                return False
        else:
            self.logger.info("鏈厤缃甇racle Client璺緞锛屼娇鐢═hin妯″紡(绾疨ython)")
            return False

    def _retry_request(self, method: str, url: str, **kwargs) -> Optional[requests.Response]:
        """甯﹂噸璇曟満鍒剁殑HTTP璇锋眰"""
        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
                return response
            except requests.RequestException as e:
                self.logger.warning(f"璇锋眰澶辫触 (灏濊瘯 {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    self.logger.error(f"璇锋眰鏈€缁堝け璐? {url}")
                    return None
        return None

    def login(self) -> bool:
        """鐧诲綍绯荤粺"""
        login_data = {
            "username": self.config.login_username,
            "password": self.config.login_password,
            "rememberMe": "true"
        }

        login_headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01"
        }

        self.logger.info(f"寮€濮嬬櫥褰? {self.config.monitor_login_url}")

        response = self._retry_request(
            "POST",
            self.config.monitor_login_url,
            data=login_data,
            headers=login_headers
        )

        if response is None:
            return False

        try:
            result = response.json()
            self.logger.info(f"鐧诲綍鍝嶅簲: {result}")

            # 妫€鏌ョ櫥褰曟垚鍔?
            if (result.get("code") == 0 or
                result.get("code") == 200 or
                result.get("success") == True or
                result.get("msg") == "鎿嶄綔鎴愬姛"):

                self.logger.info("鐧诲綍鎴愬姛")

                # 淇濆瓨token
                if "token" in result:
                    self.session.headers["Authorization"] = f"Bearer {result['token']}"

                return True
            else:
                self.logger.error(f"鐧诲綍澶辫触: {result.get('msg', '鏈煡閿欒')}")
                return False

        except json.JSONDecodeError:
            if response.status_code == 200 or response.status_code == 302:
                self.logger.info("鐧诲綍鎴愬姛锛堥潪JSON鍝嶅簲锛?")
                return True
            else:
                self.logger.error(f"鐧诲綍澶辫触锛岀姸鎬佺爜: {response.status_code}")
                return False

    def fetch_data(self) -> List[Dict[str, Any]]:
        """
        鏌ヨ璀︽儏鏁版嵁
        杩斿洖: 璀︽儏鍒楄〃
        """
        begin_date, end_date = get_dynamic_date_range()

        params = BASE_PARAMS.copy()
        params["beginDate"] = begin_date
        params["endDate"] = end_date

        self.logger.info(f"寮€濮嬫煡璇㈡暟鎹? beginDate={begin_date}, endDate={end_date}")

        response = self._retry_request("POST", self.config.monitor_api_url, data=params)

        if response is None:
            self.logger.error("鏌ヨ鏁版嵁澶辫触: 璇锋眰鏃犲搷搴?")
            return []

        try:
            data = response.json()

            if data.get("code") == 0:
                rows = data.get("rows", [])
                total = data.get("total", 0)
                self.logger.info(f"鏌ヨ鎴愬姛: 鎬昏{total}鏉★紝褰撳墠鎵规{len(rows)}鏉?")
                return rows
            else:
                self.logger.error(f"鏌ヨ澶辫触: code={data.get('code')}, msg={data.get('msg')}")
                return []

        except json.JSONDecodeError as e:
            self.logger.error(f"瑙ｆ瀽鍝嶅簲澶辫触: {e}")
            return []

    def _fetch_kingbase_mobiles(self) -> Tuple[Optional[List[str]], str]:
        """
        浠庝汉澶ч噾浠撴煡璇㈣仈绯讳汉鎵嬫満鍙?        杩斿洖: (mobiles, reason)
        - mobiles=None 琛ㄧず鏌ヨ澶辫触锛堝彲鍥為€€锛?        - mobiles=[] 涓?reason=kingbase_empty_result 琛ㄧず鏌ヨ鎴愬姛浣嗘棤鏈夋晥鍙风爜锛堜笉鍥為€€锛?        """
        if not self.config.has_kingbase_config():
            return None, "kingbase_config_incomplete"

        try:
            import psycopg2
        except ModuleNotFoundError:
            self.logger.error("Kingbase椹卞姩缂哄け: 璇峰畨瑁?psycopg2-binary")
            return None, "kingbase_driver_missing"

        sql = """
            SELECT lxdh
            FROM ywdata.b_dxpt_mdjfyj
            WHERE xqdm = %s
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
                    password=self.config.kingbase_password
                )
                with conn.cursor() as cur:
                    cur.execute(sql, (self.config.kg_target_xqdm,))
                    rows = cur.fetchall()

                raw_phones = [row[0] for row in rows]
                mobiles = normalize_mobile_list(raw_phones)
                self.logger.info(
                    "鍙风爜鏉ユ簮=kingbase, xqdm=%s, 鏌ヨ琛屾暟=%d, 娓呮礂鍚庡彿鐮佹暟=%d",
                    self.config.kg_target_xqdm,
                    len(rows),
                    len(mobiles)
                )

                if not mobiles:
                    return [], "kingbase_empty_result"
                return mobiles, "kingbase_success"
            except Exception as e:
                self.logger.warning(
                    "Kingbase鏌ヨ澶辫触 (灏濊瘯 %d/%d): %s",
                    attempt + 1,
                    MAX_RETRIES,
                    e
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
            finally:
                if conn:
                    conn.close()

        self.logger.error("Kingbase鏌ヨ鏈€缁堝け璐?")
        return None, "kingbase_query_failed"

    def resolve_target_mobiles(self) -> Tuple[List[str], str, str]:
        """
        鑾峰彇鏈疆鐭俊鎺ユ敹鍙风爜
        杩斿洖: (target_mobiles, source, reason)
        source: kingbase / fallback_sms_mobiles / none
        """
        kingbase_mobiles, reason = self._fetch_kingbase_mobiles()

        # Kingbase鏌ヨ鎴愬姛
        if kingbase_mobiles is not None:
            if kingbase_mobiles:
                return kingbase_mobiles, "kingbase", reason

            # 鏌ヨ鎴愬姛浣嗘棤鏈夋晥鍙风爜锛氫笉鍥為€€
            self.logger.warning(
                "鍙风爜鏉ユ簮=none, reason=%s, 涓嶄娇鐢⊿MS_MOBILES鍥為€€",
                reason
            )
            return [], "none", reason

        # Kingbase涓嶅彲鐢ㄦ椂鎵嶅洖閫€SMS_MOBILES
        if self.config.sms_mobiles:
            self.logger.warning(
                "鍙风爜鏉ユ簮=fallback_sms_mobiles, reason=%s, 娓呮礂鍚庡彿鐮佹暟=%d",
                reason,
                len(self.config.sms_mobiles)
            )
            return self.config.sms_mobiles, "fallback_sms_mobiles", reason

        self.logger.warning("number source=none, reason=%s, no fallback mobiles", reason)
        return [], "none", reason

    def build_sms_content(self, record: Dict[str, Any]) -> str:
        """
        缁勮鐭俊鍐呭
        鏍煎紡: callTime,dutyDeptName鎺ユ姤:caseContents鍦板潃:occurAddress銆愬熀纭€绠℃帶涓績銆?        """
        call_time = record.get("callTime", "")
        duty_dept = record.get("dutyDeptName", "")
        case_contents = record.get("caseContents", "")
        occur_address = record.get("occurAddress", "")

        content = f"{call_time},{duty_dept}接报:{case_contents}地址:{occur_address}【基础管控中心】"
        return content

    def check_duplicate(self, conn, case_no: str, mobile: str) -> bool:
        """
        妫€鏌ユ槸鍚﹀凡鍙戦€佽繃锛堝幓閲嶏級
        鏌ヨyfgadb.dfsdl琛ㄤ腑鏄惁瀛樺湪鐩稿悓eid(caseNo)鍜宮obile鐨勮褰?
        杩斿洖: True琛ㄧず宸插瓨鍦紙涓嶅彂閫侊級锛孎alse琛ㄧず涓嶅瓨鍦紙鍙彂閫侊級
        """
        dedup_delta = timedelta(hours=self.config.dedup_hours)
        cutoff_time = datetime.now() - dedup_delta

        try:
            with conn.cursor() as cur:
                sql = """
                    SELECT COUNT(*)
                    FROM yfgadb.dfsdl
                    WHERE eid = :eid
                    AND mobile = :mobile
                    AND deadtime >= :cutoff_time
                """
                cur.execute(sql, {
                    "eid": case_no,
                    "mobile": mobile,
                    "cutoff_time": cutoff_time
                })
                count = cur.fetchone()[0]
                return count > 0
        except Exception as e:
            self.logger.error(f"鍘婚噸妫€鏌ュけ璐? {e}")
            return False  # 妫€鏌ュけ璐ユ椂鍏佽鍙戦€?

    def send_sms(self, conn, mobile: str, content: str, case_no: str) -> bool:
        """
        鍙戦€佺煭淇★紙鎻掑叆Oracle琛級
        """
        try:
            with conn.cursor() as cur:
                sql = """
                    INSERT INTO yfgadb.dfsdl(
                        id, mobile, content, deadtime, status, eid,
                        userid, password, userport
                    ) VALUES (
                        yfgadb.seq_sendsms.nextval,
                        :mobile, :content, SYSDATE, '0', :eid,
                        :sms_userid, :sms_password, :sms_userport
                    )
                """
                cur.execute(sql, {
                    "mobile": mobile,
                    "content": content,
                    "eid": case_no,
                    "sms_userid": self.config.sms_userid,
                    "sms_password": self.config.sms_password,
                    "sms_userport": self.config.sms_userport
                })
                return True
        except Exception as e:
            self.logger.error(f"鐭俊鍙戦€佸け璐? {e}")
            return False

    def process_records(self, records: List[Dict[str, Any]], target_mobiles: List[str]) -> Dict[str, int]:
        """
        澶勭悊璁板綍骞跺彂閫佺煭淇?        杩斿洖: 缁熻淇℃伅
        """
        stats = {
            "total": len(records),
            "sent": 0,
            "skipped": 0,
            "failed": 0
        }

        if not records:
            return stats

        if not target_mobiles:
            self.logger.warning("鏈疆鏃犲彲鐢ㄦ帴鏀跺彿鐮侊紝璺宠繃鐭俊鍙戦€?")
            return stats

        # 杩炴帴Oracle锛堝甫閲嶈瘯锛?
        conn = None
        for attempt in range(MAX_RETRIES):
            try:
                import oracledb

                # 鏋勫缓杩炴帴鍙傛暟
                connect_params = {
                    "user": self.config.oracle_user,
                    "password": self.config.oracle_password,
                    "dsn": self.config.oracle_dsn
                }

                # 濡傛灉浣跨敤Thin妯″紡锛岀鐢ㄥ悇绉嶄笉鍙敤鐨勫姛鑳?
                if not self.use_thick_mode:
                    # Thin妯″紡涓嶉渶瑕侀澶栧弬鏁帮紝绾疨ython瀹炵幇
                    self.logger.debug("浣跨敤Oracle Thin妯″紡杩炴帴")

                conn = oracledb.connect(**connect_params)
                mode_str = "Thick" if self.use_thick_mode else "Thin"
                self.logger.info(f"Oracle杩炴帴鎴愬姛 ({mode_str}妯″紡)")
                break
            except Exception as e:
                self.logger.warning(f"Oracle杩炴帴澶辫触 (灏濊瘯 {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    self.logger.error("Oracle杩炴帴鏈€缁堝け璐?")
                    return stats

        try:
            for record in records:
                case_no = record.get("caseNo", "")
                if not case_no:
                    self.logger.warning("璁板綍缂哄皯caseNo锛岃烦杩?")
                    stats["skipped"] += 1
                    continue

                content = self.build_sms_content(record)

                for mobile in target_mobiles:
                    # 鍘婚噸妫€鏌?
                    if self.check_duplicate(conn, case_no, mobile):
                        self.logger.info(f"璺宠繃(宸插彂閫?: caseNo={case_no}, mobile={mobile}")
                        stats["skipped"] += 1
                        continue

                    # 鍙戦€佺煭淇?
                    if self.send_sms(conn, mobile, content, case_no):
                        self.logger.info(f"鐭俊宸插彂閫? caseNo={case_no}, mobile={mobile}")
                        stats["sent"] += 1
                    else:
                        stats["failed"] += 1

            conn.commit()

        except Exception as e:
            self.logger.error(f"澶勭悊璁板綍寮傚父: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

        return stats

    def run(self) -> int:
        """
        鎵ц瀹屾暣娴佺▼
        杩斿洖: 0琛ㄧず鎴愬姛锛?琛ㄧず澶辫触
        """
        self.logger.info("=" * 60)
        self.logger.info("寮€濮嬫墽琛屾湭鎴愬勾浜鸿鎯呯洃鎺т换鍔?")

        # 1. 鐧诲綍
        if not self.login():
            self.logger.error("鐧诲綍澶辫触锛屼换鍔＄粓姝?")
            return 1

        # 2. 鏌ヨ鏁版嵁
        records = self.fetch_data()

        # 3. Resolve recipient mobiles for this run
        target_mobiles, mobile_source, mobile_reason = self.resolve_target_mobiles()
        self.logger.info(
            "鍙风爜鏉ユ簮=%s, reason=%s, 鍙敤鍙风爜鏁?%d",
            mobile_source,
            mobile_reason,
            len(target_mobiles)
        )

        if not records:
            self.logger.info("鏈煡璇㈠埌鏁版嵁")
            return 0

        if not target_mobiles:
            self.logger.warning("鏃犲彲鐢ㄥ彿鐮侊紝鏈疆涓嶅彂閫佺煭淇?")
            return 0

        # 4. Send notifications
        stats = self.process_records(records, target_mobiles)

        # 5. 杈撳嚭缁熻
        self.logger.info("=" * 60)
        self.logger.info(
            "浠诲姟瀹屾垚: 鏌ヨ%d鏉? 鍙戦€?d鏉? 璺宠繃%d鏉? 澶辫触%d鏉? 鍙风爜鏉ユ簮=%s",
            stats["total"],
            stats["sent"],
            stats["skipped"],
            stats["failed"],
            mobile_source
        )
        self.logger.info("=" * 60)

        return 0


def main():
    """涓诲嚱鏁?"""
    # 璁剧疆鏃ュ織
    logger = setup_logging()

    try:
        # 鍔犺浇閰嶇疆
        config = load_config_from_env()

        # 楠岃瘉閰嶇疆
        if not config.login_username or not config.login_password:
            logger.error("缂哄皯鐧诲綍鍑瘉锛岃璁剧疆鐜鍙橀噺 LOGIN_USERNAME 鍜?LOGIN_PASSWORD")
            return 1

        if not config.oracle_dsn or not config.oracle_user or not config.oracle_password:
            logger.error("缂哄皯Oracle閰嶇疆锛岃璁剧疆鐜鍙橀噺 ORACLE_DSN, ORACLE_USER, ORACLE_PASSWORD")
            return 1

        if not config.sms_userid or not config.sms_password or not config.sms_userport:
            logger.error("缂哄皯鐭俊缃戝叧閰嶇疆锛岃璁剧疆鐜鍙橀噺 SMS_USERID, SMS_PASSWORD, SMS_USERPORT")
            return 1

        if not config.has_kingbase_config() and not config.sms_mobiles:
            logger.error(
                "缂哄皯鍙敤鍙风爜鏉ユ簮锛氳閰嶇疆瀹屾暣Kingbase鐜鍙橀噺"
                "(KINGBASE_HOST/KINGBASE_PORT/KINGBASE_DBNAME/KINGBASE_USER/KINGBASE_PASSWORD)"
                " 鎴栨彁渚?SMS_MOBILES 浣滀负鍏滃簳"
            )
            return 1

        if not config.has_kingbase_config():
            logger.warning(
                "Kingbase閰嶇疆涓嶅畬鏁达紝灏嗕粎鍦↘ingbase涓嶅彲鐢ㄥ満鏅娇鐢?SMS_MOBILES 鍏滃簳"
            )

        # 鎵ц鐩戞帶
        monitor = WcnrJqMonitor(config, logger)
        return monitor.run()

    except Exception as e:
        logger.exception(f"绋嬪簭寮傚父: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

