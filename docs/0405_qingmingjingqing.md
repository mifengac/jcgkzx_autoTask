# 主题源与主题最终配置清单

下面这些主题方案共用同一个数据源 `警情监测`，只是主题过滤条件不同。
数据源每 10 分钟跑一次，抓最近 3 天的数据，然后让各个主题分别做二次过滤。

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

## 五、方案四：黄赌打架警情

### 主题配置

- `theme_name`：`黄赌打架警情`
- `theme_code`：`huangdu_dajia_jq`
- `priority`：`100`
- `dedup_mode`：`permanent`
- `dedup_key_template`：`{event_key}`

`filter_expr` 录入下面这段，其中 `value` 里的代码列表要先按“列表生成规则”生成后再填入：

```json
{
  "field": "newOriCharaSubclass",
  "label": "原始警情细类",
  "op": "in",
  "value": [
    "09020100",
    "09020000",
    "02051899",
    "02051809",
    "02051808",
    "02051807",
    "02051806",
    "02051805",
    "02051804",
    "02051803",
    "02051802",
    "02051801",
    "02051800",
    "01051200",
    "01051199",
    "01051104",
    "01051103",
    "01051102",
    "01051101",
    "01051100",
    "09019900",
    "09010600",
    "09010500",
    "09010400",
    "09010300",
    "09010200",
    "09010100",
    "09010000",
    "02052099",
    "02052004",
    "02052003",
    "02052002",
    "02052001",
    "02052000",
    "01050499",
    "01050405",
    "02010899",
    "02010803",
    "02010802",
    "02010801",
    "01050102",
    "02010800",
    "01050404",
    "01050403",
    "01050402",
    "01050401",
    "01050400",
    "09029900",
    "09020500",
    "09020400",
    "09020300",
    "09020200",
    "01030300",
    "02031000",
    "02030100"
  ]
}
```

### 列表生成规则

在已登录环境中请求 `/dsjfx/plan/treeViewData`，从返回 JSON 数组中筛选 `pId` 属于下面 3 个值的节点，然后提取这些节点的 `tag` 字段，去重后填入上面的 `value`：

- `251CEE9D26A54E598D568AA9BA0DF463`
- `5BF6A1CA6C3D4ED9896244554A1BA87C`
- `79958C902AE14BBDBB3F1FD9AD6AA3FC`

可直接按下面这个浏览器控制台脚本生成：

```js
const targetPids = new Set([
  "251CEE9D26A54E598D568AA9BA0DF463",
  "5BF6A1CA6C3D4ED9896244554A1BA87C",
  "79958C902AE14BBDBB3F1FD9AD6AA3FC"
]);
const tags = [...new Set(treeData
  .filter(item => targetPids.has(item.pId))
  .map(item => item.tag)
  .filter(Boolean))];
console.log(tags);
```

### 接收规则

- `rule_name`：`黄赌打架警情固定接收人`
- `rule_type`：`fixed_receivers`
- `source_field`：留空
- `target_match_field`：默认 `sspcsdm`
- `priority`：`100`
- `enabled`：勾上
- `fixed_receivers`：一行一个手机号
- `filter_json`：`{}`

### 短信模板

```text
【黄赌打架警情】
报警时间：{alarmTime}
派出所：{duty_dept_name}
警情编号：{case_no}
地点：{occur_address}
报警内容：{case_contents}
处警情况：{replies}
命中关键字：{命中关键字}
```

说明：

- 这个主题主要依赖 `newOriCharaSubclass` 的代码命中。
- 如果短信里要更直观显示分类名称，建议后续在适配层补一个代码到名称的映射字段。

## 六、方案五：未成年人警情

### 主题配置

- `theme_name`：`未成年人警情`
- `theme_code`：`juvenile_case_jq`
- `priority`：`100`
- `dedup_mode`：`permanent`
- `dedup_key_template`：`{event_key}`

`filter_expr` 录入下面这段，其中第一个条件的 `value` 要先按“列表生成规则”生成后再填入：

```json
{
  "all": [
    {
      "field": "newCharaSubclass",
      "label": "警情细类",
      "op": "in",
      "value": [
        "从 /dsjfx/nature/treeNewViewData 中提取的 id 列表"
      ]
    },
    {
      "field": "caseMarkNo",
      "label": "警情标记",
      "op": "contains_any",
      "value": [
        "01020201",
        "0102020101",
        "0102020102",
        "0102020103"
      ]
    }
  ]
}
```

### 列表生成规则

在已登录环境中请求 `/dsjfx/nature/treeNewViewData`，从返回 JSON 数组中筛选 `id` 以 `01` 或 `02` 开头的节点，然后提取这些节点的 `id`，去重后填入上面第一个条件的 `value`。

可直接按下面这个浏览器控制台脚本生成：

```js
const ids = [...new Set(treeData
  .filter(item => /^(01|02)/.test(item.id || ""))
  .map(item => item.id)
  .filter(Boolean))];
console.log(ids);
```

### 接收规则

- `rule_name`：`未成年人警情固定接收人`
- `rule_type`：`fixed_receivers`
- `source_field`：留空
- `target_match_field`：默认 `sspcsdm`
- `priority`：`100`
- `enabled`：勾上
- `fixed_receivers`：一行一个手机号
- `filter_json`：`{}`

### 短信模板

```text
【未成年人警情】
报警时间：{alarmTime}
派出所：{duty_dept_name}
警情编号：{case_no}
地点：{occur_address}
报警内容：{case_contents}
处警情况：{replies}
命中关键字：{命中关键字}
```

说明：

- 这个主题要求 `newCharaSubclass` 和 `caseMarkNo` 两个条件同时满足。
- `caseMarkNo` 这里使用 `contains_any`，兼容单值和逗号拼接字符串两种返回形式。

## 七、方案六：流浪/乞讨警情

### 主题配置

- `theme_name`：`流浪/乞讨警情`
- `theme_code`：`liulang_qitao_jq`
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
      "value": ["流浪", "乞讨"]
    },
    {
      "field": "replies",
      "op": "contains_any",
      "value": ["流浪", "乞讨"]
    }
  ]
}
```

### 接收规则

- `rule_name`：`流浪乞讨警情固定接收人`
- `rule_type`：`fixed_receivers`
- `source_field`：留空
- `target_match_field`：默认 `sspcsdm`
- `priority`：`100`
- `enabled`：勾上
- `fixed_receivers`：一行一个手机号
- `filter_json`：`{}`

### 短信模板

```text
【流浪/乞讨警情】
报警时间：{alarmTime}
派出所：{duty_dept_name}
警情编号：{case_no}
地点：{occur_address}
报警内容：{case_contents}
处警情况：{replies}
命中关键字：{命中关键字}
```

## 八、方案七：出租屋警情

### 主题配置

- `theme_name`：`出租屋警情`
- `theme_code`：`chuzuwu_jq`
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
      "value": ["出租屋", "租赁"]
    },
    {
      "field": "replies",
      "op": "contains_any",
      "value": ["出租屋", "租赁"]
    }
  ]
}
```

### 接收规则

- `rule_name`：`出租屋警情固定接收人`
- `rule_type`：`fixed_receivers`
- `source_field`：留空
- `target_match_field`：默认 `sspcsdm`
- `priority`：`100`
- `enabled`：勾上
- `fixed_receivers`：一行一个手机号
- `filter_json`：`{}`

### 短信模板

```text
【出租屋警情】
报警时间：{alarmTime}
派出所：{duty_dept_name}
警情编号：{case_no}
地点：{occur_address}
报警内容：{case_contents}
处警情况：{replies}
命中关键字：{命中关键字}
```

## 九、录入顺序

1. 先录入公共数据源 `警情监测`。
2. 再录入 `清明涉林地/坟地警情` 主题和固定接收规则。
3. 再录入 `精神类警情` 主题和固定接收规则。
4. 再录入 `扬言极端警情` 主题和固定接收规则。
5. 再录入 `黄赌打架警情`，先从 `/dsjfx/plan/treeViewData` 生成 `tag` 列表，再填入 `filter_expr`。
6. 再录入 `未成年人警情`，先从 `/dsjfx/nature/treeNewViewData` 生成 `id` 列表，再填入 `filter_expr`。
7. 再录入 `流浪/乞讨警情` 和 `出租屋警情`。
8. 最后分别点“演练”，确认每个主题的 `matched_count`、`receiver_mobiles` 和 `send_status` 都符合预期。

## 十、`runtime_config` 到底怎么填

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
