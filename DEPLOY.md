# Ubuntu 22.04 内网 Docker 离线部署说明

本文档说明如何把本项目在可构建环境打包为 Docker 镜像，并传输到内网 Ubuntu 22.04 服务器部署运行。

适用场景：

- 本地或联网构建机负责 `docker compose build` 和 `docker save`。
- 内网 Ubuntu 22.04 服务器无法访问公网，只负责 `docker load` 和 `docker compose up`。
- 生产 Kingbase、Oracle 短信平台、内网 HTTP 接口均为独立服务器，通过 `.env` 配置连接地址。

## 1. 打包端需要导出的文件

在项目根目录执行构建和导出。当前推荐导出的文件如下：

| 文件/目录 | 是否必须 | 说明 |
|---|---:|---|
| `jcgkzx-autotask_latest.tar` | 必须 | Docker 镜像离线包，由 `docker save` 生成 |
| `docker-compose.yml` | 必须 | 内网服务器启动容器使用 |
| `.env` | 必须 | 生产环境配置文件，包含数据库、Oracle、短信账号等运行参数 |
| `DEPLOY.md` | 建议 | 本部署说明 |
| `.env.example` | 建议 | 配置项参考，不应直接当生产配置使用 |
| `migrations/` | 建议 | 平台建表和升级 SQL，首次部署或升级数据库约束时使用 |
| `uploads/` | 视情况 | 如需迁移已有上传脚本包，则传输；新部署可不传 |

不建议导出或传输：

- `.git/`
- `.venv/`
- `.pytest_cache/`
- `autotask-local.db`
- `run-local.stdout.log`
- `run-local.stderr.log`
- 开发机旧镜像包或临时文件

说明：

- Oracle Instant Client 已打入镜像，不需要单独传输 `instantclient_11_2/`。
- `docs/`、`tests/`、本地汇报材料等不参与容器运行，可按管理需要另行归档。
- `.env` 必须使用生产参数，不能直接使用开发机本地测试参数。

## 2. 打包端构建和导出命令

在项目根目录执行：

```bash
docker compose build
docker save -o jcgkzx-autotask_latest.tar jcgkzx-autotask:latest
```

如果 `.env` 中修改了 `IMAGE_NAME`，则 `docker save` 的镜像名也要保持一致，例如：

```bash
docker save -o jcgkzx-autotask_latest.tar ${IMAGE_NAME}
```

构建完成后确认镜像和离线包：

```bash
docker images | grep jcgkzx-autotask
ls -lh jcgkzx-autotask_latest.tar
```

Windows PowerShell 可使用：

```powershell
docker compose build
docker save -o jcgkzx-autotask_latest.tar jcgkzx-autotask:latest
Get-Item .\jcgkzx-autotask_latest.tar
```

## 3. 传输到内网服务器的文件

建议在内网 Ubuntu 22.04 服务器创建统一部署目录：

```bash
sudo mkdir -p /opt/jcgkzx-autotask
sudo chown -R $USER:$USER /opt/jcgkzx-autotask
```

把以下文件传输到 `/opt/jcgkzx-autotask/`：

```text
/opt/jcgkzx-autotask/
├── docker-compose.yml
├── .env
├── DEPLOY.md
├── .env.example
├── jcgkzx-autotask_latest.tar
└── migrations/
```

如已有历史上传脚本包需要迁移，可同时传输：

```text
/opt/jcgkzx-autotask/uploads/
```

可使用 `scp` 示例：

```bash
scp docker-compose.yml .env DEPLOY.md .env.example jcgkzx-autotask_latest.tar user@内网服务器IP:/opt/jcgkzx-autotask/
scp -r migrations user@内网服务器IP:/opt/jcgkzx-autotask/
```

如果内网服务器只能通过 U 盘或堡垒机传输，保持上述目录结构即可。

## 4. `.env` 生产配置要点

至少确认以下配置：

```env
IMAGE_NAME=jcgkzx-autotask:latest
APP_PORT=8000
TZ=Asia/Shanghai

DATABASE_URL=postgresql+psycopg2://平台库用户:密码@Kingbase服务器IP:54321/平台库名
DB_SCHEMA=jcgkzx_autotask
AUTO_CREATE_TABLES=false

THEME_DB_URL=postgresql+psycopg2://业务查询用户:密码@Kingbase服务器IP:54321/业务库名

ORACLE_DSN=Oracle服务器IP:1521/service_name
ORACLE_USER=短信库用户
ORACLE_PASSWORD=短信库密码
ORACLE_THICK_MODE=true
ORACLE_CLIENT_LIB_DIR=/opt/oracle/instantclient_11_2

SMS_USERID=短信账号
SMS_PASSWORD=短信密码
SMS_USERPORT=短信端口或业务端口

LOGIN_USERNAME=内网HTTP接口账号
LOGIN_PASSWORD=内网HTTP接口密码
```

说明：

- `DATABASE_URL` 是平台自身数据库连接串，必填。
- `THEME_DB_URL` 是数据库型主题数据源连接串，可选；`kingbase_multi_sql` 优先使用它，未配置时复用 `DATABASE_URL`。
- 生产 Kingbase 如果是独立服务器，直接写真实 IP 或域名，不要写 `127.0.0.1`。
- 密码中如果包含 `@`、`#`、`:`、`/` 等特殊字符，需要 URL 编码。
- 首次建表可以临时设置 `AUTO_CREATE_TABLES=true`，建表完成后必须改回 `false` 并重启容器。
- 生产环境必须替换 `AUTH_SECRET_KEY`，不要使用示例值。

## 5. 首次部署命令

进入部署目录：

```bash
cd /opt/jcgkzx-autotask
```

导入镜像：

```bash
sudo docker load -i jcgkzx-autotask_latest.tar
```

确认镜像已导入：

```bash
sudo docker images | grep jcgkzx-autotask
```

创建持久化目录：

```bash
sudo mkdir -p uploads/scripts uploads/extracted
sudo chown -R $USER:$USER uploads
```

检查 compose 配置：

```bash
sudo docker compose config
```

启动服务：

```bash
sudo docker compose up -d --no-build
```

查看容器状态：

```bash
sudo docker compose ps
sudo docker compose logs -f
```

健康检查：

```bash
curl -f http://127.0.0.1:${APP_PORT:-8000}/health
```

浏览器访问：

```text
http://服务器IP:APP_PORT/
```

## 6. 数据库初始化和升级

### 6.1 首次建表

方式一：自动建表。

仅首次部署时使用：

```env
AUTO_CREATE_TABLES=true
```

启动成功并确认表已创建后，改回：

```env
AUTO_CREATE_TABLES=false
```

然后重启：

```bash
sudo docker compose restart
```

方式二：手工执行 SQL。

由数据库管理员在 Kingbase 客户端执行 `migrations/` 下的建表 SQL。已有生产数据库建议优先使用手工 SQL，便于审计。

### 6.2 本次版本需要关注的迁移

如生产库已经存在主题监测表，需要确保执行以下迁移，使 `theme_source.source_type` 支持数据库型数据源：

```text
migrations/0417_theme_source_db_sql_select.sql
migrations/0419_theme_source_kingbase_multi_sql.sql
```

否则页面保存 `db_sql_select` 或 `kingbase_multi_sql` 数据源时，数据库 `CHECK` 约束会拒绝写入。

## 7. 更新部署命令

传入新镜像包后，在部署目录执行：

```bash
cd /opt/jcgkzx-autotask
sudo docker compose down
sudo docker load -i jcgkzx-autotask_latest.tar
sudo docker compose up -d --no-build
sudo docker compose ps
```

如仅修改 `.env`：

```bash
cd /opt/jcgkzx-autotask
sudo docker compose restart
```

如修改了 `docker-compose.yml`：

```bash
cd /opt/jcgkzx-autotask
sudo docker compose config
sudo docker compose up -d --no-build
```

## 8. 常用 Ubuntu 22.04 运维命令

### 系统信息

```bash
lsb_release -a
uname -a
date
timedatectl
df -h
free -h
top
```

### Docker 状态

```bash
sudo systemctl status docker
sudo systemctl restart docker
sudo docker version
sudo docker compose version
sudo docker images
sudo docker ps -a
```

### 服务启停

```bash
cd /opt/jcgkzx-autotask
sudo docker compose up -d --no-build
sudo docker compose down
sudo docker compose restart
sudo docker compose ps
```

### 日志查看

```bash
cd /opt/jcgkzx-autotask
sudo docker compose logs -f
sudo docker compose logs --tail=200 autotask
```

### 进入容器

```bash
sudo docker exec -it jcgkzx-autotask bash
```

### 网络连通性检查

```bash
ping Kingbase服务器IP
nc -vz Kingbase服务器IP 54321
nc -vz Oracle服务器IP 1521
curl -I http://内网HTTP服务器地址/
```

如果没有 `nc`，可安装：

```bash
sudo apt-get update
sudo apt-get install -y netcat-openbsd
```

离线服务器不能联网时，请提前准备对应 deb 包或使用已有运维工具替代。

### 磁盘和清理

```bash
df -h
du -sh /opt/jcgkzx-autotask/*
sudo docker system df
sudo docker image prune
sudo docker container prune
```

谨慎使用清理命令，确认不再需要旧容器和旧镜像后再执行。

## 9. 注意事项

1. 不要在生产 `.env` 中使用本地测试地址，例如 `127.0.0.1:54321`。如果 Kingbase 是独立服务器，应填写独立服务器 IP 或域名。
2. `host.docker.internal` 主要用于容器访问宿主机服务；生产 Kingbase 是独立服务器时不需要使用它。
3. 内网服务器防火墙、安全组、数据库访问控制需允许 Ubuntu 服务器访问 Kingbase、Oracle 和 HTTP 接口。
4. Oracle 11g 依赖 thick mode，镜像内已包含 Instant Client，`ORACLE_CLIENT_LIB_DIR` 保持 `/opt/oracle/instantclient_11_2`。
5. `kingbase_multi_sql` 只允许单条只读 `SELECT/WITH` SQL，不支持写操作；配置 SQL 前建议先由数据库管理员审查。
6. 平台当前调度器适合单实例部署，不建议同一数据库同时运行多个容器实例，否则可能重复触发定时任务。
7. 生产启用前建议先用页面“演练”执行数据源，确认抓取数量、主题命中、接收规则和短信内容。
8. 正式发送短信前，必须确认 Oracle 短信账号、`SMS_USERID`、`SMS_PASSWORD`、`SMS_USERPORT` 配置正确。
9. `uploads/` 是持久化目录，保存上传脚本包；升级容器时不要删除。
10. 不要把包含真实密码的 `.env` 上传到公开仓库或通过不安全渠道传输。
11. 镜像包较大，传输前后可使用文件大小或哈希校验确认完整性。

## 10. 推荐交付清单

最终交付给内网部署人员的文件建议为：

```text
docker-compose.yml
.env
.env.example
DEPLOY.md
jcgkzx-autotask_latest.tar
migrations/
```

如需迁移已有脚本包，额外提供：

```text
uploads/
```

