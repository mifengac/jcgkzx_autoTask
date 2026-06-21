#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
舆情数据抓取脚本
功能：
1. 登录指定网站进行数据抓取
2. 通过caseNo进行唯一性校验
3. 将数据保存到PostgreSQL数据库
"""

import requests
import psycopg2
from psycopg2.extras import execute_values
import json
import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

try:
    from autotask_api.services.time_utils import now_shanghai
except ModuleNotFoundError:
    SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

    def now_shanghai() -> datetime:
        return datetime.now(SHANGHAI_TZ)
# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('jingqing_zhuaqu.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

MAX_RETRIES = 5
RETRY_BASE_DELAY = 3
DB_BATCH_SIZE = 500


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
def get_end_of_day() -> str:
    """
    获取当日的结束时间，格式为 'YYYY-MM-DD 23:59:59'
    """
    return now_shanghai().strftime("%Y-%m-%d 23:59:59")

def get_begin_of_day(days_ago: int = 0) -> str:
    """
    获取指定天数前的开始时间，格式为 'YYYY-MM-DD 00:00:00'
    """
    date = now_shanghai() - timedelta(days=days_ago)
    return date.strftime("%Y-%m-%d 00:00:00")


def _to_text(value: Any) -> Optional[str]:
    """将任意值转为 TEXT 字符串，兼容 dict/list/bool/None"""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class JingqingZhuaqu:
    """舆情数据抓取类"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化抓取器
        
        Args:
            config: 配置参数字典
        """
        self.config = config
        self.session = requests.Session()
        self.db_conn = None
        
        # 设置请求头
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'X-Requested-With': 'XMLHttpRequest'
        })
    
    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """带重试的 HTTP 请求，网络抖动不丢数据"""
        last_exc = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return self.session.request(method, url, **kwargs)
            except requests.RequestException as exc:
                last_exc = exc
                wait = RETRY_BASE_DELAY * attempt
                logger.warning(f"请求失败 ({attempt}/{MAX_RETRIES}): {exc}, {wait}秒后重试")
                time.sleep(wait)
        raise RuntimeError(f"请求失败，已重试 {MAX_RETRIES} 次: {last_exc}")
    
    def connect_database(self) -> bool:
        """
        连接PostgreSQL数据库
        
        Returns:
            bool: 连接是否成功
        """
        try:
            db_config = self.config['database']
            self.db_conn = psycopg2.connect(
                host=db_config['host'],
                port=db_config['port'],
                database=db_config['database'],
                user=db_config['user'],
                password=db_config['password'],
                options=f"-c search_path={db_config.get('schema', 'public')}"
            )
            self.db_conn.autocommit = True
            logger.info(f"数据库连接成功，使用schema: {db_config.get('schema', 'public')}")
            return True
        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            return False
    
    def create_table_if_not_exists(self, sample_data: Dict[str, Any] = None):
        """
        根据样本数据动态创建数据表（如果不存在）
        
        Args:
            sample_data: 样本数据，用于分析字段结构
        """
        try:
            cursor = self.db_conn.cursor()
            
            if sample_data:
                # 根据样本数据动态构建表结构
                logger.info(f"根据样本数据动态创建表结构: {list(sample_data.keys())}")
                
                # 确保caseNo字段存在且为主键
                if 'caseNo' not in sample_data and 'caseno' not in [k.lower() for k in sample_data.keys()]:
                    logger.warning("样本数据中未找到caseNo字段，添加默认caseNo字段")
                    sample_data['caseNo'] = ''
                
                # 构建动态字段（统一转换为小写）
                fields = []
                fields.append("id SERIAL PRIMARY KEY")
                
                for field_name in sample_data.keys():
                    # 将字段名转换为小写，符合PostgreSQL惯例
                    field_name_lower = field_name.lower()
                    if field_name_lower == 'caseno':
                        fields.append(f"{field_name_lower} TEXT UNIQUE NOT NULL")
                    else:
                        fields.append(f"{field_name_lower} TEXT")
                
                # 添加系统字段
                fields.extend([
                    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                    "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                ])
                
                fields_sql = ",\n                    ".join(fields)
                create_table_sql = f"""
                CREATE TABLE IF NOT EXISTS zq_kshddpt_dsjfx_jq (
                    {fields_sql}
                );
                """
            else:
                # 如果没有样本数据，使用基础表结构
                logger.info("使用基础表结构创建表")
                create_table_sql = """
                CREATE TABLE IF NOT EXISTS zq_kshddpt_dsjfx_jq (
                    id SERIAL PRIMARY KEY,
                    caseno TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            
            cursor.execute(create_table_sql)
            
            # 创建索引以提高查询性能
            index_sql = """
            CREATE INDEX IF NOT EXISTS idx_zq_kshddpt_dsjfx_jq_caseno ON zq_kshddpt_dsjfx_jq(caseno);
            CREATE INDEX IF NOT EXISTS idx_zq_kshddpt_dsjfx_jq_created_at ON zq_kshddpt_dsjfx_jq(created_at);
            """
            cursor.execute(index_sql)
            
            logger.info("数据表创建/检查完成")
        except Exception as e:
            logger.error(f"创建数据表失败: {e}")
            raise
    
    def login(self) -> bool:
        """
        登录网站
        
        Returns:
            bool: 登录是否成功
        """
        try:
            login_config = self.config['login']
            login_url = login_config['url']
            username = login_config['username']
            password = login_config['password']
            remember_me = login_config.get('rememberMe', True)
            
            # 登录请求数据 - 使用Form Data格式
            login_data = {
                'username': username,
                'password': password,
                'rememberMe': str(remember_me).lower()  # 转换为字符串
            }
            
            # 设置登录请求的特定请求头
            login_headers = {
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json, text/javascript, */*; q=0.01'
            }
            
            logger.info(f"尝试登录: {login_url}")
            logger.info(f"登录参数: username={username}, rememberMe={remember_me}")
            
            # 使用data参数发送Form Data，而不是json参数
            response = self._request(
                'POST',
                login_url, 
                data=login_data, 
                headers=login_headers,
                timeout=30
            )
            
            logger.info(f"登录响应状态码: {response.status_code}")
            logger.info(f"登录响应内容: {response.text[:500]}...")  # 打印前500字符用于调试
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    logger.info(f"登录响应JSON: {result}")
                    
                    # 检查cookies信息
                    if response.cookies:
                        logger.info(f"收到Cookies: {dict(response.cookies)}")
                        # cookies会自动保存到session中
                    
                    # 根据实际API响应格式调整判断逻辑
                    # 您的响应格式: code=0 表示成功, msg='操作成功'
                    if (result.get('code') == 0 or 
                        result.get('code') == 200 or 
                        result.get('success') == True or 
                        result.get('msg') == '操作成功' or
                        'token' in result):
                        
                        logger.info(f"登录成功: {result.get('msg', '操作成功')}")
                        
                        # 如果响应中包含token，保存到session headers中
                        if 'token' in result:
                            self.session.headers['Authorization'] = f"Bearer {result['token']}"
                            logger.info("已保存token到请求头")
                        
                        # 保存可能的session信息
                        if 'sessionId' in result:
                            self.session.cookies.set('sessionId', result['sessionId'])
                            logger.info("已保存sessionId到cookies")
                        
                        # 保存其他可能的认证信息
                        if 'data' in result and isinstance(result['data'], dict):
                            data = result['data']
                            if 'token' in data:
                                self.session.headers['Authorization'] = f"Bearer {data['token']}"
                            if 'sessionId' in data:
                                self.session.cookies.set('sessionId', data['sessionId'])
                        
                        return True
                    else:
                        logger.error(f"登录失败: code={result.get('code')}, msg={result.get('msg', result.get('message', '未知错误'))}")
                        return False
                except json.JSONDecodeError:
                    # 如果响应不是JSON格式，检查是否是成功的重定向或其他成功标识
                    logger.warning(f"登录响应不是JSON格式: {response.text[:200]}")
                    if "成功" in response.text or "success" in response.text.lower():
                        logger.info("登录成功（非JSON响应）")
                        # 保存cookies（如果有的话）
                        if response.cookies:
                            logger.info(f"收到Cookies: {dict(response.cookies)}")
                        return True
                    else:
                        logger.error(f"登录失败，无法解析响应: {response.text[:200]}")
                        return False
            elif response.status_code == 302:  # 重定向通常表示登录成功
                logger.info("登录成功（重定向响应）")
                return True
            else:
                logger.error(f"登录请求失败，状态码: {response.status_code}")
                logger.error(f"错误响应: {response.text[:200]}")
                return False
                
        except Exception as e:
            logger.error(f"登录过程出现异常: {e}")
            return False
    
    def ensure_table_columns(self, data_fields: List[str]):
        """
        确保数据表包含所有需要的字段
        
        Args:
            data_fields: 数据中的字段列表
        """
        try:
            cursor = self.db_conn.cursor()
            
            # 获取当前表的字段（PostgreSQL中字段名都是小写）
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'zq_kshddpt_dsjfx_jq' 
                AND table_schema = current_schema()
            """)
            existing_columns = [row[0] for row in cursor.fetchall()]
            
            # 添加缺失的字段（统一转换为小写进行比较）
            for field in data_fields:
                field_lower = field.lower()  # 转换为小写进行比较
                if field_lower not in existing_columns:
                    alter_sql = f"ALTER TABLE zq_kshddpt_dsjfx_jq ADD COLUMN {field_lower} TEXT"
                    cursor.execute(alter_sql)
                    logger.info(f"添加新字段: {field} -> {field_lower}")
            
        except Exception as e:
            logger.error(f"添加表字段失败: {e}")
            # 不抛出异常，继续执行
    
    def check_case_exists(self, case_no: str) -> bool:
        """
        检查 caseNo 是否已存在于数据库中
        
        Args:
            case_no: 案例编号
            
        Returns:
            bool: 是否存在
        """
        try:
            cursor = self.db_conn.cursor()
            cursor.execute("SELECT 1 FROM zq_kshddpt_dsjfx_jq WHERE caseno = %s", (case_no,))
            return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"检查caseNo存在性失败: {e}")
            return False
    
    def fetch_data(self) -> List[Dict[str, Any]]:
        """
        分页抓取数据，循环翻页直到拉完或达到上限
        
        Returns:
            List[Dict]: 抓取到的数据列表
        """
        request_config = self.config['request']
        api_url = request_config['url']
        base_params = dict(request_config.get('params', {}))
        
        page_size = int(base_params.get('pageSize', 2000) or 2000)
        max_pages = int(os.environ.get("ZQ_MAX_PAGES", "10000") or 10000)
        
        all_rows: List[Dict[str, Any]] = []
        page_num = 1
        
        logger.info(f"开始分页抓取数据: {api_url} pageSize={page_size}")
        
        while page_num <= max_pages:
            params = dict(base_params)
            params['pageSize'] = str(page_size)
            params['pageNum'] = str(page_num)
            
            response = self._request('POST', api_url, data=params, timeout=60)
            
            logger.info(f"第 {page_num} 页响应状态码: {response.status_code}")
            
            if response.status_code != 200:
                raise RuntimeError(
                    f"数据抓取失败，状态码: {response.status_code}, 响应: {response.text[:200]}"
                )
            
            try:
                data = response.json()
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"数据抓取响应不是JSON: {response.text[:200]}") from exc
            
            if data.get('code') != 0:
                raise RuntimeError(
                    f"数据抓取失败: code={data.get('code')}, msg={data.get('msg', '未知错误')}"
                )
            
            rows = data.get('rows', [])
            total = int(data.get('total', 0))
            
            logger.info(f"第 {page_num} 页: {len(rows)} 条，总计 {total} 条")
            
            if not rows:
                break
            
            all_rows.extend(rows)
            
            if len(rows) < page_size:
                break
            if total and len(all_rows) >= total:
                break
            
            page_num += 1
        
        logger.info(f"抓取完成，共 {len(all_rows)} 条，{page_num} 页")
        return all_rows
    
    def save_data(self, items: List[Dict[str, Any]]) -> int:
        """
        批量保存数据到数据库（execute_values + ON CONFLICT）
        
        Args:
            items: 要保存的数据列表
            
        Returns:
            int: 成功保存的记录数（新增+更新）
        """
        if not items:
            logger.warning("没有数据需要保存")
            return 0
        
        # 收集所有字段名（小写、去重、保序）
        all_keys: List[str] = []
        seen = set()
        for item in items:
            for k in item.keys():
                kl = k.lower()
                if kl in ('id', 'created_at', 'updated_at'):
                    continue
                if kl not in seen:
                    seen.add(kl)
                    all_keys.append(kl)
        
        # 确保表包含所有字段
        self.ensure_table_columns(all_keys)
        
        if 'caseno' not in all_keys:
            logger.error("数据缺少caseno字段，无法保存")
            return 0
        
        # 构建 upsert SQL：按 caseno 唯一，冲突时仅当新 updatetime >= 旧 updatetime 才更新
        col_list = ', '.join(f'"{c}"' for c in all_keys)
        non_key_cols = [c for c in all_keys if c != 'caseno']
        set_exprs = [f'"{c}" = EXCLUDED."{c}"' for c in non_key_cols]
        set_exprs.append('updated_at = CURRENT_TIMESTAMP')
        update_clause = ', '.join(set_exprs)
        
        # updatetime 存在时加保护条件：只有新数据 updatetime >= 旧值才更新
        if 'updatetime' in all_keys:
            guard = "WHERE zq_kshddpt_dsjfx_jq.updatetime IS NULL OR EXCLUDED.updatetime >= zq_kshddpt_dsjfx_jq.updatetime"
        else:
            guard = ""
        
        sql = (
            f'INSERT INTO zq_kshddpt_dsjfx_jq ({col_list}) VALUES %s '
            f'ON CONFLICT (caseno) DO UPDATE SET {update_clause} {guard}'
        )
        
        # 构建值元组
        values = []
        for item in items:
            row_lower = {k.lower(): v for k, v in item.items()}
            case_no = row_lower.get('caseno')
            if not case_no:
                logger.warning("数据缺少caseno字段，跳过该条")
                continue
            tup = tuple(_to_text(row_lower.get(c)) for c in all_keys)
            values.append(tup)
        
        if not values:
            return 0
        
        written = 0
        cursor = self.db_conn.cursor()
        try:
            for i in range(0, len(values), DB_BATCH_SIZE):
                chunk = values[i:i + DB_BATCH_SIZE]
                execute_values(cursor, sql, chunk, page_size=DB_BATCH_SIZE)
                written += len(chunk)
            logger.info(f"批量保存完成 - 共 {written} 条")
        finally:
            cursor.close()
        return written
    
    def run(self):
        """执行完整的抓取流程"""
        try:
            logger.info("开始执行舆情数据抓取任务")
            
            # 1. 连接数据库
            if not self.connect_database():
                logger.error("数据库连接失败，任务终止")
                return
            
            # 2. 登录网站
            if not self.login():
                logger.error("登录失败，任务终止")
                return
            
            # 3. 抓取数据
            data_items = self.fetch_data()
            if not data_items:
                logger.warning("未抓取到任何数据")
                return
            
            # 4. 使用第一条数据作为样本创建表结构
            sample_data = data_items[0] if data_items else None
            self.create_table_if_not_exists(sample_data)
            
            # 5. 保存数据
            saved_count = self.save_data(data_items)
            logger.info(f"任务完成，共保存 {saved_count} 条新数据")
            
        except Exception as e:
            logger.error(f"任务执行过程出现异常: {e}")
        finally:
            # 关闭数据库连接
            if self.db_conn:
                self.db_conn.close()
                logger.info("数据库连接已关闭")


def _require_env(name: str, default: Optional[str] = None) -> str:
    value = (os.environ.get(name) or "").strip()
    if value:
        return value
    if default is not None:
        return str(default)
    raise SystemExit(f"缺少环境变量 {name}")


def _first_env(names: List[str], default: Optional[str] = None) -> str:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    if default is not None:
        return str(default)
    raise SystemExit(f"缺少环境变量: {'/'.join(names)}")


def load_config_from_env() -> Dict[str, Any]:
    begin_days_ago = int(os.environ.get("ZQ_BEGIN_DAYS_AGO", "3"))
    page_size = os.environ.get("ZQ_PAGE_SIZE", "2000")
    page_num = os.environ.get("ZQ_PAGE_NUM", "1")

    params = {
        "params[colArray]": "",
        "beginDate": get_begin_of_day(begin_days_ago),
        "endDate": get_end_of_day(),
        "newCaseSourceNo": "",
        "newCaseSource": "全部",
        "dutyDeptNo": "",
        "dutyDeptName": "全部",
        "newCharaSubclassNo": "",
        "newCharaSubclass": "全部",
        "newOriCharaSubclassNo": "",
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
        "caseMarkNo": "",
        "caseMark": "全部",
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
        "pageSize": page_size,
        "pageNum": page_num,
        "orderByColumn": "callTime",
        "isAsc": "desc",
    }

    config = {
        "login": {
            "url": _first_env(["ZQ_LOGIN_URL", "MONITOR_LOGIN_URL"], "http://68.253.2.111/dsjfx/login"),
            "username": _first_env(["ZQ_LOGIN_USERNAME", "LOGIN_USERNAME"]),
            "password": _first_env(["ZQ_LOGIN_PASSWORD", "LOGIN_PASSWORD"]),
            "rememberMe": True,
        },
        "request": {
            "url": _first_env(["ZQ_API_URL", "MONITOR_API_URL"], "http://68.253.2.111/dsjfx/case/list"),
            "params": params,
        },
        "database": {
            "host": _first_env(["ZQ_DB_HOST", "KINGBASE_HOST"]),
            "port": int(_first_env(["ZQ_DB_PORT", "KINGBASE_PORT"])),
            "database": _first_env(["ZQ_DB_NAME", "KINGBASE_DBNAME"]),
            "user": _first_env(["ZQ_DB_USER", "KINGBASE_USER"]),
            "password": _first_env(["ZQ_DB_PASSWORD", "KINGBASE_PASSWORD"]),
            "schema": _require_env("ZQ_DB_SCHEMA", "ywdata"),
        },
    }
    return config


def run(context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    context = context or {}
    runtime_config = context.get("runtime_config")
    if not isinstance(runtime_config, dict):
        runtime_config = {}

    env_mapping = {
        "zq_login_url": "ZQ_LOGIN_URL",
        "zq_login_username": "ZQ_LOGIN_USERNAME",
        "zq_login_password": "ZQ_LOGIN_PASSWORD",
        "zq_api_url": "ZQ_API_URL",
        "zq_db_host": "ZQ_DB_HOST",
        "zq_db_port": "ZQ_DB_PORT",
        "zq_db_name": "ZQ_DB_NAME",
        "zq_db_user": "ZQ_DB_USER",
        "zq_db_password": "ZQ_DB_PASSWORD",
        "zq_db_schema": "ZQ_DB_SCHEMA",
        "zq_begin_days_ago": "ZQ_BEGIN_DAYS_AGO",
        "zq_page_size": "ZQ_PAGE_SIZE",
        "zq_page_num": "ZQ_PAGE_NUM",
    }

    started_at = now_shanghai()
    with _temporary_runtime_env(runtime_config, env_mapping):
        config = load_config_from_env()
        scraper = JingqingZhuaqu(config)

        try:
            if not scraper.connect_database():
                raise RuntimeError("failed to connect to Kingbase")
            if not scraper.login():
                raise RuntimeError("failed to login to source system")

            data_items = scraper.fetch_data()
            target_table = f"{config['database'].get('schema', 'public')}.zq_kshddpt_dsjfx_jq"

            if not data_items:
                return [
                    {
                        "event_id": f"zq_{uuid4().hex}",
                        "task_name": "zq_kshddpt_dsjfx_jq",
                        "target_table": target_table,
                        "status": "success_no_data",
                        "fetched_record_count": 0,
                        "written_record_count": 0,
                        "message_text": "ZQ data sync finished with no data.",
                        "message_vars": {
                            "task_name": "zq_kshddpt_dsjfx_jq",
                            "target_table": target_table,
                            "written_record_count": 0,
                        },
                        "start_time": started_at.isoformat(),
                        "end_time": now_shanghai().isoformat(),
                    }
                ]

            scraper.create_table_if_not_exists(data_items[0])
            written_count = scraper.save_data(data_items)

            return [
                {
                    "event_id": f"zq_{uuid4().hex}",
                    "task_name": "zq_kshddpt_dsjfx_jq",
                    "target_table": target_table,
                    "status": "success",
                    "fetched_record_count": len(data_items),
                    "written_record_count": written_count,
                    "message_text": (
                        f"ZQ data sync finished: fetched {len(data_items)} rows, "
                        f"written {written_count} rows."
                    ),
                    "message_vars": {
                        "task_name": "zq_kshddpt_dsjfx_jq",
                        "target_table": target_table,
                        "fetched_record_count": len(data_items),
                        "written_record_count": written_count,
                    },
                    "start_time": started_at.isoformat(),
                    "end_time": now_shanghai().isoformat(),
                }
            ]
        finally:
            if scraper.db_conn:
                scraper.db_conn.close()
                scraper.db_conn = None


def main():
    """主函数"""
    config = load_config_from_env()
    scraper = JingqingZhuaqu(config)
    scraper.run()


if __name__ == '__main__':
    main()
