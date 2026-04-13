# JCGKZX AutoTask

`JCGKZX AutoTask` 是一个面向内部监测和通知场景的任务平台，当前同时支持两种模式：

- 主题监测：一个数据源抓取一次，多主题复用同一批数据，再按主题过滤、接收规则和短信模板分发。
- 自定义脚本任务：继续沿用脚本 ZIP 上传、`run(context)` 执行、模板渲染和接收规则匹配的旧模式。

前端是静态控制台，后端是 FastAPI。容器化后可作为单服务部署，运行时依赖外部 Kingbase / Oracle 网络连通。

## 核心能力

- 管理数据源、主题、主题接收规则和运行记录
- 管理脚本 ZIP、脚本版本、自定义任务、短信模板和接收规则
- 按分钟 / 小时统一调度
- 基于联系人主数据做手机号匹配
- 通过 Oracle 11g 短信队列表写入短信发送请求
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
- Oracle 11g 客户端文件已放在 `instantclient_11_2/`

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
- Kingbase：`DATABASE_URL` 或 `KINGBASE_*`
- 建表开关：`AUTO_CREATE_TABLES`
- Oracle：`ORACLE_DSN`、`ORACLE_USER`、`ORACLE_PASSWORD`
- 短信账号：`SMS_USERID`、`SMS_PASSWORD`、`SMS_USERPORT`
- 数据源 / 内置监测脚本默认凭证：`LOGIN_USERNAME`、`LOGIN_PASSWORD`

说明：

- 如果使用 `DATABASE_URL`，则 `KINGBASE_*` 可以留空。
- 如果数据库中还没有平台表，可以在首次启动前把 `AUTO_CREATE_TABLES=true`，建表完成后改回 `false`。
- 容器内访问宿主机数据库时，不要把主机地址写成 `127.0.0.1`。

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
