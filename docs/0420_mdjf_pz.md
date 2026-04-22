# 矛盾纠纷移交短信提醒配置教程

本文档用于配置矛盾纠纷移交短信提醒，推荐采用当前简化后的单主题方案：

```text
1 个 Kingbase 视图
1 个 kingbase_multi_sql 数据源
1 个主题
1 条接收规则
1 个短信模板
```

阶段提醒不再通过多个主题区分，而是通过视图输出的 `transfer_status_code` 参与去重：

```text
去重键模板：{source_event_id}:{transfer_status_code}
```

这样可以做到：

```text
同一事件同一阶段只发一次
同一事件进入下一阶段后可以再次发送
```

例如：

```text
dxpt_transfer_reminder:DXPT-001:u12
dxpt_transfer_reminder:DXPT-001:u24
dxpt_transfer_reminder:DXPT-001:u36
```

## 1. 创建 Kingbase 视图

视图名称：

```text
stdata.v_dxpt_mdjf_transfer_monitor
```

这个视图负责把原始矛盾纠纷数据整理成系统需要的标准字段，包括：

```text
source_event_id
business_no
station_code
station_name
branch_name
registered_at
transfer_status
transfer_status_code
message_text
```

执行下面 SQL 创建或替换视图。

```sql
CREATE OR REPLACE VIEW stdata.v_dxpt_mdjf_transfer_monitor AS
WITH base AS (
  SELECT DISTINCT ON (a.systemid)
    CAST(a.systemid AS text) AS systemid,
    NULLIF(CAST(a.ywlsh AS text), '') AS business_no,
    CAST(a.jfmc AS text) AS dispute_name,
    CAST(c.detail AS text) AS dispute_type,
    CAST(a.jyqk AS text) AS summary_text,
    a.fssj AS happened_at,
    CASE
      WHEN a.sssj = '445300000000' THEN CAST('云浮市公安局' AS text)
      ELSE CAST(a.sssj AS text)
    END AS city_name,
    CASE
      WHEN substring(a.ssfj, 1, 6) = '445302' THEN CAST('云城分局' AS text)
      WHEN substring(a.ssfj, 1, 6) = '445303' THEN CAST('云安分局' AS text)
      WHEN substring(a.ssfj, 1, 6) = '445321' THEN CAST('新兴县公安局' AS text)
      WHEN substring(a.ssfj, 1, 6) = '445381' THEN CAST('罗定市公安局' AS text)
      WHEN substring(a.ssfj, 1, 6) = '445322' THEN CAST('郁南县公安局' AS text)
      ELSE CAST(a.ssfj AS text)
    END AS branch_name,
    CAST(e.sspcsdm AS text) AS station_code,
    CAST(e.sspcs AS text) AS station_name,
    CAST(d.detail AS text) AS flow_status,
    a.djsj AS registered_at,
    CAST(a.djdw_mc AS text) AS register_unit_name,
    a.xgsj AS updated_at,
    b.yjqqsj AS transfer_request_at,
    CAST(g.detail AS text) AS ypa_feedback_status,
    CASE
      WHEN b.tczt = '1' THEN CAST('已化解' AS text)
      WHEN b.tczt = '0' THEN CAST('未化解' AS text)
      ELSE CAST(b.tczt AS text)
    END AS mediation_status,
    b.rksj AS storage_at,
    CASE
      WHEN b.orderstate = '2' THEN CAST('已登记:已分发待确认' AS text)
      WHEN b.orderstate = '5' THEN CAST('处理中:其他' AS text)
      WHEN b.orderstate = '6' THEN CAST('已结案' AS text)
      WHEN b.orderstate = '4' THEN CAST('处理中:业务系统已受理' AS text)
      ELSE CAST(b.orderstate AS text)
    END AS ypa_process_status,
    b.processtime AS ypa_process_time,
    round((EXTRACT(epoch FROM (b.yjqqsj - a.djsj)) / 86400 * 24), 2) AS transfer_hours,
    round((EXTRACT(epoch FROM (now() - a.djsj)) / 86400 * 24), 2) AS pending_hours
  FROM (
    SELECT *
    FROM stdata.b_per_mdjfjfsjgl
    WHERE deleteflag = '0'
      AND sfgazzfw = '0'
      AND djsj >= '2026-01-01'
  ) a
  LEFT JOIN (
    SELECT *
    FROM stdata.b_per_mdjfypafhsj
    WHERE deleteflag = '0'
  ) b ON a.systemid = b.systemid
  LEFT JOIN (
    SELECT code, detail
    FROM stdata.s_sg_dict
    WHERE kind_code = 'SQRY_XGNMK_MDJF_JFLX'
  ) c ON a.jflx = c.code
  LEFT JOIN (
    SELECT code, detail
    FROM stdata.s_sg_dict
    WHERE kind_code = 'SQRY_XGNMK_MDJF_LCZT'
  ) d ON a.lczt = d.code
  LEFT JOIN (
    SELECT code, detail
    FROM stdata.s_sg_dict
    WHERE kind_code = 'SQRY_XGNMK_MDJF_YJFKZT'
  ) g ON b.yjfkzt = g.code
  LEFT JOIN stdata.b_dic_zzjgdm e ON a.sspcs = e.sspcsdm
  WHERE a.lczt <> '6'
  ORDER BY a.systemid, b.yjqqsj DESC NULLS LAST, a.xgsj DESC NULLS LAST
),
classified AS (
  SELECT
    *,
    CASE
      WHEN pending_hours <= 12
        AND (
          transfer_request_at IS NULL
          OR ypa_feedback_status = '粤平安退回'
          OR flow_status = '移交失败'
          OR flow_status <> '已移交'
        )
        THEN CAST('12小时内未移交' AS text)
      WHEN pending_hours <= 24
        AND (
          transfer_request_at IS NULL
          OR ypa_feedback_status = '粤平安退回'
          OR flow_status = '移交失败'
          OR flow_status <> '已移交'
        )
        THEN CAST('24小时内未移交' AS text)
      WHEN pending_hours <= 36
        AND (
          transfer_request_at IS NULL
          OR ypa_feedback_status = '粤平安退回'
          OR flow_status = '移交失败'
          OR flow_status <> '已移交'
        )
        THEN CAST('36小时内未移交' AS text)
      WHEN pending_hours <= 48
        AND (
          transfer_request_at IS NULL
          OR ypa_feedback_status = '粤平安退回'
          OR flow_status = '移交失败'
          OR flow_status <> '已移交'
        )
        THEN CAST('48小时内未移交' AS text)
      WHEN pending_hours <= 72
        AND (
          transfer_request_at IS NULL
          OR ypa_feedback_status = '粤平安退回'
          OR flow_status = '移交失败'
          OR flow_status <> '已移交'
        )
        THEN CAST('72小时内未移交' AS text)
      WHEN pending_hours > 72
        AND (
          transfer_request_at IS NULL
          OR ypa_feedback_status = '粤平安退回'
          OR flow_status = '移交失败'
          OR flow_status <> '已移交'
        )
        THEN CAST('超出72小时仍未移交' AS text)
      WHEN transfer_hours <= 48
        AND (
          transfer_request_at IS NOT NULL
          OR ypa_feedback_status <> '粤平安退回'
          OR flow_status <> '移交失败'
        )
        THEN CAST('48小时内移交' AS text)
      WHEN transfer_hours <= 72
        AND (
          transfer_request_at IS NOT NULL
          OR ypa_feedback_status <> '粤平安退回'
          OR flow_status <> '移交失败'
        )
        THEN CAST('72小时内移交' AS text)
      ELSE CAST('超出72小时移交' AS text)
    END AS transfer_status
  FROM base
),
normalized AS (
  SELECT
    *,
    CASE
      WHEN transfer_status = '12小时内未移交' THEN CAST('u12' AS text)
      WHEN transfer_status = '24小时内未移交' THEN CAST('u24' AS text)
      WHEN transfer_status = '36小时内未移交' THEN CAST('u36' AS text)
      WHEN transfer_status = '48小时内未移交' THEN CAST('u48' AS text)
      WHEN transfer_status = '72小时内未移交' THEN CAST('u72' AS text)
      WHEN transfer_status = '超出72小时仍未移交' THEN CAST('u72plus' AS text)
      ELSE CAST('done' AS text)
    END AS transfer_status_code
  FROM classified
)
SELECT
  CASE
    WHEN business_no IS NULL OR business_no = '' THEN systemid
    ELSE business_no
  END AS source_event_id,
  business_no,
  dispute_name,
  dispute_type,
  summary_text,
  happened_at,
  city_name,
  branch_name,
  station_code,
  station_name,
  flow_status,
  registered_at,
  register_unit_name,
  updated_at,
  transfer_request_at,
  ypa_feedback_status,
  mediation_status,
  storage_at,
  ypa_process_status,
  ypa_process_time,
  transfer_hours,
  pending_hours,
  transfer_status,
  transfer_status_code,
  CAST('基础管控中心提醒' AS text)
    || COALESCE(branch_name, CAST('' AS text))
    || COALESCE(station_name, CAST('' AS text))
    || CAST('【纠纷名称】：' AS text)
    || COALESCE(dispute_name, CAST('' AS text))
    || CAST('；' AS text)
    || COALESCE(transfer_status, CAST('' AS text))
    || CAST('；【纠纷登记时间】：' AS text)
    || COALESCE(CAST(TO_CHAR(registered_at, 'YYYY-MM-DD HH24:MI:SS') AS text), CAST('' AS text))
    || CAST('；【纠纷类型】：' AS text)
    || COALESCE(dispute_type, CAST('' AS text))
    || CAST('；【发生时间】：' AS text)
    || COALESCE(CAST(TO_CHAR(happened_at, 'YYYY-MM-DD HH24:MI:SS') AS text), CAST('' AS text))
    AS message_text
FROM normalized;
```

创建视图后建议追加注释，方便后续维护。

```sql
COMMENT ON VIEW stdata.v_dxpt_mdjf_transfer_monitor IS
'矛盾纠纷移交提醒监测视图：供基础管控中心自动任务系统查询未移交纠纷数据，计算12/24/36/48/72小时阶段，并生成短信内容。';

COMMENT ON COLUMN stdata.v_dxpt_mdjf_transfer_monitor.source_event_id IS
'事件唯一标识，用于短信去重；优先使用业务流水号，业务流水号为空时使用 systemid。';

COMMENT ON COLUMN stdata.v_dxpt_mdjf_transfer_monitor.business_no IS
'业务流水号，对应源表 ywlsh。';

COMMENT ON COLUMN stdata.v_dxpt_mdjf_transfer_monitor.station_code IS
'派出所代码，对应组织机构字典表 sspcsdm，用于匹配联系人。';

COMMENT ON COLUMN stdata.v_dxpt_mdjf_transfer_monitor.station_name IS
'派出所名称，对应组织机构字典表 sspcs。';

COMMENT ON COLUMN stdata.v_dxpt_mdjf_transfer_monitor.branch_name IS
'分局或县区公安机关名称。';

COMMENT ON COLUMN stdata.v_dxpt_mdjf_transfer_monitor.registered_at IS
'纠纷登记时间，对应源表 djsj。';

COMMENT ON COLUMN stdata.v_dxpt_mdjf_transfer_monitor.happened_at IS
'纠纷发生时间，对应源表 fssj。';

COMMENT ON COLUMN stdata.v_dxpt_mdjf_transfer_monitor.transfer_status IS
'移交状态，例如12小时内未移交、24小时内未移交、超出72小时仍未移交。';

COMMENT ON COLUMN stdata.v_dxpt_mdjf_transfer_monitor.transfer_status_code IS
'移交状态编码，用于单主题阶段去重；取值包括 u12、u24、u36、u48、u72、u72plus、done。';

COMMENT ON COLUMN stdata.v_dxpt_mdjf_transfer_monitor.message_text IS
'已拼接完成的短信正文，短信模板可直接使用 {message_text}。';
```

如果 Kingbase 提示 `now() - a.djsj` 类型不匹配，说明 `a.djsj` 不是时间类型。可以把视图中的相关字段改成：

```sql
CAST(a.djsj AS timestamp)
```

例如：

```sql
CAST(a.djsj AS timestamp) AS registered_at
round((EXTRACT(epoch FROM (now() - CAST(a.djsj AS timestamp))) / 86400 * 24), 2) AS pending_hours
```

## 2. 数据源配置

### 2.1 数据库连接

`kingbase_multi_sql` 数据源默认从 `.env` 读取数据库连接。

优先级：

```text
1. THEME_DB_URL
2. DATABASE_URL
```

如果主题数据源查询的 Kingbase 库和平台库不是同一个库，建议单独配置：

```env
THEME_DB_URL=postgresql+psycopg2://用户名:密码@Kingbase地址:端口/数据库名
```

如果主题数据源查询的库和平台库是同一个库，可以只配置：

```env
DATABASE_URL=postgresql+psycopg2://用户名:密码@Kingbase地址:端口/数据库名
```

修改 `.env` 后需要重启服务或容器。

### 2.2 前端创建数据源

进入：

```text
数据源管理 -> 配置编辑
```

推荐填写：

```text
数据源名称：矛盾纠纷移交提醒数据源
数据源编码：dxpt_transfer_source
数据源类型：kingbase_multi_sql
调度间隔：20
调度单位：分钟
时区：Asia/Shanghai
启用数据源：是
```

当前前端已提供预设按钮：

```text
填入矛盾纠纷单主题配置
```

点击后会自动填入下面的 `source_config`。

### 2.3 source_config JSON

生产配置建议先只监测 `u12` 到 `u72`。

```json
{
  "query_params": {
    "start_date": "2026-01-01",
    "limit": 5000
  },
  "fetch_profile": {
    "chunk_size": 500,
    "max_rows": 5000
  },
  "field_map": {
    "event_key": "source_event_id",
    "case_no": "business_no",
    "sspcsdm": "station_code",
    "dwdm": "station_code",
    "message_text": "message_text"
  },
  "queries": [
    {
      "query_code": "dxpt_transfer_all",
      "topic_codes": ["dxpt_transfer_reminder"],
      "query": "SELECT * FROM stdata.v_dxpt_mdjf_transfer_monitor WHERE registered_at >= CAST(:start_date AS timestamp) AND transfer_status_code IN ('u12', 'u24', 'u36', 'u48', 'u72') ORDER BY registered_at DESC LIMIT :limit"
    }
  ]
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `query_params.start_date` | 查询起始登记时间 |
| `query_params.limit` | SQL 返回上限 |
| `fetch_profile.max_rows` | 单次运行最大处理行数 |
| `field_map.event_key` | 映射为系统事件 key |
| `field_map.sspcsdm` | 映射为接收规则使用的派出所代码 |
| `field_map.message_text` | 映射为短信正文 |
| `queries[0].topic_codes` | 指定结果只交给 `dxpt_transfer_reminder` 主题 |

本地测试如果库里只有超过 72 小时的数据，可以临时把 SQL 改成包含 `u72plus`：

```sql
AND transfer_status_code IN ('u12', 'u24', 'u36', 'u48', 'u72', 'u72plus')
```

生产是否包含 `u72plus`，按业务要求决定。如果不希望超 72 小时继续提醒，就不要加入 `u72plus`。

## 3. 主题配置

进入：

```text
主题管理 -> 主题配置
```

先选择刚才创建的数据源：

```text
矛盾纠纷移交提醒数据源 / dxpt_transfer_source
```

当前前端已提供预设按钮：

```text
填入矛盾纠纷单主题配置
```

点击后会自动填入推荐值。

推荐配置：

```text
主题名称：矛盾纠纷移交提醒
主题编码：dxpt_transfer_reminder
短信模板：选择“矛盾纠纷移交提醒”
优先级：100
去重模式：永久不重发
时间窗口：留空
去重键模板：{source_event_id}:{transfer_status_code}
启用主题：是
```

命中过滤 JSON：

```json
{
  "field": "transfer_status_code",
  "op": "in",
  "value": ["u12", "u24", "u36", "u48", "u72"]
}
```

这个配置表示：一个主题处理所有阶段，但只处理未移交阶段。

如果本地测试需要查看超 72 小时数据，可以临时改成：

```json
{
  "field": "transfer_status_code",
  "op": "in",
  "value": ["u12", "u24", "u36", "u48", "u72", "u72plus"]
}
```

去重逻辑示例：

```text
source_event_id = DXPT-001
transfer_status_code = u24
theme_code = dxpt_transfer_reminder
```

系统生成：

```text
dedup_key = DXPT-001:u24
oracle_eid = dxpt_transfer_reminder:DXPT-001:u24
```

同一事件到 `u36` 阶段时：

```text
oracle_eid = dxpt_transfer_reminder:DXPT-001:u36
```

所以同一事件进入新阶段后可以再次发送。

## 4. 接收规则配置

进入：

```text
主题管理 -> 接收规则
```

选择主题：

```text
矛盾纠纷移交提醒 / dxpt_transfer_reminder
```

当前前端已提供预设按钮：

```text
填入派出所接收规则
```

点击后会自动填入推荐值。

推荐配置：

```text
规则名称：按派出所匹配接收人
规则类型：字段匹配并带上级单位
源字段：sspcsdm
目标字段：sspcsdm
优先级：100
手机号字段：mobile
固定手机号：留空
联系人过滤 JSON：{}
启用规则：是
包含本级：是
包含县级：是
包含市级：否
```

含义：

| 配置 | 含义 |
|---|---|
| `源字段 = sspcsdm` | 从数据源结果行里取派出所代码 |
| `目标字段 = sspcsdm` | 到联系人表里按派出所代码匹配 |
| `包含本级` | 通知本派出所联系人 |
| `包含县级` | 同时通知县区或分局联系人 |
| `包含市级` | 同时通知市局联系人，一般先不勾 |

如果只想通知派出所，不通知县区分局：

```text
包含本级：是
包含县级：否
包含市级：否
```

如果希望市局也收到：

```text
包含市级：是
```

联系人是否能匹配成功，取决于 `联系人管理` 中是否有对应的 `sspcsdm`、`county_code`、`city_code` 以及有效手机号。

## 5. 短信模板配置

进入：

```text
短信模板 -> 模板编辑
```

当前前端已提供预设按钮：

```text
填入矛盾纠纷模板
```

推荐配置：

```text
模板名称：矛盾纠纷移交提醒
模板编码：dxpt_transfer_template
模板内容：{message_text}
启用模板：是
```

因为视图已经拼好了完整短信正文，所以模板只需要：

```text
{message_text}
```

视图生成的短信类似：

```text
基础管控中心提醒云城分局某某派出所【纠纷名称】：某某纠纷；24小时内未移交；【纠纷登记时间】：2026-01-01 09:00:00；【纠纷类型】：邻里纠纷；【发生时间】：2026-01-01 08:30:00
```

如果后续要调整短信文案，有两种方式：

```text
1. 改视图里的 message_text 拼接逻辑
2. 改短信模板，让视图只输出变量字段
```

当前推荐先使用 `{message_text}`，配置最简单，也最稳定。

## 6. 如何测试数据是否连通

建议按下面顺序测试。

### 6.1 测试视图是否正常

先在 Kingbase 客户端执行：

```sql
SELECT count(*) AS total_count
FROM stdata.v_dxpt_mdjf_transfer_monitor
WHERE registered_at >= '2026-01-01';
```

再看各阶段数量：

```sql
SELECT
  transfer_status_code,
  transfer_status,
  count(*) AS cnt,
  min(registered_at) AS min_registered_at,
  max(registered_at) AS max_registered_at
FROM stdata.v_dxpt_mdjf_transfer_monitor
WHERE registered_at >= '2026-01-01'
GROUP BY transfer_status_code, transfer_status
ORDER BY transfer_status_code;
```

查看最近 72 小时内是否有数据：

```sql
SELECT
  source_event_id,
  business_no,
  station_name,
  registered_at,
  pending_hours,
  transfer_status,
  transfer_status_code
FROM stdata.v_dxpt_mdjf_transfer_monitor
WHERE registered_at >= now() - interval '3 day'
ORDER BY registered_at DESC
LIMIT 50;
```

如果这条没有数据，说明当前库里没有最近 72 小时内的记录，系统按 `u12/u24/u36/u48/u72` 查询时也会没有数据。

本地测试库如果都是历史数据，可以临时查：

```sql
SELECT
  source_event_id,
  station_name,
  registered_at,
  pending_hours,
  transfer_status,
  transfer_status_code
FROM stdata.v_dxpt_mdjf_transfer_monitor
WHERE transfer_status_code = 'u72plus'
ORDER BY registered_at DESC
LIMIT 50;
```

### 6.2 测试系统能否连接 Kingbase

确认 `.env` 至少有一个数据库连接：

```env
THEME_DB_URL=postgresql+psycopg2://用户名:密码@Kingbase地址:端口/数据库名
```

或者：

```env
DATABASE_URL=postgresql+psycopg2://用户名:密码@Kingbase地址:端口/数据库名
```

Docker 部署后修改 `.env` 需要重启：

```bash
sudo docker compose down
sudo docker compose up -d --force-recreate
```

查看容器是否启动：

```bash
sudo docker ps
sudo docker logs -f jcgkzx-autotask
```

### 6.3 测试数据源演练

进入：

```text
数据源管理 -> 运行测试/演练
```

建议先点演练，不要直接正式发送。

演练后查看：

```text
运行历史 -> 数据源运行历史 -> 详情
```

重点看：

```text
状态是否 success
fetched_count 是否大于 0
matched_count 是否大于 0
错误信息是否为空
```

如果 `fetched_count = 0`，优先检查：

```text
1. 视图是否有数据
2. source_config 的 start_date 是否太晚
3. SQL 是否只过滤了 u12/u24/u36/u48/u72，而本地库只有 u72plus
4. THEME_DB_URL 是否连到了正确库
```

如果本地只想验证流程，可以临时把数据源 SQL 改成：

```sql
AND transfer_status_code IN ('u12', 'u24', 'u36', 'u48', 'u72', 'u72plus')
```

### 6.4 测试主题命中

进入：

```text
命中结果
```

查看是否生成结果。

重点检查详情里的原始结果 JSON 是否包含：

```text
source_event_id
transfer_status_code
sspcsdm
message_text
```

如果有 `fetched_count`，但没有命中结果，优先检查：

```text
1. 主题是否启用
2. 主题编码是否是 dxpt_transfer_reminder
3. 数据源 queries[0].topic_codes 是否包含 dxpt_transfer_reminder
4. 主题 filter_expr 是否把当前 transfer_status_code 过滤掉
```

### 6.5 测试接收人匹配

如果命中结果里 `receiver_mobiles` 为空，说明没有匹配到接收人。

优先检查：

```text
1. 数据行里 sspcsdm 是否有值
2. 联系人管理里是否有相同 sspcsdm 的联系人
3. 联系人手机号是否有效且状态为 active
4. 接收规则是否启用
5. 接收规则源字段是否为 sspcsdm
6. 接收规则目标字段是否为 sspcsdm
```

如果你希望未匹配派出所联系人时通知县区联系人，需要：

```text
包含县级：是
```

并确保联系人表里有县级或分局联系人。

### 6.6 测试短信内容

进入：

```text
短信模板 -> 模板编辑 -> 本地预览
```

模板内容应为：

```text
{message_text}
```

变量预览 JSON 可以填：

```json
{
  "message_text": "基础管控中心提醒云城分局某某派出所【纠纷名称】：示例纠纷；24小时内未移交；【纠纷登记时间】：2026-01-01 09:00:00；【纠纷类型】：邻里纠纷；【发生时间】：2026-01-01 08:30:00"
}
```

预览结果应该直接显示完整短信正文。

### 6.7 正式发送前检查

正式发送前建议确认：

```text
1. Oracle 短信平台连接配置正确
2. 主题去重模式是 permanent
3. 去重键模板是 {source_event_id}:{transfer_status_code}
4. 数据源 SQL 没有误包含不需要提醒的 done 状态
5. 联系人规则不会把不该通知的层级包含进去
```

第一次正式运行建议先只保留较小 `limit`：

```json
{
  "query_params": {
    "start_date": "2026-01-01",
    "limit": 50
  }
}
```

确认短信发送记录正常后，再恢复：

```json
{
  "query_params": {
    "start_date": "2026-01-01",
    "limit": 5000
  }
}

```

## 7. 常见问题

### 7.1 视图查出来全是 u72plus

这是正常现象，说明当前库里的数据都已经超过 72 小时。

可以用下面 SQL 查看最近 3 天是否有数据：

```sql
SELECT count(*) AS recent_count
FROM stdata.v_dxpt_mdjf_transfer_monitor
WHERE registered_at >= now() - interval '3 day';
```

如果结果是 0，说明测试库没有最近数据。

### 7.2 数据源运行成功但没有结果

常见原因是数据源 SQL 只查 `u12` 到 `u72`，但库里只有 `u72plus`。

测试时可以临时加入：

```text
u72plus
```

生产是否加入，按业务要求决定。

### 7.3 提示 CONCAT 类型错误

不要使用 `CONCAT(...)` 拼短信内容，KingbaseV8 对混合类型可能解析失败。

推荐使用：

```sql
CAST('文字' AS text) || COALESCE(字段, CAST('' AS text))
```

本文视图 SQL 已经采用这种写法。

### 7.4 重复发送如何控制

本方案通过：

```text
{source_event_id}:{transfer_status_code}
```

控制阶段去重。

同一事件同一阶段不会重复发送；进入下一阶段后会生成新的去重键，可以再次发送。

### 7.5 不想提醒超 72 小时怎么办

数据源 SQL 和主题过滤 JSON 都不要包含：

```text
u72plus
```

### 7.6 想提醒超 72 小时怎么办

数据源 SQL 增加：

```text
u72plus
```

主题过滤 JSON 也增加：

```json
"u72plus"
```
