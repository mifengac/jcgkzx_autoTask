# 主题源与主题最终配置清单

这三套方案共用同一个数据源 `警情监测`，只是主题过滤条件不同。  
数据源每 10 分钟跑一次，抓最近 3 天的数据，然后让三个主题分别做二次过滤。

## 一、公共数据源配置

先在“数据源”里录入 1 条公共数据源，后面的 3 个主题都复用它。

- `source_name`：`警情监测`
- `source_code`：`jingqing_monitor`
- `source_type`：`dsjfx_case_list`
- `enabled`：`true`
- `schedule.interval_value`：`10`
- `schedule.interval_unit`：`minute`
- `schedule.timezone`：`Asia/Shanghai`
- `source_config`：见下方 JSON

```json
{
  "credential_ref": {
    "username_env": "LOGIN_USERNAME",
    "password_env": "LOGIN_PASSWORD"
  },
  "login_url": "http://your-dsjfx-host/dsjfx/login",
  "api_url": "http://your-dsjfx-host/dsjfx/case/list",
  "time_range": {
    "mode": "rolling_days",
    "days_back": 3
  },
  "fetch_profile": {
    "page_size": 5000,
    "max_pages": 50
  },
  "base_params": {}
}
```

说明：

- 每次运行都会重新抓近 3 天的 `/dsjfx/case/list` 数据。
- `page_size=5000` 表示尽量用大页拉取，减少分页请求。
- `base_params` 先保持空，由主题层做二次过滤。
- 数据源没有单独的定时任务，跟着调度一起跑。

## 二、方案一：清明涉林地/坟地警情

### 主题配置

- `theme_name`：`清明涉林地/坟地警情`
- `theme_code`：`qingming_selin_fendi_jq`
- `priority`：`100`
- `dedup_mode`：`permanent`
- `dedup_key_template`：`{event_key}`
- `message_template`：见下方短信模板

`filter_expr` 直接录入下面这段：

```json
{
  "any": [
    {
      "field": "caseContents",
      "op": "contains_any",
      "value": [
        "清明", "扫墓", "祭扫", "上坟", "坟地", "坟墓", "墓地", "墓园",
        "坟头", "林地", "山林", "山场", "林区", "林权", "地界", "烧纸", "焚香"
      ]
    },
    {
      "field": "occurAddress",
      "op": "contains_any",
      "value": ["林地", "坟地", "墓地", "墓园", "坟头", "山林", "山场", "林区"]
    },
    {
      "field": "replies",
      "op": "contains_any",
      "value": [
        "已出警", "已到场", "已处置", "已劝离", "已调解", "已平息", "已移交"
      ]
    }
  ]
}
```

### 接收规则

新建 1 条“主题接收规则”，这样填：

- `rule_name`：`清明涉林地/坟地固定接收人`
- `rule_type`：`fixed_receivers`
- `source_field`：留空
- `target_match_field`：保持默认 `sspcsdm`
- `priority`：`100`
- `enabled`：勾上
- `fixed_receivers`：一行一个手机号，或者用逗号分隔
- `filter_json`：`{}`

说明：

- `fixed_receivers` 模式下，`source_field` 不参与计算。
- `filter_json` 先保持空，不额外限制联系人。

### 短信模板

```text
【清明涉林地/坟地警情】
报警时间：{alarmTime}
派出所：{duty_dept_name}
警情编号：{case_no}
地点：{occur_address}
报警内容：{case_contents}
处警情况：{replies}
命中关键字：{命中关键字}
```

说明：

- `{alarmTime}` 是源数据里的报警时间。
- `{命中关键字}` 会自动显示成 `字段标签→命中值`，例如 `报警内容→坟地`。
- 如果你想显示 `callTime`，也可以改成 `{callTime}`。

## 三、方案二：精神类警情

### 主题配置

- `theme_name`：`精神类警情`
- `theme_code`：`mental_case_jq`
- `priority`：`100`
- `dedup_mode`：`permanent`
- `dedup_key_template`：`{event_key}`

`filter_expr` 录入下面这段：

```json
{
  "any": [
    {
      "field": "caseContents",
      "op": "regex",
      "value": "精神病|精神障碍|精神异常|精神发病|犯病|肇事肇祸"
    },
    {
      "field": "replies",
      "op": "regex",
      "value": "精神病|精神障碍|精神异常|精神发病|犯病|肇事肇祸"
    }
  ]
}
```

### 接收规则

- `rule_name`：`精神类警情固定接收人`
- `rule_type`：`fixed_receivers`
- `source_field`：留空
- `target_match_field`：默认 `sspcsdm`
- `priority`：`100`
- `enabled`：勾上
- `fixed_receivers`：一行一个手机号
- `filter_json`：`{}`

### 短信模板

```text
【精神类警情】
报警时间：{alarmTime}
派出所：{duty_dept_name}
警情编号：{case_no}
地点：{occur_address}
报警内容：{case_contents}
处警情况：{replies}
命中关键字：{命中关键字}
```

说明：

- 如果 `caseContents` 命中 `精神障碍`，短信里会显示 `命中关键字：报警内容→精神障碍`。

## 四、方案三：扬言极端警情

### 主题配置

- `theme_name`：`扬言极端警情`
- `theme_code`：`yyjd_jq`
- `priority`：`100`
- `dedup_mode`：`permanent`
- `dedup_key_template`：`{event_key}`

`filter_expr` 录入下面这段：

```json
{
  "any": [
    {
      "field": "caseContents",
      "op": "contains_any",
      "value": [
        "报复社会", "杀人", "放火", "爆炸", "投毒", "持刀", "砍人", "捅人",
        "威胁", "恐吓", "扬言", "极端言论", "极端行为", "暴力倾向"
      ]
    },
    {
      "field": "replies",
      "op": "contains_any",
      "value": [
        "报复社会", "杀人", "放火", "爆炸", "投毒", "持刀", "砍人", "捅人",
        "威胁", "恐吓", "扬言", "极端言论", "极端行为", "暴力倾向"
      ]
    }
  ]
}
```

### 接收规则

- `rule_name`：`扬言极端警情固定接收人`
- `rule_type`：`fixed_receivers`
- `source_field`：留空
- `target_match_field`：默认 `sspcsdm`
- `priority`：`100`
- `enabled`：勾上
- `fixed_receivers`：一行一个手机号
- `filter_json`：`{}`

### 短信模板

```text
【扬言极端警情】
报警时间：{alarmTime}
派出所：{duty_dept_name}
警情编号：{case_no}
地点：{occur_address}
报警内容：{case_contents}
处警情况：{replies}
命中关键字：{命中关键字}
```

说明：

- 这一版只做关键词二次过滤，不再加额外的分局、派出所维度条件。
- `dedup_key_template` 继续保持 `{event_key}`，先把 Oracle `EID` 长度控制住。

## 五、录入顺序

1. 先录入公共数据源 `警情监测`。
2. 再录入 `清明涉林地/坟地警情` 主题和固定接收规则。
3. 再录入 `精神类警情` 主题和固定接收规则。
4. 再录入 `扬言极端警情` 主题和固定接收规则。
5. 最后分别点“演练”，确认短信模板和接收手机号都正确。

## 六、`runtime_config` 到底怎么填

`runtime_config` 不是 `.env`，也不是把账号密码硬编码进脚本 ZIP。  
它是“任务级运行配置 JSON”，前端会把它传给脚本的 `run(context)`。

### `0123_dxpt_ceshi.py`

这个脚本的“运行配置 JSON”只填下面这一层：

```json
{
  "kingbase_host": "your-kingbase-host",
  "kingbase_port": 5432,
  "kingbase_dbname": "your-db",
  "kingbase_user": "your-user",
  "kingbase_password": "your-password",
  "dxpt_start_date": "2026-04-01",
  "limit": 0
}
```

### `zq_kshddpt_dsjfx_jq.py`

这个脚本也一样，**运行配置 JSON 只填 `runtime_config` 这一层**，不要把 `task_name`、`script_id`、`schedule` 这些外层字段一起塞进去。

```json
{
  "zq_login_url": "http://68.253.2.111/dsjfx/login",
  "zq_login_username": "your-login-user",
  "zq_login_password": "your-login-password",
  "zq_api_url": "http://68.253.2.111/dsjfx/case/list",
  "zq_db_host": "your-kingbase-host",
  "zq_db_port": 5432,
  "zq_db_name": "your-db",
  "zq_db_user": "your-user",
  "zq_db_password": "your-password",
  "zq_db_schema": "ywdata",
  "zq_begin_days_ago": 3,
  "zq_page_size": 99999,
  "zq_page_num": 1
}
```

说明：

- `zq_kshddpt_dsjfx_jq.py` 只做同步，不发短信，所以不需要模板和接收规则。
- `runtime_config` 里只放它运行需要的登录、接口、数据库参数即可。

