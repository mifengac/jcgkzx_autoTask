# zq_dsjfx_jingqing —— dsjfx 警情数据同步（同一业务，两种运行方式）

把 dsjfx 系统 `/dsjfx/case/list` 的警情数据灌进 Kingbase 表 `ywdata.zq_kshddpt_dsjfx_jq`。
同一业务、同一张表、同一套字段，只是运行方式不同，合并在此文件夹下：

| 子目录 | 原任务名 | 运行方式 | 用途 |
|---|---|---|---|
| `auto/` | `zq_kshddpt_dsjfx_jq` | 平台定时任务（`entry_func=run`） | 每天滚动同步最近 N 天的新警情 |
| `manual/` | `zq_full_resync` | 一次性手动 CLI（`entry_func=main`） | 历史全量回填，按月切片、断点续跑、影子表切换 |

两者各自独立打 zip（zip 根放各自的 `manifest.json` + 入口脚本）。平台只认上传的 zip，
本目录仅为源码组织，合并不影响平台契约。

- 日常增量：`auto/`，配置见其 `config/manifest.json`。
- 历史回填：`manual/`，详见 `manual/docs/README_zq_full_resync.md`。
