# zq_full_resync.py 使用说明

`dist_scripts/zq_full_resync.py` 是一次性全量重同步脚本，用来把 `dsjfx` 系统的 `/case/list` 历史警情数据全量灌进 Kingbase 表 `ywdata.zq_kshddpt_dsjfx_jq`。

适用场景：

- 生产已有 70+ 万条历史数据，需要清空重灌
- 老的平台调度脚本（`examples/zq_kshddpt_dsjfx_jq.py`）只能按近 N 天滚动同步，跑不动历史回填
- 需要断点续跑、批量写入、可观察进度

---

## 1. 脚本设计概要

| 模块 | 说明 |
|---|---|
| 登录 | POST `http://68.253.2.111/dsjfx/login`，cookie/token 自动维持在 session 里 |
| 拉数 | POST `http://68.253.2.111/dsjfx/case/list`，参数完全沿用 `examples/zq_kshddpt_dsjfx_jq.py` 默认值 |
| 时间切片 | 在 `[--start-date, --end-date]` 范围内按自然月切片，单个月窗内翻页 |
| 翻页 | `pageSize=2000`（可配），翻到 `rows<pageSize` 或累计 `>=total` 即下一窗 |
| 重试 | HTTP 失败指数退避，最多 5 次 |
| 写库 | `psycopg2 execute_values` 批量 upsert，`ON CONFLICT (caseno) DO UPDATE` |
| 建表 | 沿用 `examples/zq_kshddpt_dsjfx_jq.py` 行为：第一条数据决定 schema，后续数据若多出列自动 `ALTER TABLE ADD COLUMN IF NOT EXISTS` |
| 进度 | 每个月窗完成或失败前都会写 `zq_full_resync_progress.json`，`--resume` 自动跳过已完成的窗口 |
| TRUNCATE | 必须 `--truncate --confirm-truncate` 一起使用，防止误删 |

---

## 2. 依赖

生产 Python 环境只需要两个第三方包，不依赖项目其它代码：

```bash
pip install requests psycopg2-binary
```

Python 3.8+ 即可。

---

## 3. 推荐的「影子表 + 切换」流程（强烈建议）

不直接清空生产正在用的老表，而是先灌一张影子表，比对无误后再 RENAME 切换。这样：

- 灌数期间老表不受影响，平台调度任务继续可用
- 切换是秒级的 `ALTER TABLE RENAME`，几乎零中断
- 出问题随时回滚到老表

### 3.1 灌新表

```bash
python3 zq_full_resync.py \
  --username XXX --password XXX \
  --db-host 10.x.x.x --db-port 54321 --db-name yfgxpt \
  --db-user XXX --db-password XXX --db-schema ywdata \
  --table-name zq_kshddpt_dsjfx_jq_new \
  --progress-file zq_full_resync_progress_new.json \
  --log-file zq_full_resync_new.log \
  --start-date 2020-01-01 --end-date 2026-06-17
```

要点：

- `--table-name zq_kshddpt_dsjfx_jq_new`：写到新表
- **不要加** `--truncate`：新表是 `CREATE TABLE IF NOT EXISTS` 自动建的
- `--progress-file` / `--log-file` 单独命名，避免和老的混
- `--start-date` 要覆盖到生产历史最早一天

中途挂掉续跑：

```bash
python3 zq_full_resync.py [上面那一堆参数] --resume
```

### 3.2 核对数据

```sql
-- 老表 vs 新表行数
SELECT count(*) FROM ywdata.zq_kshddpt_dsjfx_jq;
SELECT count(*) FROM ywdata.zq_kshddpt_dsjfx_jq_new;

-- 新表时间范围
SELECT min(calltime), max(calltime), count(*) FROM ywdata.zq_kshddpt_dsjfx_jq_new;

-- 抽样
SELECT * FROM ywdata.zq_kshddpt_dsjfx_jq_new ORDER BY id DESC LIMIT 5;

-- 字段是否齐
SELECT column_name FROM information_schema.columns
WHERE table_schema='ywdata' AND table_name='zq_kshddpt_dsjfx_jq_new'
ORDER BY ordinal_position;
```

### 3.3 切换前停调度

切换瞬间如果老的同步任务正好触发会写到老表（已被改名）。建议先在前端把对应 `AlertTask` 设置 `enabled=false`，切换完再启用。

### 3.4 一键 RENAME 切换（事务内完成）

```sql
BEGIN;

-- 老表改备份名
ALTER TABLE ywdata.zq_kshddpt_dsjfx_jq
  RENAME TO zq_kshddpt_dsjfx_jq_bak_20260617;

-- 老表的普通索引跟着改名（caseno UNIQUE 是表级约束，会自动跟着表走）
ALTER INDEX ywdata.idx_zq_kshddpt_dsjfx_jq_caseno
  RENAME TO idx_zq_kshddpt_dsjfx_jq_bak_20260617_caseno;
ALTER INDEX ywdata.idx_zq_kshddpt_dsjfx_jq_created_at
  RENAME TO idx_zq_kshddpt_dsjfx_jq_bak_20260617_created_at;

-- 新表升级为正式表
ALTER TABLE ywdata.zq_kshddpt_dsjfx_jq_new
  RENAME TO zq_kshddpt_dsjfx_jq;

-- 新表索引改成生产标准名
ALTER INDEX ywdata.idx_zq_kshddpt_dsjfx_jq_new_caseno
  RENAME TO idx_zq_kshddpt_dsjfx_jq_caseno;
ALTER INDEX ywdata.idx_zq_kshddpt_dsjfx_jq_new_created_at
  RENAME TO idx_zq_kshddpt_dsjfx_jq_created_at;

COMMIT;
```

### 3.5 观察 1~2 天后清理备份

```sql
DROP TABLE ywdata.zq_kshddpt_dsjfx_jq_bak_20260617;
```

---

## 4. 直接清空原表方式（不推荐，但可用）

如果你确认可以接受灌数过程中老表为空：

```bash
python3 zq_full_resync.py \
  --username XXX --password XXX \
  --db-host 10.x.x.x --db-port 54321 --db-name yfgxpt \
  --db-user XXX --db-password XXX --db-schema ywdata \
  --start-date 2020-01-01 --end-date 2026-06-17 \
  --truncate --confirm-truncate
```

风险：

- 灌完之前老表是空的，依赖这张表的查询/告警全部异常
- 跑到一半挂掉时表里只有一部分数据
- 平台调度任务期间可能并发写入，干扰进度

---

## 5. dry-run 验证

正式跑前可以先用 `--dry-run` 跑一个小窗口，确认能登录、能拉数、字段结构符合预期，但不会建表也不会写库：

```bash
python3 zq_full_resync.py \
  --username XXX --password XXX \
  --db-host 10.x.x.x --db-port 54321 --db-name yfgxpt \
  --db-user XXX --db-password XXX --db-schema ywdata \
  --table-name zq_kshddpt_dsjfx_jq_new \
  --start-date 2026-06-01 --end-date 2026-06-17 \
  --dry-run
```

---

## 6. 完整命令行参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--login-url` | `http://68.253.2.111/dsjfx/login` | 登录接口 |
| `--api-url` | `http://68.253.2.111/dsjfx/case/list` | 拉数接口 |
| `--username` / `--password` | 必填 | 数据源账号 |
| `--db-host` / `--db-name` / `--db-user` / `--db-password` | 必填 | Kingbase 连接 |
| `--db-port` | `54321` | 默认 Kingbase 端口 |
| `--db-schema` | `ywdata` | 目标 schema |
| `--table-name` | `zq_kshddpt_dsjfx_jq` | **影子表关键参数**，传不同表名即可写到影子表 |
| `--start-date` | 首次必填 | 起点日期 `YYYY-MM-DD`（含） |
| `--end-date` | 今天 | 终点日期 `YYYY-MM-DD`（含） |
| `--page-size` | `2000` | 单页大小 |
| `--max-pages-per-window` | `10000` | 单月窗最大页数（防死循环） |
| `--sleep-between-pages` | `0.0` | 翻页之间 sleep 秒数，源端压力大时可设 `0.5~1` |
| `--truncate` | off | 开始前清空表（重置 id 序列） |
| `--confirm-truncate` | off | `--truncate` 必须配合此开关才生效 |
| `--resume` | off | 从进度文件续跑，不会再 truncate |
| `--progress-file` | `zq_full_resync_progress.json` | 进度文件路径 |
| `--log-file` | `zq_full_resync.log` | 日志文件路径 |
| `--dry-run` | off | 只拉数不写库不 truncate |

也支持环境变量（命令行参数优先）：

```
ZQ_LOGIN_URL ZQ_API_URL ZQ_LOGIN_USERNAME ZQ_LOGIN_PASSWORD
ZQ_DB_HOST ZQ_DB_PORT ZQ_DB_NAME ZQ_DB_USER ZQ_DB_PASSWORD ZQ_DB_SCHEMA
```

---

## 7. 进度文件结构

`zq_full_resync_progress.json` 内容示例：

```json
{
  "started_at": "2026-06-17T10:00:00",
  "completed_windows": [
    "2024-01-01_2024-01-31",
    "2024-02-01_2024-02-29"
  ],
  "last_window": "2024-03-01_2024-03-31",
  "total_fetched": 53217,
  "total_written": 53217,
  "updated_at": "2026-06-17T10:42:11"
}
```

- `completed_windows` 列表里的窗口下次 `--resume` 时会被跳过
- 如果中途想从某个月强制重跑：把那个 key 从 `completed_windows` 里删掉再加 `--resume`
- 如果 `--truncate` 启用，进度会被自动重置

---

## 8. 常见问题

### Q1：跑到一半挂了怎么办？

直接加 `--resume` 重新执行，**不要再加 `--truncate`**（否则会重置进度并清表）。

### Q2：源端 caseNo 大小写问题

脚本统一把字段名 lowercase 写库，`caseno` 唯一约束就建在小写列上，与 `examples/zq_kshddpt_dsjfx_jq.py` 行为一致。

### Q3：单个月数据特别多怎么办？

- 默认 `pageSize=2000`，单月最多 `max-pages-per-window=10000` 页 = 2000 万行上限，正常生产远到不了
- 如果源端单页 2000 太重，可改 `--page-size 1000`
- 如果连续翻页源端报错，加 `--sleep-between-pages 1`

### Q4：影子表跑完之后还要不要清进度文件？

不用清，进度文件就放着。下次再做全量回填可以直接换一个 `--progress-file` 和 `--table-name` 跑新一轮，互不影响。

### Q5：能不能跑到一半切换跑别的时间段？

不建议。脚本设计是单一连续区间逐月推进。要跑另一个区间请：

1. 换一个 `--progress-file`
2. 换一个 `--table-name`
3. 重新指定 `--start-date` / `--end-date`

### Q6：能不能不用 TRUNCATE 也不用影子表，直接「续传缺失的数据」？

可以。脚本本身就是 upsert，只要老表 `caseno` 已经是 UNIQUE 索引，重复跑也只会更新不会插入重复。具体做法：

```bash
python3 zq_full_resync.py \
  [DB 参数] \
  --start-date 2020-01-01 --end-date 2026-06-17
  # 不加 --truncate、不加 --resume，使用默认表名
```

但前提是老表结构能容纳所有字段。如果字段缺失脚本会自动 `ALTER TABLE` 补列。

---

## 9. 文件清单

- `zq_full_resync.py` —— 同步脚本
- `README_zq_full_resync.md` —— 本说明
- 运行后会生成：
  - `zq_full_resync.log` —— 日志（默认名，可改）
  - `zq_full_resync_progress.json` —— 进度文件（默认名，可改）

---

## 10. 与平台原有同步脚本的关系

- 本脚本**完全独立**，不修改 `autotask_api/` 任何代码
- 平台原有的 `examples/zq_kshddpt_dsjfx_jq.py` 继续按分钟级滚动同步「最近几天」的数据，写同一张表
- 历史回填只跑这个一次性脚本，跑完后该脚本就不再使用
- 表结构两边一致，新表通过 RENAME 切换后老的调度脚本继续工作不受影响

---

## 11. 去重键从 `caseno` 改为 `caseno + updatetime` 的迁移

老脚本 `examples/zq_kshddpt_dsjfx_jq.py` 和新脚本 `zq_full_resync.py` 的去重键都已改为 `caseno + updatetime` 复合键，允许同一案件多次更新各留一条。表结构必须配套迁移。

### 11.1 影子表已用旧版脚本灌过数据 —— 必须先迁移结构再 `--resume`

**这是当前生产面临的实际情况。** 之前用旧版 `zq_full_resync.py`（`caseno UNIQUE`）灌了 `2020-01-01 ~ 2026-06-17` 的数据到影子表 `zq_kshddpt_dsjfx_jq_new`。现在脚本已改为 `ON CONFLICT (caseno, updatetime)`，但影子表结构还是老的 `caseno UNIQUE`，直接 `--resume` 补 `06-17 ~ 06-20` 的数据会报错。

迁移 SQL（在影子表上执行）：

```sql
-- 1) 查出影子表 caseno 上的 UNIQUE 约束名
SELECT con.conname
FROM pg_constraint con
JOIN pg_class rel ON rel.oid = con.conrelid
JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
WHERE nsp.nspname = 'ywdata'
  AND rel.relname = 'zq_kshddpt_dsjfx_jq_new'
  AND con.contype = 'u';

-- 2) 删掉 caseno 上的 UNIQUE 约束（名字按上面查询结果替换，通常是 zq_kshddpt_dsjfx_jq_new_caseno_key）
ALTER TABLE ywdata.zq_kshddpt_dsjfx_jq_new
  DROP CONSTRAINT zq_kshddpt_dsjfx_jq_new_caseno_key;

-- 3) 加复合唯一索引
CREATE UNIQUE INDEX IF NOT EXISTS uq_zq_kshddpt_dsjfx_jq_new_caseno_updatetime
  ON ywdata.zq_kshddpt_dsjfx_jq_new(caseno, updatetime);
```

执行完之后，影子表结构就和改造后的新脚本、老脚本完全对齐了，可以安全 `--resume`。

> 注：影子表里已有的数据不受影响。因为之前是 `caseno UNIQUE`，每个 caseno 只有一行，所以 `(caseno, updatetime)` 自然也不会重复，加复合唯一索引不会失败。

### 11.2 从未灌过影子表 —— 直接用新脚本即可

如果影子表还没创建，新脚本 `zq_full_resync.py` 的 `ensure_table` 会自动建表，建表语句里已经是 `caseno TEXT NOT NULL`（无 UNIQUE）+ 复合唯一索引 `uq_{table}_caseno_updatetime`，**不需要任何手动迁移**。

### 11.3 老生产表（非影子表）的迁移

如果将来需要对老生产表 `zq_kshddpt_dsjfx_jq` 本身改去重键（不走影子表方案），执行：

```sql
-- 查约束名
SELECT con.conname
FROM pg_constraint con
JOIN pg_class rel ON rel.oid = con.conrelid
JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
WHERE nsp.nspname = 'ywdata'
  AND rel.relname = 'zq_kshddpt_dsjfx_jq'
  AND con.contype = 'u';

-- 删约束（名字按实际查询结果替换）
ALTER TABLE ywdata.zq_kshddpt_dsjfx_jq
  DROP CONSTRAINT zq_kshddpt_dsjfx_jq_caseno_key;

-- 加复合唯一索引
CREATE UNIQUE INDEX IF NOT EXISTS uq_zq_kshddpt_dsjfx_jq_caseno_updatetime
  ON ywdata.zq_kshddpt_dsjfx_jq(caseno, updatetime);
```

### 11.4 生产完整切换步骤（影子表方案）

当前生产的实际情况：影子表已灌 `2020-01-01 ~ 2026-06-17`，需补齐到 `2026-06-20` 再切换。

```
步骤 1：迁移影子表结构（§11.1 的 SQL）
步骤 2：--resume 补齐 06-17 ~ 06-20 的数据
步骤 3：停老 AlertTask（前端 enabled=false）
步骤 4：核对影子表数据
步骤 5：RENAME 切换（老表→bak，new→正式表）
步骤 6：上传改造后的老脚本 ZIP，AlertTask 切新版本 + enabled=true
步骤 7：观察 1~2 天
步骤 8：DROP bak 表
```

具体命令：

```bash
# 步骤 2：补齐最新数据（--resume 会跳过已完成的月份，只跑 06-17 ~ 06-20）
python3 zq_full_resync.py \
  --username XXX --password XXX \
  --db-host 10.x.x.x --db-port 54321 --db-name yfgxpt \
  --db-user XXX --db-password XXX --db-schema ywdata \
  --table-name zq_kshddpt_dsjfx_jq_new \
  --progress-file zq_full_resync_progress_new.json \
  --log-file zq_full_resync_new.log \
  --start-date 2020-01-01 --end-date 2026-06-20 \
  --resume
```

步骤 5 的 RENAME SQL（事务内完成）：

```sql
BEGIN;
ALTER TABLE ywdata.zq_kshddpt_dsjfx_jq RENAME TO zq_kshddpt_dsjfx_jq_bak_20260620;
ALTER INDEX ywdata.idx_zq_kshddpt_dsjfx_jq_caseno RENAME TO idx_zq_kshddpt_dsjfx_jq_bak_20260620_caseno;
ALTER INDEX ywdata.idx_zq_kshddpt_dsjfx_jq_created_at RENAME TO idx_zq_kshddpt_dsjfx_jq_bak_20260620_created_at;
ALTER TABLE ywdata.zq_kshddpt_dsjfx_jq_new RENAME TO zq_kshddpt_dsjfx_jq;
ALTER INDEX ywdata.idx_zq_kshddpt_dsjfx_jq_new_caseno RENAME TO idx_zq_kshddpt_dsjfx_jq_caseno;
ALTER INDEX ywdata.idx_zq_kshddpt_dsjfx_jq_new_created_at RENAME TO idx_zq_kshddpt_dsjfx_jq_created_at;
ALTER INDEX ywdata.uq_zq_kshddpt_dsjfx_jq_new_caseno_updatetime RENAME TO uq_zq_kshddpt_dsjfx_jq_caseno_updatetime;
COMMIT;
```

步骤 8（观察 1~2 天后）：

```sql
DROP TABLE ywdata.zq_kshddpt_dsjfx_jq_bak_20260620;
```

---

## 12. 老脚本改造记录

`examples/zq_kshddpt_dsjfx_jq.py` 已完成以下改造，打包为 `dist_scripts/zq_kshddpt_dsjfx_jq_v2.zip`：

### 12.1 HTTP 重试（已实现）

新增 `_request` 方法，5 次指数退避重试。`login` 和 `fetch_data` 都改用它，网络抖动不再丢数据。

### 12.2 批量写库（已实现）

`save_data` 从逐条 `SELECT+INSERT/UPDATE` 改为 `psycopg2.extras.execute_values` 批量 upsert，500 条/批，`ON CONFLICT (caseno, updatetime) DO UPDATE`。

### 12.3 分页拉数（已实现）

`fetch_data` 从 `pageSize=99999` 一次拉完改为 `pageSize=2000` 循环翻页，到 `rows<pageSize` 或达 `total` 停止。默认 `ZQ_PAGE_SIZE` 也从 `99999` 改为 `2000`。

### 12.4 错误处理（已实现）

`fetch_data` 失败从 `return []` 改为 `raise RuntimeError`，不再吞异常。`run()` 层面的 `login` 失败也已改为 `raise RuntimeError`。

### 12.5 去重键改为 `caseno + updatetime`（已实现）

建表 `caseno` 由 `TEXT UNIQUE NOT NULL` 改为 `TEXT NOT NULL`，新增复合唯一索引 `(caseno, updatetime)`。`save_data` 的 `ON CONFLICT` 改为 `(caseno, updatetime)`。

### 12.6 保留不变的平台契约

- `run(context) -> list[dict]` 返回值结构
- `_temporary_runtime_env` 配置注入机制
- 固定表名 `zq_kshddpt_dsjfx_jq`
- `login` 返回 bool（`run()` 层已用 `raise RuntimeError` 兜底）
