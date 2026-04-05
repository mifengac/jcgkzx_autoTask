# 主题源与主题最终配置清单

这三套方案共用同一个数据源 `警情监测`，只是主题过滤条件不同。

## 公共数据源配置

先在“数据源”里录入 1 条公共数据源，后面三个主题都复用它。

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
- 每次数据源执行时，都会抓最近 3 天的 `/dsjfx/case/list` 数据。
- `page_size=5000` 的意思是尽量大页拉取，减少分页请求次数。
- `base_params` 除时间相关参数外先保持空，由主题层做二次过滤。
- 主题本身没有单独定时器，它跟着数据源一起运行。

## 方案一：清明涉林地/坟地警情

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

### 主题接收规则

新建 1 条“主题接收规则”，录入时这样填：

- `rule_name`：`清明涉林地/坟地固定接收人`
- `rule_type`：`fixed_receivers`
- `source_field`：留空
- `target_match_field`：保持默认 `sspcsdm`
- `priority`：`100`
- `enabled`：勾选
- `fixed_receivers`：一行一个手机号，或用逗号分隔
- `filter_json`：`{}`

说明：
- `fixed_receivers` 模式下，`source_field` 不参与计算。
- `filter_json` 也不做限制，留空即可。

### 短信模板

短信模板直接录入下面这段：

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
- `命中关键字` 现在会自动输出成 `字段标签→命中值`。
- 例如 `caseContents` 命中 `坟地`，短信里就是 `命中关键字：报警内容→坟地`。

## 方案二：精神类警情

### 主题配置

- `theme_name`：`精神类警情`
- `theme_code`：`mental_case_jq`
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

### 主题接收规则

新建 1 条“主题接收规则”，录入时这样填：

- `rule_name`：`精神类警情固定接收人`
- `rule_type`：`fixed_receivers`
- `source_field`：留空
- `target_match_field`：保持默认 `sspcsdm`
- `priority`：`100`
- `enabled`：勾选
- `fixed_receivers`：一行一个手机号，或用逗号分隔
- `filter_json`：`{}`

### 短信模板

短信模板直接录入下面这段：

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
- 如果 `caseContents` 命中 `精神障碍`，短信里就是 `命中关键字：报警内容→精神障碍`。

## 方案三：扬言极端警情

### 主题配置

- `theme_name`：`扬言极端警情`
- `theme_code`：`yyjd_jq`
- `priority`：`100`
- `dedup_mode`：`permanent`
- `dedup_key_template`：`{event_key}`
- `message_template`：见下方短信模板

说明：
- 这一版沿用 `jingqing_fenxi` 的关键词二次过滤思路，只做报警内容和处警情况的关键词命中。
- `dedup_key_template` 保持 `{event_key}`，尽量把短信平台 `EID` 长度压低；如果后面还提示超长，就继续缩短 `theme_code`。
- 第一版先不加分局、派出所等额外维度，避免把命中范围收得过紧。

`filter_expr` 直接录入下面这段：

```json
{
  "any": [
    {
      "field": "caseContents",
      "op": "contains_any",
      "value": [
        "报复社会", "杀人", "放火", "爆炸", "投毒", "持刀", "砍人", "捅人",
        "威胁", "恐吓", "扬言", "同归于尽", "自杀", "轻生",
        "极端言论", "极端行为", "暴力倾向"
      ]
    },
    {
      "field": "replies",
      "op": "contains_any",
      "value": [
        "报复社会", "杀人", "放火", "爆炸", "投毒", "持刀", "砍人", "捅人",
        "威胁", "恐吓", "扬言", "同归于尽", "自杀", "轻生",
        "极端言论", "极端行为", "暴力倾向"
      ]
    }
  ]
}
```

### 主题接收规则

新建 1 条“主题接收规则”，录入时这样填：

- `rule_name`：`扬言极端警情固定接收人`
- `rule_type`：`fixed_receivers`
- `source_field`：留空
- `target_match_field`：保持默认 `sspcsdm`
- `priority`：`100`
- `enabled`：勾选
- `fixed_receivers`：一行一个手机号，或用逗号分隔
- `filter_json`：`{}`

说明：
- `fixed_receivers` 模式下，`source_field` 不参与计算。
- `filter_json` 也不做限制，留空即可。

### 短信模板

短信模板直接录入下面这段：

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
- 如果 `caseContents` 命中 `扬言放火`，短信里就是 `命中关键字：报警内容→扬言放火`。
- 如果 `replies` 命中 `威胁`，短信里就是 `命中关键字：处警情况→威胁`。
- `alarmTime` 是源数据里的报警时间；如果你想打印另一列 `callTime`，可以直接在模板里用 `{callTime}`。

## 录入顺序

1. 先录入公共数据源 `警情监测`。
2. 再录入 `清明涉林地/坟地警情` 主题和它的固定接收规则。
3. 再录入 `精神类警情` 主题和它的固定接收规则。
4. 再录入 `扬言极端警情` 主题和它的固定接收规则。
5. 最后分别点“演练”，确认短信模板和接收手机号都正确。

## 补充说明

- 数据源每 10 分钟跑一次，近 3 天的数据会在每次运行时重新拉取。
- 主题没有单独的定时轮询，它跟着数据源一起执行。
- 如果多个关键词都命中，系统会按 `filter_expr` 里从前到后的顺序，取第一个命中的关键词来展示。
- 现在 `命中关键字` 的格式已经统一成 `字段标签→命中值`，适合直接给运维和值班人员看。
- 三个主题都可以挂同一个 `警情监测` 数据源，执行时分别按自己的关键词过滤。
