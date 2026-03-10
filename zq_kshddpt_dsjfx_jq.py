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
import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from uuid import uuid4
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
    return datetime.now().strftime("%Y-%m-%d 23:59:59")

def get_begin_of_day(days_ago: int = 0) -> str:
    """
    获取指定天数前的开始时间，格式为 'YYYY-MM-DD 00:00:00'
    """
    date = datetime.now() - timedelta(days=days_ago)
    return date.strftime("%Y-%m-%d 00:00:00")

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
            response = self.session.post(
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
                    if field_lower == 'caseno':
                        # caseno字段需要唯一约束
                        alter_sql = f"ALTER TABLE zq_kshddpt_dsjfx_jq ADD COLUMN {field_lower} TEXT UNIQUE"
                    else:
                        alter_sql = f"ALTER TABLE zq_kshddpt_dsjfx_jq ADD COLUMN {field_lower} TEXT"
                    
                    cursor.execute(alter_sql)
                    logger.info(f"添加新字段: {field} -> {field_lower}")
            
        except Exception as e:
            logger.error(f"添加表字段失败: {e}")
            # 不抛出异常，继续执行
    
    def check_case_exists(self, case_no: str) -> bool:
        """
        检查caseNo是否已存在于数据库中
        
        Args:
            case_no: 案例编号
            
        Returns:
            bool: 是否存在
        """
        try:
            cursor = self.db_conn.cursor()
            # 使用小写的caseno字段名
            cursor.execute("SELECT 1 FROM zq_kshddpt_dsjfx_jq WHERE caseno = %s", (case_no,))
            return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"检查caseNo存在性失败: {e}")
            return False
    
    def fetch_data(self) -> List[Dict[str, Any]]:
        """
        抓取数据
        
        Returns:
            List[Dict]: 抓取到的数据列表
        """
        try:
            request_config = self.config['request']
            api_url = request_config['url']
            params = request_config.get('params', {})
            # post_data = request_config.get('data', {})
            
            # 设置数据请求的请求头
            # data_headers = {
            #     'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            #     'X-Requested-With': 'XMLHttpRequest',
            #     'Accept': 'application/json, text/javascript, */*; q=0.01'
            # }
            
            logger.info(f"开始抓取数据: {api_url}")
            # logger.info(f"POST参数: {post_data}")
            
            # 使用POST请求获取数据
            response = self.session.post(
                api_url, 
                data=params, 
                timeout=30
            )
            
            logger.info(f"数据抓取响应状态码: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"数据抓取响应: {str(data)[:500]}...")  # 打印前500字符用于调试
                
                # 检查响应格式: {"total":123,"rows":[{}],"code":0}
                if data.get('code') == 0:
                    rows = data.get('rows', [])
                    total = data.get('total', 0)
                    
                    logger.info(f"成功抓取到数据 - 总计: {total} 条，当前批次: {len(rows)} 条")
                    
                    if not rows:
                        logger.warning("响应中的rows为空或不存在")
                        return []
                    
                    return rows
                else:
                    logger.error(f"数据抓取失败: code={data.get('code')}, msg={data.get('msg', '未知错误')}")
                    return []
            else:
                logger.error(f"数据抓取失败，状态码: {response.status_code}")
                logger.error(f"错误响应: {response.text[:200]}")
                return []
                
        except Exception as e:
            logger.error(f"数据抓取过程出现异常: {e}")
            return []
    
    def save_data(self, items: List[Dict[str, Any]]) -> int:
        """
        保存数据到数据库
        
        Args:
            items: 要保存的数据列表
            
        Returns:
            int: 成功保存的记录数（新增+更新）
        """
        saved_count = 0
        updated_count = 0
        
        if not items:
            logger.warning("没有数据需要保存")
            return 0
        
        try:
            cursor = self.db_conn.cursor()
            
            # 获取第一条数据的字段，用于确保表结构完整
            sample_item = items[0]
            data_fields = list(sample_item.keys())
            
            # 确保表包含所有需要的字段
            self.ensure_table_columns(data_fields)
            
            for item in items:
                # 查找caseNo字段（不区分大小写）
                case_no = None
                for key, value in item.items():
                    if key.lower() == 'caseno':
                        case_no = value
                        break
                
                if not case_no:
                    logger.warning("数据缺少caseNo字段，跳过")
                    continue

                # 动态构建字段映射（将字段名转换为小写）
                fields_mapping = {}  # 原始字段名 -> 小写字段名映射
                db_fields = []  # 数据库中的字段名（小写）
                values = []  # 对应的值

                for field_name, field_value in item.items():
                    db_field_name = field_name.lower()
                    fields_mapping[field_name] = db_field_name
                    db_fields.append(db_field_name)
                    values.append(str(field_value))

                # 检查是否已存在，存在则更新，否则插入
                if self.check_case_exists(case_no):
                    set_clauses = ', '.join([f"{field} = %s" for field in db_fields])
                    update_sql = f"""
                    UPDATE zq_kshddpt_dsjfx_jq
                    SET {set_clauses}, updated_at = CURRENT_TIMESTAMP
                    WHERE caseno = %s
                    """
                    cursor.execute(update_sql, values + [case_no])
                    updated_count += 1
                    logger.debug(f"成功更新 caseNo: {case_no}，字段映射: {fields_mapping}")
                else:
                    placeholders = ', '.join(['%s'] * len(db_fields))
                    field_names = ', '.join(db_fields)

                    insert_sql = f"""
                    INSERT INTO zq_kshddpt_dsjfx_jq ({field_names}) 
                    VALUES ({placeholders})
                    """

                    cursor.execute(insert_sql, values)
                    saved_count += 1
                    logger.debug(f"成功保存 caseNo: {case_no}，字段映射: {fields_mapping}")

            logger.info(f"数据保存完成 - 新增: {saved_count} 条，更新: {updated_count} 条")
            return saved_count + updated_count
            
        except Exception as e:
            logger.error(f"数据保存过程出现异常: {e}")
            return saved_count
    
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
    page_size = os.environ.get("ZQ_PAGE_SIZE", "99999")
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

    started_at = datetime.now()
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
                        "end_time": datetime.now().isoformat(),
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
                    "end_time": datetime.now().isoformat(),
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
