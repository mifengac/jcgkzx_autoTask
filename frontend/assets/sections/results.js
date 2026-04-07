import { formatTime, optionList, panel, renderPagination, statusBadge, table, truncateText } from "../core/ui.js";

function renderFilters(app) {
  const filters = app.state.themeResultPage.filters;
  return `
    <form id="result-filter-form" class="form-stack">
      <div class="filter-grid">
        <div class="field-block">
          <label for="result_source_id">数据源</label>
          <select id="result_source_id" name="source_id">
            ${optionList(app.state.themeSources, (item) => `${item.source_name} (${item.source_code})`, filters.source_id, "全部数据源")}
          </select>
        </div>
        <div class="field-block">
          <label for="result_topic_id">主题</label>
          <select id="result_topic_id" name="topic_id">
            ${optionList(app.getTopicsForSource(filters.source_id), (item) => `${item.theme_name} (${item.theme_code})`, filters.topic_id, "全部主题")}
          </select>
        </div>
        <div class="field-block">
          <label for="result_send_status">发送状态</label>
          <select id="result_send_status" name="send_status">
            <option value="">全部状态</option>
            ${["sent", "failed", "partial_failed", "skipped_duplicate", "skipped_no_receivers", "skipped_sms_disabled", "dry_run"].map((item) => `<option value="${item}" ${filters.send_status === item ? "selected" : ""}>${item}</option>`).join("")}
          </select>
        </div>
        <div class="field-block">
          <label for="result_keyword">关键字</label>
          <input id="result_keyword" name="keyword" type="text" value="${filters.keyword || ""}">
        </div>
        <div class="field-block">
          <label for="result_start_time">开始时间</label>
          <input id="result_start_time" name="start_time" type="datetime-local" value="${filters.start_time || ""}">
        </div>
        <div class="field-block">
          <label for="result_end_time">结束时间</label>
          <input id="result_end_time" name="end_time" type="datetime-local" value="${filters.end_time || ""}">
        </div>
      </div>
      <div class="inline-actions">
        <button class="button" type="submit">应用筛选</button>
        <button class="button button-secondary" type="button" data-action="results-reset">重置筛选</button>
      </div>
    </form>
  `;
}

function renderResultTable(app) {
  const page = app.state.themeResultPage;
  const rows = page.items.map((item) => [
    formatTime(item.created_at),
    item.source_name,
    item.topic_name,
    item.case_no || "-",
    statusBadge(item.send_status),
    item.receiver_mobiles.join("<br>") || "-",
    `<span class="mono">${truncateText(item.oracle_eid, 36)}</span>`,
    truncateText(item.event_key, 28),
    `<div class="table-action"><button class="small-button" type="button" data-action="open-detail" data-type="theme-result" data-id="${item.id}">详情</button></div>`,
  ]);

  return `
    ${table(
      ["命中时间", "数据源", "主题", "警情编号", "发送状态", "接收人", "Oracle EID", "事件键", "操作"],
      rows
    )}
    ${renderPagination({ total: page.total, limit: page.limit, offset: page.offset, action: "results-page" })}
  `;
}

export const resultsSection = {
  key: "results",
  label: "命中结果",
  description: "按页查看命中结果。",
  tabs: [{ key: "list", label: "结果列表", hint: "结果分页" }],
  async load(app) {
    await app.reloadThemeSources();
    await app.refreshThemeResults();
  },
  render(app) {
    return `
      <div class="content-grid">
        ${panel("筛选条件", "先缩范围。", renderFilters(app), { span: 4 })}
        ${panel("命中结果列表", "列表看摘要。", renderResultTable(app), { span: 8 })}
      </div>
    `;
  },
  bind(app) {
    const form = document.querySelector("#result-filter-form");
    if (form) {
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const payload = new FormData(form);
        app.state.themeResultPage.filters = {
          source_id: payload.get("source_id") ? Number(payload.get("source_id")) : null,
          topic_id: payload.get("topic_id") ? Number(payload.get("topic_id")) : null,
          send_status: payload.get("send_status") || "",
          keyword: payload.get("keyword") || "",
          start_time: payload.get("start_time") || "",
          end_time: payload.get("end_time") || "",
        };
        app.state.themeResultPage.offset = 0;
        await app.refreshThemeResults();
        app.render();
      });
    }

    const sourceSelect = document.querySelector("#result_source_id");
    if (sourceSelect) {
      sourceSelect.addEventListener("change", async () => {
        const nextSourceId = sourceSelect.value ? Number(sourceSelect.value) : null;
        app.state.themeResultPage.filters.source_id = nextSourceId;
        app.state.themeResultPage.filters.topic_id = null;
        if (nextSourceId) {
          await app.ensureThemeSourceDetail(nextSourceId);
        }
        app.render();
      });
    }

    document.querySelectorAll("[data-action='results-reset']").forEach((button) => {
      button.addEventListener("click", async () => {
        app.resetThemeResultFilters();
        await app.refreshThemeResults();
        app.render();
      });
    });

    document.querySelectorAll("[data-action='results-page']").forEach((button) => {
      button.addEventListener("click", async () => {
        const direction = button.dataset.direction;
        const page = app.state.themeResultPage;
        page.offset = direction === "next" ? page.offset + page.limit : Math.max(0, page.offset - page.limit);
        await app.refreshThemeResults();
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
