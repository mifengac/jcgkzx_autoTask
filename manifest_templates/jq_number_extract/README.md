# jq_number_extract —— 警情文本号码提取（同一业务，两种运行方式）

从警情表 `ywdata.zq_kshddpt_dsjfx_jq` 的报警内容和处警情况中提取身份证、手机号、
固话、车牌、银行卡等号码，写入 `jcgkzx_monitor.zq_jingqing_number_extract`。

同一业务、同一张目标表、同一套提取规则，只是运行方式不同，合并在此文件夹下：

| 子目录 | 原任务名 | 运行方式 | 用途 |
|---|---|---|---|
| `auto/` | `jq_number_extract` | 平台定时任务（`entry_func=run`） | 按 `source_updatetime` 水位线做增量提取 |
| `manual/` | `jq_number_extract_yearly` | 一次性手动 CLI（`entry_func=main`） | 按年份历史回溯，服务端游标流式处理 |

两者各自独立打 zip：zip 根目录放对应子目录里的 `manifest.json` 和入口脚本。
本目录只调整源码组织，不改变平台上传契约。

- 日常增量：`auto/`，配置见 `auto/config/manifest.json`。
- 历史回溯：`manual/`，详见 `manual/docs/README_yearly_extract.md`。
