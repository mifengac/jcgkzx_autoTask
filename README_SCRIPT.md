# 平台导入脚本规范

## 1. 文档目的

本文档说明当前平台导入脚本时必须遵守的规范。

目标是让不同类型的脚本都能以统一方式接入平台，包括：

- 短信预警脚本
- 数据同步脚本
- 定时采集脚本

## 2. 平台对脚本的核心要求

平台导入脚本时，不是直接运行任意 Python 文件，而是要求脚本对外暴露统一入口。

当前统一入口规范是：

```python
def run(context: dict) -> list[dict]:
    ...
```

也就是说，平台只认两件事：

1. 能不能找到入口函数 `run`
2. `run` 的返回值是不是 `list[dict]`

如果不满足这两个条件，当前平台就不能直接接入。

## 3. ZIP 包规范

导入平台的脚本必须打成 ZIP 包。

ZIP 根目录至少包含：

- 入口 Python 文件
- `manifest.json`

推荐结构：

```text
your_task.zip
├── manifest.json
├── main.py
└── other_module.py
```

`manifest.json` 最小示例：

```json
{
  "entry_file": "main.py",
  "entry_func": "run",
  "script_type": "python_zip"
}
```

其中：

- `entry_file` 表示入口文件
- `entry_func` 表示入口函数

## 4. context 约定

平台运行脚本时，会给脚本传入一个 `context` 字典。

当前主要包含：

```python
{
  "task": {
    "id": 1,
    "task_name": "任务名称",
    "script_code": "script_code",
    "script_version": "1.0.0"
  },
  "runtime_config": {},
  "trigger": "manual",
  "dry_run": True,
  "now": "2026-03-10T08:00:00"
}
```

脚本应该优先从：

- `context["runtime_config"]`

读取运行参数。

不建议把业务参数继续写死在代码里。

## 5. 返回值规范

脚本必须返回：

```python
list[dict]
```

每个 `dict` 代表一条平台可记录的结果。

平台当前不会理解脚本内部过程，只会记录你返回的这些结果。

所以返回结果要尽量具备业务可解释性。

## 6. 通用字段规范

### 6.1 必须建议提供的字段

虽然平台当前不是所有字段都强制必填，但建议每条结果至少包含：

- `event_id`
- `message_text`

原因：

- `event_id` 用于平台识别这一条结果
- `message_text` 用于直接展示执行摘要或短信正文

如果没有 `event_id`，平台会退化使用：

- `event_key`
- `caseNo`
- `id`
- 或按序号生成

但这不稳定，不建议依赖。

### 6.2 短信任务建议字段

如果脚本是短信预警类脚本，建议返回：

- `event_id`
- `case_no`
- `event_time`
- `sspcsdm`
- `dwdm`
- `xqdm`
- `message_vars`
- `message_text`

其中：

- `message_vars` 用于短信模板渲染
- `sspcsdm` / `dwdm` / `xqdm` 用于发送规则匹配联系人

### 6.3 数据同步任务建议字段

如果脚本是导数类脚本，不发短信，也应返回摘要结果，建议字段：

- `event_id`
- `task_name`
- `target_table`
- `mode`
- `status`
- `fetched_response_count`
- `parsed_record_count`
- `written_record_count`
- `error_message`
- `message_text`
- `start_time`
- `end_time`

这样平台运行记录里就能看出：

- 本次抓到了多少数据
- 解析了多少条
- 写入了多少条
- 是否失败

## 7. 两类脚本的区别

### 7.1 短信任务脚本

职责是：

- 查出事件
- 返回可供规则匹配和模板渲染的数据

它不应该自己发短信。

短信发送应该由平台统一完成。

### 7.2 数据同步脚本

职责是：

- 定时抓数
- 定时写入目标系统
- 把执行摘要返回给平台

它通常不需要：

- 短信模板
- 发送规则
- 联系人匹配

但仍然需要：

- 统一调度
- 统一运行记录
- 统一失败追踪

## 8. 运行参数规范

平台脚本推荐通过 `runtime_config` 接收参数。

例如：

```json
{
  "api_url": "http://example/api",
  "username": "user1",
  "password": "pwd1",
  "db_host": "10.45.100.148",
  "db_port": 54321
}
```

推荐原则：

1. 业务可变参数放 `runtime_config`
2. 脚本内部只保留默认值或兜底值
3. 不要把账号、地址、表名长期写死在源码里

## 9. 错误处理规范

脚本在平台中运行时，推荐遵循以下规则：

1. 能汇总成结果的错误，尽量返回失败摘要
2. 真正无法继续执行时，再抛异常
3. 返回结果里尽量写清楚失败原因

例如导数任务失败摘要：

```python
{
  "event_id": "multi_task_001",
  "task_name": "duty_schedule",
  "status": "failed",
  "error_message": "login failed",
  "message_text": "导数任务失败: duty_schedule, 错误: login failed"
}
```

## 10. 平台兼容性要求

为了能被当前平台直接导入，脚本至少要满足：

1. ZIP 根目录有 `manifest.json`
2. `manifest.json` 指向正确入口文件
3. 入口函数存在
4. 入口函数签名兼容 `run(context)`
5. 返回值是 `list[dict]`

如果不满足其中任意一项，当前平台就不能直接接入。

## 11. 不推荐的写法

下面这些写法不推荐继续使用：

### 11.1 只提供 `main()`，不提供 `run(context)`

这样平台无法统一调用。

### 11.2 直接在脚本内部发短信

这样平台无法统一审计和去重。

### 11.3 只写日志，不返回结构化结果

这样平台虽然知道“脚本跑过了”，但不知道“脚本到底做了什么”。

### 11.4 全部依赖环境变量

这样前端无法真正配置脚本参数。

## 12. 推荐模板

最简单的兼容脚本模板如下：

```python
from typing import Any


def run(context: dict[str, Any]) -> list[dict[str, Any]]:
    runtime_config = context.get("runtime_config") or {}
    value = runtime_config.get("value", "default")

    return [
        {
            "event_id": "demo_001",
            "message_text": f"脚本执行成功: {value}",
            "message_vars": {
                "value": value
            }
        }
    ]


def main() -> None:
    results = run({"runtime_config": {}})
    print(results)


if __name__ == "__main__":
    main()
```

这个模板同时兼容：

- 平台调用
- 本地直接运行

## 13. data_scraper_multi.py 现在属于哪种情况

目前 [data_scraper_multi.py](C:/Users/So/Desktop/doc/02/jcgkzx_autoTask/data_scraper_multi.py) 已经改造成兼容当前平台规范：

- 保留 `main()` 兼容旧运行方式
- 新增 `run(context)` 兼容平台
- 返回 `list[dict]` 执行摘要

这就是后续改造旧脚本的推荐方向：

- 旧逻辑保留
- 新接口补齐
- 对平台输出结构化结果

## 14. 一句话总结

当前平台导入脚本的本质要求只有一句话：

“脚本必须能被平台统一调用，并且必须把执行结果以结构化列表返回给平台。”
