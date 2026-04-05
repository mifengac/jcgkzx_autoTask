import { formatTime, metricCard, panel, statusBadge, table, truncateText } from "../core/ui.js";

function renderRecentRunRows(items, type) {
  return items.map((item) => [
    `<span class="mono">${item.run_no}</span>`,
    type === "theme" ? `数据源 ${item.source_id}` : `任务 ${item.task_id}`,
    statusBadge(item.status),
    String(type === "theme" ? item.matched_count : item.hit_count),
    String(item.send_count),
    formatTime(item.finished_at || item.started_at),
  ]);
}

function renderFailureRows(items) {
  return items.map((item) => [
    formatTime(item.created_at),
    item.source_name,
    item.topic_name,
    item.mobile,
    statusBadge(item.status),
    truncateText(item.error_message || item.content_preview, 64),
    `<button class="small-button" type="button" data-action="open-detail" data-type="theme-sms-log" data-id="${item.id}">查看详情</button>`,
  ]);
}

export const overviewSection = {
  key: "overview",
  label: "总览",
  description: "查看系统健康状态、运行摘要和最近异常。",
  tabs: [{ key: "home", label: "概览", hint: "系统运行快照" }],
  async load(app) {
    await app.loadOverviewData();
  },
  render(app) {
    const stats = app.getOverviewStats();
    const failedLogs = app.state.overview.failedSmsLogs || [];
    const recentThemeRuns = app.state.overview.themeRuns || [];
    const recentTaskRuns = app.state.overview.taskRuns || [];

    return `
      <div class="content-grid">
        ${panel("今日运行概览", "先看数量，再看问题点，帮助快速定位异常区域。",
          `<div class="stat-grid">
            ${metricCard("数据源", stats.sourceCount)}
            ${metricCard("主题", stats.topicCount)}
            ${metricCard("短信模板", stats.templateCount)}
            ${metricCard("自定义任务", stats.taskCount)}
          </div>
          <div class="stat-grid" style="margin-top:12px;">
            ${metricCard("近期开奖源运行", stats.themeRunCount)}
            ${metricCard("近期开奖任务运行", stats.taskRunCount)}
            ${metricCard("失败短信", stats.failedSmsCount)}
            ${metricCard("待处理告警", stats.alertCount)}
          </div>`,
          { span: 12 }
        )}
        ${panel(
          "最近短信异常",
          "这里聚焦失败或需要复核的短信发送记录。",
          failedLogs.length
            ? table(
              ["发送时间", "数据源", "主题", "手机号", "状态", "原因 / 内容", "操作"],
              renderFailureRows(failedLogs)
            )
            : `<div class="empty-state">最近没有失败短信，当前状态比较稳定。</div>`,
          { span: 7 }
        )}
        ${panel(
          "最近数据源运行",
          "关注抓取、命中和发送三个指标是否同步增长。",
          recentThemeRuns.length
            ? table(
              ["运行号", "范围", "状态", "命中", "发送", "结束时间"],
              renderRecentRunRows(recentThemeRuns, "theme")
            )
            : `<div class="empty-state">暂无数据源运行记录。</div>`,
          { span: 5 }
        )}
        ${panel(
          "最近自定义任务运行",
          "旧模块能力保留在一级导航下，这里只展示摘要。",
          recentTaskRuns.length
            ? table(
              ["运行号", "范围", "状态", "命中", "发送", "结束时间"],
              renderRecentRunRows(recentTaskRuns, "task")
            )
            : `<div class="empty-state">暂无自定义任务运行记录。</div>`,
          { span: 12 }
        )}
      </div>
    `;
  },
  bind(app) {
    document.querySelectorAll("[data-action='open-detail']").forEach((button) => {
      button.addEventListener("click", () => {
        app.openDrawer(button.dataset.type, Number(button.dataset.id));
      });
    });
  },
};
