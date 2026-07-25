# JCGKZX AutoTask

`JCGKZX AutoTask` 是一个面向内部监测和通知场景的任务平台，当前同时支持两种模式：

- 主题监测：一个数据源抓取一次，多主题复用同一批数据，再按主题过滤、接收规则和短信模板分发。
- 自定义脚本任务：继续沿用脚本 ZIP 上传、`run(context)` 执行、模板渲染和接收规则匹配的旧模式。

前端是静态控制台，后端是 FastAPI。容器化后可作为单服务部署，运行时依赖外部 Kingbase 与内网短信网关 `oracle-sms-gateway`（默认宿主端口 5011）。

## 核心能力

- 管理数据源、主题、主题接收规则和运行记录
- 管理脚本 ZIP、脚本版本、自定义任务、短信模板和接收规则
- 按分钟 / 小时统一调度
- 基于联系人主数据做手机号匹配
- 通过内网 `oracle-sms-gateway` HTTP 接口发送短信（不再直连 Oracle 短信队列表）
- 保留运行结果、命中规则、短信发送日志，便于排障和审计

## 当前目录

```text
jcgkzx_autoTask/
├── autotask_api/          # FastAPI 后端、调度器、执行器、适配器
├── frontend/              # 静态前端控制台
├── instantclient_11_2/    # Oracle Instant Client 11g
├── manifest_templates/    # 脚本上传示例清单
├── tests/                 # Python 单元测试
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── DEPLOY.md
└── README.md
```

## 架构概览

### 数据源监测链路

1. `ThemeSource`（数据源）定义抓数来源和调度频率。
2. 适配器根据 `source_type` 抓取原始数据，目前已实现 `dsjfx_case_list`。
3. `ThemeTopic` 使用 `filter_expr` 对原始数据做二次过滤。
4. `ThemeReceiverRule` 解析接收人手机号。
5. `ThemeSourceRun` / `ThemeTopicResult` / `ThemeSmsSendLog` 记录数据源运行全过程。

### 自定义脚本链路

1. 上传 ZIP 包，入口函数必须兼容 `run(context) -> list[dict]`。
2. `AlertTask` 选择脚本版本、运行参数、短信模板和接收规则。
3. 调度器触发后，平台执行脚本并对返回结果做模板渲染、接收人匹配和短信发送。

## 本地开发

### 环境要求

- Python 3.11
- Kingbase / PostgreSQL 兼容数据库
- 内网已部署 `oracle-sms-gateway`（宿主端口 5011）；本服务只发 HTTP，不直连 Oracle 发短信
- 镜像内仍保留 `instantclient_11_2/`，供用户上传脚本等可能的 Oracle 访问使用

### 启动步骤

```bash
cp .env.example .env
uv sync --index-url https://pypi.tuna.tsinghua.edu.cn/simple
uv run uvicorn autotask_api.main:app --host 0.0.0.0 --port 8000 --reload
```

访问地址：

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/health`

## Docker 使用

### 快速启动

```bash
cp .env.example .env
docker compose build
docker compose up -d
```

停止：

```bash
docker compose down
```

### 构建策略

`docker-compose.yml` 包含完整的运行配置和构建参数。
构建时可通过环境变量覆盖以下构建参数：

- `PYTHON_BASE_IMAGE`
- `UV_INDEX_URL`
- `UV_EXTRA_INDEX_URL`
- `APT_MIRROR`
- `APT_SECURITY_MIRROR`

默认优先使用国内 Python / Debian 镜像源；如果构建环境无法访问国内源，把这些变量改成官方源即可：

- `UV_INDEX_URL=https://pypi.org/simple`
- `UV_EXTRA_INDEX_URL=https://pypi.org/simple`
- `APT_MIRROR=http://deb.debian.org/debian`
- `APT_SECURITY_MIRROR=http://security.debian.org/debian-security`

说明：

- 容器内服务固定监听 `8000`
- 宿主机暴露端口由 `.env` 中的 `APP_PORT` 控制
- `uploads/` 会挂载到宿主机当前目录，脚本包和解压目录会持久化
- `host.docker.internal:host-gateway` 已写入 compose，便于容器访问宿主机数据库
- 内网服务器只需要 `docker-compose.yml`、`.env` 和已导出的镜像包

## 配置说明

`.env.example` 中已经整理了部署所需的核心变量，建议至少确认以下几组：

- 应用：`APP_NAME`、`APP_PORT`、`TZ`
- Kingbase / PostgreSQL 兼容平台库：`DATABASE_URL`
- 建表开关：`AUTO_CREATE_TABLES`
- 短信网关：`SMS_GATEWAY_BASE_URL`、`SMS_GATEWAY_TOKEN`、`SMS_GATEWAY_BIZ`、`SMS_GATEWAY_TIMEOUT_SECONDS`、`SMS_GATEWAY_MAX_RETRIES`、`SMS_GATEWAY_PERMANENT_DEDUP_HOURS`
- 数据源 / 内置监测脚本默认凭证：`LOGIN_USERNAME`、`LOGIN_PASSWORD`

说明：

- `DATABASE_URL` 是平台数据库连接串；`kingbase_multi_sql` 主题数据源默认优先使用 `THEME_DB_URL`，未配置时复用 `DATABASE_URL`。
- 如果数据库中还没有平台表，可以在首次启动前把 `AUTO_CREATE_TABLES=true`，建表完成后改回 `false`。
- 容器内访问宿主机数据库或网关时，不要把主机地址写成 `127.0.0.1`（可用 `host.docker.internal`）。
- **部署顺序：先升级并启动 `oracle-sms-gateway`，再部署本服务。** 业务侧发的是 `dedup_minutes`；若网关仍是旧版会忽略该字段并退回默认 `DEDUP_HOURS_DEFAULT`（通常 12 小时），**不会报错但会错误放大去重窗口**。
- 本服务与网关必须配置**同一个非空 token**（`SMS_GATEWAY_TOKEN` = 网关 `API_TOKEN`）。网关在 token 为空时会放行请求，本客户端 fail-closed 要求 token——两边都要填。
- 短信发送依赖网关可用；不可达或 5xx 时单条记失败（日志语义区分 4xx 数据问题与 5xx/连接问题），任务/主题运行本身不会因此整体崩溃。连接类错误默认最多再重试 2 次。
- 网关会校验手机号 `^1[3-9]\d{9}$` 与正文 ≤4000 字，不合规返回 400 并记 `failed`；原先直插 Oracle 不做这些校验。上线前请检查联系人手机号是否合规。
- 旧的 `ORACLE_*` / `SMS_USERID` / `SMS_PASSWORD` / `SMS_USERPORT` 配置项仍可出现在 `.env` 中以免加载失败，但**平台发短信已不再使用**；凭证与 `userport` 在网关侧配置。

## 数据源配置示例

前端创建 `dsjfx_case_list` 数据源时，可在 `source_config` 中使用类似结构：

```json
{
  "credential_ref": {
    "username_env": "LOGIN_USERNAME",
    "password_env": "LOGIN_PASSWORD"
  },
  "login_url": "http://68.253.2.111/dsjfx/login",
  "api_url": "http://68.253.2.111/dsjfx/case/list",
  "time_range": {
    "mode": "rolling_hours",
    "hours_back": 24
  },
  "fetch_profile": {
    "page_size": 100,
    "max_pages": 10
  },
  "base_params": {}
}
```

新增的 `db_sql_select` 数据源可以配置为外部数据库只读 SQL 查询，建议使用环境变量传递连接字符串，例如 `THEME_DB_URL`：

```json
{
  "credential_ref": {
    "url_env": "THEME_DB_URL"
  },
  "query": "SELECT id, case_no, alarm_time, dept_code, dept_name, content, replies, address FROM alert_view WHERE alarm_time >= :begin_time AND alarm_time < :end_time ORDER BY alarm_time DESC",
  "time_range": {
    "mode": "rolling_hours",
    "hours_back": 2
  },
  "fetch_profile": {
    "chunk_size": 500,
    "max_rows": 5000
  },
  "field_map": {
    "event_key": "id",
    "case_no": "case_no",
    "alarmTime": "alarm_time",
    "callTime": "alarm_time",
    "sspcsdm": "dept_code",
    "dutyDeptName": "dept_name",
    "caseContents": "content",
    "replies": "replies",
    "occurAddress": "address"
  }
}
```

说明：

- `db_sql_select` 只支持单条只读 `SELECT/WITH`，不支持多语句和写操作。
- 查询默认可使用参数：`begin_time`、`end_time`、`begin_time_text`、`end_time_text`、`limit`、`source_code`。
- 查询结果会按 `field_map` 映射到平台统一字段，后续的主题过滤、接收人匹配和短信发送都复用现有逻辑。

主题过滤表达式示例：

```json
{
  "all": [
    {"field": "caseContents", "op": "contains", "value": "未成年人"},
    {"field": "dwdm", "op": "exists"}
  ]
}
```

更完整的三套主题配置清单见 [0405_qingmingjingqing.md](./0405_qingmingjingqing.md)，里面包含 `清明涉林地/坟地警情`、`精神类警情` 和 `扬言极端警情` 三套可直接录入的配置。

## 自定义脚本上传要求

上传 ZIP 根目录至少包含：

- 入口 Python 文件
- `manifest.json`

最小 `manifest.json` 示例：

```json
{
  "entry_file": "main.py",
  "entry_func": "run",
  "script_type": "python_zip"
}
```

脚本入口约定：

```python
def run(context: dict) -> list[dict]:
    ...
```

## 测试

运行 Python 测试：

```bash
pytest
```

如需验证 compose 配置：

```bash
docker compose config
```

## 离线部署

内网 Ubuntu 22.04 部署步骤单独放在 [DEPLOY.md](DEPLOY.md)。

## kingbase_multi_sql 数据源

主题监测支持 `kingbase_multi_sql` 数据源类型：一个 KingbaseV8/PostgreSQL 兼容连接下配置多条只读 SQL，一次运行只创建一个数据库连接，按顺序执行多条 SQL，并通过 `queries[].topic_codes` 把结果分发给指定主题。

该数据源默认从环境变量读取连接串，优先使用 `THEME_DB_URL`，未配置时复用平台库 `DATABASE_URL`。

配置说明见 [docs/0419_kingbase_multi_sql_theme_source.md](docs/0419_kingbase_multi_sql_theme_source.md)。

矛盾纠纷移交提醒推荐使用单主题配置：一个数据源、一条基础 SQL、一个主题、一个接收规则，并用 `{source_event_id}:{transfer_status_code}` 做阶段去重。配置步骤见 [docs/0421_dxpt_single_topic_setup.md](docs/0421_dxpt_single_topic_setup.md)。
