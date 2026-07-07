# 巡防排班（dutySchedule）自定义任务

内网「云浮公安可视化指挥调度平台」(`/zhksh`) 巡防排班数据同步模块。
抓 `dutySchedule/crossDayList`，UPSERT 进 `ywdata.zq_kshddpt_zxzgl`（唯一键 `scheduleId`）。

来源：`/mnt/c/Users/MR/Desktop/local_doc/202607/0701/xunfang/xunfang.har`

## 目录

```
xunfang_dutyschedule/
├── scripts/
│   └── probe_crossday_range.py            # ① 压测脚本(只读、无依赖) —— 定容量用
├── manual/                                 # ② 手动全量回填(内网自己跑)
│   ├── scripts/xunfang_backfill.py         #    2024-12→今天, 断点续跑, upsert
│   └── docs/README_backfill.md
├── auto/                                    # ③ 平台自定义任务(上传后按计划跑)
│   ├── config/manifest.json                #    script_code=xunfang_dutyschedule_sync
│   └── scripts/xunfang_dutyschedule_sync.py#    增量: 重拉近端 [今-3,今+1] 天
├── legacy/                                  # ④ 老版平台任务(保留作对照/回滚)
│   ├── config/manifest.json                #    script_code=data_scraper_multi
│   └── scripts/data_scraper_multi.py        #    scheduleDate + pageSize=99999 旧实现
└── docs/
    └── README.md
```

压测、回填和新平台增量任务共用同一套「**按天开窗 + `pageSize=500` 翻页**」策略
（单窗口≤一天≈1700 行 → 永不卡死），并写同一张表、同一 TEXT 格式
（与 `legacy/data_scraper_multi.py` 兼容）。

## 接口速览（抓包还原）

- **站点**：`http://68.253.2.107/zhksh`（Shiro 会话：`JSESSIONID` + `rememberMe`，RuoYi 风格）
- **登录**：`POST /zhksh/login`
  - 表单：`username`、`password`（**客户端加密后的密文**，16 字节 AES 单块，对固定账号是确定值）、
    `rememberMe=true`、`isPkiLogin=false`、`isAccLogin=true`、`isSmsLogin=false`
  - 因为密文确定，直接复用抓包里的 `username=270378` + 密文即可重新登录，无需明文口令。
- **查询**：`POST /zhksh/dutySchedule/crossDayList`（`application/x-www-form-urlencoded`）
  - 关键时间参数：`params[beginTime]`、`params[endTime]`，格式 `YYYY-MM-DD HH:MM:SS`
  - 其余字段（照抄默认）：`pageSize=10`、`pageNum=1`、`orderByColumn=startTime`、
    `isAsc=asc`、`deptName=全部`，其它筛选项留空。
  - 响应 JSON：`{"total": <总数>, "rows": [...]}`。抓包样例单日 `total=1705`。

## 压测脚本用法

脚本**只读**（只看 `total`/返回行数/耗时/响应体积，不落库、不改数据），仅用 Python 标准库，
必须在**能访问内网 68.253.2.107 的机器**上运行。分两阶段：

- **阶段A — 时间跨度扫描**（`pageSize=10`）：结束日期锚定不动，起始日期按天数梯度前移放大跨度。
  因为服务端 `LIMIT 10`，这一阶段测的是**日期范围/COUNT 本身**的成本。
  实测（2026-07-01）：**到 30 天仍只需 3.0s，无卡死** → 范围/COUNT 不是瓶颈。
- **阶段B — pageSize 扫描**（固定跨度，放大 `pageSize`）：模拟同步任务**一次性全量拉取**，
  测的是**结果集序列化 + 网络传输**成本 —— 这才是真正会卡死的地方。
  每个 `pageSize` 记录返回行数、响应体积、耗时，直到取回全部行或卡死为止。

```bash
# 默认: 结束日期=今天; 阶段A 梯度 1..90 天; 阶段B 在 7 天上放大 pageSize
python3 scripts/probe_crossday_range.py

# 自定义示例
XF_END_DATE=2026-07-01 \
XF_LADDER="7,14,30,60,90,120" \
XF_PS_DAYS=30 \
XF_PS_LADDER="500,1000,2000,5000,10000,40000" \
XF_TIMEOUT=90 \
python3 scripts/probe_crossday_range.py

XF_RUN_PAGESIZE=0 python3 scripts/probe_crossday_range.py   # 只跑阶段A
```

### 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `XF_BASE` | `http://68.253.2.107/zhksh` | 站点根 |
| `XF_USERNAME` | `270378` | 登录账号（抓包值） |
| `XF_PASSWORD_ENC` | 抓包密文 | 客户端加密后的口令密文 |
| `XF_COOKIE` | 空 | 直接贴 `JSESSIONID=..; rememberMe=..` 跳过登录（应急） |
| `XF_END_DATE` | 今天 | 结束日期锚点 `YYYY-MM-DD` |
| `XF_LADDER` | `1,2,3,5,7,10,14,21,30,45,60,90` | 阶段A 天数梯度 |
| `XF_PS_DAYS` | `7` | 阶段B 固定的时间跨度（天） |
| `XF_PS_LADDER` | `10,100,500,1000,2000,5000,10000,20000` | 阶段B 的 pageSize 梯度 |
| `XF_RUN_PAGESIZE` | `1` | 设 `0` 只跑阶段A |
| `XF_TIMEOUT` | `60` | 单请求硬超时（秒），超过视为卡死 |
| `XF_SLOW` | `15` | 慢查询告警阈值（秒） |

### 实测结论（2026-07-01）

**阶段A（pageSize=10，变跨度）—— 日期范围不是瓶颈：**

| 跨度 | 耗时 | total |
|---|---|---|
| 1 天 | 0.80s | 1731 |
| 7 天 | 1.14s | 10118 |
| 30 天 | 3.12s | 37667 |
| 90 天 | 7.38s | 97593 |

90 天也只 7.4s，无卡死。因为服务端 `LIMIT 10`，范围/COUNT 很便宜。

**阶段B（固定 7 天，变 pageSize）—— 真正瓶颈是单请求返回的行数：**

| pageSize | 返回行数 | 耗时 | 体积 | 结果 |
|---|---|---|---|---|
| 100 | 100 | 2.1s | 140KB | OK |
| 500 | 499 | 6.0s | 840KB | OK |
| 1000 | 997 | 11.1s | 1.6MB | OK |
| 2000 | 1988 | 20.9s | 3.5MB | 慢 |
| 5000 | 4967 | 50.6s | 8.7MB | 慢 |
| 10000 | — | 60s | — | **504 网关超时** |

成本约 **10ms/行**（序列化+传输主导），与时间范围几乎无关。页面"卡死"根因是
**一次拉太多行**，撑到 Nginx 60s 网关超时（504）。

**结论 / 拉取参数建议：**

- **安全分页大小 `pageSize=500`**（约 6s，余量足）；`1000` 也可但 11s、余量偏小。
- 用 `params[beginTime]/params[endTime]` 圈定范围后，**按 `pageSize=500` 翻页**拉全量。
- 单请求硬上限在 ~5000 行/50s，务必留足余量，不要贪大页。

> 备注：`legacy/data_scraper_multi.py` 是同一接口、同一目标表的旧版任务，但走的是
> **按 `scheduleDate` 一天一请求 + `pageSize=99999` + 并发** 的路子，写入
> `ywdata.zq_kshddpt_zxzgl`（`unique_key=scheduleId`）。正式任务建议改用
> `beginTime/endTime` 范围 + `pageSize=500` 翻页，语义与并发更可控。

### 认证失效时

若打印「登录疑似失败」或探测出现「错误(非 JSON/未登录)」：

1. 重新抓一次登录包，更新 `XF_PASSWORD_ENC`（密文）；或
2. 从浏览器 DevTools 复制有效 Cookie，用 `XF_COOKIE` 覆盖后再跑。

## 两个正式脚本（已落地）

### ② 手动全量回填 · `manual/scripts/xunfang_backfill.py`

内网自己跑，`2024-12-01 → 今天` 按天开窗回填，`scheduleId` UPSERT，断点续跑。
详见 `manual/docs/README_backfill.md`。核心：

```bash
python3 manual/scripts/xunfang_backfill.py \
  --db-host <IP> --db-port 54321 --db-name yfywk \
  --db-user XXX --db-password XXX --db-schema ywdata \
  --start-date 2024-12-01
# 中断后加 --resume 续跑
```

### ③ 平台增量任务 · `auto/scripts/xunfang_dutyschedule_sync.py`

打包上传到平台按计划执行。入口 `run(context)`，每次**重拉近端窗口**
（默认 `[今天-3, 今天+1]`，`XF_LOOKBACK_DAYS`/`XF_LOOKAHEAD_DAYS` 可调），
按天开窗 + `pageSize=500` 翻页，`scheduleId` UPSERT 刷新新建/改动的排班。
`runtime_config` 键见脚本头注释；DB 回退 `KINGBASE_*` / `MULTI_DB_*`。

> crossDayList 只能按排班时间（`beginTime/endTime`）过滤、无法按 `updateTime` 增量，
> 故增量策略是「重拉最近几天 + 幂等 UPSERT」，而非水位线。

### 与 legacy/data_scraper_multi.py 的关系

`legacy/data_scraper_multi.py` 也抓同一接口写同一张表，但走**按 `scheduleDate` 一天一请求 +
`pageSize=99999`** 的老路。本模块统一改用 `beginTime/endTime` 按天开窗 + `pageSize=500`
翻页，语义/并发/容量更可控，写库格式（camelCase 列、全 TEXT、`ON CONFLICT scheduleId`）
与其保持一致，可安全共写同一张表。
