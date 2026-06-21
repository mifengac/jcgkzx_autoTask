# 矛盾纠纷移交提醒单主题配置

本文档说明矛盾纠纷移交提醒的推荐配置方式：一个 Kingbase 数据源、一个主题、一个接收规则、一个短信模板。

## 设计目标

原来的阶段拆分方式需要分别配置 `12小时`、`24小时`、`36小时`、`48小时`、`72小时` 多个主题和多条接收规则。推荐改为单主题：

```text
Kingbase 视图
  -> kingbase_multi_sql 数据源
  -> dxpt_transfer_reminder 主题
  -> 一条按 sspcsdm 匹配的接收规则
  -> 一个 {message_text} 短信模板
```

同一事件在不同阶段是否重发，由主题去重键控制：

```text
{source_event_id}:{transfer_status_code}
```

最终写入 Oracle 短信去重的 `eid` 形如：

```text
dxpt_transfer_reminder:DXPT-001:u12
dxpt_transfer_reminder:DXPT-001:u24
```

这样同一事件同一阶段不会重复发送，进入下一阶段后可以再次发送。

## 视图要求

`stdata.v_dxpt_mdjf_transfer_monitor` 至少需要输出以下字段：

```text
source_event_id
business_no
station_code
transfer_status
transfer_status_code
registered_at
message_text
```

`transfer_status_code` 建议取值：

```text
u12
u24
u36
u48
u72
u72plus
```

如果当前只监测到 72 小时，数据源 SQL 可只保留 `u12` 到 `u72`。

## 前端预设

当前前端已增加四个预设按钮：

```text
数据源管理 -> 配置编辑 -> 填入矛盾纠纷单主题配置
短信模板 -> 模板编辑 -> 填入矛盾纠纷模板
主题管理 -> 主题配置 -> 填入矛盾纠纷单主题配置
主题管理 -> 接收规则 -> 填入派出所接收规则
```

使用预设后仍可手工修改。预设只负责填表，不会自动提交保存。

## 数据源预设

数据源类型使用：

```text
kingbase_multi_sql
```

数据源配置只包含一条 SQL：

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

如果要包含超 72 小时，增加 `u72plus`：

```sql
AND transfer_status_code IN ('u12', 'u24', 'u36', 'u48', 'u72', 'u72plus')
```

## 主题预设

主题建议：

```text
主题名称：矛盾纠纷移交提醒
主题编码：dxpt_transfer_reminder
去重模式：永久不重发
去重键模板：{source_event_id}:{transfer_status_code}
```

命中过滤 JSON：

```json
{
  "field": "transfer_status_code",
  "op": "in",
  "value": ["u12", "u24", "u36", "u48", "u72"]
}
```

## 接收规则预设

```text
规则名称：按派出所匹配接收人
规则类型：字段匹配并带上级单位
源字段：sspcsdm
目标字段：sspcsdm
手机号字段：mobile
包含本级：是
包含县级：是
包含市级：否
```

如果不需要县级联系人收到提醒，可取消 `包含县级`。

## 短信模板预设

模板内容：

```text
{message_text}
```

短信正文由视图中的 `message_text` 生成，后续要改文案时优先改视图或模板。
