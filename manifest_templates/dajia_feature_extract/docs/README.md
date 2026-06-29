# 打架斗殴语义特征提取（dajia_feature_extract）

从警情表抽取"打架斗殴"警情，清洗处警情况，用锐智大模型提取结构化特征，落到
`jcgkzx_monitor.zq_dajia_feature_extract`，用于打架斗殴规律分析与警情压降。

## 数据流

```
ywdata.zq_kshddpt_dsjfx_jq           源表（打架斗殴：原始性质 或 确认性质）
   │  水位线增量（MAX(source_updatetime) - lookback buffer）
   ▼
clean_replies（vendored）             清洗 replies → cjqk_cleaned + 质量标记
   │  只取 data_quality_flag == 有效案情
   ▼
锐智 ayenaspring-pro-001（并发抽取）   处警情况 + 警情地址 → 特征 JSON
   │
   ▼
jcgkzx_monitor.zq_dajia_feature_extract   一条警情一行（caseno 唯一，UPSERT）
```

## 口径

- **打架斗殴过滤**（口径来自配置表，非名称硬匹配）：取 `jcgkzx_monitor.case_type_config`
  中 `leixing='打架斗殴'` 的 `newcharasubclass_list`（叶子代码数组），再用源表**代码列**
  `neworicharasubclass`（原始）或 `newcharasubclass`（确认）`= ANY(代码集)` 命中其一即纳入。
  类别名用 `DJ_CASE_TYPE` 改、配置表 schema 用 `DJ_CONFIG_SCHEMA` 改（默认 `jcgkzx_monitor`）。
- **特征来源**：除 `地点(警情地址)/地点分类(警情地址)` 取自 `occuraddress` 外，
  其余特征均从清洗后的 `处警情况` 提取。
- **只对"有效案情"调模型**：低质量/无效/外市转办/无有效信息 的警情仍入库（保留基础+
  清洗字段），`extract_status='skipped'`，不浪费模型算力。
- **时段维度**（incident_hour/time_period/weekday/is_weekend）由 `calltime` 在代码内推导，
  不调用模型。

## 特征字段

必需（用户指定）：是否持械、持械类型、是否饮酒、打架原因、打架原因分类、是否多人、
地点(警情地址)、地点分类(警情地址)、地点(处警情况)、地点分类(处警情况)。

补充（服务规律分析/压降）：是否受伤、伤情、当事人关系、矛盾性质（临时起意/长期积怨——
判断能否靠调解前置预防）、涉及人数、是否涉及未成年人、处置结果分类。

枚举见建表 SQL 注释与脚本 `*_ENUM` 常量。

## 环境变量

| 变量 | 说明 | 默认 |
|---|---|---|
| `RUIZHI_API_KEY` | 锐智 APIKEY（必填，不硬编码） | — |
| `DJ_*` / 回退 `NE_*` / `ZQ_*` / `KINGBASE_*` | 源/目标库连接 | 复用号码提取任务同一套库 |
| `DJ_SRC_SCHEMA` | 源 schema | `ywdata` |
| `DJ_DST_SCHEMA` | 目标 schema | `jcgkzx_monitor` |
| `DJ_LOOKBACK_MIN` | 水位线回溯 buffer（分钟） | `10` |
| `DJ_CONCURRENCY` | 锐智并发（共享 key，建议 3，429 时自行降级） | `3` |
| `DJ_RETRIES` | 单条重试次数 | `2` |
| `DJ_MAX_TOKENS` | 单条最大输出 token | `700` |
| `DJ_CASE_TYPE` | `case_type_config.leixing` 值 | `打架斗殴` |
| `DJ_CONFIG_SCHEMA` | `case_type_config` 所在 schema | `jcgkzx_monitor` |

DB 连接既可用 `DJ_DB_URL`（postgresql URL），也可用 `DJ_*_HOST/PORT/DB/USER/PASSWORD`
拆字段；二者皆可回退到号码提取任务用的 `NE_*`/`ZQ_*`/`KINGBASE_*`，免重复配置。

## 建表

先在内网执行 `migrations/0629_create_zq_dajia_feature_extract.sql` 建目标表。

## 入口

平台调 `dajia_feature_extract.py` 的 `run(context)`，可经 `context["runtime_config"]`
覆盖上述变量（key 为小写，如 `dj_concurrency`、`ruizhi_api_key`）。
本地直跑：配好环境变量后 `python dajia_feature_extract.py`。

## 历史回填（一次性补数）

实时任务用 `MAX(source_updatetime)` 水位线，空表只回溯 3 天，**刷不到历史**。补历史用
同目录的 `dajia_feature_extract_backfill.py`（内网手动执行，与实时任务共用清洗/Prompt/
枚举/落库逻辑，打标一致）：

- 显式 `--begin/--end` 按 `calltime` 划区间；服务端游标流式读，内存恒定。
- **断点续跑 + 分批落库**：每 `--batch-size` 条警情抽取并 UPSERT 一次；`--resume`（默认开）
  跳过目标表已 `extract_status='ok'` 的 caseno，崩溃/重跑只补未完成项，不重烧共享 key 配额。

建议**分段灰度**（分段=天然 checkpoint）：

```bash
# 同库 yfywk，源 ywdata / 目标 jcgkzx_monitor，只需一个库 URL
export DJ_DB_URL="postgresql://ywkuser:<密码>@<内网IP>:54321/yfywk"
export RUIZHI_API_KEY="sk-...."

# 先小范围验证打标质量（一个月），人工抽查若干 raw_answer
python3 dajia_feature_extract_backfill.py --begin 2025-01-01 --end 2025-02-01 \
  --concurrency 3 --batch-size 200
# 质量 OK 后按季度推进，最后一段 --begin 2026-04-01 --end 2026-06-28
```

> 校验：2025-01 起原始打架斗殴省厅口径 1651 条；本任务计原始+确认两口径、且含全部质量
> 标记的警情，总行数高于 1651 属正常。

## 打包上传到平台

### 1. 打包（manifest.json 必须在 zip 包根）

平台只认 **包根目录下的 `manifest.json`**，入口脚本与它同级。仓库里 `config/` + `scripts/`
是源结构，上传前要拍平。用随附脚本一键打包（回填脚本不进平台包）：

```bash
python3 manifest_templates/dajia_feature_extract/build_zip.py v1.0.0
# 产物 dajia_feature_extract_v1.0.0.zip：根目录含 manifest.json + dajia_feature_extract.py
```

### 2. 上传（前端：自定义任务页右上角「＋ 上传脚本」）

> ⚠️ 该按钮自 commit `0be7d24`（2026-06-24）才加入。若界面看不到，是**运行的镜像比这个
> 提交旧** —— 重新构建镜像并重新部署，再 **Ctrl+Shift+R 强刷**浏览器（JS 用固定缓存键
> `?v=…`，不强刷会用旧缓存）。

「自定义任务」页那排 `全部/启用中/已停用` 是**状态筛选**，不是功能标签；上传入口是右上角
**「＋ 上传脚本」按钮**（不在「＋ 新增任务」表单里）。点开填：

| 字段 | 值 |
|---|---|
| 脚本名称 | `打架斗殴语义特征提取` |
| 脚本编码 | `dajia_feature_extract`（须与 manifest 一致） |
| 版本号 | `v1.0.0` |
| 入口文件 / 入口函数 | **留空**（manifest.json 已带，自动读） |
| ZIP 包 | `dajia_feature_extract_v1.0.0.zip` |

### 3. 建任务（「＋ 新增任务」）

选刚上传的脚本 + 版本，配置：

- **运行配置 JSON（runtime_config）**：库连接会自动回退到平台 `DATABASE_URL`（已是 yfywk），
  唯一缺的是锐智 key。推荐把 `RUIZHI_API_KEY` 放容器 `.env`（避免明文入库），runtime_config
  仅放调优项：

  ```json
  { "dj_concurrency": 3, "dj_lookback_min": 10 }
  ```

  若不便改 `.env`，则退而求其次（注意明文存进平台库）：`{ "ruizhi_api_key": "sk-…", "dj_concurrency": 3 }`
- **调度**：建议 **每 1 小时**（`interval_value=1`,`interval_unit=hour`）。完整性由水位线保证，
  与频率无关；打架特征依赖 `处警情况`(replies) 回填、天然滞后数小时，跑太密只会对未就绪
  警情做无效抽取、空烧共享 key。想更实时可设 30 分钟，不建议 <15 分钟。
  - replies 补全后若 `updatetime` 前移，下轮会被重新捞起、抽取成功并 UPSERT 覆盖，滞后能自动追上。
