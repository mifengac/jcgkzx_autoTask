import { formatTime, optionList, panel, statusBadge, table } from "../core/ui.js";

function renderThemeRunFilters(app) {
  const filters = app.state.themeRunPage.filters;
  return `
    <form id="theme-run-filter-form" class="form-stack">
      <div class="filter-grid">
        <div class="field-block">
          <label for="theme_run_source_id">数据源</label>
          <select id="theme_run_source_id" name="source_id">
            ${optionList(app.state.themeSources, (item) => `${item.source_name} (${item.source_code})`, filters.source_id, "全部数据源")}
          </select>
        </div>
        <div class="field-block">
          <label for="theme_run_topic_id">主题</label>
          <select id="theme_run_topic_id" name="topic_id">
            ${optionList(app.getTopicsForSource(filters.source_id), (item) => `${item.theme_name} (${item.theme_code})`, filters.topic_id, "全部主题")}
          </select>
        </div>
        <div class="field-block">
          <label for="theme_run_status">状态</label>
          <select id="theme_run_status" name="status">
            <option value="">全部状态</option>
            ${["running", "completed", "completed_dry_run", "failed"].map((item) => `<option value="${item}" ${filters.status === item ? "selected" : ""}>${item}</option>`).join("")}
          </select>
        </div>
      </div>
      <div class="inline-actions">
        <button class="button" type="submit">应用筛选</button>
        <button class="button button-secondary" type="button" data-action="theme-runs-reset">重置筛选</button>
      </div>
    </form>
  `;
}

function renderThemeRunTable(app) {
  const page = app.state.themeRunPage;
  const rows = page.items.map((run) => [
    `<span class="mono">${run.run_no}</span>`,
    `数据源 ${run.source_id}`,
    statusBadge(run.status),
    String(run.fetched_count),
    String(run.matched_count),
    String(run.send_count),
    formatTime(run.finished_at || run.started_at),
    `<div class="table-action"><button class="small-button" type="button" data-action="open-detail" data-type="theme-run" data-id="${run.id}">详情</button></div>`,
  ]);
  return table(["运行号", "范围", "状态", "抓取", "命中", "发送", "时间", "操作"], rows);
}

function renderTaskRunFilters(app) {
  return `
    <form id="task-run-filter-form" class="form-stack">
      <div class="filter-grid">
        <div class="field-block">
          <label for="task_run_task_id">自定义任务</label>
          <select id="task_run_task_id" name="task_id">
            ${optionList(app.state.tasks, (item) => `${item.task_name} (#${item.id})`, app.state.taskRunPage.taskId, "全部任务")}
          </select>
        </div>
      </div>
      <div class="inline-actions">
        <button class="button" type="submit">应用筛选</button>
        <button class="button button-secondary" type="button" data-action="task-runs-reset">重置筛选</button>
      </div>
    </form>
  `;
}

function renderTaskRunTable(app) {
  const items = app.state.taskRunPage.items;
  const rows = items.map((run) => [
    `<span class="mono">${run.run_no}</span>`,
    `任务 ${run.task_id}`,
    statusBadge(run.status),
    String(run.result_count),
    String(run.hit_count),
    String(run.send_count),
    formatTime(run.finished_at || run.started_at),
    `<div class="table-action"><button class="small-button" type="button" data-action="open-detail" data-type="task-run" data-id="${run.id}">详情</button></div>`,
  ]);
  return table(["运行号", "范围", "状态", "结果", "命中", "发送", "时间", "操作"], rows);
}

export const runsSection = {
  key: "runs",
  label: "运行历史",
  description: "查看运行记录。",
  tabs: [
    { key: "theme", label: "数据源运行", hint: "主题流程" },
    { key: "task", label: "自定义任务运行", hint: "任务流程" },
  ],
  async load(app) {
    await app.reloadThemeSources();
    await app.reloadTasks();
    if (app.state.route.secondary === "task") {
      await app.refreshTaskRuns();
    } else {
      await app.refreshThemeRuns();
    }
  },
  render(app) {
    if (app.state.route.secondary === "task") {
      return `
        <div class="content-grid">
          ${panel("运行筛选", "先筛任务。", renderTaskRunFilters(app), { span: 4 })}
          ${panel("自定义任务运行", "默认看最近。", renderTaskRunTable(app), { span: 8 })}
        </div>
      `;
    }

    return `
      <div class="content-grid">
        ${panel("运行筛选", "先筛来源。", renderThemeRunFilters(app), { span: 4 })}
        ${panel("数据源运行历史", "抽屉看详情。", renderThemeRunTable(app), { span: 8 })}
      </div>
    `;
  },
  bind(app) {
    const themeFilterForm = document.querySelector("#theme-run-filter-form");
    if (themeFilterForm) {
      themeFilterForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const payload = new FormData(themeFilterForm);
        app.state.themeRunPage.filters = {
          source_id: payload.get("source_id") ? Number(payload.get("source_id")) : null,
          topic_id: payload.get("topic_id") ? Number(payload.get("topic_id")) : null,
          status: payload.get("status") || "",
        };
        app.state.themeRunPage.offset = 0;
        await app.refreshThemeRuns();
        app.render();
      });
    }

    const sourceSelect = document.querySelector("#theme_run_source_id");
    if (sourceSelect) {
      sourceSelect.addEventListener("change", async () => {
        app.state.themeRunPage.filters.source_id = sourceSelect.value ? Number(sourceSelect.value) : null;
        app.state.themeRunPage.filters.topic_id = null;
        if (app.state.themeRunPage.filters.source_id) {
          await app.ensureThemeSourceDetail(app.state.themeRunPage.filters.source_id);
        }
        app.render();
      });
    }

    document.querySelectorAll("[data-action='theme-runs-reset']").forEach((button) => {
      button.addEventListener("click", async () => {
        app.resetThemeRunFilters();
        await app.refreshThemeRuns();
        app.render();
      });
    });

    const taskFilterForm = document.querySelector("#task-run-filter-form");
    if (taskFilterForm) {
      taskFilterForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const payload = new FormData(taskFilterForm);
        app.state.taskRunPage.taskId = payload.get("task_id") ? Number(payload.get("task_id")) : null;
        await app.refreshTaskRuns();
        app.render();
      });
    }

    document.querySelectorAll("[data-action='task-runs-reset']").forEach((button) => {
      button.addEventListener("click", async () => {
        app.state.taskRunPage.taskId = null;
        await app.refreshTaskRuns();
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
