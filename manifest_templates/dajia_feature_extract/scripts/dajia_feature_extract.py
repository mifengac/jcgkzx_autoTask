#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
打架斗殴语义特征提取任务 v1

来源表: ywdata.zq_kshddpt_dsjfx_jq  (打架斗殴: 原始性质 或 确认性质)
目标表: jcgkzx_monitor.zq_dajia_feature_extract  (一条警情一行, caseno 唯一)

流程:
  1. 水位线增量拉取打架斗殴警情(原始性质 neworicharasubclassname='打架斗殴'
     或 确认性质 newcharasubclassname='打架斗殴')。
  2. clean_replies 清洗 replies(处警情况), 打质量标记。
  3. 只把 data_quality_flag=='有效案情' 的 cjqk_cleaned + occuraddress 喂锐智
     ayenaspring-pro-001 做语义抽取(并发, 退避重试, 解析 JSON)。
  4. 代码按 calltime 推导时段维度(不耗模型)。
  5. UPSERT 入目标表(ON CONFLICT caseno)。

特征来源: 除"地点(警情地址)/地点分类(警情地址)"取自 occuraddress 外,
          其余特征均从清洗后的 处警情况 提取。

清洗逻辑 vendored 自 skills/dsjjqfx-interface/scripts/clean_replies.py
锐智调用 vendored 自 skills/ruizhi-police-semantic-extraction(引擎规则与并发口径)。
依赖: psycopg2(其余仅标准库)。
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import re
import ssl
import time
import urllib.error
import urllib.request
import gzip
import zlib
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


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 500

# ══════════════════════════════════════════════════════
#  1. 处警情况清洗 (vendored from dsjjqfx-interface/clean_replies.py)
# ══════════════════════════════════════════════════════

COLON = r"\s*[：:]\s*"

HEADER_RE = re.compile(
    r"\[(?:19|20)\d{2}[-/年]\d{1,2}[-/月]\d{1,2}(?:日)?\s+"
    r"\d{1,2}:\d{2}:\d{2}[^\]\n]{0,120}\]"
)
JJF_BLOCK_RE = re.compile(
    r"【结警反馈】(?P<block>.*?)(?=【报警回执】|发送【报警回执】|$)", re.S
)
JJF_DESC_RE = re.compile(
    rf"处理结果说明{COLON}(?P<desc>.*?)(?=补充【|录入当事人信息{COLON}|$)", re.S
)
GCFK_BLOCK_RE = re.compile(
    r"【过程反馈】(?P<block>.*?)(?=【结警反馈】|【报警回执】|$)", re.S
)
GCFK_DESC_RE = re.compile(
    rf"出警处置情况说明{COLON}(?P<desc>.*?)(?=补充【|录入当事人信息{COLON}|$)", re.S
)
NO_DISPATCH_RE = re.compile(
    rf"选择不出警.*?不出警原因{COLON}(?P<desc>.*?)(?=补充【|【[^】]+】|$)", re.S
)
SELF_BUILT_RE = re.compile(
    rf"新建自接警情{COLON}?(?P<desc>.*?)(?=补充【|【[^】]+】|录入当事人信息{COLON}|$)",
    re.S,
)
SUPPLEMENT_RE = re.compile(
    rf"补充【[^】]+】{COLON}(?P<desc>.*?)(?=补充【|【[^】]+】|录入当事人信息{COLON}|$)",
    re.S,
)
DISPOSITION_RE = re.compile(
    rf"处理结果{COLON}(?P<result>.*?)"
    rf"(?=确认性质{COLON}|处理结果说明{COLON}|录入当事人信息{COLON}|$)",
    re.S,
)
INVALID_RE = re.compile(r"取消报警|报假警|醉酒后报警|查无此地|重复报警|误报警")
OUTCITY_RE = re.compile(r"跨地市转警|跨区协作|跨地市转办|肇庆跨区协作")
LOWQ_PHRASES = ["已到场处置", "正在了解", "现场已处理", "处置完毕",
                "已通知相关人员", "现场处置完毕"]
MIN_VALID_LEN = 10


def _denoise(text: str) -> str:
    return HEADER_RE.sub("", text).strip()


def _extract_disposition(raw: str) -> str:
    m = DISPOSITION_RE.search(raw)
    return _denoise(m.group("result")).strip() if m else ""


def clean_one(raw: Optional[str]) -> Dict[str, Any]:
    """输入一条 replies 原文, 返回清洗结果 dict。"""
    out = {"cjqk_cleaned": "", "feedback_source": "无",
           "disposition_result": "", "data_quality_flag": "无有效信息"}
    if not raw or not raw.strip():
        return out
    raw = raw.strip()

    out["disposition_result"] = _extract_disposition(raw)

    main, source = "", "无"

    m = JJF_BLOCK_RE.search(raw)
    if m:
        d = JJF_DESC_RE.search(m.group("block"))
        if d and d.group("desc").strip():
            main, source = _denoise(d.group("desc")), "结警反馈"

    if not main:
        m = GCFK_BLOCK_RE.search(raw)
        if m:
            d = GCFK_DESC_RE.search(m.group("block"))
            if d and d.group("desc").strip():
                main, source = _denoise(d.group("desc")), "过程反馈"

    if not main:
        m = NO_DISPATCH_RE.search(raw)
        if m and m.group("desc").strip():
            main, source = _denoise(m.group("desc")), "不出警原因"

    if not main:
        m = SELF_BUILT_RE.search(raw)
        if m and m.group("desc").strip():
            seg = _denoise(m.group("desc"))
            main = seg.split("\n")[0].strip() if seg else ""
            source = "自接警情" if main else "无"

    sups: List[str] = []
    for sm in SUPPLEMENT_RE.finditer(raw):
        s = _denoise(sm.group("desc"))
        if s and s not in main and s not in sups:
            sups.append(s)
    if sups:
        main = (main + " " + " ".join(sups)).strip() if main else " ".join(sups)
        if source == "无":
            source = "补充"

    out["cjqk_cleaned"] = main
    out["feedback_source"] = source
    out["data_quality_flag"] = _classify(raw, main)
    return out


def _classify(raw: str, main: str) -> str:
    if OUTCITY_RE.search(raw) and "【结警反馈】" not in raw:
        return "外市转办"
    if INVALID_RE.search(raw):
        return "无效警情"
    if not main:
        if "【结警反馈】" not in raw and "【过程反馈】" not in raw:
            return "无有效信息"
        return "低质量"
    if len(main) < MIN_VALID_LEN or any(p in main and len(main) < MIN_VALID_LEN + 5
                                        for p in LOWQ_PHRASES):
        return "低质量"
    if any(main.strip() == p or main.strip().startswith(p) for p in LOWQ_PHRASES) \
            and len(main) < MIN_VALID_LEN + 8:
        return "低质量"
    return "有效案情"


# ══════════════════════════════════════════════════════
#  2. 锐智客户端 (vendored from ruizhi-police-semantic-extraction)
# ══════════════════════════════════════════════════════

RUIZHI_BASE_URL = "https://10.2.164.106/v2"
RUIZHI_MODEL = "ayenaspring-pro-001"


class ApiError(RuntimeError):
    def __init__(self, status_code: Optional[int], message: str):
        super().__init__(message)
        self.status_code = status_code


def _decode_body(raw: bytes, encoding: str) -> str:
    encoding = (encoding or "").lower()
    if "gzip" in encoding:
        raw = gzip.decompress(raw)
    elif "deflate" in encoding:
        raw = zlib.decompress(raw)
    return raw.decode("utf-8", errors="replace")


class RuizhiClient:
    def __init__(self, base_url: str, api_key: str, timeout: float):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.context = ssl._create_unverified_context()

    def chat(self, messages: List[Dict[str, str]], max_tokens: int, temperature: float) -> Dict[str, Any]:
        payload = {
            "model": RUIZHI_MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",
            },
        )
        try:
            with urllib.request.urlopen(request, context=self.context, timeout=self.timeout) as response:
                text = _decode_body(response.read(), response.headers.get("Content-Encoding", ""))
                return json.loads(text)
        except urllib.error.HTTPError as exc:
            text = _decode_body(exc.read(), exc.headers.get("Content-Encoding", ""))
            raise ApiError(exc.code, text[:1000]) from exc
        except urllib.error.URLError as exc:
            raise ApiError(None, str(exc.reason)) from exc


def _first_balanced_object(text: str) -> Optional[str]:
    for start, char in enumerate(text):
        if char != "{":
            continue
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            current = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == '"':
                    in_string = False
                continue
            if current == '"':
                in_string = True
            elif current == "{":
                depth += 1
            elif current == "}":
                depth -= 1
                if depth == 0:
                    return text[start:index + 1]
    return None


def extract_json_object(text: str) -> Dict[str, Any]:
    stripped = (text or "").strip()
    if not stripped:
        raise ValueError("empty answer")
    fenced = re.search(r"```(?:json)?\s*(.*?)```", stripped, re.DOTALL | re.IGNORECASE)
    candidates = [fenced.group(1).strip()] if fenced else []
    candidates.append(stripped)
    balanced = _first_balanced_object(stripped)
    if balanced:
        candidates.append(balanced)
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("no valid JSON object found")


def _model_content(response: Dict[str, Any]) -> str:
    choices = response.get("choices") or []
    if not choices:
        raise ValueError("response has no choices")
    content = ((choices[0].get("message") or {}).get("content"))
    if content is None:
        raise ValueError("response has no message.content")
    return str(content)


# ══════════════════════════════════════════════════════
#  3. 打架斗殴抽取 Prompt + 枚举校验
# ══════════════════════════════════════════════════════

REASON_ENUM = [
    "情感纠纷", "经济纠纷", "酒后滋事", "邻里纠纷", "土地纠纷",
    "交通纠纷", "消费纠纷", "学生间（同事间）琐事纠纷", "医疗纠纷", "其他纠纷",
]
LOCATION_ENUM = [
    "农村", "街面", "一般商店", "学校（包含学校附近）", "住宅区",
    "娱乐场所（包含酒店）", "医院", "机关政府", "工厂公司", "山林野外", "其他",
]
YESNO_ENUM = ["是", "否", "未载明"]
INJURY_ENUM = ["无", "轻微伤", "轻伤", "重伤", "死亡", "未载明"]
RELATION_ENUM = ["陌生人", "熟人朋友", "邻里", "亲属家庭", "夫妻情侣",
                 "同事", "同学", "医患", "商家顾客", "其他", "未载明"]
CONFLICT_ENUM = ["临时起意", "偶发口角", "长期积怨", "未载明"]
DISPOSITION_ENUM = ["当场调解", "治安调解", "行政处罚", "刑事立案处理",
                    "劝离", "移交其他部门", "无需处置", "未载明"]

PROMPT = """你是一名公安警情分析员。下面给你一条"打架斗殴"警情的【处警情况】(已清洗)和【警情地址】，请抽取结构化特征，用于打架斗殴规律分析与警情压降。

【判断依据】
- 除"地点（警情地址）"和"地点分类（警情地址）"取自【警情地址】外，其余所有特征都只从【处警情况】判断。
- 【处警情况】反映民警到场后的实际情况，以它为准；未提及的信息一律填"未载明"，不要臆测、不要编造。
- 只返回一个 JSON 对象，不要任何解释、前后缀或 markdown。

【字段与取值约束】
1. 是否持械：是/否/未载明
2. 持械类型：刀具/棍棒/砖石/酒瓶/钝器/徒手/其他/未持械/未载明（未持械时填"徒手"或"未持械"）
3. 是否饮酒：是/否/未载明
4. 打架原因：用一句话简述起因(原文表述)
5. 打架原因分类：情感纠纷/经济纠纷/酒后滋事/邻里纠纷/土地纠纷/交通纠纷/消费纠纷/学生间（同事间）琐事纠纷/医疗纠纷/其他纠纷（单选其一）
6. 是否多人：打人者是否3人及以上，是/否/未载明
7. 地点_警情地址：从【警情地址】提炼的具体地点
8. 地点分类_警情地址：农村/街面/一般商店/学校（包含学校附近）/住宅区/娱乐场所（包含酒店）/医院/机关政府/工厂公司/山林野外/其他（单选其一）
9. 地点_处警情况：从【处警情况】提炼的事发地点
10. 地点分类_处警情况：同第8项枚举（单选其一）
11. 是否受伤：是否有人受伤，是/否/未载明
12. 伤情：无/轻微伤/轻伤/重伤/死亡/未载明
13. 当事人关系：陌生人/熟人朋友/邻里/亲属家庭/夫妻情侣/同事/同学/医患/商家顾客/其他/未载明
14. 矛盾性质：临时起意/偶发口角/长期积怨/未载明
15. 涉及人数：涉打架人数，能判断就填数字或原文(如"约5人")，否则"未载明"
16. 是否涉及未成年人：是/否/未载明
17. 处置结果分类：当场调解/治安调解/行政处罚/刑事立案处理/劝离/移交其他部门/无需处置/未载明
18. 原因原文：支撑第4/5项判断的处警情况原文片段
19. 地址原文_警情地址：支撑第7/8项的警情地址原文
20. 地址原文_处警情况：支撑第9/10项的处警情况原文片段

只返回如下 JSON（键名完全一致）：
{"是否持械":"","持械类型":"","是否饮酒":"","打架原因":"","打架原因分类":"","是否多人":"","地点_警情地址":"","地点分类_警情地址":"","地点_处警情况":"","地点分类_处警情况":"","是否受伤":"","伤情":"","当事人关系":"","矛盾性质":"","涉及人数":"","是否涉及未成年人":"","处置结果分类":"","原因原文":"","地址原文_警情地址":"","地址原文_处警情况":""}
"""


def _norm_enum(value: Any, enum: List[str], default: str = "未载明") -> str:
    """归一到枚举; 命中别名/包含关系则取标准值, 否则回退默认。"""
    if value is None:
        return default
    s = str(value).strip()
    if not s:
        return default
    if s in enum:
        return s
    for e in enum:
        # 处理含括号的枚举(如"学校（包含学校附近）"), 用主词做包含匹配
        head = re.split(r"[（(]", e)[0]
        if head and (head in s or s in head):
            return e
    return s if default == "" else default


def build_messages(cjqk_cleaned: str, occuraddress: str) -> List[Dict[str, str]]:
    material = f"【处警情况】\n{cjqk_cleaned or '(空)'}\n\n【警情地址】\n{occuraddress or '(空)'}"
    return [
        {"role": "system", "content": PROMPT.strip()},
        {"role": "user", "content": material},
    ]


def map_features(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """模型 JSON -> 目标表特征列(带枚举归一)。"""
    g = parsed.get
    return {
        "is_armed": _norm_enum(g("是否持械"), YESNO_ENUM),
        "weapon_type": (str(g("持械类型") or "").strip() or "未载明")[:50],
        "is_drunk": _norm_enum(g("是否饮酒"), YESNO_ENUM),
        "brawl_reason": (str(g("打架原因") or "").strip())[:500],
        "brawl_reason_category": _norm_enum(g("打架原因分类"), REASON_ENUM, default="其他纠纷"),
        "is_group_fight": _norm_enum(g("是否多人"), YESNO_ENUM),
        "location_address": (str(g("地点_警情地址") or "").strip())[:500],
        "location_address_category": _norm_enum(g("地点分类_警情地址"), LOCATION_ENUM, default="其他"),
        "location_replies": (str(g("地点_处警情况") or "").strip())[:500],
        "location_replies_category": _norm_enum(g("地点分类_处警情况"), LOCATION_ENUM, default="其他"),
        "has_injury": _norm_enum(g("是否受伤"), YESNO_ENUM),
        "injury_severity": _norm_enum(g("伤情"), INJURY_ENUM),
        "party_relationship": _norm_enum(g("当事人关系"), RELATION_ENUM),
        "conflict_nature": _norm_enum(g("矛盾性质"), CONFLICT_ENUM),
        "people_count_est": (str(g("涉及人数") or "").strip() or "未载明")[:20],
        "involves_minor": _norm_enum(g("是否涉及未成年人"), YESNO_ENUM),
        "disposition_category": _norm_enum(g("处置结果分类"), DISPOSITION_ENUM),
        "reason_evidence": (str(g("原因原文") or "").strip())[:500],
        "location_address_evidence": (str(g("地址原文_警情地址") or "").strip())[:500],
        "location_replies_evidence": (str(g("地址原文_处警情况") or "").strip())[:500],
    }


# ══════════════════════════════════════════════════════
#  4. 时段维度(代码推导, 不耗模型)
# ══════════════════════════════════════════════════════

_WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


def _period_of(hour: int) -> str:
    if 0 <= hour < 6:
        return "凌晨"
    if 6 <= hour < 12:
        return "上午"
    if 12 <= hour < 17:
        return "下午"
    if 17 <= hour < 19:
        return "傍晚"
    return "夜间"  # 19-24


def time_dimensions(calltime: Optional[datetime]) -> Dict[str, Any]:
    if not calltime:
        return {"incident_hour": None, "time_period": None, "weekday": None, "is_weekend": None}
    h = calltime.hour
    wd = calltime.weekday()
    return {
        "incident_hour": h,
        "time_period": _period_of(h),
        "weekday": _WEEKDAYS[wd],
        "is_weekend": wd >= 5,
    }


# ══════════════════════════════════════════════════════
#  5. 主任务
# ══════════════════════════════════════════════════════

def _parse_dt(v: Any) -> Optional[datetime]:
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).strip().replace("/", "-"))
    except (ValueError, TypeError):
        return None


# 与源表共有的基础字段(对齐参考表 zq_jingqing_number_extract)
BASE_COLUMNS = [
    "caseno", "updatetime", "calltime", "cmdid", "cmdname", "callerphone", "callername",
    "occuraddress", "casecontents", "replies", "dutydeptno", "dutydeptname", "callway",
    "newrecvtype", "newrecvtypename", "neworicharacategory", "neworicharacategoryname",
    "neworicharatype", "neworicharatypename", "neworicharasubcategory", "neworicharasubcategoryname",
    "neworicharasubclass", "neworicharasubclassname", "newcharacategory", "newcharacategoryname",
    "newcharatype", "newcharatypename", "newcharasubcategory", "newcharasubcategoryname",
    "newcharasubclass", "newcharasubclassname", "lngofcriterion", "latofcriterion",
    "casemark", "casemarkno", "casemarkok", "casemarkokno", "standardcaseno",
]

# 目标表写入列顺序(基础 + 清洗 + 特征 + 时段 + 审计)
INSERT_COLUMNS = [
    "caseno", "source_updatetime", "calltime", "cmdid", "cmdname", "callerphone", "callername",
    "occuraddress", "casecontents", "replies", "dutydeptno", "dutydeptname", "callway",
    "newrecvtype", "newrecvtypename", "neworicharacategory", "neworicharacategoryname",
    "neworicharatype", "neworicharatypename", "neworicharasubcategory", "neworicharasubcategoryname",
    "neworicharasubclass", "neworicharasubclassname", "newcharacategory", "newcharacategoryname",
    "newcharatype", "newcharatypename", "newcharasubcategory", "newcharasubcategoryname",
    "newcharasubclass", "newcharasubclassname", "lngofcriterion", "latofcriterion",
    "casemark", "casemarkno", "casemarkok", "casemarkokno", "standardcaseno",
    # 清洗
    "cjqk_cleaned", "feedback_source", "disposition_result", "data_quality_flag",
    # 必需特征
    "is_armed", "weapon_type", "is_drunk", "brawl_reason", "brawl_reason_category",
    "is_group_fight", "location_address", "location_address_category",
    "location_replies", "location_replies_category",
    # 补充特征
    "has_injury", "injury_severity", "party_relationship", "conflict_nature",
    "people_count_est", "involves_minor", "disposition_category",
    # 时段
    "incident_hour", "time_period", "weekday", "is_weekend",
    # 审计
    "reason_evidence", "location_address_evidence", "location_replies_evidence",
    "model_name", "extract_status", "extract_error", "raw_answer",
    "extracted_at",
]

# UPSERT 时需要刷新的列(除 caseno / extracted_at 外全部覆盖)
_UPDATE_COLUMNS = [c for c in INSERT_COLUMNS if c not in ("caseno",)]


class DajiaFeatureTask:
    def __init__(
        self,
        src_dsn: str,
        dst_dsn: str,
        api_key: str,
        src_schema: str = "ywdata",
        dst_schema: str = "jcgkzx_monitor",
        lookback_min: int = 10,
        concurrency: int = 3,
        retries: int = 2,
        max_tokens: int = 700,
        temperature: float = 0.1,
        timeout: float = 120.0,
        case_type: str = "打架斗殴",
        config_schema: str = "jcgkzx_monitor",
    ):
        self.src_dsn = src_dsn
        self.dst_dsn = dst_dsn
        self.api_key = api_key
        self.src_schema = src_schema
        self.dst_schema = dst_schema
        self.lookback_min = lookback_min
        self.concurrency = concurrency
        self.retries = retries
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout
        self.case_type = case_type          # case_type_config.leixing 值
        self.config_schema = config_schema  # case_type_config 所在 schema
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
                f"SELECT MAX(source_updatetime) FROM {self.dst_schema}.zq_dajia_feature_extract"
            )
            row = cur.fetchone()
        if row and row[0]:
            wm = row[0] - timedelta(minutes=self.lookback_min)
            logger.info(f"水位线: {wm}（MAX source_updatetime - {self.lookback_min}min buffer）")
            return wm
        fallback = now_shanghai().replace(tzinfo=None) - timedelta(days=3)
        logger.info(f"目标表为空，回溯至 {fallback}")
        return fallback

    # ── 取打架斗殴叶子代码(来自 case_type_config) ───────
    def _subclass_codes(self) -> List[str]:
        """jcgkzx_monitor.case_type_config 里 leixing=case_type 的 newcharasubclass_list。"""
        sql = (
            f"SELECT unnest(newcharasubclass_list) "
            f"FROM {self.config_schema}.case_type_config WHERE leixing = %s"
        )
        with self._dst.cursor() as cur:
            cur.execute(sql, (self.case_type,))
            codes = [r[0] for r in cur.fetchall() if r[0] is not None]
        if not codes:
            raise ValueError(
                f"{self.config_schema}.case_type_config 中 leixing='{self.case_type}' "
                f"未取到任何 newcharasubclass 代码，请先核对配置表。"
            )
        logger.info(f"case_type_config: leixing='{self.case_type}' 匹配 {len(codes)} 个叶子代码")
        return codes

    # ── 拉源数据(打架斗殴: 原始 或 确认 叶子代码命中) ──────
    def _fetch_src(self, since: datetime, codes: List[str]) -> List[Dict]:
        # 用代码列 neworicharasubclass(原始)/newcharasubclass(确认) 匹配 case_type_config 代码集
        sql = (
            f"SELECT {', '.join(BASE_COLUMNS)} "
            f"FROM {self.src_schema}.zq_kshddpt_dsjfx_jq "
            f"WHERE updatetime IS NOT NULL AND updatetime >= %s "
            f"  AND (neworicharasubclass = ANY(%s) OR newcharasubclass = ANY(%s)) "
            f"ORDER BY updatetime"
        )
        with self._src.cursor() as cur:
            cur.execute(sql, (since, codes, codes))
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        logger.info(
            f"源表读取 {len(rows)} 条 {self.case_type} 警情（updatetime >= {since}，"
            f"原始或确认叶子代码命中 case_type_config）"
        )
        return rows

    # ── 单条语义抽取(供线程池调用) ──────────────────────
    def _extract_one(self, client: RuizhiClient, cjqk_cleaned: str, occuraddress: str) -> Dict[str, Any]:
        last_error = ""
        raw_answer = ""
        for attempt in range(self.retries + 1):
            try:
                resp = client.chat(
                    build_messages(cjqk_cleaned, occuraddress),
                    self.max_tokens,
                    self.temperature,
                )
                raw_answer = _model_content(resp)
                parsed = extract_json_object(raw_answer)
                feats = map_features(parsed)
                feats["extract_status"] = "ok"
                feats["extract_error"] = ""
                feats["raw_answer"] = raw_answer
                return feats
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < self.retries:
                    sleep_s = min(30, 2 ** attempt)
                    if isinstance(exc, ApiError) and exc.status_code == 429:
                        sleep_s = max(sleep_s, 8)
                    time.sleep(sleep_s)
        return {"extract_status": "failed", "extract_error": last_error, "raw_answer": raw_answer}

    # ── 组装一行 ────────────────────────────────────────
    def _assemble_row(self, rec: Dict, cleaned: Dict, feats: Dict, now: datetime) -> tuple:
        src_ut = _parse_dt(rec.get("updatetime"))
        calltime = _parse_dt(rec.get("calltime"))
        tdim = time_dimensions(calltime)
        f = feats or {}
        values = {
            "caseno": (rec.get("caseno") or "").strip(),
            "source_updatetime": src_ut,
            "calltime": calltime,
            "cmdid": rec.get("cmdid"),
            "cmdname": rec.get("cmdname"),
            "callerphone": rec.get("callerphone"),
            "callername": rec.get("callername"),
            "occuraddress": rec.get("occuraddress"),
            "casecontents": rec.get("casecontents"),
            "replies": rec.get("replies"),
            "dutydeptno": rec.get("dutydeptno"),
            "dutydeptname": rec.get("dutydeptname"),
            "callway": rec.get("callway"),
            "newrecvtype": rec.get("newrecvtype"),
            "newrecvtypename": rec.get("newrecvtypename"),
            "neworicharacategory": rec.get("neworicharacategory"),
            "neworicharacategoryname": rec.get("neworicharacategoryname"),
            "neworicharatype": rec.get("neworicharatype"),
            "neworicharatypename": rec.get("neworicharatypename"),
            "neworicharasubcategory": rec.get("neworicharasubcategory"),
            "neworicharasubcategoryname": rec.get("neworicharasubcategoryname"),
            "neworicharasubclass": rec.get("neworicharasubclass"),
            "neworicharasubclassname": rec.get("neworicharasubclassname"),
            "newcharacategory": rec.get("newcharacategory"),
            "newcharacategoryname": rec.get("newcharacategoryname"),
            "newcharatype": rec.get("newcharatype"),
            "newcharatypename": rec.get("newcharatypename"),
            "newcharasubcategory": rec.get("newcharasubcategory"),
            "newcharasubcategoryname": rec.get("newcharasubcategoryname"),
            "newcharasubclass": rec.get("newcharasubclass"),
            "newcharasubclassname": rec.get("newcharasubclassname"),
            "lngofcriterion": rec.get("lngofcriterion"),
            "latofcriterion": rec.get("latofcriterion"),
            "casemark": rec.get("casemark"),
            "casemarkno": rec.get("casemarkno"),
            "casemarkok": rec.get("casemarkok"),
            "casemarkokno": rec.get("casemarkokno"),
            "standardcaseno": rec.get("standardcaseno"),
            "cjqk_cleaned": cleaned.get("cjqk_cleaned"),
            "feedback_source": cleaned.get("feedback_source"),
            "disposition_result": (cleaned.get("disposition_result") or "")[:200],
            "data_quality_flag": cleaned.get("data_quality_flag"),
            "is_armed": f.get("is_armed"),
            "weapon_type": f.get("weapon_type"),
            "is_drunk": f.get("is_drunk"),
            "brawl_reason": f.get("brawl_reason"),
            "brawl_reason_category": f.get("brawl_reason_category"),
            "is_group_fight": f.get("is_group_fight"),
            "location_address": f.get("location_address"),
            "location_address_category": f.get("location_address_category"),
            "location_replies": f.get("location_replies"),
            "location_replies_category": f.get("location_replies_category"),
            "has_injury": f.get("has_injury"),
            "injury_severity": f.get("injury_severity"),
            "party_relationship": f.get("party_relationship"),
            "conflict_nature": f.get("conflict_nature"),
            "people_count_est": f.get("people_count_est"),
            "involves_minor": f.get("involves_minor"),
            "disposition_category": f.get("disposition_category"),
            "incident_hour": tdim["incident_hour"],
            "time_period": tdim["time_period"],
            "weekday": tdim["weekday"],
            "is_weekend": tdim["is_weekend"],
            "reason_evidence": f.get("reason_evidence"),
            "location_address_evidence": f.get("location_address_evidence"),
            "location_replies_evidence": f.get("location_replies_evidence"),
            "model_name": RUIZHI_MODEL,
            "extract_status": f.get("extract_status", "skipped"),
            "extract_error": f.get("extract_error", ""),
            "raw_answer": f.get("raw_answer", ""),
            "extracted_at": now,
        }
        return tuple(values[c] for c in INSERT_COLUMNS)

    # ── upsert ─────────────────────────────────────────
    def _upsert(self, rows: List[tuple]) -> int:
        if not rows:
            return 0
        set_clause = ",\n                ".join(
            f"{c} = EXCLUDED.{c}" for c in _UPDATE_COLUMNS
        )
        sql = f"""
            INSERT INTO {self.dst_schema}.zq_dajia_feature_extract (
                {', '.join(INSERT_COLUMNS)}
            )
            VALUES %s
            ON CONFLICT (caseno) DO UPDATE SET
                {set_clause},
                updated_at = CURRENT_TIMESTAMP
        """
        written = 0
        with self._dst.cursor() as cur:
            for i in range(0, len(rows), BATCH_SIZE):
                chunk = rows[i:i + BATCH_SIZE]
                execute_values(cur, sql, chunk, page_size=BATCH_SIZE)
                written += len(chunk)
        logger.info(f"upsert {written} 行完成")
        return written

    def run(self) -> Dict[str, Any]:
        wm = self._watermark()
        codes = self._subclass_codes()
        records = [r for r in self._fetch_src(wm, codes) if (r.get("caseno") or "").strip()]

        # 1) 清洗
        cleaned_list = [clean_one(r.get("replies")) for r in records]

        # 2) 只对"有效案情"调模型
        to_model_idx = [
            i for i, c in enumerate(cleaned_list)
            if c.get("data_quality_flag") == "有效案情"
        ]
        feats_by_idx: Dict[int, Dict[str, Any]] = {}
        if to_model_idx:
            client = RuizhiClient(RUIZHI_BASE_URL, self.api_key, self.timeout)
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.concurrency) as pool:
                future_to_idx = {
                    pool.submit(
                        self._extract_one,
                        client,
                        cleaned_list[i].get("cjqk_cleaned", ""),
                        records[i].get("occuraddress", "") or "",
                    ): i
                    for i in to_model_idx
                }
                done = 0
                for fut in concurrent.futures.as_completed(future_to_idx):
                    idx = future_to_idx[fut]
                    feats_by_idx[idx] = fut.result()
                    done += 1
                    if done % 20 == 0:
                        logger.info(f"语义抽取进度 {done}/{len(to_model_idx)}")

        # 3) 组装
        now = now_shanghai().replace(tzinfo=None)
        rows: List[tuple] = []
        ok = failed = skipped = 0
        for i, rec in enumerate(records):
            feats = feats_by_idx.get(i)
            if feats is None:
                feats = {"extract_status": "skipped", "extract_error": "", "raw_answer": ""}
                skipped += 1
            elif feats.get("extract_status") == "ok":
                ok += 1
            else:
                failed += 1
            rows.append(self._assemble_row(rec, cleaned_list[i], feats, now))

        written = self._upsert(rows)
        return {
            "source_records": len(records),
            "model_called": len(to_model_idx),
            "extract_ok": ok,
            "extract_failed": failed,
            "extract_skipped": skipped,
            "written_rows": written,
            "watermark": wm.isoformat(),
        }


# ══════════════════════════════════════════════════════
#  6. 环境变量 / runtime_config(复用 number_extract 的 DB 回退链)
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


def _clean_url(url: str) -> str:
    if not url:
        return url
    if "postgresql+psycopg2://" in url:
        return url.replace("postgresql+psycopg2://", "postgresql://")
    if "postgresql+pg8000://" in url:
        return url.replace("postgresql+pg8000://", "postgresql://")
    return url


def _build_dsn(host_keys, port_keys, db_keys, user_keys, pwd_keys) -> str:
    h = _first(*host_keys)
    p = _first(*port_keys, default="5432")
    d = _first(*db_keys)
    u = _first(*user_keys)
    w = _first(*pwd_keys)
    return f"host={h} port={p} dbname={d} user={u} password={w}"


def _src_dsn() -> str:
    url = _first("DJ_SRC_DB_URL", "DJ_DB_URL", "NE_SRC_DB_URL", "NE_DB_URL", "DATABASE_URL", default="")
    if url:
        return _clean_url(url)
    return _build_dsn(
        ["DJ_SRC_HOST", "DJ_DB_HOST", "NE_SRC_HOST", "NE_DB_HOST", "ZQ_DB_HOST", "KINGBASE_HOST"],
        ["DJ_SRC_PORT", "DJ_DB_PORT", "NE_SRC_PORT", "NE_DB_PORT", "ZQ_DB_PORT", "KINGBASE_PORT"],
        ["DJ_SRC_DB", "DJ_DB_NAME", "NE_SRC_DB", "NE_DB_NAME", "ZQ_DB_NAME", "KINGBASE_DBNAME"],
        ["DJ_SRC_USER", "DJ_DB_USER", "NE_SRC_USER", "NE_DB_USER", "ZQ_DB_USER", "KINGBASE_USER"],
        ["DJ_SRC_PASSWORD", "DJ_DB_PASSWORD", "NE_SRC_PASSWORD", "NE_DB_PASSWORD", "ZQ_DB_PASSWORD", "KINGBASE_PASSWORD"],
    )


def _dst_dsn() -> str:
    url = _first("DJ_DST_DB_URL", "DJ_DB_URL", "NE_DST_DB_URL", "NE_DB_URL", "DATABASE_URL", default="")
    if url:
        return _clean_url(url)
    return _build_dsn(
        ["DJ_DST_HOST", "DJ_DB_HOST", "NE_DST_HOST", "NE_DB_HOST", "ZQ_DB_HOST", "KINGBASE_HOST"],
        ["DJ_DST_PORT", "DJ_DB_PORT", "NE_DST_PORT", "NE_DB_PORT", "ZQ_DB_PORT", "KINGBASE_PORT"],
        ["DJ_DST_DB", "DJ_DB_NAME", "NE_DST_DB", "NE_DB_NAME", "ZQ_DB_NAME", "KINGBASE_DBNAME"],
        ["DJ_DST_USER", "DJ_DB_USER", "NE_DST_USER", "NE_DB_USER", "ZQ_DB_USER", "KINGBASE_USER"],
        ["DJ_DST_PASSWORD", "DJ_DB_PASSWORD", "NE_DST_PASSWORD", "NE_DB_PASSWORD", "ZQ_DB_PASSWORD", "KINGBASE_PASSWORD"],
    )


# runtime_config key → 环境变量名
_ENV_MAP = {
    "dj_src_db_url": "DJ_SRC_DB_URL",
    "dj_dst_db_url": "DJ_DST_DB_URL",
    "dj_db_url": "DJ_DB_URL",
    "dj_src_host": "DJ_SRC_HOST",
    "dj_src_port": "DJ_SRC_PORT",
    "dj_src_db": "DJ_SRC_DB",
    "dj_src_user": "DJ_SRC_USER",
    "dj_src_password": "DJ_SRC_PASSWORD",
    "dj_dst_host": "DJ_DST_HOST",
    "dj_dst_port": "DJ_DST_PORT",
    "dj_dst_db": "DJ_DST_DB",
    "dj_dst_user": "DJ_DST_USER",
    "dj_dst_password": "DJ_DST_PASSWORD",
    "dj_src_schema": "DJ_SRC_SCHEMA",
    "dj_dst_schema": "DJ_DST_SCHEMA",
    "dj_lookback_min": "DJ_LOOKBACK_MIN",
    "dj_concurrency": "DJ_CONCURRENCY",
    "dj_retries": "DJ_RETRIES",
    "dj_max_tokens": "DJ_MAX_TOKENS",
    "dj_case_type": "DJ_CASE_TYPE",
    "dj_config_schema": "DJ_CONFIG_SCHEMA",
    "ruizhi_api_key": "RUIZHI_API_KEY",
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
        api_key = _env("RUIZHI_API_KEY")
        task = DajiaFeatureTask(
            src_dsn=_src_dsn(),
            dst_dsn=_dst_dsn(),
            api_key=api_key,
            src_schema=_env("DJ_SRC_SCHEMA", "ywdata"),
            dst_schema=_env("DJ_DST_SCHEMA", "jcgkzx_monitor"),
            lookback_min=int(_env("DJ_LOOKBACK_MIN", "10")),
            concurrency=int(_env("DJ_CONCURRENCY", "3")),
            retries=int(_env("DJ_RETRIES", "2")),
            max_tokens=int(_env("DJ_MAX_TOKENS", "700")),
            case_type=_env("DJ_CASE_TYPE", "打架斗殴"),
            config_schema=_env("DJ_CONFIG_SCHEMA", _env("DJ_DST_SCHEMA", "jcgkzx_monitor")),
        )
        try:
            task.connect()
            stats = task.run()
        finally:
            task.close()

    ended = now_shanghai()
    return [
        {
            "event_id": f"dj_{uuid4().hex}",
            "task_name": "dajia_feature_extract",
            "status": "success",
            "source_records": stats["source_records"],
            "model_called": stats["model_called"],
            "extract_ok": stats["extract_ok"],
            "extract_failed": stats["extract_failed"],
            "extract_skipped": stats["extract_skipped"],
            "written_rows": stats["written_rows"],
            "watermark": stats["watermark"],
            "message_text": (
                f"打架斗殴特征提取完成: 警情 {stats['source_records']} 条，"
                f"入模 {stats['model_called']} 条（成功 {stats['extract_ok']}，"
                f"失败 {stats['extract_failed']}，跳过 {stats['extract_skipped']}），"
                f"写入 {stats['written_rows']} 行"
            ),
            "start_time": started.isoformat(),
            "end_time": ended.isoformat(),
        }
    ]


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
