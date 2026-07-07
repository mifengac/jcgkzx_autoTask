#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
巡防系统 dutySchedule/crossDayList 时间范围压测脚本
====================================================

目的
----
内网"智慧可视化指挥调度平台"(zhksh) 的排班跨天查询接口
    POST /zhksh/dutySchedule/crossDayList
在时间跨度较大时会变慢甚至卡死。本脚本自动登录后, 用逐步放大的
时间跨度(params[beginTime] / params[endTime])反复请求该接口,
测出"在给定超时内能查询多大的时间范围", 为后续做自定义任务定容量。

只读探测: pageSize=10 / pageNum=1, 只看 total 与响应耗时, 不落库、
不翻页、不改动任何数据。

用法
----
    python3 probe_crossday_range.py

    # 常用可调项(环境变量):
    XF_END_DATE=2026-07-01 \        # 锚定的结束日期(默认=今天)
    XF_LADDER="1,2,3,5,7,10,14,21,30" \  # 逐步放大的天数梯度
    XF_TIMEOUT=60 \                 # 单请求硬超时(秒), 超过视为"卡死"
    XF_SLOW=15 \                    # 慢查询告警阈值(秒)
    python3 probe_crossday_range.py

认证
----
登录接口 POST /zhksh/login 的口令字段是客户端加密后的密文
(16 字节 AES 块, 对固定账号是确定值), 因此直接复用 HAR 抓到的
username + 密文即可重新登录, 无需明文。也可用两种方式覆盖:

  1) 账号密文登录(默认):
       XF_USERNAME=270378  XF_PASSWORD_ENC=IIhlt+k0TQ06d6PUm4yV+Q==
  2) 直接贴 Cookie 跳过登录(密文/会话失效时应急):
       XF_COOKIE="JSESSIONID=xxx; rememberMe=yyy"

依赖: 仅标准库(urllib / http.cookiejar), 无需 pip 安装。
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# ── 配置(默认值取自 xunfang.har) ─────────────────────────────
BASE = os.environ.get("XF_BASE", "http://68.253.2.107/zhksh").rstrip("/")
USERNAME = os.environ.get("XF_USERNAME", "270378")
# 客户端加密后的口令密文(AES 单块, 对固定账号确定); 见文件头说明
PASSWORD_ENC = os.environ.get("XF_PASSWORD_ENC", "IIhlt+k0TQ06d6PUm4yV+Q==")
COOKIE_OVERRIDE = os.environ.get("XF_COOKIE", "").strip()

# 结束日期锚点(YYYY-MM-DD); 逐步放大的是起始日期, 结束日期固定
END_DATE = os.environ.get("XF_END_DATE", datetime.now().strftime("%Y-%m-%d"))
# 阶段A: 时间跨度梯度(天), pageSize=10, 测"日期范围/COUNT"成本
LADDER = [
    int(x) for x in os.environ.get(
        "XF_LADDER", "1,2,3,5,7,10,14,21,30,45,60,90").split(",")
    if x.strip()
]
REQUEST_TIMEOUT = float(os.environ.get("XF_TIMEOUT", "60"))   # 硬超时 -> "卡死"
SLOW_WARN = float(os.environ.get("XF_SLOW", "15"))            # 慢查询告警

# 阶段B: 单请求"全量拉取"成本 = 真正会卡死的地方(大 pageSize 序列化+传输)。
# 在固定跨度 XF_PS_DAYS 天上, 逐步放大 pageSize, 直到卡死。
PS_DAYS = int(os.environ.get("XF_PS_DAYS", "7"))
PS_LADDER = [
    int(x) for x in os.environ.get(
        "XF_PS_LADDER", "10,100,500,1000,2000,5000,10000,20000").split(",")
    if x.strip()
]
RUN_PS = os.environ.get("XF_RUN_PAGESIZE", "1").strip() not in ("0", "false", "")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36")


# ── HTTP 会话(自动管理 JSESSIONID / rememberMe) ──────────────
class Session:
    def __init__(self) -> None:
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar)
        )

    def _base_headers(self) -> Dict[str, str]:
        h = {
            "User-Agent": UA,
            "Origin": BASE.rsplit("/", 1)[0] if "/" in BASE[8:] else BASE,
            "Referer": f"{BASE}/dutySchedule",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        if COOKIE_OVERRIDE:
            h["Cookie"] = COOKIE_OVERRIDE
        return h

    def get(self, path: str, timeout: float) -> Tuple[int, str]:
        req = urllib.request.Request(f"{BASE}{path}", headers=self._base_headers())
        with self.opener.open(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")

    def post_form(self, path: str, form: Dict[str, str], timeout: float
                  ) -> Tuple[int, str]:
        body = urllib.parse.urlencode(form).encode("utf-8")
        headers = self._base_headers()
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        req = urllib.request.Request(
            f"{BASE}{path}", data=body, headers=headers, method="POST"
        )
        with self.opener.open(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")


# ── 登录 ────────────────────────────────────────────────────
def login(sess: Session) -> None:
    if COOKIE_OVERRIDE:
        print(f"[login] 使用 XF_COOKIE 覆盖, 跳过账号登录")
        return
    # 1) 先 GET 登录页拿到一个 JSESSIONID 会话
    try:
        sess.get("/login", timeout=30)
    except Exception as exc:  # 拿不到也不致命, 继续尝试 POST
        print(f"[login] GET /login 提示: {exc}")

    # 2) POST 登录(字段与 HAR 完全一致)
    form = {
        "username": USERNAME,
        "password": PASSWORD_ENC,
        "rememberMe": "true",
        "isPkiLogin": "false",
        "isAccLogin": "true",
        "isSmsLogin": "false",
    }
    status, text = sess.post_form("/login", form, timeout=30)
    ok = False
    snippet = text.strip()[:200]
    try:
        j = json.loads(text)
        # RuoYi 风格: code==0/200 或 msg 含"成功"
        code = j.get("code")
        ok = code in (0, 200, "0", "200") or ("成功" in (j.get("msg") or ""))
    except Exception:
        # 非 JSON: 只要不是又被打回登录页, 就先当作可能成功, 靠首个探测请求验证
        ok = "loginForm" not in text and "用户名" not in text
    if not ok:
        print(f"[login] 登录疑似失败 (HTTP {status}): {snippet}")
        print("[login] 若密文/会话已失效, 请用 XF_COOKIE 覆盖或更新 XF_PASSWORD_ENC")
    else:
        print(f"[login] 登录请求已提交 (HTTP {status})")


# ── 构造 crossDayList 表单(其余字段照抄 HAR 默认) ────────────
def build_form(begin_time: str, end_time: str,
               page_size: int = 10, page_num: int = 1) -> Dict[str, str]:
    return {
        "pageSize": str(page_size),
        "pageNum": str(page_num),
        "orderByColumn": "startTime",
        "isAsc": "asc",
        "keywords": "",
        "deploymentType": "",
        "deploymentId": "",
        "deploymentName": "",
        "scheduleDate": "",
        "params[beginTime]": begin_time,
        "params[endTime]": end_time,
        "deptId": "",
        "deptName": "全部",
        "schemeId": "",
        "shiftId": "",
        "userTypeCode": "",
        "dutyTypeCode": "",
        "dutyTypeName": "",
        "policeCategory": "",
        "userId": "",
        "userName": "",
    }


def span_times(end_date: str, span_days: int) -> Tuple[str, str]:
    """span_days=N -> [end_date-(N-1) 00:00:00, end_date 23:59:59]。"""
    end_d = datetime.strptime(end_date, "%Y-%m-%d")
    begin_d = end_d - timedelta(days=span_days - 1)
    return (begin_d.strftime("%Y-%m-%d 00:00:00"),
            end_d.strftime("%Y-%m-%d 23:59:59"))


class ProbeResult:
    def __init__(self, days: int, begin: str, end: str,
                 page_size: int = 10) -> None:
        self.days = days
        self.begin = begin
        self.end = end
        self.page_size = page_size
        self.elapsed: Optional[float] = None
        self.total: Optional[int] = None       # 服务端 COUNT 总数
        self.rows_returned: Optional[int] = None  # 本次实际返回行数
        self.nbytes: Optional[int] = None      # 响应体字节数
        self.status = "?"      # ok / slow / timeout / error
        self.detail = ""

    @property
    def ok(self) -> bool:
        return self.status in ("ok", "slow")


def _request(sess: Session, form: Dict[str, str], r: ProbeResult) -> ProbeResult:
    """发一次 crossDayList 请求, 把结果填进 r(耗时/总数/行数/字节/状态)。"""
    t0 = time.monotonic()
    try:
        http_status, text = sess.post_form(
            "/dutySchedule/crossDayList", form, timeout=REQUEST_TIMEOUT
        )
        r.elapsed = time.monotonic() - t0
        r.nbytes = len(text.encode("utf-8", "replace"))
        try:
            j = json.loads(text)
        except Exception:
            r.status = "error"
            r.detail = f"HTTP {http_status} 非 JSON(疑似未登录): {text.strip()[:120]}"
            return r
        if "rows" in j or "total" in j:
            r.total = j.get("total")
            r.rows_returned = len(j.get("rows") or [])
            r.status = "slow" if r.elapsed >= SLOW_WARN else "ok"
        else:
            r.status = "error"
            r.detail = f"响应无 rows/total: {json.dumps(j, ensure_ascii=False)[:120]}"
    except socket.timeout:
        r.elapsed = time.monotonic() - t0
        r.status = "timeout"
        r.detail = f">= {REQUEST_TIMEOUT:.0f}s 未返回(卡死)"
    except urllib.error.HTTPError as exc:
        r.elapsed = time.monotonic() - t0
        r.status = "error"
        r.detail = f"HTTP {exc.code}: {exc.reason}"
    except Exception as exc:  # URLError / socket 等
        r.elapsed = time.monotonic() - t0
        # 读超时在部分平台是 URLError(reason=timeout)
        if isinstance(getattr(exc, "reason", None), socket.timeout):
            r.status = "timeout"
            r.detail = f">= {REQUEST_TIMEOUT:.0f}s 未返回(卡死)"
        else:
            r.status = "error"
            r.detail = f"{type(exc).__name__}: {exc}"
    return r


def probe(sess: Session, days: int) -> ProbeResult:
    """阶段A: 固定 pageSize=10, 变时间跨度。"""
    begin, end = span_times(END_DATE, days)
    r = ProbeResult(days, begin, end, page_size=10)
    return _request(sess, build_form(begin, end, page_size=10), r)


def probe_pagesize(sess: Session, days: int, page_size: int) -> ProbeResult:
    """阶段B: 固定时间跨度, 变 pageSize(单请求全量拉取成本)。"""
    begin, end = span_times(END_DATE, days)
    r = ProbeResult(days, begin, end, page_size=page_size)
    return _request(sess, build_form(begin, end, page_size=page_size), r)


def _human_bytes(n: Optional[int]) -> str:
    if n is None:
        return "-"
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024.0
    return f"{size:.1f}GB"


_TAG = {"ok": "OK", "slow": "慢", "timeout": "卡死", "error": "错误"}


def fmt(r: ProbeResult) -> str:
    el = f"{r.elapsed:6.2f}s" if r.elapsed is not None else "   -  "
    tot = str(r.total) if r.total is not None else "-"
    tag = _TAG.get(r.status, "?")
    line = f"  {r.days:>3}天  {el}  total={tot:<7} [{tag}]  {r.begin} ~ {r.end}"
    if r.detail:
        line += f"\n         └─ {r.detail}"
    return line


def fmt_ps(r: ProbeResult) -> str:
    el = f"{r.elapsed:7.2f}s" if r.elapsed is not None else "    -   "
    rows = str(r.rows_returned) if r.rows_returned is not None else "-"
    tag = _TAG.get(r.status, "?")
    line = (f"  pageSize={r.page_size:<6} {el}  返回={rows:<7} "
            f"体积={_human_bytes(r.nbytes):<9} [{tag}]")
    if r.detail:
        line += f"\n         └─ {r.detail}"
    return line


def run_phase_a(sess: Session) -> int:
    """阶段A: 时间跨度扫描(pageSize=10)。返回安全跨度天数 boundary。"""
    print(f"阶段A · 时间跨度扫描 (pageSize=10, 测日期范围/COUNT 成本)")
    print(f"  梯度(天)={LADDER}")
    print("-" * 72)
    results: List[ProbeResult] = []
    last_good = 0        # 最大"未卡死"天数
    first_bad = None     # 最小"卡死"天数
    for days in sorted(set(LADDER)):
        r = probe(sess, days)
        results.append(r)
        print(fmt(r))
        if r.status == "timeout":
            first_bad = days
            break        # 已经卡死, 更大的跨度只会更慢, 停止放大
        if r.status == "error":
            # 多为未登录/接口异常, 无法据此判定容量, 停止
            print("  ! 出现错误响应, 终止探测(通常是登录失效)。")
            break
        last_good = days

    # ── 二分细化边界: (last_good, first_bad) 之间找最大可用天数 ──
    boundary = last_good
    if first_bad is not None and first_bad - last_good > 1:
        print("-" * 72)
        print(f"  在 {last_good}天(可用) 与 {first_bad}天(卡死) 之间二分细化...")
        lo, hi = last_good, first_bad
        while hi - lo > 1:
            mid = (lo + hi) // 2
            r = probe(sess, mid)
            results.append(r)
            print(fmt(r))
            if r.ok:
                lo = mid
            elif r.status == "timeout":
                hi = mid
            else:
                break    # 错误, 无法继续二分
        boundary = lo

    print("-" * 72)
    if boundary > 0:
        b, e = span_times(END_DATE, boundary)
        note = ""
        gr = next((x for x in results if x.days == boundary), None)
        if gr and gr.status == "slow":
            note = f" (注意: 此跨度已达 {gr.elapsed:.1f}s, 接近超时)"
        print(f"阶段A结论: pageSize=10 时, {REQUEST_TIMEOUT:.0f}s 内最大跨度约 "
              f"{boundary} 天{note}")
        print(f"           示例范围: {b} ~ {e}")
        if first_bad is None:
            print("           (梯度内未出现卡死, 日期范围/COUNT 本身不是瓶颈)")
    else:
        print("阶段A结论: 连最小跨度都失败(多为登录失效/接口异常), 请检查认证。")
    return boundary


def run_phase_b(sess: Session) -> None:
    """阶段B: 固定跨度, pageSize 逐步放大, 测单请求全量拉取的卡死点。"""
    begin, end = span_times(END_DATE, PS_DAYS)
    print()
    print("=" * 72)
    print(f"阶段B · pageSize 扫描 (固定跨度 {PS_DAYS} 天, 测单请求全量拉取成本)")
    print(f"  范围 {begin} ~ {end}   pageSize 梯度={PS_LADDER}")
    print("-" * 72)

    last_ok_ps = 0
    last_ok_rows = 0
    total_rows = None
    for ps in sorted(set(PS_LADDER)):
        r = probe_pagesize(sess, PS_DAYS, ps)
        print(fmt_ps(r))
        if r.total is not None:
            total_rows = r.total
        if r.ok:
            last_ok_ps = ps
            last_ok_rows = r.rows_returned or 0
            # 已经把该跨度全部行一次取回, 再加大 pageSize 没意义
            if r.total is not None and (r.rows_returned or 0) >= r.total:
                print("  · 单请求已取回该跨度全部行, 停止放大 pageSize。")
                break
        elif r.status == "timeout":
            print("  · 该 pageSize 卡死, 停止放大。")
            break
        elif r.status == "error":
            print("  ! 错误响应, 终止阶段B。")
            break

    print("-" * 72)
    if last_ok_ps > 0:
        tot_txt = f"(该 {PS_DAYS} 天共 {total_rows} 行)" if total_rows is not None else ""
        print(f"阶段B结论: 单请求在 {REQUEST_TIMEOUT:.0f}s 内最多稳定取回约 "
              f"{last_ok_rows} 行 (pageSize={last_ok_ps}) {tot_txt}")
        print(f"           => 同步任务建议以每页 {last_ok_ps} 行左右分页拉取, "
              f"必要时再按时间分段。")
    else:
        print("阶段B结论: 大 pageSize 均失败, 建议保持小页(如 200~500)分页拉取。")


def main() -> int:
    print("=" * 72)
    print("巡防 crossDayList 压测")
    print(f"  接口 : {BASE}/dutySchedule/crossDayList")
    print(f"  锚点 : 结束日期={END_DATE}")
    print(f"  阈值 : 硬超时={REQUEST_TIMEOUT:.0f}s  慢查询告警>={SLOW_WARN:.0f}s")
    print("=" * 72)

    sess = Session()
    login(sess)
    print("-" * 72)

    run_phase_a(sess)
    if RUN_PS:
        run_phase_b(sess)
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
