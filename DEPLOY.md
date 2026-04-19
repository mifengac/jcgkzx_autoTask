# Ubuntu 22.04 内网离线部署说明

本文档说明如何在无互联网的 Ubuntu 22.04 环境中部署当前项目。推荐做法是：

1. 在可联网机器上构建镜像并导出
2. 把镜像和部署文件复制到内网服务器
3. 在内网服务器导入镜像并用 `docker compose` 启动

## 1. 前置条件

目标服务器需要具备：

- Ubuntu 22.04
- Docker Engine
- Docker Compose Plugin
- 能访问业务依赖的 Kingbase / Oracle 网络地址

建议先确认：

- 宿主机磁盘空间充足
- `uploads/` 挂载目录有写权限
- `.env` 将与 `docker-compose.yml` 放在同一目录

## 2. 需要准备的交付文件

部署目录建议至少包含：

```text
deploy/
├── docker-compose.yml
├── .env
├── DEPLOY.md
└── jcgkzx-autotask_latest.tar
```

说明：

- `.env` 和 `docker-compose.yml` 放在同一目录即可
- `jcgkzx-autotask_latest.tar` 是预先导出的镜像包
- `uploads/` 目录可不提前创建，首次启动前补一个空目录即可

## 3. 联网机器上构建镜像

### 3.1 准备环境文件

```bash
cp .env.example .env
```

根据需要修改：

- `IMAGE_NAME`
- `APP_PORT`
- `DATABASE_URL`
- `THEME_DB_URL`（可选，供 `kingbase_multi_sql` 主题数据源优先使用）
- `ORACLE_*`
- `SMS_*`

### 3.2 构建镜像

默认配置优先使用国内镜像源：

- Python 依赖默认走清华源
- Debian 依赖默认走清华 Debian 镜像

直接构建：

```bash
docker compose build
```

如果国内源不可用，把 `.env` 中这些变量改成官方源后重新构建：

```text
UV_INDEX_URL=https://pypi.org/simple
UV_EXTRA_INDEX_URL=https://pypi.org/simple
APT_MIRROR=http://deb.debian.org/debian
APT_SECURITY_MIRROR=http://security.debian.org/debian-security
```

### 3.3 导出镜像

```bash
docker save -o jcgkzx-autotask_latest.tar ${IMAGE_NAME:-jcgkzx-autotask:latest}
```

如果使用的是 `bash` 以外的 shell，也可以直接写死镜像名：

```bash
docker save -o jcgkzx-autotask_latest.tar jcgkzx-autotask:latest
```

## 4. 传输到内网服务器

把以下文件复制到 Ubuntu 22.04 服务器同一个目录：

- `docker-compose.yml`
- `.env`
- `jcgkzx-autotask_latest.tar`

建议同时准备空目录：

```bash
mkdir -p uploads/scripts uploads/extracted
```

## 5. 内网服务器导入镜像

```bash
docker load -i jcgkzx-autotask_latest.tar
```

确认镜像已导入：

```bash
docker images | grep jcgkzx-autotask
```

## 6. 内网服务器启动服务

在 `docker-compose.yml` 所在目录执行：

```bash
docker compose up -d --no-build
```

说明：

- `--no-build` 可以避免离线环境误触发重新构建
- compose 会读取同目录下的 `.env`
- 容器启动后会把 `./uploads` 挂载到容器内 `/app/uploads`

检查状态：

```bash
docker compose ps
docker compose logs -f
```

健康检查地址：

- `http://127.0.0.1:${APP_PORT}/health`

## 7. 首次启动建议

如果数据库中还没有平台表，有两种方式：

### 方式 A：自动建表

把 `.env` 中的：

```text
AUTO_CREATE_TABLES=true
```

首次启动成功后，改回：

```text
AUTO_CREATE_TABLES=false
```

然后重启容器：

```bash
docker compose up -d --no-build
```

### 方式 B：手工建表

在数据库中预先执行项目里的建表 SQL，再保持：

```text
AUTO_CREATE_TABLES=false
```

如果你们生产环境对自动建表比较敏感，建议优先用手工建表。

## 8. `.env` 关键配置说明

至少需要关注这些变量：

- `IMAGE_NAME`：compose 运行时使用的镜像标签，必须和导入的镜像标签一致
- `APP_PORT`：宿主机暴露端口
- `DATABASE_URL`：平台数据库连接串，必填
- `THEME_DB_URL`：主题数据库连接串，可选；`kingbase_multi_sql` 优先使用它，未配置时复用 `DATABASE_URL`
- `DB_SCHEMA`：平台表所在 schema
- `AUTO_CREATE_TABLES`：是否自动建表
- `ORACLE_DSN` / `ORACLE_USER` / `ORACLE_PASSWORD`
- `ORACLE_CLIENT_LIB_DIR=/opt/oracle/instantclient_11_2`
- `SMS_USERID` / `SMS_PASSWORD` / `SMS_USERPORT`
- `LOGIN_USERNAME` / `LOGIN_PASSWORD`：可供数据源或内置监测脚本引用

## 9. 内网部署注意事项

- 容器内访问宿主机数据库时，不要使用 `127.0.0.1`，应使用 `host.docker.internal` 或真实 IP。
- 如果数据库在远端服务器上，直接填写远端 IP 或域名。
- `instantclient_11_2` 已经打进镜像，离线运行阶段不需要再单独安装 Oracle 客户端。
- 只要镜像已经导入，离线启动不依赖公网，也不需要再次拉取基础镜像或 Python 依赖。
- 如果后续升级版本，推荐沿用同样流程：联网构建 -> `docker save` -> 内网 `docker load` -> `docker compose up -d --no-build`。

## 10. 常用运维命令

启动：

```bash
docker compose up -d --no-build
```

停止：

```bash
docker compose down
```

重启：

```bash
docker compose restart
```

查看日志：

```bash
docker compose logs -f autotask
```

查看容器内环境变量：

```bash
docker compose exec autotask env
```

## 11. MobaXterm 上传权限问题

如果你在用 MobaXterm 上传镜像包时看到类似错误：

```text
Error #3 (/home/yfza/file/jcgkzx_autotask/jcgkzx-autotask_2026.04.05.tar): Permission denied
```

这通常不是文件损坏，而是目标目录没有写权限。可以按下面顺序处理：

### 11.1 先检查目录权限

```bash
ls -ld /home/yfza/file /home/yfza/file/jcgkzx_autotask
```

如果目录不是 `yfza` 用户拥有，MobaXterm 就可能无法直接上传。

### 11.2 调整目录归属

如果你有 `sudo` 权限，可以这样修复：

```bash
sudo mkdir -p /home/yfza/file/jcgkzx_autotask
sudo chown -R yfza:yfza /home/yfza/file/jcgkzx_autotask
chmod 755 /home/yfza/file/jcgkzx_autotask
```

### 11.3 没有 sudo 时的替代方案

如果你没有 `sudo` 权限，先上传到你自己有写权限的目录，比如：

```text
/home/yfza/
```

然后登录服务器后再手动移动：

```bash
mv ~/jcgkzx-autotask_2026.04.05.tar /home/yfza/file/jcgkzx_autotask/
```

### 11.4 如果还是失败

可以先把文件上传到家目录，再执行：

```bash
ls -l ~/jcgkzx-autotask_2026.04.05.tar
```

确认文件存在后，再继续 `docker load -i ...`。
