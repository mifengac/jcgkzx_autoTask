# sjtb:1.3 内网 CentOS Stream 10 使用说明

适用场景：
- 内网服务器（无互联网）
- 使用 `sudo docker` 运行
- 使用宿主机 `crontab` 调度
- 不使用 `docker-compose`

## 1. 有网机器构建并导出镜像（清华源）
```bash
cd /path/to/sjtb
sudo docker build -t sjtb:1.3 .
sudo docker save sjtb:1.3 -o ./sjtb_1.3.tar
```

将以下内容拷贝到 U 盘：
- `sjtb_1.3.tar`
- `env/sjtb.env.example`
- `instantclient_11_2/`（Linux 版 Oracle Instant Client 11g）

## 2. 内网服务器导入镜像和准备目录
```bash
sudo docker load -i /path/to/sjtb_1.3.tar
sudo mkdir -p /opt/sjtb/env /opt/sjtb/logs /opt/oracle
sudo cp /path/to/usb/sjtb.env.example /opt/sjtb/env/sjtb.env
sudo cp -r /path/to/usb/instantclient_11_2 /opt/oracle/
sudo vi /opt/sjtb/env/sjtb.env
```

## 3. Oracle 11g 客户端必须处理（关键）
`python-oracledb` Thick 模式需要标准库名软链接：
```bash
sudo ln -sf /opt/oracle/instantclient_11_2/libclntsh.so.11.1 /opt/oracle/instantclient_11_2/libclntsh.so
sudo ln -sf /opt/oracle/instantclient_11_2/libocci.so.11.1   /opt/oracle/instantclient_11_2/libocci.so
```

## 4. 必填环境变量（/opt/sjtb/env/sjtb.env）
至少确认以下项：
```env
LOGIN_USERNAME=
LOGIN_PASSWORD=

ORACLE_DSN=
ORACLE_USER=
ORACLE_PASSWORD=
ORACLE_CLIENT_LIB_DIR=/opt/oracle/instantclient

SMS_USERID=
SMS_PASSWORD=
SMS_USERPORT=

KINGBASE_HOST=
KINGBASE_PORT=
KINGBASE_DBNAME=
KINGBASE_USER=
KINGBASE_PASSWORD=

DXPT_START_DATE=2026-01-01
```

## 5. 手工测试命令（可直接复制）
```bash
sudo docker run --rm \
  --env-file /opt/sjtb/env/sjtb.env \
  -e TZ=Asia/Shanghai \
  -e LD_LIBRARY_PATH=/opt/oracle/instantclient \
  -v /opt/sjtb/logs:/app/logs \
  -v /opt/oracle/instantclient_11_2:/opt/oracle/instantclient:ro \
  sjtb:1.3 monitor

sudo docker run --rm \
  --env-file /opt/sjtb/env/sjtb.env \
  -e TZ=Asia/Shanghai \
  -e LD_LIBRARY_PATH=/opt/oracle/instantclient \
  -v /opt/sjtb/logs:/app/logs \
  -v /opt/oracle/instantclient_11_2:/opt/oracle/instantclient:ro \
  sjtb:1.3 dxpt0123

sudo docker run --rm \
  --env-file /opt/sjtb/env/sjtb.env \
  -e TZ=Asia/Shanghai \
  -e LD_LIBRARY_PATH=/opt/oracle/instantclient \
  -v /opt/sjtb/logs:/app/logs \
  -v /opt/oracle/instantclient_11_2:/opt/oracle/instantclient:ro \
  sjtb:1.3 zq

sudo docker run --rm \
  --env-file /opt/sjtb/env/sjtb.env \
  -e TZ=Asia/Shanghai \
  -e LD_LIBRARY_PATH=/opt/oracle/instantclient \
  -v /opt/sjtb/logs:/app/logs \
  -v /opt/oracle/instantclient_11_2:/opt/oracle/instantclient:ro \
  sjtb:1.3 multi
```

任务名对应关系：
- `monitor` -> `monitor_wcnr_jq.py`（每 10 分钟）
- `dxpt0123` -> `0123_dxpt_ceshi.py`（每 30 分钟）
- `zq` -> `zq_kshddpt_dsjfx_jq.py`（每 3 小时）
- `multi` -> `data_scraper_multi.py`（每 3 小时，错峰 30 分钟）

## 6. crontab（宿主机调度 + 防重入）
```bash
crontab -e
```

粘贴：
```cron
*/10 * * * * flock -n /var/lock/sjtb_monitor.lock sudo docker run --rm --name sjtb_monitor --env-file /opt/sjtb/env/sjtb.env -e TZ=Asia/Shanghai -e LD_LIBRARY_PATH=/opt/oracle/instantclient -v /opt/sjtb/logs:/app/logs -v /opt/oracle/instantclient_11_2:/opt/oracle/instantclient:ro sjtb:1.3 monitor >> /opt/sjtb/logs/cron_monitor.log 2>&1
*/30 * * * * flock -n /var/lock/sjtb_0123.lock sudo docker run --rm --name sjtb_0123 --env-file /opt/sjtb/env/sjtb.env -e TZ=Asia/Shanghai -e LD_LIBRARY_PATH=/opt/oracle/instantclient -v /opt/sjtb/logs:/app/logs -v /opt/oracle/instantclient_11_2:/opt/oracle/instantclient:ro sjtb:1.3 dxpt0123 >> /opt/sjtb/logs/cron_0123.log 2>&1
0 */3 * * * flock -n /var/lock/sjtb_zq.lock sudo docker run --rm --name sjtb_zq --env-file /opt/sjtb/env/sjtb.env -e TZ=Asia/Shanghai -e LD_LIBRARY_PATH=/opt/oracle/instantclient -v /opt/sjtb/logs:/app/logs -v /opt/oracle/instantclient_11_2:/opt/oracle/instantclient:ro sjtb:1.3 zq >> /opt/sjtb/logs/cron_zq.log 2>&1
30 */3 * * * flock -n /var/lock/sjtb_multi.lock sudo docker run --rm --name sjtb_multi --env-file /opt/sjtb/env/sjtb.env -e TZ=Asia/Shanghai -e LD_LIBRARY_PATH=/opt/oracle/instantclient -v /opt/sjtb/logs:/app/logs -v /opt/oracle/instantclient_11_2:/opt/oracle/instantclient:ro sjtb:1.3 multi >> /opt/sjtb/logs/cron_multi.log 2>&1
```

## 7. 常见问题
1. `DPI-1047 ... libaio.so.1`
- 原因：旧镜像缺 Oracle 运行依赖。
- 处理：使用最新 `sjtb:1.3` 镜像（已内置兼容）。

2. `DPI-1047 ... libclntsh.so` 或 `libnnz11.so`
- 原因：Instant Client 目录未挂载、未设置 `LD_LIBRARY_PATH`、或缺 `libclntsh.so` 软链接。
- 处理：确认第 3 步软链接已执行，并使用第 5 步命令运行。

3. 权限不足无法修改 `/opt/sjtb/env/sjtb.env`
```bash
sudo vi /opt/sjtb/env/sjtb.env
# 或
sudo chown -R $USER:$USER /opt/sjtb
```
