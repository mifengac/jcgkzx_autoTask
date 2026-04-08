import { formatTime, optionList, panel, renderPagination, statusBadge, table, truncateText } from "../core/ui.js";

function renderFilters(app) {
  const filters = app.state.themeSmsLogPage.filters;
  return `
    <form id="sms-log-filter-form">
      <div class="grid" style="grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));">
        <div>
          <label for="sms_source_id">数据源</label>
          <select id="sms_source_id" name="source_id">
            ${optionList(app.state.themeSources, (item) => `${item.source_name} (${item.source_code})`, filters.source_id, "全部数据源")}
          </select>
        </div>
        <div>
          <label for="sms_topic_id">主题</label>
          <select id="sms_topic_id" name="topic_id">
            ${optionList(app.getTopicsForSource(filters.source_id), (item) => `${item.theme_name} (${item.theme_code})`, filters.topic_id, "全部主题")}
          </select>
        </div>
        <div>
          <label for="sms_status">状态</label>
          <select id="sms_status" name="status">
            <option value="">全部状态</option>
            ${["sent", "failed", "skipped_duplicate", "skipped_sms_disabled", "dry_run"].map((item) => `<option value="${item}" ${filters.status === item ? "selected" : ""}>${item}</option>`).join("")}
          </select>
        </div>
        <div>
          <label for="sms_mobile">手机号</label>
          <input id="sms_mobile" name="mobile" type="text" value="${filters.mobile || ""}">
        </div>
      </div>
      <div role="group">
        <button type="submit">应用筛选</button>
        <button class="secondary" type="button" data-action="sms-reset">重置筛选</button>
      </div>
    </form>
  `;
}

function renderSmsLogTable(app) {
  const page = app.state.themeSmsLogPage;
  const rows = page.items.map((item) => [
    formatTime(item.created_at),
    item.source_name,
    item.topic_name,
    item.mobile,
    statusBadge(item.status),
    item.error_message ? `<span>${truncateText(item.error_message, 52)}</span>` : truncateText(item.content_preview, 52),
    `<span>${truncateText(item.provider_msg_id || "-", 20)}</span>`,
    `<div role="group"><button class="outline" type="button" data-action="open-detail" data-type="theme-sms-log" data-id="${item.id}">详情</button></div>`,
  ]);
  return `
    ${table(
      ["发送时间", "数据源", "主题", "手机号", "状态", "失败原因 / 内容", "平台回执", "操作"],
      rows
    )}
    ${renderPagination({ total: page.total, limit: page.limit, offset: page.offset, action: "sms-page" })}
  `;
}

export const smsLogsSection = {
  key: "sms-logs",
  label: "短信发送记录",
  description: "查看短信结果与失败原因。",
  tabs: [{ key: "list", label: "发送记录", hint: "按状态筛选" }],
  async load(app) {
    await app.reloadThemeSources();
    await app.refreshThemeSmsLogs();
  },
  render(app) {
    return `
      <div class="grid" style="grid-template-columns: repeat(12, minmax(0, 1fr)); align-items:start;">
        ${panel("筛选条件", "先筛失败项。", renderFilters(app), { span: 4 })}
        ${panel("短信发送记录", "列表看摘要。", renderSmsLogTable(app), { span: 8 })}
      </div>
    `;
  },
  bind(app) {
    const form = document.querySelector("#sms-log-filter-form");
    if (form) {
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const payload = new FormData(form);
        app.state.themeSmsLogPage.filters = {
          source_id: payload.get("source_id") ? Number(payload.get("source_id")) : null,
          topic_id: payload.get("topic_id") ? Number(payload.get("topic_id")) : null,
          status: payload.get("status") || "",
          mobile: payload.get("mobile") || "",
        };
        app.state.themeSmsLogPage.offset = 0;
        await app.refreshThemeSmsLogs();
        app.render();
      });
    }

    const sourceSelect = document.querySelector("#sms_source_id");
    if (sourceSelect) {
      sourceSelect.addEventListener("change", async () => {
        app.state.themeSmsLogPage.filters.source_id = sourceSelect.value ? Number(sourceSelect.value) : null;
        app.state.themeSmsLogPage.filters.topic_id = null;
        if (app.state.themeSmsLogPage.filters.source_id) {
          await app.ensureThemeSourceDetail(app.state.themeSmsLogPage.filters.source_id);
        }
        app.render();
      });
    }

    document.querySelectorAll("[data-action='sms-reset']").forEach((button) => {
      button.addEventListener("click", async () => {
        app.resetThemeSmsLogFilters();
        await app.refreshThemeSmsLogs();
        app.render();
      });
    });

    document.querySelectorAll("[data-action='sms-page']").forEach((button) => {
      button.addEventListener("click", async () => {
        const direction = button.dataset.direction;
        const page = app.state.themeSmsLogPage;
        page.offset = direction === "next" ? page.offset + page.limit : Math.max(0, page.offset - page.limit);
        await app.refreshThemeSmsLogs();
        app.render();
      });
    });

    document.querySelectorAll("[data-action='open-detail']").forEach((button) => {
      button.addEventListener("click", () => {
        app.openDrawer(button.dataset.type, Number(button.dataset.id));
      });
    });
  },
};
