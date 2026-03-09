# JCGKZX AutoTask API

## 1. 目标

这套服务把现有脚本任务改造成统一的 Web 管理台，前端可直接完成：

- 上传脚本 ZIP 包
- 配置短信模板
- 配置任务频率，单位支持 `minute` / `hour`
- 配置发送规则
- 手动演练或立即发送
- 查看运行记录和短信写入日志

前端为纯静态页面，后端为 FastAPI，整体可离线运行，不依赖 CDN 或外部前端包管理。

## 2. 本地开发

安装依赖：

```bash
uv sync --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

准备环境文件：

```bash
cp .env.example .env
```

启动：

```bash
uv run uvicorn autotask_api.main:app --host 0.0.0.0 --port 8000 --reload
```

访问：

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/health`

## 3. Oracle 11g Thick Mode

短信通道使用 `python-oracledb` 的 thick 模式。

必须配置：

- `ORACLE_DSN`
- `ORACLE_USER`
- `ORACLE_PASSWORD`
- `ORACLE_THICK_MODE=true`
- `ORACLE_CLIENT_LIB_DIR=/opt/oracle/instantclient_11_2`

当前代码会在运行时校验 `instantclient_11_2` 目录中是否存在：

- `libclntsh.so.11.1`
- `libnnz11.so`
- `libocci.so.11.1`
- `libociei.so`

## 4. Docker Compose

先准备 `.env`：

```bash
cp .env.example .env
```

启动：

```bash
docker compose up -d --build
```

如需切换环境文件：

```bash
docker compose --env-file compose.test.env up -d --build
```

停止：

```bash
docker compose down
```

说明：

- `docker-compose.yml` 统一启动前后端一体化服务
- `uploads/` 挂载到宿主机，脚本包和解压目录会持久化
- 容器内默认 Oracle 客户端路径是 `/opt/oracle/instantclient_11_2`

## 5. 纯离线运行说明

运行阶段不依赖互联网：

- 前端无 CDN 依赖
- 后端依赖已打入镜像
- Oracle Instant Client 已随本地构建上下文复制进镜像

注意：

- 若要在完全离线的生产服务器构建镜像，需要提前准备好 Python 基础镜像和依赖缓存
- 更稳妥的做法是在联网页面构建好镜像后执行 `docker save`，离线环境用 `docker load` 导入
- 由于 `instantclient_11_2` 中大文件不适合直接提交到 GitHub，生产部署时要确保本地构建上下文或离线镜像中已经带上这些文件

## 6. 主要 API

- `GET /health`
- `POST /api/scripts/upload`
- `GET /api/scripts`
- `POST /api/message-templates`
- `GET /api/message-templates`
- `PUT /api/message-templates/{template_id}`
- `POST /api/tasks`
- `GET /api/tasks`
- `PUT /api/tasks/{task_id}`
- `PUT /api/tasks/{task_id}/schedule`
- `POST /api/tasks/{task_id}/enable`
- `POST /api/tasks/{task_id}/disable`
- `POST /api/tasks/{task_id}/rules`
- `PUT /api/rules/{rule_id}`
- `DELETE /api/rules/{rule_id}`
- `POST /api/tasks/{task_id}/run`
- `GET /api/task-runs`
- `GET /api/task-runs/{run_id}`
- `GET /api/contacts`

## 7. 脚本上传约定

上传 ZIP 包根目录必须包含 `manifest.json`，至少要有：

```json
{
  "entry_file": "main.py",
  "entry_func": "run"
}
```

脚本入口函数签名约定：

```python
def run(context: dict) -> list[dict]:
    ...
```

返回值必须是 `list[dict]`，每个 `dict` 代表一条待判断事件记录。
