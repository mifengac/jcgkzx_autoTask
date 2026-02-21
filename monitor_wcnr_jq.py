#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monitor script for juvenile case notifications.

Behavior:
1. Login and query case records from monitor API.
2. Resolve recipient mobiles (Kingbase first, optional SMS_MOBILES fallback).
3. Deduplicate by caseNo + mobile and send SMS through Oracle.

Key environment variables:
- LOGIN_USERNAME / LOGIN_PASSWORD
- MONITOR_LOGIN_URL / MONITOR_API_URL
- ORACLE_DSN / ORACLE_USER / ORACLE_PASSWORD / ORACLE_CLIENT_LIB_DIR
- SMS_USERID / SMS_PASSWORD / SMS_USERPORT
- KINGBASE_HOST / KINGBASE_PORT / KINGBASE_DBNAME / KINGBASE_USER / KINGBASE_PASSWORD
- KG_TARGET_XQDM (default: 445300)
- SMS_MOBILES (fallback only when Kingbase is unavailable)
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

# 常量定义
DEFAULT_LOGIN_URL = "http://68.253.2.111/dsjfx/login"
DEFAULT_API_URL = "http://68.253.2.111/dsjfx/case/list"
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds
MOBILE_PATTERN = re.compile(r"^1[3-9]\d{9}$")

# 固定请求参数
BASE_PARAMS = {
    "params[colArray]": "selectItem,callTime,newRecvTypeName,newCaseSourceName,newComeTelephoneName,newOriCharaSubclassName,newCharaSubclassName,newCaseHandleStatusName,caseResultStateName,dutyDeptName,77,",
    "newCaseSourceNo": "",
    "newCaseSource": "全部",
    "dutyDeptNo": "",
    "dutyDeptName": "全部",
    "newCharaSubclassNo": "",
    "newCharaSubclass": "全部",
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
    "caseMark": "未成年人,未成年人（加害方）,未成年人（受害方）,未成年人（其他）",
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


# 第二次查询（可通过环境变量覆盖）
# 说明：该列表来自 0215.md 的需求参数，默认启用第二次查询。
DEFAULT_SECOND_QUERY_ORI_SUBCLASS_NO = (
    "09020100,09020000,02051899,02051809,02051808,02051807,02051806,02051805,02051804,02051803,02051802,02051801,02051800,"
    "01051200,01051199,01051104,01051103,01051102,01051101,01051100,"
    "09029900,09020500,09020400,09020300,09020200,"
    "02010899,02010803,02010802,02010801,01050102,02010800,01030300,02031000,02030100,"
    "09019900,09010600,09010500,09010400,09010300,09010200,09010100,09010000,"
    "02052099,02052004,02052003,02052002,02052001,02052000,"
    "01050499,01050405,01050404,01050403,01050402,01050401,01050400,"
    "02031499,02031404,02031403,02031402,02031401,02031400,"
    "01030699,01030602,01030601,01030600,"
    "01030504,01030503,01030502,01030501,01030500"
)


@dataclass
class Config:
    """配置类"""
    # 登录配置
    login_username: str
    login_password: str
    monitor_login_url: str
    monitor_api_url: str

    # Oracle配置
    oracle_dsn: str
    oracle_user: str
    oracle_password: str
    oracle_client_lib_dir: Optional[str] = None

    # 短信配置
    sms_mobiles: List[str] = field(default_factory=list)
    sms_userid: str = ""
    sms_password: str = ""
    sms_userport: str = ""
    kg_target_xqdm: str = "445300"

    # 人大金仓配置
    kingbase_host: Optional[str] = None
    kingbase_port: Optional[int] = None
    kingbase_dbname: Optional[str] = None
    kingbase_user: Optional[str] = None
    kingbase_password: Optional[str] = None

    # monitor 第二次查询配置
    monitor_second_query_enabled: bool = True
    monitor_second_query_new_ori_chara_subclass_no: str = DEFAULT_SECOND_QUERY_ORI_SUBCLASS_NO
    monitor_second_query_case_mark_no: str = ""

    def has_kingbase_config(self) -> bool:
        """检查人大金仓配置是否完整可用"""
        return all([
            self.kingbase_host,
            self.kingbase_port is not None,
            self.kingbase_dbname,
            self.kingbase_user,
            self.kingbase_password
        ])


def _split_mobile_candidates(raw: Any) -> List[str]:
    """按常见分隔符拆分手机号候选"""
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    return [x.strip() for x in re.split(r"[,\s，；;]+", text) if x.strip()]


def normalize_mobile_list(raw_values: List[Any]) -> List[str]:
    """清洗并去重手机号，仅保留合法11位手机号"""
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
    """配置日志，按日期分割"""
    log_dir = "/app/logs"
    os.makedirs(log_dir, exist_ok=True)

    today = datetime.now().strftime("%Y%m%d")
    log_file = os.path.join(log_dir, f"monitor_wcnr_jq_{today}.log")

    logger = logging.getLogger("monitor_wcnr_jq")
    logger.setLevel(logging.INFO)

    # 清除已有处理器
    logger.handlers.clear()

    # 文件处理器
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    # 格式化
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
    """从环境变量加载配置"""
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

    def _env_bool(name: str, default: bool) -> bool:
        raw = (os.environ.get(name) or "").strip().lower()
        if not raw:
            return default
        return raw in {"1", "true", "yes", "y", "on"}

    monitor_second_query_enabled = _env_bool("MONITOR_SECOND_QUERY_ENABLED", True)
    monitor_second_query_new_ori = (
        os.environ.get("MONITOR_SECOND_QUERY_NEWORI_SUBCLASS_NO")
        or DEFAULT_SECOND_QUERY_ORI_SUBCLASS_NO
    ).strip()
    monitor_second_query_case_mark_no = (
        os.environ.get("MONITOR_SECOND_QUERY_CASE_MARK_NO") or ""
    ).strip()

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
        sms_userid=(os.environ.get("SMS_USERID") or "").strip(),
        sms_password=(os.environ.get("SMS_PASSWORD") or "").strip(),
        sms_userport=(os.environ.get("SMS_USERPORT") or "").strip(),
        kg_target_xqdm=(os.environ.get("KG_TARGET_XQDM") or "445300").strip() or "445300",
        kingbase_host=kingbase_host,
        kingbase_port=kingbase_port,
        kingbase_dbname=kingbase_dbname,
        kingbase_user=kingbase_user,
        kingbase_password=kingbase_password,
        monitor_second_query_enabled=monitor_second_query_enabled,
        monitor_second_query_new_ori_chara_subclass_no=monitor_second_query_new_ori,
        monitor_second_query_case_mark_no=monitor_second_query_case_mark_no,
    )


def get_dynamic_date_range() -> Tuple[str, str]:
    """
    获取动态日期范围
    endDate: 当前时间
    beginDate: 当前时间前1天
    返回: (beginDate, endDate) 格式: YYYY-MM-DD HH:MM:SS
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
        初始化Oracle客户端
        如果配置了客户端路径且初始化成功，使用Thick模式
        否则使用Thin模式（纯Python，无需客户端）
        返回: True表示使用Thick模式，False表示使用Thin模式
        """
        if self.config.oracle_client_lib_dir:
            try:
                import oracledb
                oracledb.init_oracle_client(lib_dir=self.config.oracle_client_lib_dir)
                self.logger.info(f"Oracle Instant Client已初始化(Thick模式): {self.config.oracle_client_lib_dir}")
                return True
            except Exception as e:
                self.logger.warning(f"Oracle Instant Client初始化失败，将使用Thin模式: {e}")
                return False
        else:
            self.logger.info("未配置Oracle Client路径，使用Thin模式(纯Python)")
            return False

    def _retry_request(self, method: str, url: str, **kwargs) -> Optional[requests.Response]:
        """带重试机制的HTTP请求"""
        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
                return response
            except requests.RequestException as e:
                self.logger.warning(f"请求失败 (尝试 {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    self.logger.error(f"请求最终失败: {url}")
                    return None
        return None

    def login(self) -> bool:
        """登录系统"""
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

        self.logger.info(f"开始登录: {self.config.monitor_login_url}")

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
            self.logger.info(f"登录响应: {result}")

            # 检查登录成功
            if (result.get("code") == 0 or
                result.get("code") == 200 or
                result.get("success") == True or
                result.get("msg") == "操作成功"):

                self.logger.info("登录成功")

                # 保存token
                if "token" in result:
                    self.session.headers["Authorization"] = f"Bearer {result['token']}"

                return True
            else:
                self.logger.error(f"登录失败: {result.get('msg', '未知错误')}")
                return False

        except json.JSONDecodeError:
            if response.status_code == 200 or response.status_code == 302:
                self.logger.info("登录成功（非JSON响应）")
                return True
            else:
                self.logger.error(f"登录失败，状态码: {response.status_code}")
                return False

    def fetch_data(self) -> List[Dict[str, Any]]:
        """
        查询警情数据
        返回: 警情列表
        """
        begin_date, end_date = get_dynamic_date_range()

        query1_params = BASE_PARAMS.copy()
        query1_params["beginDate"] = begin_date
        query1_params["endDate"] = end_date

        self.logger.info(
            "开始查询数据(第1次): beginDate=%s, endDate=%s",
            begin_date,
            end_date
        )
        rows1 = self._fetch_rows(query1_params, query_name="query1")

        rows2: List[Dict[str, Any]] = []
        if self.config.monitor_second_query_enabled:
            query2_params = BASE_PARAMS.copy()
            query2_params["beginDate"] = begin_date
            query2_params["endDate"] = end_date
            query2_params["newOriCharaSubclassNo"] = self.config.monitor_second_query_new_ori_chara_subclass_no

            # 第二次查询默认不限定“未成年人”标记，可用环境变量覆盖
            query2_params["caseMarkNo"] = self.config.monitor_second_query_case_mark_no
            query2_params["caseMark"] = "全部"

            self.logger.info(
                "开始查询数据(第2次): beginDate=%s, endDate=%s, newOriCharaSubclassNo.len=%d, caseMarkNo=%s",
                begin_date,
                end_date,
                len(self.config.monitor_second_query_new_ori_chara_subclass_no or ""),
                query2_params.get("caseMarkNo", "")
            )
            rows2 = self._fetch_rows(query2_params, query_name="query2")

        merged = self._merge_case_rows(rows1, rows2)
        self.logger.info(
            "两次查询合并完成: query1=%d, query2=%d, merged=%d",
            len(rows1),
            len(rows2),
            len(merged)
        )
        return merged

    def _fetch_rows(self, params: Dict[str, Any], query_name: str) -> List[Dict[str, Any]]:
        """单次查询封装：失败返回空列表，不抛出异常"""
        response = self._retry_request("POST", self.config.monitor_api_url, data=params)
        if response is None:
            self.logger.error("查询数据失败(%s): 请求无响应", query_name)
            return []

        try:
            data = response.json()
        except json.JSONDecodeError as e:
            self.logger.error("解析响应失败(%s): %s", query_name, e)
            return []

        if data.get("code") == 0:
            rows = data.get("rows", [])
            total = data.get("total", 0)
            self.logger.info(
                "查询成功(%s): total=%s, rows=%d",
                query_name,
                total,
                len(rows)
            )
            if isinstance(rows, list):
                return rows
            return []

        self.logger.error(
            "查询失败(%s): code=%s, msg=%s",
            query_name,
            data.get("code"),
            data.get("msg")
        )
        return []

    @staticmethod
    def _parse_call_time(value: Any) -> datetime:
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

    @classmethod
    def _merge_case_rows(
        cls,
        rows1: List[Dict[str, Any]],
        rows2: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """按 caseNo 合并两次查询结果，优先保留非空字段，并对重复 caseNo 去重。"""
        merged_by_case: Dict[str, Dict[str, Any]] = {}
        no_case_records: List[Dict[str, Any]] = []

        def _pick_better_str(old: Any, new: Any) -> Any:
            old_s = ("" if old is None else str(old)).strip()
            new_s = ("" if new is None else str(new)).strip()
            if not old_s and new_s:
                return new
            if old_s and new_s and len(new_s) > len(old_s):
                return new
            return old

        def _merge_into(target: Dict[str, Any], incoming: Dict[str, Any]) -> None:
            for k, v in incoming.items():
                if k not in target or target.get(k) in (None, ""):
                    if v not in (None, ""):
                        target[k] = v
                    continue

                # 关键文本字段：优先保留更长/更完整的内容
                if k in {"caseContents", "occurAddress"}:
                    target[k] = _pick_better_str(target.get(k), v)

        for record in (rows1 or []):
            case_no = (record.get("caseNo") or "").strip()
            if not case_no:
                no_case_records.append(record)
                continue
            merged_by_case[case_no] = dict(record)

        for record in (rows2 or []):
            case_no = (record.get("caseNo") or "").strip()
            if not case_no:
                no_case_records.append(record)
                continue
            if case_no not in merged_by_case:
                merged_by_case[case_no] = dict(record)
                continue
            _merge_into(merged_by_case[case_no], record)

        merged_list = list(merged_by_case.values()) + no_case_records
        merged_list.sort(key=lambda r: cls._parse_call_time(r.get("callTime")), reverse=True)
        return merged_list

    def _fetch_kingbase_mobiles(self) -> Tuple[Optional[List[str]], str]:
        """
        从人大金仓查询联系人手机号
        返回: (mobiles, reason)
        - mobiles=None 表示查询失败（可回退）
        - mobiles=[] 且 reason=kingbase_empty_result 表示查询成功但无有效号码（不回退）
        """
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
                    "号码来源=kingbase, xqdm=%s, 查询行数=%d, 清洗后号码数=%d",
                    self.config.kg_target_xqdm,
                    len(rows),
                    len(mobiles)
                )

                if not mobiles:
                    return [], "kingbase_empty_result"
                return mobiles, "kingbase_success"
            except Exception as e:
                self.logger.warning(
                    "Kingbase查询失败 (尝试 %d/%d): %s",
                    attempt + 1,
                    MAX_RETRIES,
                    e
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
            finally:
                if conn:
                    conn.close()

        self.logger.error("Kingbase查询最终失败")
        return None, "kingbase_query_failed"

    def resolve_target_mobiles(self) -> Tuple[List[str], str, str]:
        """
        获取本轮短信接收号码
        返回: (target_mobiles, source, reason)
        source: kingbase / fallback_sms_mobiles / none
        """
        kingbase_mobiles, reason = self._fetch_kingbase_mobiles()

        # Kingbase查询成功
        if kingbase_mobiles is not None:
            if kingbase_mobiles:
                return kingbase_mobiles, "kingbase", reason

            # 查询成功但无有效号码：不回退
            self.logger.warning(
                "号码来源=none, reason=%s, 不使用SMS_MOBILES回退",
                reason
            )
            return [], "none", reason

        # Kingbase不可用时才回退SMS_MOBILES
        if self.config.sms_mobiles:
            self.logger.warning(
                "号码来源=fallback_sms_mobiles, reason=%s, 清洗后号码数=%d",
                reason,
                len(self.config.sms_mobiles)
            )
            return self.config.sms_mobiles, "fallback_sms_mobiles", reason

        self.logger.warning("number source=none, reason=%s, no fallback mobiles", reason)
        return [], "none", reason

    def build_sms_content(self, record: Dict[str, Any]) -> str:
        """
        组装短信内容
        格式: callTime,dutyDeptName接报:caseContents地址:occurAddress【基础管控中心】
        """
        call_time = record.get("callTime", "")
        duty_dept = record.get("dutyDeptName", "")
        case_contents = record.get("caseContents", "")
        occur_address = record.get("occurAddress", "")

        content = f"{call_time},{duty_dept}接报:{case_contents}地址:{occur_address}【基础管控中心】"
        return content

    def check_duplicate(self, conn, case_no: str, mobile: str) -> bool:
        """
        检查是否已发送过（去重）
        查询yfgadb.dfsdl表中是否存在相同eid(caseNo)和mobile的记录
        返回: True表示已存在（不发送），False表示不存在（可发送）
        """
        try:
            with conn.cursor() as cur:
                sql = """
                    SELECT COUNT(*)
                    FROM yfgadb.dfsdl
                    WHERE eid = :eid
                    AND mobile = :mobile
                """
                cur.execute(sql, {
                    "eid": case_no,
                    "mobile": mobile
                })
                count = cur.fetchone()[0]
                return count > 0
        except Exception as e:
            self.logger.error(f"去重检查失败: {e}")
            return False  # 检查失败时允许发送

    def send_sms(self, conn, mobile: str, content: str, case_no: str) -> bool:
        """
        发送短信（插入Oracle表）
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
            self.logger.error(f"短信发送失败: {e}")
            return False

    def process_records(self, records: List[Dict[str, Any]], target_mobiles: List[str]) -> Dict[str, int]:
        """
        处理记录并发送短信
        返回: 统计信息
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
            self.logger.warning("本轮无可用接收号码，跳过短信发送")
            return stats

        # 连接Oracle（带重试）
        conn = None
        for attempt in range(MAX_RETRIES):
            try:
                import oracledb

                # 构建连接参数
                connect_params = {
                    "user": self.config.oracle_user,
                    "password": self.config.oracle_password,
                    "dsn": self.config.oracle_dsn
                }

                # 如果使用Thin模式，禁用各种不可用的功能
                if not self.use_thick_mode:
                    # Thin模式不需要额外参数，纯Python实现
                    self.logger.debug("使用Oracle Thin模式连接")

                conn = oracledb.connect(**connect_params)
                mode_str = "Thick" if self.use_thick_mode else "Thin"
                self.logger.info(f"Oracle连接成功 ({mode_str}模式)")
                break
            except Exception as e:
                self.logger.warning(f"Oracle连接失败 (尝试 {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    self.logger.error("Oracle连接最终失败")
                    return stats

        try:
            for record in records:
                case_no = record.get("caseNo", "")
                if not case_no:
                    self.logger.warning("记录缺少caseNo，跳过")
                    stats["skipped"] += 1
                    continue

                content = self.build_sms_content(record)

                for mobile in target_mobiles:
                    # 去重检查
                    if self.check_duplicate(conn, case_no, mobile):
                        self.logger.info(f"跳过(已发送): caseNo={case_no}, mobile={mobile}")
                        stats["skipped"] += 1
                        continue

                    # 发送短信
                    if self.send_sms(conn, mobile, content, case_no):
                        self.logger.info(f"短信已发送: caseNo={case_no}, mobile={mobile}")
                        stats["sent"] += 1
                    else:
                        stats["failed"] += 1

            conn.commit()

        except Exception as e:
            self.logger.error(f"处理记录异常: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

        return stats

    def run(self) -> int:
        """
        执行完整流程
        返回: 0表示成功，1表示失败
        """
        self.logger.info("=" * 60)
        self.logger.info("开始执行未成年人警情监控任务")

        # 1. 登录
        if not self.login():
            self.logger.error("登录失败，任务终止")
            return 1

        # 2. 查询数据
        records = self.fetch_data()

        # 3. Resolve recipient mobiles for this run
        target_mobiles, mobile_source, mobile_reason = self.resolve_target_mobiles()
        self.logger.info(
            "号码来源=%s, reason=%s, 可用号码数=%d",
            mobile_source,
            mobile_reason,
            len(target_mobiles)
        )

        if not records:
            self.logger.info("未查询到数据")
            return 0

        if not target_mobiles:
            self.logger.warning("无可用号码，本轮不发送短信")
            return 0

        # 4. Send notifications
        stats = self.process_records(records, target_mobiles)

        # 5. 输出统计
        self.logger.info("=" * 60)
        self.logger.info(
            "任务完成: 查询%d条, 发送%d条, 跳过%d条, 失败%d条, 号码来源=%s",
            stats["total"],
            stats["sent"],
            stats["skipped"],
            stats["failed"],
            mobile_source
        )
        self.logger.info("=" * 60)

        return 0


def main():
    """主函数"""
    # 设置日志
    logger = setup_logging()

    try:
        # 加载配置
        config = load_config_from_env()

        # 验证配置
        if not config.login_username or not config.login_password:
            logger.error("缺少登录凭证，请设置环境变量 LOGIN_USERNAME 和 LOGIN_PASSWORD")
            return 1

        if not config.oracle_dsn or not config.oracle_user or not config.oracle_password:
            logger.error("缺少Oracle配置，请设置环境变量 ORACLE_DSN, ORACLE_USER, ORACLE_PASSWORD")
            return 1

        if not config.sms_userid or not config.sms_password or not config.sms_userport:
            logger.error("缺少短信网关配置，请设置环境变量 SMS_USERID, SMS_PASSWORD, SMS_USERPORT")
            return 1

        if not config.has_kingbase_config() and not config.sms_mobiles:
            logger.error(
                "缺少可用号码来源：请配置完整Kingbase环境变量"
                "(KINGBASE_HOST/KINGBASE_PORT/KINGBASE_DBNAME/KINGBASE_USER/KINGBASE_PASSWORD)"
                " 或提供 SMS_MOBILES 作为兜底"
            )
            return 1

        if not config.has_kingbase_config():
            logger.warning(
                "Kingbase配置不完整，将仅在Kingbase不可用场景使用 SMS_MOBILES 兜底"
            )

        # 执行监控
        monitor = WcnrJqMonitor(config, logger)
        return monitor.run()

    except Exception as e:
        logger.exception(f"程序异常: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

