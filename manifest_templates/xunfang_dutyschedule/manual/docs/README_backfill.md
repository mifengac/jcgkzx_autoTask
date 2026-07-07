# 巡防排班全量回填（手动一次性）

`xunfang_backfill.py`：在**内网**把 `dutySchedule/crossDayList` 的排班数据从起始日期
（默认 `2024-12-01`）回填到今天，UPSERT 进 `ywdata.zq_kshddpt_zxzgl`
（唯一键 `scheduleId`，与 `legacy/data_scraper_multi.py` 写同一张表、同一 TEXT 格式）。

## 原理

压测（见 `../../docs/README.md`）证明接口卡死的根因是**单请求返回行数太多**（≈10ms/行，
5000 行 50s，1 万行直接 504），而**时间范围本身很便宜**。所以脚本：

- **一天一个窗口**（`params[beginTime]=当天 00:00:00`，`params[endTime]=当天 23:59:59`，
  单日约 1700 行），每窗口 `pageSize=500` 翻页（每页约 6s、offset 浅）→ **永不超过一天、不卡死**；
- **多天并发**拉取（默认 8 并发）缩短总时长；**DB 写入串行在主线程**；
- **按天断点续跑**：进度写 `xunfang_backfill_progress.json`，`--resume` 跳过已完成的天；
- `scheduleId` 去重 UPSERT，重复/重叠（跨天班）安全幂等。

回填天数：`2024-12-01 → 今天` 约 578 天；默认参数下大致 20~40 分钟量级（取决于网络与并发）。

## 依赖

```bash
pip install requests psycopg2-binary
```

## 运行

```bash
python3 xunfang_backfill.py \
  --db-host <内网库IP> --db-port 54321 --db-name yfywk \
  --db-user <用户> --db-password <口令> --db-schema ywdata \
  --start-date 2024-12-01
```

中断后**原样重跑并加 `--resume`**即可续跑（不会重复写、自动跳过已完成的天）：

```bash
python3 xunfang_backfill.py [同样参数] --resume
```

先验证不写库（干跑，只拉取计数）：

```bash
python3 xunfang_backfill.py --dry-run --start-date 2026-06-25
```

只拉取落成 JSONL、暂不入库（之后可另行导入）：

```bash
python3 xunfang_backfill.py --no-db --dump-jsonl ./xunfang_dump.jsonl --start-date 2024-12-01
```

## 常用参数

| 参数 / 环境变量 | 默认 | 说明 |
|---|---|---|
| `--base` / `XF_BASE` | `http://68.253.2.107/zhksh` | 站点根 |
| `--username` / `XF_USERNAME` | `270378` | 登录账号 |
| `--password-enc` / `XF_PASSWORD_ENC` | 抓包密文 | 客户端加密后的口令密文 |
| `--cookie` / `XF_COOKIE` | 空 | 直接贴 Cookie 跳过登录（应急） |
| `--start-date` / `XF_START_DATE` | `2024-12-01` | 起始日期（含） |
| `--end-date` / `XF_END_DATE` | 今天 | 结束日期（含） |
| `--page-size` / `XF_PAGE_SIZE` | `500` | 每页行数（压测建议 ≤500） |
| `--concurrency` / `XF_CONCURRENCY` | `8` | 并发天窗口数 |
| `--db-host/port/name/user/password` | 环境变量回退 | 回退 `KINGBASE_*` / `MULTI_DB_*` |
| `--db-schema` / `XF_DB_SCHEMA` | `ywdata` | 目标 schema |
| `--table-name` / `XF_TABLE` | `zq_kshddpt_zxzgl` | 目标表 |
| `--resume` | 关 | 断点续跑 |
| `--dry-run` | 关 | 只拉取不写库/不落文件 |
| `--no-db` | 关 | 不写库（配合 `--dump-jsonl`） |

## 认证失效

若报“登录疑似失败”或抓取报“非 JSON（疑似掉登录）”：更新 `--password-enc`（重新抓一次登录包的密文），
或从浏览器复制有效 Cookie 用 `--cookie` 覆盖。
