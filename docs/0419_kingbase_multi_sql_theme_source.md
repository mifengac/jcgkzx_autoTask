# KingbaseV8 多 SQL 主题数据源配置

## 1. 用途

`kingbase_multi_sql` 用于一个 KingbaseV8/PostgreSQL 兼容数据源下配置多条只读 SQL。系统运行该数据源时只创建一个数据库连接，按配置顺序执行多条 SQL，并把每条 SQL 的结果只交给绑定的主题处理。

适合类似矛盾纠纷提醒这类场景：

- 同一个 KingbaseV8 库
- 不同主题需要不同 SQL 或不同状态阶段
- 希望一次调度内复用同一个数据库连接
- 希望主题之间独立去重

## 2. 连接环境变量

`kingbase_multi_sql` 不需要在页面配置数据库连接参数，默认从环境变量读取连接串，优先级如下：

1. `THEME_DB_URL`
2. `DATABASE_URL`

建议优先配置 `THEME_DB_URL`，这样主题数据源库可以和平台自身数据库分开；如果不配置 `THEME_DB_URL`，系统会复用当前平台数据库的 `DATABASE_URL`。

```env
DATABASE_URL=postgresql+psycopg2://platform_user:password@host:port/platform_db
THEME_DB_URL=postgresql+psycopg2://theme_user:password@host:port/theme_db
```

如果密码中包含 `@`、`#`、`:`、`/` 等特殊字符，需要先做 URL 编码。

## 3. 数据源配置示例

数据源类型选择：

```text
kingbase_multi_sql
```

`source_config` 示例：

```json
{
  "time_range": {
    "mode": "rolling_hours",
    "hours_back": 24
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
      "query_code": "dxpt_u24",
      "topic_codes": ["dxpt_u24"],
      "query": "SELECT source_event_id, business_no, station_code, dispute_name, dispute_type, transfer_status, transfer_status_code, message_text FROM dxpt_view WHERE transfer_status_code = :status_code",
      "query_params": {
        "status_code": "u24"
      }
    },
    {
      "query_code": "dxpt_u36",
      "topic_codes": ["dxpt_u36"],
      "query": "SELECT source_event_id, business_no, station_code, dispute_name, dispute_type, transfer_status, transfer_status_code, message_text FROM dxpt_view WHERE transfer_status_code = :status_code",
      "query_params": {
        "status_code": "u36"
      }
    }
  ]
}
```

## 4. 配置字段

| 字段 | 说明 |
|---|---|
| `queries` | 多条 SQL 配置，必须是非空数组 |
| `queries[].query_code` | SQL 编码，同一数据源内必须唯一 |
| `queries[].topic_codes` | 该 SQL 结果允许进入的主题编码，必须非空 |
| `queries[].query` | 单条只读 `SELECT` 或 `WITH` SQL |
| `queries[].query_params` | 当前 SQL 的额外参数 |
| `time_range` | 全局时间窗口，可被单条 SQL 覆盖 |
| `fetch_profile` | 全局抓取设置，可被单条 SQL 覆盖 |
| `field_map` | 全局字段映射，可被单条 SQL 覆盖 |

每条 SQL 会自动获得这些参数：

- `begin_time`
- `end_time`
- `begin_time_text`
- `end_time_text`
- `now_time`
- `now_time_text`
- `limit`
- `source_code`

## 5. 返回字段

适配器会把每条 SQL 的每一行标准化为主题引擎可用的数据，并额外补充：

| 字段 | 说明 |
|---|---|
| `source_query_code` | 当前 SQL 的 `query_code` |
| `source_query_index` | 当前 SQL 在配置中的顺序，从 1 开始 |
| `target_topic_codes` | 当前 SQL 绑定的主题编码列表 |
| `event_key` | 标准事件 key |
| `case_no` | 案件或业务编号 |
| `sspcsdm` / `dwdm` | 单位或派出所代码 |
| `message_vars` | 短信模板变量 |
| `raw_fields` | 原始 SQL 返回字段 |

主题执行时，如果数据行包含 `target_topic_codes`，系统只会让对应 `theme_code` 的主题继续处理该行。

## 6. DXPT 推荐配置

为矛盾纠纷未移交提醒建议每个阶段一个主题：

| 主题编码 | 说明 |
|---|---|
| `dxpt_u12` | 12小时内未移交 |
| `dxpt_u24` | 24小时内未移交 |
| `dxpt_u36` | 36小时内未移交 |
| `dxpt_u48` | 48小时内未移交 |
| `dxpt_u72` | 72小时内未移交 |
| `dxpt_u72plus` | 超出72小时仍未移交 |

每个主题建议：

```json
{
  "dedup_mode": "permanent",
  "dedup_key_template": "{source_event_id}"
}
```

接收规则建议：

| 配置项 | 建议值 |
|---|---|
| 规则类型 | 字段匹配，或字段匹配并包含上级 |
| 来源字段 | `sspcsdm` |
| 联系人匹配字段 | `sspcsdm` |

## 7. 去重效果

主题链路最终写入 Oracle 短信队列时会使用：

```text
{theme_code}:{dedup_key}
```

如果 `dedup_key_template = "{source_event_id}"`，同一个事件在不同阶段的 Oracle `eid` 会不同：

| 原始事件 | 主题 | Oracle eid |
|---|---|---|
| `YW001` | `dxpt_u24` | `dxpt_u24:YW001` |
| `YW001` | `dxpt_u36` | `dxpt_u36:YW001` |
| `YW001` | `dxpt_u72plus` | `dxpt_u72plus:YW001` |

这样同一事件同一阶段同一手机号只发一次；状态升级到新阶段后会重新发送一次。

## 8. 验证建议

首次配置后建议先使用演练运行，确认：

- 数据源运行成功且抓取数量符合预期
- 主题命中数量与 SQL 绑定关系一致
- 结果详情中的 `target_topic_codes`、`source_query_code` 正确
- 接收规则能通过 `sspcsdm` 匹配到联系人
- 发送日志中的 `oracle_eid` 符合 `{theme_code}:{source_event_id}`
