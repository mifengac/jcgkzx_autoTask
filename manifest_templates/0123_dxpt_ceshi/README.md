# 0123_dxpt_ceshi 自定义任务配置教程

## 1. 脚本用途

该脚本用于监测矛盾纠纷数据中仍未移交的记录。脚本只负责查询人大金仓、过滤命中数据、返回系统标准字段；短信模板渲染、接收人匹配、短信去重、Oracle 短信入队和发送日志都由当前系统统一处理。

## 2. 上传 ZIP 包

ZIP 根目录需要包含：

- `0123_dxpt_ceshi.py`
- `manifest.json`

`manifest.json` 使用本目录示例：

```json
{
  "script_code": "0123_dxpt_ceshi",
  "script_name": "DXPT SMS Task",
  "script_type": "python_zip",
  "entry_file": "0123_dxpt_ceshi.py",
  "entry_func": "run"
}
```

系统上传表单建议填写：

- 脚本名称：`矛盾纠纷未移交短信提醒`
- 脚本编码：`0123_dxpt_ceshi`
- 入口文件：`0123_dxpt_ceshi.py`
- 入口函数：`run`

## 3. 自定义任务运行配置

在任务的运行配置中填写 JSON：

```json
{
  "kingbase_host": "127.0.0.1",
  "kingbase_port": 54321,
  "kingbase_dbname": "数据库名",
  "kingbase_user": "用户名",
  "kingbase_password": "密码",
  "dxpt_start_date": "2026-01-01",
  "only_untransferred": true,
  "dedup_with_transfer_status": true,
  "limit": 0
}
```

字段说明：

| 字段 | 必填 | 说明 |
|---|---:|---|
| `kingbase_host` | 是 | 人大金仓地址 |
| `kingbase_port` | 是 | 人大金仓端口 |
| `kingbase_dbname` | 是 | 人大金仓数据库名 |
| `kingbase_user` | 是 | 人大金仓账号 |
| `kingbase_password` | 是 | 人大金仓密码 |
| `dxpt_start_date` | 否 | 查询登记时间起点，默认 `2026-01-01` |
| `only_untransferred` | 否 | 默认 `true`，只返回“未移交”记录 |
| `dedup_with_transfer_status` | 否 | 默认 `true`，按“事件 + 移交状态阶段”去重 |
| `limit` | 否 | 限制本次返回条数，`0` 表示不限制 |

## 4. 短信模板配置

任务绑定了系统短信模板时，实际发送内容以系统短信模板为准；脚本里的 `message_text` 只是未绑定模板时的兜底内容。

推荐短信模板：

```text
基础管控中心提醒{branch_name}{station_name}【纠纷名称】：{dispute_name}；{transfer_status}；【纠纷登记时间】：{registered_at}；【纠纷类型】：{dispute_type}；【发生时间】：{happened_at}
```

可用变量包括：

| 变量 | 说明 |
|---|---|
| `{business_no}` | 业务流水号 |
| `{systemid}` | 系统编号 |
| `{source_event_id}` | 原始事件去重 ID |
| `{dedup_status_code}` | 移交状态短码 |
| `{station_code}` | 派出所代码 |
| `{branch_name}` | 分局名称 |
| `{station_name}` | 派出所名称 |
| `{dispute_name}` | 纠纷名称 |
| `{dispute_type}` | 纠纷类型 |
| `{transfer_status}` | 移交状态 |
| `{registered_at}` | 纠纷登记时间 |
| `{happened_at}` | 发生时间 |

## 5. 接收规则配置

如需按派出所联系人发送，接收规则建议配置为：

| 配置项 | 建议值 |
|---|---|
| 规则类型 | 字段匹配，或字段匹配并包含上级 |
| 来源字段 | `sspcsdm` |
| 联系人匹配字段 | `sspcsdm` |
| 是否启用 | 启用 |

脚本返回结果中同时包含 `sspcsdm` 和 `dwdm`，两者当前都等于派出所代码。一般优先使用 `sspcsdm`。

## 6. 去重逻辑

当前系统发送短信时，会用 Oracle 短信表中的 `eid + mobile` 判断是否重复。脚本开启 `dedup_with_transfer_status` 后，会把系统使用的 `event_key` 生成成：

```text
DXPT:{原始事件ID}:{移交状态短码}
```

例如：

| 原始事件ID | 移交状态 | 系统 event_key / Oracle eid |
|---|---|---|
| `YW001` | `24小时内未移交` | `DXPT:YW001:u24` |
| `YW001` | `36小时内未移交` | `DXPT:YW001:u36` |
| `YW001` | `超出72小时仍未移交` | `DXPT:YW001:u72plus` |

这样同一个事件、同一个手机号、同一个状态阶段只会发送一次；当 `transfer_status` 从 `24小时内未移交` 变化为 `36小时内未移交` 时，会生成新的 `event_key`，系统会重新发送一次。

常用状态短码：

| transfer_status | 短码 |
|---|---|
| `12小时内未移交` | `u12` |
| `24小时内未移交` | `u24` |
| `36小时内未移交` | `u36` |
| `48小时内未移交` | `u48` |
| `72小时内未移交` | `u72` |
| `超出72小时仍未移交` | `u72plus` |

如果需要临时恢复旧行为，将任务运行配置中的 `dedup_with_transfer_status` 改为 `false`。此时系统只按原始事件 ID 去重。

## 7. 验证建议

首次启用建议先用“试运行”执行一次，确认：

- 任务结果中 `event_key` 类似 `DXPT:YW001:u24`
- 任务结果中 `sspcsdm` 能匹配到联系人
- 短信内容使用的是系统绑定的短信模板
- 发送日志中重复状态符合预期
