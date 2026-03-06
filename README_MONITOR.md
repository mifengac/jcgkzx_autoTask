# sjtb:1.3 Offline Delivery and Deployment

This directory packages 5 scripts into one image: `sjtb:1.3`.
Production scheduling uses host `crontab` + `sudo docker run --rm`.

## 1. Task Entrypoints

- `monitor` -> `monitor_wcnr_jq.py` (every 10 minutes)
- `jsbrjq` -> `0306jsbrjq_monitor.py` (every 2 hours)
- `dxpt0123` -> `0123_dxpt_ceshi.py` (every 30 minutes)
- `zq` -> `zq_kshddpt_dsjfx_jq.py` (every 3 hours at minute 0)
- `multi` -> `data_scraper_multi.py` (every 3 hours at minute 30)

Container entrypoint is `task_runner.py`, usage:

```bash
docker run --rm sjtb:1.3 monitor
docker run --rm sjtb:1.3 jsbrjq
docker run --rm sjtb:1.3 dxpt0123
docker run --rm sjtb:1.3 zq
docker run --rm sjtb:1.3 multi
```

## 2. Environment File

Use `/opt/sjtb/env/sjtb.env` on the target server.
Template file:

- `env/sjtb.env.example`

### monitor 二次查询（合并后再发短信）

`monitor_wcnr_jq.py` 默认会对 `/dsjfx/case/list` 做 2 次查询，并将两次结果按 `caseNo` 合并去重后再统一发送短信。
可通过以下环境变量调整：

- `MONITOR_SECOND_QUERY_ENABLED`：是否启用第二次查询（默认启用）
- `MONITOR_SECOND_QUERY_NEWORI_SUBCLASS_NO`：第二次查询的 `newOriCharaSubclassNo`
- `MONITOR_SECOND_QUERY_CASE_MARK_NO`：第二次查询的 `caseMarkNo`（默认空表示不限定“未成年人”标记）

Main runtime call format:

```bash
sudo docker run --rm \
  --env-file /opt/sjtb/env/sjtb.env \
  -e TZ=Asia/Shanghai \
  -e LD_LIBRARY_PATH=/opt/oracle/instantclient \
  -v /opt/sjtb/logs:/app/logs \
  -v /opt/oracle/instantclient_11_2:/opt/oracle/instantclient:ro \
  sjtb:1.3 monitor
```

`0306jsbrjq_monitor.py` queries the last 24 hours with `params[startTime]` / `params[endTime]`, filters rows whose `caseContents` or `replies` contains `精神病|精神障碍|精神异常|精神发病|犯病|肇事肇祸`, and then sends SMS after deduping by `caseNo + mobile`.

## 3. Build and Offline Transfer

On online machine:

```bash
cd sjtb
docker build -t sjtb:1.3 .
docker save sjtb:1.3 -o /path/to/usb/sjtb_1.3.tar
```

On internal CentOS Stream 10 server:

```bash
sudo docker load -i /path/to/usb/sjtb_1.3.tar
sudo mkdir -p /opt/sjtb/env /opt/sjtb/logs
```

Copy and edit env file:

```bash
cp /path/to/repo/sjtb/env/sjtb.env.example /opt/sjtb/env/sjtb.env
```

## 4. Host Crontab (Recommended)

Use `flock` to prevent re-entry:

```cron
*/10 * * * * flock -n /var/lock/sjtb_monitor.lock sudo docker run --rm --name sjtb_monitor --env-file /opt/sjtb/env/sjtb.env -e TZ=Asia/Shanghai -e LD_LIBRARY_PATH=/opt/oracle/instantclient -v /opt/sjtb/logs:/app/logs -v /opt/oracle/instantclient_11_2:/opt/oracle/instantclient:ro sjtb:1.3 monitor >> /opt/sjtb/logs/cron_monitor.log 2>&1
0 */2 * * * flock -n /var/lock/sjtb_jsbrjq.lock sudo docker run --rm --name sjtb_jsbrjq --env-file /opt/sjtb/env/sjtb.env -e TZ=Asia/Shanghai -e LD_LIBRARY_PATH=/opt/oracle/instantclient -v /opt/sjtb/logs:/app/logs -v /opt/oracle/instantclient_11_2:/opt/oracle/instantclient:ro sjtb:1.3 jsbrjq >> /opt/sjtb/logs/cron_jsbrjq.log 2>&1
*/30 * * * * flock -n /var/lock/sjtb_0123.lock sudo docker run --rm --name sjtb_0123 --env-file /opt/sjtb/env/sjtb.env -e TZ=Asia/Shanghai -e LD_LIBRARY_PATH=/opt/oracle/instantclient -v /opt/sjtb/logs:/app/logs -v /opt/oracle/instantclient_11_2:/opt/oracle/instantclient:ro sjtb:1.3 dxpt0123 >> /opt/sjtb/logs/cron_0123.log 2>&1
0 */3 * * * flock -n /var/lock/sjtb_zq.lock sudo docker run --rm --name sjtb_zq --env-file /opt/sjtb/env/sjtb.env -e TZ=Asia/Shanghai -e LD_LIBRARY_PATH=/opt/oracle/instantclient -v /opt/sjtb/logs:/app/logs -v /opt/oracle/instantclient_11_2:/opt/oracle/instantclient:ro sjtb:1.3 zq >> /opt/sjtb/logs/cron_zq.log 2>&1
30 */3 * * * flock -n /var/lock/sjtb_multi.lock sudo docker run --rm --name sjtb_multi --env-file /opt/sjtb/env/sjtb.env -e TZ=Asia/Shanghai -e LD_LIBRARY_PATH=/opt/oracle/instantclient -v /opt/sjtb/logs:/app/logs -v /opt/oracle/instantclient_11_2:/opt/oracle/instantclient:ro sjtb:1.3 multi >> /opt/sjtb/logs/cron_multi.log 2>&1
```

## 5. Optional docker-compose (Development Only)

`docker-compose.yml` is only for local development/testing and is not the production scheduler.
