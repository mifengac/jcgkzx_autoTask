# legacy/data_scraper_multi

这是巡防排班 `dutySchedule/crossDayList` 的老版平台任务，原目录名为
`data_scraper_multi`。

它和 `xunfang_dutyschedule` 下的新脚本属于同一业务：抓同一接口，写同一张表
`ywdata.zq_kshddpt_zxzgl`，唯一键都是 `scheduleId`。区别是老版使用
`scheduleDate` 按天请求，并把 `pageSize` 设为 `99999`；新版本改为
`beginTime/endTime` 按天开窗并用 `pageSize=500` 翻页，容量更可控。

保留此目录用于对照、回滚或重新打包旧版脚本。若要上传旧版，仍然只把
`legacy/config/manifest.json` 和 `legacy/scripts/data_scraper_multi.py` 拍平到 zip 根目录。
