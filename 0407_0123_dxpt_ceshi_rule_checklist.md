# 0123_dxpt_ceshi 规则填写清单

这份清单用于“自定义任务 -> 接收规则”页面，目标是让你照着字段直接录入，不用再对照代码猜字段含义。

## 页面输入框说明

| 页面输入框 | 作用 | 你该怎么填 |
|---|---|---|
| 选择主题/任务 | 绑定这条规则属于哪个主题或任务 | 先选 `0123_dxpt_ceshi` 对应的任务 |
| 规则名称 | 这条规则的名字 | 随便起，建议一看就懂，例如 `0123按派出所发送` |
| 规则类型 | 决定短信号码怎么来 | 三选一：`固定接收人`、`字段直接匹配`、`字段匹配并带上级单位` |
| 源字段 | 从源数据里取哪个字段来匹配 | 只有“字段匹配”类才填，推荐填 `sspcsdm` |
| 目标字段 | 去联系人表里用哪个字段找人 | 推荐填 `sspcsdm` |
| 优先级 | 多条规则同时命中时先用谁 | 数字越小越优先，通常先填 `100` |
| 手机号字段 | 联系人表里哪个字段是手机号 | 一般填 `mobile`，默认就可以 |
| 固定手机号 | 直接写死接收人手机号 | 只有“固定接收人”规则才填，一行一个手机号 |
| 联系人过滤 JSON | 给联系人再加筛选条件 | 一般留 `{}`，只有要限定联系人属性时才填 |
| 启用规则 | 这条规则是否生效 | 要生效就勾上 |
| 包含本级 | 字段匹配时是否包含自己 | 只有“带上级单位”规则才有意义，通常勾上 |
| 包含县级 | 是否把县级单位也带上 | 需要县级一起发就勾上 |
| 包含市级 | 是否把市级单位也带上 | 需要市级一起发就勾上 |

## 3 种规则怎么填

| 规则类型 | 源字段 | 目标字段 | 包含本级 | 包含县级 | 包含市级 | 固定手机号 |
|---|---|---|---|---|---|---|
| 固定接收人 | 留空 | 默认 `sspcsdm` 也行 | 不用管 | 不用管 | 不用管 | 填手机号，一行一个 |
| 字段直接匹配 | 填 `sspcsdm` | `sspcsdm` | 勾上 | 不勾 | 不勾 | 留空 |
| 字段匹配并带上级单位 | 填 `sspcsdm` | `sspcsdm` | 勾上 | 需要就勾 | 需要就勾 | 留空 |

## 以 `0123_dxpt_ceshi.py` 为例

这个脚本返回的结果里，最适合拿来做接收规则匹配的字段是：

- `sspcsdm`
- `dwdm`

但当前规则引擎支持的目标字段只有：

- `sspcsdm`
- `xqdm`
- `county_code`
- `city_code`

所以最稳妥的填写方式是：

- `源字段`：`sspcsdm`
- `目标字段`：`sspcsdm`

## 常见场景

### 1. 只发固定几个手机

- `规则类型` 选 `固定接收人`
- `源字段` 留空
- `固定手机号` 一行一个手机号
- `目标字段` 不用改，默认即可

### 2. 按派出所发送

- `规则类型` 选 `字段直接匹配`
- `源字段` 填 `sspcsdm`
- `目标字段` 选 `sspcsdm`
- `固定手机号` 留空

### 3. 按派出所并带上下级发送

- `规则类型` 选 `字段匹配并带上级单位`
- `源字段` 填 `sspcsdm`
- `目标字段` 选 `sspcsdm`
- `包含本级` 勾上
- `包含县级` 需要就勾
- `包含市级` 需要就勾
- `固定手机号` 留空

## 你可以直接照抄的示例

### 示例 A：固定接收人

```json
{
  "rule_name": "0123固定接收人",
  "rule_type": "fixed_receivers",
  "source_field": "",
  "target_match_field": "sspcsdm",
  "priority": 100,
  "enabled": true,
  "include_self": true,
  "include_county": false,
  "include_city": false,
  "fixed_receivers": [
    "13800000000",
    "13900000000"
  ],
  "filter_json": {}
}
```

### 示例 B：按派出所精确匹配

```json
{
  "rule_name": "0123按派出所匹配",
  "rule_type": "field_match",
  "source_field": "sspcsdm",
  "target_match_field": "sspcsdm",
  "priority": 100,
  "enabled": true,
  "include_self": true,
  "include_county": false,
  "include_city": false,
  "fixed_receivers": [],
  "filter_json": {}
}
```

### 示例 C：按派出所并带上下级

```json
{
  "rule_name": "0123按派出所带上下级",
  "rule_type": "field_match_with_ancestors",
  "source_field": "sspcsdm",
  "target_match_field": "sspcsdm",
  "priority": 100,
  "enabled": true,
  "include_self": true,
  "include_county": true,
  "include_city": true,
  "fixed_receivers": [],
  "filter_json": {}
}
```

## 最后记住两点

- `fixed_receivers` 模式下，`source_field` 不参与计算。
- `target_match_field` 只建议用 `sspcsdm`，不要填 `dwdm`，因为当前规则引擎不支持它。
