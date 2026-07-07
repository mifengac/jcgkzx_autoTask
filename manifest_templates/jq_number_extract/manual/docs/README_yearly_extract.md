# 警情文本号码提取 - 内网历史回溯与优化执行指南

本指南用于指导在内网环境下停止卡死的任务、重建优化后的提取目标表、执行年份历史数据同步，以及升级平台脚本。

---

## 1. 停止当前在平台界面显示“运行中”的任务

由于平台目前没有针对自定义脚本的直接强杀/停止按钮，需要手动在数据库中重置任务运行状态，并防止其再次被调度。

### 步骤 A：在平台控制台禁用任务
1. 登录平台控制台前端。
2. 进入 **“任务管理”** -> **“自定义任务”** 列表。
3. 找到原有的号码提取任务，将定时触发状态切换为 **“禁用”**，防止在更新镜像或做历史回溯时调度器在后台二次触发。

### 步骤 B：在数据库中重置状态为“已结束/失败”
登录平台数据库（Kingbase/PostgreSQL），执行以下 SQL 将挂起的任务状态强制重置：

```sql
UPDATE jcgkzx_autotask.task_run 
SET status = 'failed', 
    error_message = 'Cancelled by operator for manual archive maintenance', 
    finished_at = CURRENT_TIMESTAMP 
WHERE status = 'running';
```
*(注：如果您的平台库在默认的 public 模式下，请将 `jcgkzx_autotask.task_run` 改为 `public.task_run`。)*

---

## 2. 内网单独执行“年份历史回溯”脚本

为了在开启实时自动增量任务前，安全、稳定地消化源表积累的 200 多万条历史数据，建议在内网先手动按年份依次执行回溯。

### 脚本位置与原理
* **脚本文件**：`manual/scripts/jq_number_extract_yearly.py`
* **内存安全原理**：该脚本内置了 **Server-side Cursor (服务端流式游标)** 机制，一次仅预取并处理少量数据（由 `--batch-size` 控制，默认 500 条），在处理千万级数据时**内存占用固定在几百KB，绝不 OOM**。

### 内网执行命令模板
在内网服务器的终端中，指定年份及源库、目标库的 DSN 连接串执行脚本：

```bash
# 提取 2024 年的数据
python3 manual/scripts/jq_number_extract_yearly.py \
  --year 2024 \
  --src-url "host=127.0.0.1 port=54321 dbname=ywdata user=postgres password=xxxx" \
  --dst-url "host=127.0.0.1 port=54321 dbname=jcgkzx_monitor user=postgres password=xxxx" \
  --src-schema "ywdata" \
  --dst-schema "jcgkzx_monitor" \
  --batch-size 1000

# 提取 2025 年的数据
python3 manual/scripts/jq_number_extract_yearly.py \
  --year 2025 \
  --src-url "host=127.0.0.1 port=54321 dbname=ywdata user=postgres password=xxxx" \
  --dst-url "host=127.0.0.1 port=54321 dbname=jcgkzx_monitor user=postgres password=xxxx" \
  --src-schema "ywdata" \
  --dst-schema "jcgkzx_monitor" \
  --batch-size 1000
```

---

## 3. 目标表新增字段与 DDL 重建

根据业务需求，提取结果表除了记录提取出的电话/身份证等号码外，还需要冗余记录警情原始的基本情况。

### 结构迁移 SQL 文件
* **SQL 文件路径**：`migrations/0623_update_zq_jingqing_number_extract.sql`
* **新增字段包含**：原始报警时间 `calltime`、地区编码与名称 `cmdid/cmdname`、原始内容及处警结果 `casecontents/replies`、管辖单位 `dutydeptname` 等。
* **索引加速（防止卡死的核心）**：
  * 对 `source_updatetime`（源数据更新时间）创建了索引，确保平台后续做实时增量同步查询时不会发生全表扫描。
  * 对唯一联合索引 `(caseno, extract_field, number_type, number_value)` 进行了定义，支持高并发下的 `ON CONFLICT UPSERT` 去重插入。

### 执行方式
在内网数据库中，使用管理员账号执行该 SQL 脚本进行建表与索引初始化：

```bash
# 示例：通过 psql 或 Kingbase ksql 导入 SQL
psql -h 127.0.0.1 -p 54321 -U postgres -d platformdb -f migrations/0623_update_zq_jingqing_number_extract.sql
```

---

## 4. 平台自动任务脚本同步升级

在手动回溯完成历史年份数据，并重新在平台控制台开启定时自定义任务后，平台执行器将调用升级后的版本。

* **升级脚本路径**：`auto/scripts/jq_number_extract.py`
* **变更点**：
  * `_fetch_src` 增量数据拉取语句已扩充字段，保持和扩展后的 DDL 一致。
  * `_build_rows` 写入元组重构，完美对齐新目标表的列顺序。
  * `_upsert` 写入 SQL 在 `INSERT` 以及 `DO UPDATE SET` 阶段全面兼容新增的所有字段。
* **部署建议**：
  * 请在回溯完成后，构建并发布新版本的 Docker 镜像，在内网平台中重新使能该任务。后续平台将能够以 10 分钟为滑动水位线进行实时增量提取。
