import { formatTime, metricCard, panel, statusBadge, table, truncateText } from "../core/ui.js";

function renderRecentRunRows(items, type) {
  return items.map((item) => [
    `<span>${item.run_no}</span>`,
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
    `<div role="group"><button class="outline" type="button" data-action="open-detail" data-type="theme-sms-log" data-id="${item.id}">详情</button></div>`,
  ]);
}

function renderHero(stats) {
  return `
    <section class="surface-card surface-card--hero overview-hero">
      <div class="overview-hero__copy">
        <p class="section-kicker">Overview Desk</p>
        <h3>先看今日总量，再顺着异常和运行轨迹往下查。</h3>
        <p>这一版模板把运行概览、异常短信和最近执行记录放到同一条阅读路径里，方便值守时快速定位异常来源。</p>
        <span class="overview-stat-note">失败短信与待处理告警当前使用同一组异常短信数据计算。</span>
      </div>

      <div class="overview-hero__aside">
        <div class="metric-grid">
          ${metricCard("数据源", stats.sourceCount, "当前已接入")}
          ${metricCard("主题", stats.topicCount, "按源归类")}
          ${metricCard("短信模板", stats.templateCount, "统一渲染")}
          ${metricCard("自定义任务", stats.taskCount, "支持脚本执行")}
          ${metricCard("近期数据源运行", stats.themeRunCount, "最近 5 条")}
          ${metricCard("近期任务运行", stats.taskRunCount, "最近 5 条")}
          ${metricCard("失败短信", stats.failedSmsCount, "优先关注")}
          ${metricCard("待处理告警", stats.alertCount, "当前口径")}
        </div>
      </div>
    </section>
  `;
}

export const overviewSection = {
  key: "overview",
  label: "总览",
  description: "查看运行摘要和异常。",
  tabs: [{ key: "home", label: "概览", hint: "系统快照" }],
  async load(app) {
    await app.loadOverviewData();
  },
  render(app) {
    const stats = app.getOverviewStats();
    const failedLogs = app.state.overview.failedSmsLogs || [];
    const recentThemeRuns = app.state.overview.themeRuns || [];
    const recentTaskRuns = app.state.overview.taskRuns || [];

    return `
      <section class="overview-shell">
        ${renderHero(stats)}

        <div class="overview-grid">
          ${panel(
            "最近短信异常",
            "优先处理失败短信，并直接跳到详情抽屉查看原因。",
            failedLogs.length
              ? table(
                ["发送时间", "数据源", "主题", "手机号", "状态", "原因 / 内容", "操作"],
                renderFailureRows(failedLogs)
              )
              : `<div class="empty-state"><p><em>最近没有失败短信，当前状态较稳定。</em></p></div>`,
            { span: 7, className: "overview-panel overview-panel--priority" }
          )}

          ${panel(
            "最近数据源运行",
            "看抓取、命中和发送链路是否连续正常。",
            recentThemeRuns.length
              ? table(
                ["运行号", "范围", "状态", "命中", "发送", "结束时间"],
                renderRecentRunRows(recentThemeRuns, "theme")
              )
              : `<div class="empty-state"><p><em>暂无数据源运行记录。</em></p></div>`,
            { span: 5, variant: "dark", className: "overview-panel" }
          )}

          ${panel(
            "最近自定义任务运行",
            "保留同样的阅读方式，方便和数据源运行并排比对。",
            recentTaskRuns.length
              ? table(
                ["运行号", "范围", "状态", "命中", "发送", "结束时间"],
                renderRecentRunRows(recentTaskRuns, "task")
              )
              : `<div class="empty-state"><p><em>暂无自定义任务运行记录。</em></p></div>`,
            { span: 12, className: "overview-panel" }
          )}
        </div>
      </section>
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
