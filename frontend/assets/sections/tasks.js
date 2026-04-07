import { api, jsonRequest, parseJson, splitLines } from "../core/api.js";
import { emptyState, escapeHtml, formatTime, optionList, panel, statusBadge, table } from "../core/ui.js";

function currentTask(app) {
  return app.getCurrentTask();
}

function renderVersionOptions(app, scriptId, selectedVersionId = null) {
  const script = app.state.scripts.find((item) => item.id === Number(scriptId));
  const versions = script?.versions || [];
  return optionList(versions, (item) => item.version_no, selectedVersionId || versions[0]?.id || null, "请选择版本");
}

function taskSelector(app, id = "task-select", current = app.state.selectedTaskId) {
  return `
    <div class="field-block">
      <label for="${id}">自定义任务</label>
      <select id="${id}" data-action="task-select">
        ${optionList(app.state.tasks, (item) => `${item.task_name} (#${item.id})`, current, "请选择任务")}
      </select>
    </div>
  `;
}

function renderScriptUpload(app) {
  return `
    <form id="script-upload-form" class="form-stack">
      <div class="form-grid two">
        <div class="field-block">
          <label for="script_name">脚本名称</label>
          <input id="script_name" name="script_name" type="text" required>
        </div>
        <div class="field-block">
          <label for="script_code">脚本编码</label>
          <input id="script_code" name="script_code" type="text" required>
        </div>
      </div>
      <div class="form-grid three">
        <div class="field-block">
          <label for="version_no">版本号</label>
          <input id="version_no" name="version_no" type="text" required>
        </div>
        <div class="field-block">
          <label for="entry_file">入口文件</label>
          <input id="entry_file" name="entry_file" type="text">
        </div>
        <div class="field-block">
          <label for="entry_func">入口函数</label>
          <input id="entry_func" name="entry_func" type="text" placeholder="默认 run">
        </div>
      </div>
      <div class="field-block">
        <label for="change_log">变更说明</label>
        <input id="change_log" name="change_log" type="text">
      </div>
      <div class="field-block">
        <label for="package">ZIP 包</label>
        <input id="package" name="package" type="file" accept=".zip" required>
      </div>
      <div class="inline-actions">
        <button class="button" type="submit">上传脚本</button>
      </div>
    </form>
  `;
}

function renderScriptList(app) {
  if (!app.state.scripts.length) {
    return emptyState("暂无脚本包。");
  }
  return `
    <div class="card-list">
      ${app.state.scripts.map((script) => `
        <article class="card-item">
          <div class="card-head">
            <div>
              <h4>${escapeHtml(script.script_name)}</h4>
              <div class="card-meta">编码: <span class="mono">${escapeHtml(script.script_code)}</span></div>
            </div>
            ${statusBadge(script.status)}
          </div>
          <div class="card-meta">
            入口: ${escapeHtml(script.entry_file)}#${escapeHtml(script.entry_func || "run")}<br>
            版本: ${(script.versions || []).map((item) => escapeHtml(item.version_no)).join(", ") || "暂无"}
          </div>
        </article>
      `).join("")}
    </div>
  `;
}

function renderTaskList(app) {
  if (!app.state.tasks.length) {
    return emptyState("暂无自定义任务。");
  }
  return `
    <div class="card-list">
      ${app.state.tasks.map((task) => {
        const schedule = (task.schedules || [])[0];
        return `
          <article class="card-item ${app.state.selectedTaskId === task.id ? "active" : ""}">
            <div class="card-head">
              <div>
                <h4>${escapeHtml(task.task_name)}</h4>
                <div class="card-meta">任务 ID: ${task.id}</div>
              </div>
              ${statusBadge(task.enabled ? "启用" : "停用")}
            </div>
              <div class="card-meta">
              script_id=${task.script_id} / version_id=${task.script_version_id}<br>
              模板: ${task.message_template_id || "未绑定"}<br>
              调度: ${schedule ? `${schedule.interval_value} ${schedule.interval_unit}` : "未配置"}<br>
              规则数: ${(task.rules || []).length}
            </div>
            <div class="card-actions">
              <button class="small-button" type="button" data-action="task-select-card" data-id="${task.id}">选中</button>
              <button class="small-button" type="button" data-action="task-edit" data-id="${task.id}">编辑</button>
              <button class="small-button ${task.enabled ? "warn" : ""}" type="button" data-action="${task.enabled ? "task-disable" : "task-enable"}" data-id="${task.id}">${task.enabled ? "停用" : "启用"}</button>
              <button class="small-button danger" type="button" data-action="task-delete" data-id="${task.id}">删除</button>
            </div>
          </article>
        `;
      }).join("")}
    </div>
  `;
}

function renderTaskForm(app) {
  const task = app.state.tasks.find((item) => item.id === app.state.editingTaskId) || null;
  const schedule = task?.schedules?.[0];
  const scripts = app.state.scripts;
  const selectedScriptId = task?.script_id || scripts[0]?.id || "";
  const currentScript = scripts.find((item) => item.id === selectedScriptId) || scripts[0];
  const versions = currentScript?.versions || [];
  return `
    <form id="task-form" class="form-stack">
      <div class="field-block">
        <label for="task_name">任务名称</label>
        <input id="task_name" name="task_name" type="text" value="${escapeHtml(task?.task_name || "")}" required>
      </div>
      <div class="form-grid three">
        <div class="field-block">
          <label for="task_script_id">脚本</label>
          <select id="task_script_id" name="script_id">
            ${optionList(scripts, (item) => `${item.script_name} (${item.script_code})`, selectedScriptId, "请选择脚本")}
          </select>
        </div>
        <div class="field-block">
          <label for="task_script_version_id">版本</label>
          <select id="task_script_version_id" name="script_version_id">
            ${optionList(versions, (item) => item.version_no, task?.script_version_id, "请选择版本")}
          </select>
        </div>
        <div class="field-block">
          <label for="task_template_id">短信模板</label>
          <select id="task_template_id" name="message_template_id">
            <option value="">不使用模板</option>
            ${app.state.templates.map((item) => `<option value="${item.id}" ${task?.message_template_id === item.id ? "selected" : ""}>${escapeHtml(item.template_name)}</option>`).join("")}
          </select>
        </div>
      </div>
      <div class="form-grid three">
        <div class="field-block">
          <label for="dedup_window_minutes">去重窗口(分钟)</label>
          <input id="dedup_window_minutes" name="dedup_window_minutes" type="number" value="${task?.dedup_window_minutes || 720}">
        </div>
        <div class="field-block">
          <label for="schedule_interval_value">调度值</label>
          <input id="schedule_interval_value" name="schedule_interval_value" type="number" value="${schedule?.interval_value || 20}">
        </div>
        <div class="field-block">
          <label for="schedule_interval_unit">调度单位</label>
          <select id="schedule_interval_unit" name="schedule_interval_unit">
            <option value="minute" ${(schedule?.interval_unit || "minute") === "minute" ? "selected" : ""}>分钟</option>
            <option value="hour" ${schedule?.interval_unit === "hour" ? "selected" : ""}>小时</option>
          </select>
        </div>
      </div>
      <div class="field-block">
        <label for="dedup_key_expr">去重表达式</label>
        <input id="dedup_key_expr" name="dedup_key_expr" type="text" value="${escapeHtml(task?.dedup_key_expr || "")}">
      </div>
      <div class="field-block">
        <label for="runtime_config">运行配置 JSON</label>
        <textarea id="runtime_config" name="runtime_config" rows="8">${escapeHtml(JSON.stringify(task?.runtime_config || {}, null, 2))}</textarea>
      </div>
      <div class="checkbox-row">
        <label class="checkbox"><input name="enabled" type="checkbox" ${task?.enabled ?? true ? "checked" : ""}><span>启用任务</span></label>
      </div>
      <div class="inline-actions">
        <button class="button" type="submit">${task ? "更新任务" : "创建任务"}</button>
        <button class="button button-secondary" type="button" data-action="task-reset">新建任务</button>
        <button class="button button-ghost" type="button" data-action="task-run-dry" ${app.state.selectedTaskId ? "" : "disabled"}>演练</button>
        <button class="button button-danger" type="button" data-action="task-run-live" ${app.state.selectedTaskId ? "" : "disabled"}>立即执行</button>
      </div>
    </form>
  `;
}

function renderTaskRuleForm(app) {
  const task = currentTask(app);
  const rule = task?.rules?.find((item) => item.id === app.state.editingTaskRuleId) || null;
  return `
    <div class="banner">${task ? `当前任务: ${escapeHtml(task.task_name)}` : "请先选中任务，再维护接收规则。"}</div>
    <form id="task-rule-form" class="form-stack">
      <div class="form-grid two">
        ${taskSelector(app)}
        <div class="field-block">
          <label for="rule_name">规则名称</label>
          <input id="rule_name" name="rule_name" type="text" value="${escapeHtml(rule?.rule_name || "")}" required>
        </div>
      </div>
      <div class="form-grid three">
        <div class="field-block">
          <label for="rule_type">规则类型</label>
          <select id="rule_type" name="rule_type">
            <option value="fixed_receivers" ${(rule?.rule_type || "fixed_receivers") === "fixed_receivers" ? "selected" : ""}>固定接收人</option>
            <option value="field_match" ${rule?.rule_type === "field_match" ? "selected" : ""}>字段直接匹配</option>
            <option value="field_match_with_ancestors" ${rule?.rule_type === "field_match_with_ancestors" ? "selected" : ""}>字段匹配并带上级单位</option>
          </select>
        </div>
        <div class="field-block">
          <label for="source_field">源字段</label>
          <input id="source_field" name="source_field" type="text" value="${escapeHtml(rule?.source_field || "")}">
        </div>
        <div class="field-block">
          <label for="target_match_field">目标字段</label>
          <select id="target_match_field" name="target_match_field">
            ${["sspcsdm", "xqdm", "county_code", "city_code"].map((item) => `<option value="${item}" ${(rule?.target_match_field || "sspcsdm") === item ? "selected" : ""}>${escapeHtml(item)}</option>`).join("")}
          </select>
        </div>
      </div>
      <div class="form-grid two">
        <div class="field-block">
          <label for="priority">优先级</label>
          <input id="priority" name="priority" type="number" value="${rule?.priority || 100}">
        </div>
        <div class="field-block">
          <label for="target_mobile_field">手机号字段</label>
          <input id="target_mobile_field" name="target_mobile_field" type="text" value="${escapeHtml(rule?.target_mobile_field || "mobile")}">
        </div>
      </div>
      <div class="field-block">
        <label for="fixed_receivers">固定手机号</label>
        <textarea id="fixed_receivers" name="fixed_receivers" rows="4">${escapeHtml((rule?.fixed_receivers || []).join("\n"))}</textarea>
      </div>
      <div class="field-block">
        <label for="filter_json">联系人过滤 JSON</label>
        <textarea id="filter_json" name="filter_json" rows="4">${escapeHtml(JSON.stringify(rule?.filter_json || {}, null, 2))}</textarea>
      </div>
      <div class="checkbox-row">
        <label class="checkbox"><input name="enabled" type="checkbox" ${rule?.enabled ?? true ? "checked" : ""}><span>启用规则</span></label>
        <label class="checkbox"><input name="include_self" type="checkbox" ${rule?.include_self ?? true ? "checked" : ""}><span>包含本级</span></label>
        <label class="checkbox"><input name="include_county" type="checkbox" ${rule?.include_county ? "checked" : ""}><span>包含县级</span></label>
        <label class="checkbox"><input name="include_city" type="checkbox" ${rule?.include_city ? "checked" : ""}><span>包含市级</span></label>
      </div>
      <div class="inline-actions">
        <button class="button" type="submit">${rule ? "更新规则" : "创建规则"}</button>
        <button class="button button-secondary" type="button" data-action="task-rule-reset">新建规则</button>
      </div>
    </form>
  `;
}

function renderTaskRuleList(app) {
  const task = currentTask(app);
  if (!task || !(task.rules || []).length) {
    return emptyState("当前任务暂无接收规则。");
  }
  return `
    <div class="card-list">
      ${task.rules.map((rule) => `
        <article class="card-item ${app.state.editingTaskRuleId === rule.id ? "active" : ""}">
          <div class="card-head">
            <div>
              <h4>${escapeHtml(rule.rule_name)}</h4>
              <div class="card-meta">类型: ${escapeHtml(rule.rule_type)}</div>
            </div>
            ${statusBadge(rule.enabled ? "启用" : "停用")}
          </div>
          <div class="card-meta">
            匹配字段: ${escapeHtml(rule.source_field || "-")} → ${escapeHtml(rule.target_match_field)}<br>
            固定接收人: ${escapeHtml((rule.fixed_receivers || []).join(", ") || "-")}
          </div>
          <div class="card-actions">
            <button class="small-button" type="button" data-action="task-rule-edit" data-id="${rule.id}">编辑规则</button>
            <button class="small-button danger" type="button" data-action="task-rule-delete" data-id="${rule.id}">删除规则</button>
          </div>
        </article>
      `).join("")}
    </div>
  `;
}

function renderContactSearch(app) {
  const contacts = app.state.contacts.items || [];
  return `
    <form id="contact-search-form" class="form-stack">
      <div class="filter-grid">
        <div class="field-block">
          <label for="contact_keyword">关键字</label>
          <input id="contact_keyword" name="keyword" type="text" value="${escapeHtml(app.state.contacts.query.keyword || "")}">
        </div>
        <div class="field-block">
          <label for="contact_sspcsdm">sspcsdm</label>
          <input id="contact_sspcsdm" name="sspcsdm" type="text" value="${escapeHtml(app.state.contacts.query.sspcsdm || "")}">
        </div>
        <div class="field-block">
          <label for="contact_xqdm">xqdm</label>
          <input id="contact_xqdm" name="xqdm" type="text" value="${escapeHtml(app.state.contacts.query.xqdm || "")}">
        </div>
      </div>
      <div class="inline-actions">
        <button class="button" type="submit">查询联系人</button>
      </div>
    </form>
    <div style="margin-top:14px;">
      ${contacts.length ? table(
        ["姓名", "派出所", "县区", "手机号", "状态"],
        contacts.map((item) => [
          escapeHtml(item.xm || item.sspcs || "未命名联系人"),
          escapeHtml(item.sspcs || "-"),
          escapeHtml(item.xq || "-"),
          escapeHtml((item.phones || []).map((phone) => phone.mobile).join(", ") || "-"),
          escapeHtml(item.status),
        ])
      ) : emptyState("还没有联系人查询结果。")}
    </div>
  `;
}

function renderTaskRuns(app) {
  const items = app.state.taskRunPage.items || [];
  return items.length ? table(
    ["运行号", "状态", "结果", "命中", "发送", "时间", "操作"],
    items.map((run) => [
      `<span class="mono">${escapeHtml(run.run_no)}</span>`,
      statusBadge(run.status),
      String(run.result_count),
      String(run.hit_count),
      String(run.send_count),
      formatTime(run.finished_at || run.started_at),
      `<button class="small-button" type="button" data-action="open-detail" data-type="task-run" data-id="${run.id}">查看详情</button>`,
    ])
  ) : emptyState("当前任务暂无运行记录。");
}

export const tasksSection = {
  key: "tasks",
  label: "自定义任务",
  description: "保留旧模块能力，但按脚本、任务、规则、运行记录拆成二级页面。",
  tabs: [
    { key: "scripts", label: "脚本上传", hint: "管理脚本包" },
    { key: "config", label: "任务配置", hint: "管理任务与调度" },
    { key: "rules", label: "接收规则", hint: "维护任务规则与联系人查询" },
    { key: "runs", label: "运行记录", hint: "查看旧模块运行详情" },
  ],
  async load(app) {
    await Promise.all([app.reloadScripts(), app.reloadTemplates(), app.reloadTasks()]);
    if (app.state.route.secondary === "runs") {
      await app.refreshTaskRuns();
    }
  },
  render(app) {
    if (app.state.route.secondary === "scripts") {
      return `<div class="content-grid">
        ${panel("上传脚本 ZIP", "继续沿用现有脚本上传模式，但单独放在这里。", renderScriptUpload(app), { span: 5 })}
        ${panel("脚本列表", "查看脚本入口文件和已上传版本。", renderScriptList(app), { span: 7 })}
      </div>`;
    }

    if (app.state.route.secondary === "rules") {
      return `<div class="content-grid">
        ${panel("任务接收规则", "规则编辑和任务选择分开管理，便于持续扩展。", renderTaskRuleForm(app), { span: 7 })}
        ${panel("规则列表", "这里只展示当前任务的规则。", renderTaskRuleList(app), { span: 5 })}
        ${panel("联系人检索", "保留原有联系人查询能力，方便核对规则命中对象。", renderContactSearch(app), { span: 12 })}
      </div>`;
    }

    if (app.state.route.secondary === "runs") {
      return `<div class="content-grid">
        ${panel("当前任务", "运行记录默认跟随当前选中任务。", `<div class="banner">${currentTask(app) ? `当前任务: ${escapeHtml(currentTask(app).task_name)}` : "请先在任务配置中选中一个任务。"}</div>${taskSelector(app, "task-run-current", app.state.taskRunPage.taskId || app.state.selectedTaskId)}`, { span: 4 })}
        ${panel("运行记录", "点击后统一在抽屉中看详情，不再把整包 JSON 直接铺开。", renderTaskRuns(app), { span: 8 })}
      </div>`;
    }

    return `<div class="content-grid">
      ${panel("任务表单", "旧的任务配置保留，但从脚本上传和规则管理中拆开。", renderTaskForm(app), { span: 7 })}
      ${panel("任务列表", "选中任务后，规则页和运行记录页都会复用当前上下文。", renderTaskList(app), { span: 5 })}
    </div>`;
  },
  bind(app) {
    const scriptForm = document.querySelector("#script-upload-form");
    if (scriptForm) {
      scriptForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
          const result = await api("/api/scripts/upload", { method: "POST", body: new FormData(scriptForm) });
          app.flash(`脚本上传成功: script_id=${result.script_id}, version_id=${result.script_version_id}`);
          scriptForm.reset();
          await app.reloadScripts();
          app.render();
        } catch (error) {
          app.flash(error.message, true);
        }
      });
    }

    const taskForm = document.querySelector("#task-form");
    if (taskForm) {
      const scriptSelect = taskForm.querySelector("#task_script_id");
      if (scriptSelect) {
        scriptSelect.addEventListener("change", () => {
          const versionSelect = taskForm.querySelector("#task_script_version_id");
          if (versionSelect) {
            versionSelect.innerHTML = renderVersionOptions(app, scriptSelect.value);
          }
        });
      }
      taskForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
          const payload = new FormData(taskForm);
          const body = {
            task_name: payload.get("task_name"),
            script_id: Number(payload.get("script_id")),
            script_version_id: Number(payload.get("script_version_id")),
            message_template_id: payload.get("message_template_id") ? Number(payload.get("message_template_id")) : null,
            enabled: payload.get("enabled") === "on",
            dedup_key_expr: payload.get("dedup_key_expr") || "",
            dedup_window_minutes: Number(payload.get("dedup_window_minutes") || 720),
            runtime_config: parseJson(payload.get("runtime_config"), {}),
          };
          const schedule = {
            interval_value: Number(payload.get("schedule_interval_value") || 20),
            interval_unit: payload.get("schedule_interval_unit") || "minute",
            enabled: true,
            timezone: "Asia/Shanghai",
            start_at: null,
            end_at: null,
          };
          if (app.state.editingTaskId) {
            await api(`/api/tasks/${app.state.editingTaskId}`, jsonRequest("PUT", body));
            await api(`/api/tasks/${app.state.editingTaskId}/schedule`, jsonRequest("PUT", schedule));
            app.flash("自定义任务已更新。");
          } else {
            const created = await api("/api/tasks", jsonRequest("POST", { ...body, schedule }));
            app.state.selectedTaskId = created.id;
            app.flash("自定义任务已创建。");
          }
          app.state.editingTaskId = null;
          await app.reloadTasks();
          await app.refreshTaskRuns();
          app.render();
        } catch (error) {
          app.flash(error.message, true);
        }
      });
    }

    document.querySelectorAll("[data-action='task-select-card']").forEach((button) => {
      button.addEventListener("click", async () => {
        await app.setSelectedTask(Number(button.dataset.id));
        app.render();
      });
    });

    document.querySelectorAll("[data-action='task-edit']").forEach((button) => {
      button.addEventListener("click", async () => {
        app.state.editingTaskId = Number(button.dataset.id);
        await app.setSelectedTask(Number(button.dataset.id));
        app.render();
      });
    });

    document.querySelectorAll("[data-action='task-enable'], [data-action='task-disable']").forEach((button) => {
      button.addEventListener("click", async () => {
        try {
          const action = button.dataset.action === "task-enable" ? "enable" : "disable";
          await api(`/api/tasks/${button.dataset.id}/${action}`, jsonRequest("POST", {}));
          app.flash(`任务已${action === "enable" ? "启用" : "停用"}。`);
          await app.reloadTasks();
          app.render();
        } catch (error) {
          app.flash(error.message, true);
        }
      });
    });

    document.querySelectorAll("[data-action='task-delete']").forEach((button) => {
      button.addEventListener("click", async () => {
        const task = app.state.tasks.find((item) => item.id === Number(button.dataset.id));
        const label = task ? `${task.task_name} (#${task.id})` : `#${button.dataset.id}`;
        if (!window.confirm(`确认删除任务 ${label} 吗？删除后该任务的调度、规则和运行记录都会一起清除。`)) {
          return;
        }
        try {
          await api(`/api/tasks/${button.dataset.id}`, { method: "DELETE" });
          if (app.state.selectedTaskId === Number(button.dataset.id)) {
            app.state.selectedTaskId = null;
          }
          if (app.state.editingTaskId === Number(button.dataset.id)) {
            app.state.editingTaskId = null;
          }
          if (app.state.taskRunPage.taskId === Number(button.dataset.id)) {
            app.state.taskRunPage.taskId = null;
          }
          app.flash("任务已删除。");
          await app.reloadTasks();
          await app.refreshTaskRuns();
          app.render();
        } catch (error) {
          app.flash(error.message, true);
        }
      });
    });

    document.querySelectorAll("[data-action='task-reset']").forEach((button) => {
      button.addEventListener("click", () => {
        app.state.editingTaskId = null;
        app.render();
      });
    });

    document.querySelectorAll("[data-action='task-run-dry']").forEach((button) => {
      button.addEventListener("click", async () => {
        try {
          const run = await api(`/api/tasks/${app.state.selectedTaskId}/run`, jsonRequest("POST", { dry_run: true, context_override: {} }));
          app.flash(`任务演练已触发，run_id=${run.id}`);
          await app.refreshTaskRuns();
          app.render();
        } catch (error) {
          app.flash(error.message, true);
        }
      });
    });

    document.querySelectorAll("[data-action='task-run-live']").forEach((button) => {
      button.addEventListener("click", async () => {
        try {
          const run = await api(`/api/tasks/${app.state.selectedTaskId}/run`, jsonRequest("POST", { dry_run: false, context_override: {} }));
          app.flash(`任务立即执行已触发，run_id=${run.id}`);
          await app.refreshTaskRuns();
          app.render();
        } catch (error) {
          app.flash(error.message, true);
        }
      });
    });

    document.querySelectorAll("[data-action='task-select']").forEach((select) => {
      select.addEventListener("change", async () => {
        await app.setSelectedTask(Number(select.value || 0) || null);
        if (app.state.route.secondary === "runs") {
          app.state.taskRunPage.taskId = app.state.selectedTaskId;
          await app.refreshTaskRuns();
        }
        app.render();
      });
    });

    const taskRuleForm = document.querySelector("#task-rule-form");
    if (taskRuleForm) {
      taskRuleForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
          const taskId = Number(document.querySelector("#task-select").value || app.state.selectedTaskId || 0);
          if (!taskId) {
            throw new Error("请先选择任务。");
          }
          const payload = new FormData(taskRuleForm);
          const body = {
            rule_name: payload.get("rule_name"),
            rule_type: payload.get("rule_type"),
            priority: Number(payload.get("priority") || 100),
            enabled: payload.get("enabled") === "on",
            source_field: payload.get("source_field") || "",
            target_table: "jcgkzx_autotask.org_contact",
            target_match_field: payload.get("target_match_field"),
            target_mobile_field: payload.get("target_mobile_field") || "mobile",
            include_self: payload.get("include_self") === "on",
            include_county: payload.get("include_county") === "on",
            include_city: payload.get("include_city") === "on",
            filter_json: parseJson(payload.get("filter_json"), {}),
            fixed_receivers: splitLines(payload.get("fixed_receivers")),
          };
          if (app.state.editingTaskRuleId) {
            await api(`/api/rules/${app.state.editingTaskRuleId}`, jsonRequest("PUT", body));
            app.flash("任务规则已更新。");
          } else {
            await api(`/api/tasks/${taskId}/rules`, jsonRequest("POST", body));
            app.flash("任务规则已创建。");
          }
          app.state.editingTaskRuleId = null;
          await app.setSelectedTask(taskId);
          await app.reloadTasks();
          app.render();
        } catch (error) {
          app.flash(error.message, true);
        }
      });
    }

    document.querySelectorAll("[data-action='task-rule-edit']").forEach((button) => {
      button.addEventListener("click", () => {
        app.state.editingTaskRuleId = Number(button.dataset.id);
        app.render();
      });
    });

    document.querySelectorAll("[data-action='task-rule-delete']").forEach((button) => {
      button.addEventListener("click", async () => {
        try {
          await api(`/api/rules/${button.dataset.id}`, { method: "DELETE" });
          app.flash("任务规则已删除。");
          app.state.editingTaskRuleId = null;
          await app.reloadTasks();
          app.render();
        } catch (error) {
          app.flash(error.message, true);
        }
      });
    });

    document.querySelectorAll("[data-action='task-rule-reset']").forEach((button) => {
      button.addEventListener("click", () => {
        app.state.editingTaskRuleId = null;
        app.render();
      });
    });

    const contactForm = document.querySelector("#contact-search-form");
    if (contactForm) {
      contactForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
          const payload = new FormData(contactForm);
          await app.loadContacts({
            keyword: payload.get("keyword") || "",
            sspcsdm: payload.get("sspcsdm") || "",
            xqdm: payload.get("xqdm") || "",
          });
          app.render();
        } catch (error) {
          app.flash(error.message, true);
        }
      });
    }

    document.querySelectorAll("[data-action='open-detail']").forEach((button) => {
      button.addEventListener("click", () => {
        app.openDrawer(button.dataset.type, Number(button.dataset.id));
      });
    });
  },
};
