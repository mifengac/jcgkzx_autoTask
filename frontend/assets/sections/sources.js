import { api, jsonRequest, parseJson } from "../core/api.js";
import { emptyState, escapeHtml, formatTime, jsonBlock, metricCard, optionList, panel, statusBadge, table } from "../core/ui.js";

function sourceTypeOptions(currentType) {
  const value = currentType || "dsjfx_case_list";
  return [
    `<option value="dsjfx_case_list" ${value === "dsjfx_case_list" ? "selected" : ""}>dsjfx_case_list</option>`,
    `<option value="db_sql_select" ${value === "db_sql_select" ? "selected" : ""}>db_sql_select</option>`,
    `<option value="kingbase_multi_sql" ${value === "kingbase_multi_sql" ? "selected" : ""}>kingbase_multi_sql</option>`,
  ].join("");
}

function sourceConfigHint(sourceType) {
  if (sourceType === "kingbase_multi_sql") {
    return "KingbaseV8 多 SQL 数据源：连接串默认读取 THEME_DB_URL，未配置时复用 DATABASE_URL；这里只需配置 queries[].query_code、queries[].topic_codes、queries[].query、field_map；每条 SQL 只支持单条只读 SELECT/WITH。";
  }
  if (sourceType === "db_sql_select") {
    return "数据库型数据源建议配置 credential_ref.url_env、query、time_range、fetch_profile 和 field_map；查询只支持单条只读 SELECT/WITH。";
  }
  return "HTTP 型数据源沿用 dsjfx_case_list 配置，通常包含 credential_ref、login_url、api_url、time_range 和 fetch_profile。";
}

function currentSource(app) {
  return app.getCurrentSource();
}

function renderSourceCards(app) {
  if (!app.state.themeSources.length) {
    return emptyState("暂无数据源，请先创建一条数据源配置。");
  }

  return `
    <div>
      ${app.state.themeSources.map((item) => `
        <article>
          <div class="card-head">
            <div>
              <h4>${escapeHtml(item.source_name)}</h4>
              <div>编码: <span>${escapeHtml(item.source_code)}</span></div>
            </div>
            ${statusBadge(item.enabled ? "启用" : "停用")}
          </div>
          <div class="card-meta">
            类型: ${escapeHtml(item.source_type)}<br>
            调度: ${item.schedule.interval_value} ${escapeHtml(item.schedule.interval_unit)}<br>
            主题数: ${item.topic_count}
          </div>
          <div role="group">
            <button class="outline" type="button" data-action="source-select" data-id="${item.id}">选中</button>
            <button class="outline" type="button" data-action="source-edit" data-id="${item.id}">编辑</button>
          </div>
        </article>
      `).join("")}
    </div>
  `;
}

function renderSourceForm(app) {
  const source = currentSource(app);
  const editing = app.state.editingSourceId ? currentSource(app) : null;
  const value = editing || source;
  return `
    <div>${source ? `当前数据源: ${escapeHtml(source.source_name)} / ${escapeHtml(source.source_code)}` : "当前未选中数据源"}</div>
    <form id="source-form">
      <div class="grid" style="grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));">
        <div>
          <label for="source_name">数据源名称</label>
          <input id="source_name" name="source_name" type="text" value="${escapeHtml(value?.source_name || "")}" required>
        </div>
        <div>
          <label for="source_code">数据源编码</label>
          <input id="source_code" name="source_code" type="text" value="${escapeHtml(value?.source_code || "")}" required>
        </div>
      </div>
      <div class="grid" style="grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));">
        <div>
          <label for="source_type">数据源类型</label>
          <select id="source_type" name="source_type">
            ${sourceTypeOptions(value?.source_type)}
          </select>
        </div>
        <div>
          <label for="schedule_interval_value">调度值</label>
          <input id="schedule_interval_value" name="schedule_interval_value" type="number" min="1" value="${value?.schedule?.interval_value || 20}">
        </div>
        <div>
          <label for="schedule_interval_unit">调度单位</label>
          <select id="schedule_interval_unit" name="schedule_interval_unit">
            <option value="minute" ${(value?.schedule?.interval_unit || "minute") === "minute" ? "selected" : ""}>分钟</option>
            <option value="hour" ${(value?.schedule?.interval_unit || "") === "hour" ? "selected" : ""}>小时</option>
          </select>
        </div>
      </div>
      <div>
        <label for="schedule_timezone">时区</label>
        <input id="schedule_timezone" name="schedule_timezone" type="text" value="${escapeHtml(value?.schedule?.timezone || "Asia/Shanghai")}">
      </div>
      <div>
        <label for="source_config">数据源配置 JSON</label>
        <div id="source-config-hint" style="margin:4px 0 8px;color:var(--muted);font-size:.9rem;">${escapeHtml(sourceConfigHint(value?.source_type || "dsjfx_case_list"))}</div>
        <textarea id="source_config" name="source_config" rows="12">${escapeHtml(JSON.stringify(value?.source_config || {}, null, 2))}</textarea>
      </div>
      <div>
        <label class="switch-field">
          <input name="enabled" type="checkbox" ${value?.enabled ?? true ? "checked" : ""}>
          <span>
            <strong>启用数据源</strong>
            <small>打开后参与调度和手动执行，关闭后保留配置但不执行。</small>
          </span>
        </label>
      </div>
      <div role="group">
        <button type="submit">${app.state.editingSourceId ? "更新数据源" : "创建数据源"}</button>
        <button class="secondary" type="button" data-action="source-reset">新建数据源</button>
      </div>
    </form>
  `;
}

function renderSourceRunPanel(app) {
  const source = currentSource(app);
  const runs = app.state.themeRunPage.items || [];
  return `
    <div>${source ? `当前数据源: ${escapeHtml(source.source_name)}` : "请先在列表概览中选中一条数据源。"}</div>
    <div role="group" style="margin-top:12px;">
      <button class="outline" type="button" data-action="source-run-dry" ${source ? "" : "disabled"}>演练</button>
      <button class="contrast" type="button" data-action="source-run-live" ${source ? "" : "disabled"}>立即执行</button>
      <button class="secondary" type="button" data-action="source-refresh-runs" ${source ? "" : "disabled"}>刷新运行记录</button>
    </div>
    <div style="margin-top:16px;">
      ${source ? jsonBlock(source.source_config) : emptyState("选中数据源后可以在这里查看当前抓取配置。")}
    </div>
    <div style="margin-top:16px;">
      ${runs.length ? table(
        ["运行号", "状态", "抓取", "命中", "发送", "时间", "操作"],
        runs.map((run) => [
          `<span>${escapeHtml(run.run_no)}</span>`,
          statusBadge(run.status),
          String(run.fetched_count),
          String(run.matched_count),
          String(run.send_count),
          formatTime(run.finished_at || run.started_at),
          `<div role="group"><button class="outline" type="button" data-action="open-detail" data-type="theme-run" data-id="${run.id}">详情</button></div>`,
        ])
      ) : emptyState("当前数据源暂无运行记录。")}
    </div>
  `;
}

export const sourcesSection = {
  key: "sources",
  label: "数据源管理",
  description: "管理数据源与调度。",
  tabs: [
    { key: "list", label: "列表概览", hint: "查看数据源" },
    { key: "editor", label: "配置编辑", hint: "编辑参数" },
    { key: "run", label: "运行测试", hint: "演练执行" },
  ],
  async load(app) {
    await app.reloadThemeSources();
    if (app.state.route.secondary === "run" && app.state.selectedSourceId) {
      await app.refreshThemeRuns({ source_id: app.state.selectedSourceId, limit: 10, offset: 0 });
    }
  },
  render(app) {
    const enabledCount = app.state.themeSources.filter((item) => item.enabled).length;
    const tab = app.state.route.secondary;
    const summary = `
      <div class="grid" style="grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));">
        ${metricCard("数据源总数", app.state.themeSources.length)}
        ${metricCard("已启用", enabledCount)}
        ${metricCard("主题总数", app.state.themeSources.reduce((sum, item) => sum + item.topic_count, 0))}
        ${metricCard("当前选中", currentSource(app)?.source_name || "-")}
      </div>
    `;

    if (tab === "editor") {
      return `<div class="grid" style="grid-template-columns: repeat(12, minmax(0, 1fr)); align-items:start;">
        ${panel("数据源概况", "先选数据源。", summary, { span: 4 })}
        ${panel("数据源配置", "编辑调度与参数。", renderSourceForm(app), { span: 8 })}
      </div>`;
    }

    if (tab === "run") {
      return `<div class="grid" style="grid-template-columns: repeat(12, minmax(0, 1fr)); align-items:start;">
        ${panel("数据源概况", "确认当前来源。", summary, { span: 4 })}
        ${panel("运行测试", "只作用当前源。", renderSourceRunPanel(app), { span: 8 })}
      </div>`;
    }

    return `<div class="grid" style="grid-template-columns: repeat(12, minmax(0, 1fr)); align-items:start;">
      ${panel("数据源概况", "看当前状态。", summary, { span: 4 })}
      ${panel("数据源列表", "列表只做切换。", renderSourceCards(app), { span: 8 })}
    </div>`;
  },
  bind(app) {
    document.querySelectorAll("[data-action='source-select']").forEach((button) => {
      button.addEventListener("click", async () => {
        await app.setSelectedSource(Number(button.dataset.id));
        app.render();
      });
    });

    document.querySelectorAll("[data-action='source-edit']").forEach((button) => {
      button.addEventListener("click", async () => {
        await app.setSelectedSource(Number(button.dataset.id));
        app.state.editingSourceId = Number(button.dataset.id);
        app.navigate("sources", "editor");
      });
    });

    document.querySelectorAll("[data-action='source-reset']").forEach((button) => {
      button.addEventListener("click", () => {
        app.state.editingSourceId = null;
        app.render();
      });
    });

    const form = document.querySelector("#source-form");
    if (form) {
      const sourceTypeSelect = form.querySelector("#source_type");
      const sourceConfigHintNode = form.querySelector("#source-config-hint");
      if (sourceTypeSelect && sourceConfigHintNode) {
        sourceTypeSelect.addEventListener("change", () => {
          sourceConfigHintNode.textContent = sourceConfigHint(sourceTypeSelect.value || "dsjfx_case_list");
        });
      }

      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
          const payload = new FormData(form);
          const body = {
            source_name: payload.get("source_name"),
            source_code: payload.get("source_code"),
            source_type: payload.get("source_type"),
            enabled: payload.get("enabled") === "on",
            source_config: parseJson(payload.get("source_config"), {}),
            schedule: {
              interval_value: Number(payload.get("schedule_interval_value") || 20),
              interval_unit: payload.get("schedule_interval_unit") || "minute",
              timezone: payload.get("schedule_timezone") || "Asia/Shanghai",
              start_at: null,
              end_at: null,
            },
          };
          if (app.state.editingSourceId) {
            await api(`/api/theme-sources/${app.state.editingSourceId}`, jsonRequest("PUT", body));
            app.flash("数据源已更新。");
          } else {
            const created = await api("/api/theme-sources", jsonRequest("POST", body));
            app.state.selectedSourceId = created.id;
            app.flash("数据源已创建。");
          }
          app.state.editingSourceId = null;
          await app.reloadThemeSources();
          app.render();
        } catch (error) {
          app.flash(error.message, true);
        }
      });
    }

    document.querySelectorAll("[data-action='source-run-dry']").forEach((button) => {
      button.addEventListener("click", async () => {
        try {
          const run = await api(`/api/theme-sources/${app.state.selectedSourceId}/run`, jsonRequest("POST", { dry_run: true, context_override: {} }));
          app.flash(`数据源演练已触发，run_id=${run.id}`);
          await app.refreshThemeRuns({ source_id: app.state.selectedSourceId, limit: 10, offset: 0 });
          app.render();
        } catch (error) {
          app.flash(error.message, true);
        }
      });
    });

    document.querySelectorAll("[data-action='source-run-live']").forEach((button) => {
      button.addEventListener("click", async () => {
        try {
          const run = await api(`/api/theme-sources/${app.state.selectedSourceId}/run`, jsonRequest("POST", { dry_run: false, context_override: {} }));
          app.flash(`数据源立即执行已触发，run_id=${run.id}`);
          await app.refreshThemeRuns({ source_id: app.state.selectedSourceId, limit: 10, offset: 0 });
          app.render();
        } catch (error) {
          app.flash(error.message, true);
        }
      });
    });

    document.querySelectorAll("[data-action='source-refresh-runs']").forEach((button) => {
      button.addEventListener("click", async () => {
        await app.refreshThemeRuns({ source_id: app.state.selectedSourceId, limit: 10, offset: 0 });
        app.flash("数据源运行记录已刷新。");
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
