const state = {
  scripts: [],
  templates: [],
  tasks: [],
  runs: [],
  contacts: [],
  selectedTaskId: null,
  editingTemplateId: null,
  editingTaskId: null,
  editingRuleId: null,
};

const dom = {};

document.addEventListener("DOMContentLoaded", () => {
  bindDom();
  bindEvents();
  loadAll();
});

function bindDom() {
  dom.healthPill = document.querySelector("#health-pill");
  dom.flash = document.querySelector("#flash");
  dom.summaryText = document.querySelector("#summary-text");
  dom.statScripts = document.querySelector("#stat-scripts");
  dom.statTemplates = document.querySelector("#stat-templates");
  dom.statTasks = document.querySelector("#stat-tasks");
  dom.statRuns = document.querySelector("#stat-runs");
  dom.scriptForm = document.querySelector("#script-form");
  dom.scriptList = document.querySelector("#script-list");
  dom.templateForm = document.querySelector("#template-form");
  dom.templateList = document.querySelector("#template-list");
  dom.taskForm = document.querySelector("#task-form");
  dom.taskList = document.querySelector("#task-list");
  dom.taskCurrent = document.querySelector("#task-current");
  dom.ruleForm = document.querySelector("#rule-form");
  dom.ruleList = document.querySelector("#rule-list");
  dom.contactForm = document.querySelector("#contact-form");
  dom.contactList = document.querySelector("#contact-list");
  dom.runList = document.querySelector("#run-list");
  dom.scriptSelect = document.querySelector("#task-script-id");
  dom.scriptVersionSelect = document.querySelector("#task-script-version-id");
  dom.templateSelect = document.querySelector("#task-template-id");
}

function bindEvents() {
  document.querySelector("#refresh-all").addEventListener("click", loadAll);
  dom.scriptForm.addEventListener("submit", submitScript);
  dom.templateForm.addEventListener("submit", submitTemplate);
  dom.taskForm.addEventListener("submit", submitTask);
  dom.ruleForm.addEventListener("submit", submitRule);
  dom.contactForm.addEventListener("submit", submitContacts);
  dom.scriptSelect.addEventListener("change", updateVersionSelect);

  document.querySelector("#template-reset").addEventListener("click", resetTemplateForm);
  document.querySelector("#task-reset").addEventListener("click", resetTaskForm);
  document.querySelector("#rule-reset").addEventListener("click", resetRuleForm);
  document.querySelector("#task-run-dry").addEventListener("click", () => runTask(true));
  document.querySelector("#task-run-live").addEventListener("click", () => runTask(false));

  dom.templateList.addEventListener("click", handleTemplateListClick);
  dom.taskList.addEventListener("click", handleTaskListClick);
  dom.ruleList.addEventListener("click", handleRuleListClick);
  dom.runList.addEventListener("click", handleRunListClick);
}

async function loadAll() {
  await loadHealth();
  await Promise.all([loadScripts(), loadTemplates(), loadTasks()]);
  await loadRuns();
  renderSummary();
}

async function loadHealth() {
  try {
    await api("/health");
    dom.healthPill.textContent = "服务正常";
    dom.healthPill.className = "pill pill-ok";
  } catch (error) {
    dom.healthPill.textContent = "服务异常";
    dom.healthPill.className = "pill pill-bad";
    flash(error.message, true);
  }
}

async function loadScripts() {
  state.scripts = await api("/api/scripts");
  renderScripts();
  updateScriptSelects();
}

async function loadTemplates() {
  state.templates = await api("/api/message-templates");
  renderTemplates();
  updateTemplateSelect();
}

async function loadTasks() {
  state.tasks = await api("/api/tasks");
  if (!state.selectedTaskId && state.tasks.length) {
    state.selectedTaskId = state.tasks[0].id;
  }
  if (state.selectedTaskId && !state.tasks.some((item) => item.id === state.selectedTaskId)) {
    state.selectedTaskId = state.tasks[0] ? state.tasks[0].id : null;
  }
  renderTasks();
  renderRules();
}

async function loadRuns() {
  const query = state.selectedTaskId ? `?task_id=${state.selectedTaskId}` : "";
  state.runs = await api(`/api/task-runs${query}`);
  renderRuns();
}

function renderSummary() {
  dom.statScripts.textContent = state.scripts.length;
  dom.statTemplates.textContent = state.templates.length;
  dom.statTasks.textContent = state.tasks.length;
  dom.statRuns.textContent = state.runs.length;
  dom.summaryText.textContent = state.selectedTaskId
    ? `当前选中任务 ID ${state.selectedTaskId}，最近加载 ${state.runs.length} 条运行记录`
    : "当前未选中任务";
}

function renderScripts() {
  if (!state.scripts.length) {
    dom.scriptList.innerHTML = emptyHtml("暂无脚本");
    return;
  }
  dom.scriptList.innerHTML = state.scripts.map((script) => {
    const versions = script.versions
      .map((version) => `${escapeHtml(version.version_no)} / ${escapeHtml(version.checksum.slice(0, 12))}`)
      .join("<br>");
    return `
      <article class="list-item">
        <h3>${escapeHtml(script.script_name)}</h3>
        <div class="item-meta">
          编码: ${escapeHtml(script.script_code)}<br>
          入口: ${escapeHtml(script.entry_file)}#${escapeHtml(script.entry_func || "run")}<br>
          版本:<br>${versions || "无"}
        </div>
      </article>
    `;
  }).join("");
}

function renderTemplates() {
  if (!state.templates.length) {
    dom.templateList.innerHTML = emptyHtml("暂无模板");
    return;
  }
  dom.templateList.innerHTML = state.templates.map((template) => `
    <article class="list-item ${state.editingTemplateId === template.id ? "selected" : ""}">
      <h3>${escapeHtml(template.template_name)}</h3>
      <div class="item-meta">
        编码: ${escapeHtml(template.template_code)}<br>
        状态: ${template.enabled ? "启用" : "停用"}<br>
        内容: ${escapeHtml(template.template_content)}
      </div>
      <div class="item-actions">
        <button class="small-button" data-action="edit-template" data-id="${template.id}" type="button">编辑</button>
      </div>
    </article>
  `).join("");
}

function renderTasks() {
  const current = currentTask();
  dom.taskCurrent.textContent = current
    ? `当前任务: ${current.task_name} / script_id=${current.script_id} / version_id=${current.script_version_id}`
    : "当前未选中任务";

  if (!state.tasks.length) {
    dom.taskList.innerHTML = emptyHtml("暂无任务");
    renderSummary();
    return;
  }

  dom.taskList.innerHTML = state.tasks.map((task) => {
    const schedule = task.schedules[0];
    const statusClass = task.enabled ? "" : "failed";
    return `
      <article class="list-item ${task.id === state.selectedTaskId ? "selected" : ""}">
        <div class="panel-head">
          <h3>${escapeHtml(task.task_name)}</h3>
          <span class="status ${statusClass}">${task.enabled ? "启用" : "停用"}</span>
        </div>
        <div class="item-meta">
          script_id=${task.script_id} / version_id=${task.script_version_id}<br>
          模板: ${task.message_template_id || "未配置"}<br>
          频率: ${schedule ? `${schedule.interval_value} ${schedule.interval_unit}` : "未配置"}<br>
          规则数: ${task.rules.length}
        </div>
        <div class="item-actions">
          <button class="small-button" data-action="select-task" data-id="${task.id}" type="button">选中</button>
          <button class="small-button" data-action="edit-task" data-id="${task.id}" type="button">编辑</button>
          <button class="small-button" data-action="${task.enabled ? "disable-task" : "enable-task"}" data-id="${task.id}" type="button">${task.enabled ? "停用" : "启用"}</button>
        </div>
      </article>
    `;
  }).join("");
  renderSummary();
}

function renderRules() {
  const task = currentTask();
  if (!task) {
    dom.ruleList.innerHTML = emptyHtml("先选中任务后再配置规则");
    return;
  }
  if (!task.rules.length) {
    dom.ruleList.innerHTML = emptyHtml("当前任务暂无规则");
    return;
  }
  dom.ruleList.innerHTML = task.rules.map((rule) => `
    <article class="list-item ${state.editingRuleId === rule.id ? "selected" : ""}">
      <h4>${escapeHtml(rule.rule_name)}</h4>
      <div class="item-meta">
        类型: ${escapeHtml(rule.rule_type)} / 优先级: ${rule.priority}<br>
        源字段: ${escapeHtml(rule.source_field || "-")} / 目标字段: ${escapeHtml(rule.target_match_field)}<br>
        上级匹配: self=${rule.include_self} county=${rule.include_county} city=${rule.include_city}<br>
        固定人员: ${escapeHtml((rule.fixed_receivers || []).join(","))}
      </div>
      <div class="item-actions">
        <button class="small-button" data-action="edit-rule" data-id="${rule.id}" type="button">编辑</button>
        <button class="small-button" data-action="delete-rule" data-id="${rule.id}" type="button">删除</button>
      </div>
    </article>
  `).join("");
}

function renderRuns() {
  if (!state.runs.length) {
    dom.runList.innerHTML = emptyHtml("暂无运行记录");
    return;
  }
  dom.runList.innerHTML = state.runs.map((run) => `
    <article class="list-item">
      <div class="panel-head">
        <h4>${escapeHtml(run.run_no)}</h4>
        <span class="status ${run.status.includes("fail") ? "failed" : ""}">${escapeHtml(run.status)}</span>
      </div>
      <div class="item-meta">
        任务: ${run.task_id} / 结果数: ${run.result_count} / 命中: ${run.hit_count} / 发送: ${run.send_count}<br>
        开始: ${escapeHtml(formatTime(run.started_at))}<br>
        结束: ${escapeHtml(formatTime(run.finished_at))}<br>
        错误: ${escapeHtml(run.error_message || "-")}
      </div>
      <div class="item-actions">
        <button class="small-button" data-action="view-run" data-id="${run.id}" type="button">查看详情</button>
      </div>
    </article>
  `).join("");
}

function renderContacts(items = state.contacts) {
  if (!items.length) {
    dom.contactList.innerHTML = emptyHtml("暂无联系人结果");
    return;
  }
  dom.contactList.innerHTML = items.map((contact) => `
    <article class="list-item">
      <h4>${escapeHtml(contact.xm || contact.sspcs || contact.xq || "未命名联系人")}</h4>
      <div class="item-meta">
        sspcsdm: ${escapeHtml(contact.sspcsdm || "-")} / xqdm: ${escapeHtml(contact.xqdm || "-")}<br>
        单位级别: ${escapeHtml(contact.unit_level)} / 职务: ${escapeHtml(contact.zw || "-")}<br>
        手机: ${escapeHtml((contact.phones || []).map((item) => item.mobile).join(","))}
      </div>
    </article>
  `).join("");
}

function updateScriptSelects() {
  const options = ['<option value="">请选择脚本</option>'].concat(
    state.scripts.map((script) => `<option value="${script.id}">${escapeHtml(script.script_name)} (${escapeHtml(script.script_code)})</option>`)
  );
  dom.scriptSelect.innerHTML = options.join("");
  if (!dom.scriptSelect.value && state.scripts.length) {
    dom.scriptSelect.value = String(state.scripts[0].id);
  }
  updateVersionSelect();
}

function updateVersionSelect() {
  const scriptId = Number(dom.scriptSelect.value || 0);
  const script = state.scripts.find((item) => item.id === scriptId);
  const versions = script ? script.versions : [];
  dom.scriptVersionSelect.innerHTML = ['<option value="">请选择版本</option>'].concat(
    versions.map((version) => `<option value="${version.id}">${escapeHtml(version.version_no)}</option>`)
  ).join("");
  if (versions.length) {
    dom.scriptVersionSelect.value = String(versions[0].id);
  }
}

function updateTemplateSelect() {
  dom.templateSelect.innerHTML = ['<option value="">不使用模板</option>'].concat(
    state.templates.map((template) => `<option value="${template.id}">${escapeHtml(template.template_name)}</option>`)
  ).join("");
}

function currentTask() {
  return state.tasks.find((item) => item.id === state.selectedTaskId) || null;
}

async function submitScript(event) {
  event.preventDefault();
  try {
    const formData = new FormData(dom.scriptForm);
    const result = await api("/api/scripts/upload", { method: "POST", body: formData });
    dom.scriptForm.reset();
    flash(`脚本上传成功: script_id=${result.script_id}, version_id=${result.script_version_id}`);
    await loadScripts();
  } catch (error) {
    flash(error.message, true);
  }
}

async function submitTemplate(event) {
  event.preventDefault();
  try {
    const form = new FormData(dom.templateForm);
    const payload = {
      template_name: form.get("template_name"),
      template_code: form.get("template_code"),
      template_content: form.get("template_content"),
      render_example: form.get("render_example") || "",
      enabled: form.get("enabled") === "on",
    };
    if (state.editingTemplateId) {
      await api(`/api/message-templates/${state.editingTemplateId}`, jsonRequest("PUT", payload));
      flash("模板更新成功");
    } else {
      await api("/api/message-templates", jsonRequest("POST", payload));
      flash("模板创建成功");
    }
    resetTemplateForm();
    await loadTemplates();
  } catch (error) {
    flash(error.message, true);
  }
}

async function submitTask(event) {
  event.preventDefault();
  try {
    const form = new FormData(dom.taskForm);
    const runtimeConfig = parseJson(form.get("runtime_config"), {});
    const schedule = {
      interval_value: Number(form.get("schedule_interval_value") || 0),
      interval_unit: form.get("schedule_interval_unit"),
      enabled: true,
    };
    const payload = {
      task_name: form.get("task_name"),
      script_id: Number(form.get("script_id")),
      script_version_id: Number(form.get("script_version_id")),
      message_template_id: form.get("message_template_id") ? Number(form.get("message_template_id")) : null,
      enabled: form.get("enabled") === "on",
      dedup_window_minutes: Number(form.get("dedup_window_minutes") || 0),
      runtime_config: runtimeConfig,
    };

    let taskId = state.editingTaskId;
    if (taskId) {
      await api(`/api/tasks/${taskId}`, jsonRequest("PUT", payload));
      await api(`/api/tasks/${taskId}/schedule`, jsonRequest("PUT", schedule));
      flash(`任务 ${taskId} 更新成功`);
    } else {
      const created = await api("/api/tasks", jsonRequest("POST", { ...payload, schedule }));
      taskId = created.id;
      state.selectedTaskId = taskId;
      flash(`任务 ${taskId} 创建成功`);
    }

    resetTaskForm();
    await loadTasks();
    await loadRuns();
  } catch (error) {
    flash(error.message, true);
  }
}

async function submitRule(event) {
  event.preventDefault();
  if (!state.selectedTaskId) {
    flash("请先选中任务", true);
    return;
  }
  try {
    const form = new FormData(dom.ruleForm);
    const payload = {
      rule_name: form.get("rule_name"),
      rule_type: form.get("rule_type"),
      priority: Number(form.get("priority") || 100),
      enabled: form.get("enabled") === "on",
      source_field: form.get("source_field") || "",
      target_table: "jcgkzx_autotask.org_contact",
      target_match_field: form.get("target_match_field"),
      target_mobile_field: form.get("target_mobile_field") || "mobile",
      include_self: form.get("include_self") === "on",
      include_county: form.get("include_county") === "on",
      include_city: form.get("include_city") === "on",
      filter_json: parseJson(form.get("filter_json"), {}),
      fixed_receivers: splitLines(form.get("fixed_receivers")),
    };

    if (state.editingRuleId) {
      await api(`/api/rules/${state.editingRuleId}`, jsonRequest("PUT", payload));
      flash("规则更新成功");
    } else {
      await api(`/api/tasks/${state.selectedTaskId}/rules`, jsonRequest("POST", payload));
      flash("规则创建成功");
    }

    resetRuleForm();
    await loadTasks();
  } catch (error) {
    flash(error.message, true);
  }
}

async function submitContacts(event) {
  event.preventDefault();
  try {
    const form = new FormData(dom.contactForm);
    const params = new URLSearchParams();
    ["keyword", "sspcsdm", "xqdm"].forEach((key) => {
      const value = String(form.get(key) || "").trim();
      if (value) {
        params.set(key, value);
      }
    });
    const result = await api(`/api/contacts?${params.toString()}`);
    state.contacts = result.items || [];
    renderContacts();
    flash(`联系人查询完成，共 ${result.total} 条`);
  } catch (error) {
    flash(error.message, true);
  }
}

async function runTask(dryRun) {
  if (!state.selectedTaskId) {
    flash("请先选中任务", true);
    return;
  }
  try {
    const run = await api(`/api/tasks/${state.selectedTaskId}/run`, jsonRequest("POST", { dry_run: dryRun, context_override: {} }));
    flash(`${dryRun ? "演练" : "发送"}已触发: run_id=${run.id}`);
    await loadRuns();
  } catch (error) {
    flash(error.message, true);
  }
}

async function handleTemplateListClick(event) {
  const button = event.target.closest("button[data-action='edit-template']");
  if (!button) {
    return;
  }
  const template = state.templates.find((item) => item.id === Number(button.dataset.id));
  if (!template) {
    return;
  }
  state.editingTemplateId = template.id;
  fillForm(dom.templateForm, {
    template_name: template.template_name,
    template_code: template.template_code,
    template_content: template.template_content,
    render_example: template.render_example,
  });
  dom.templateForm.elements.enabled.checked = template.enabled;
  renderTemplates();
}

async function handleTaskListClick(event) {
  const button = event.target.closest("button[data-action]");
  if (!button) {
    return;
  }
  const taskId = Number(button.dataset.id);
  if (button.dataset.action === "select-task") {
    state.selectedTaskId = taskId;
    await loadTasks();
    await loadRuns();
    return;
  }
  if (button.dataset.action === "edit-task") {
    const task = state.tasks.find((item) => item.id === taskId);
    if (!task) {
      return;
    }
    state.selectedTaskId = task.id;
    state.editingTaskId = task.id;
    fillTaskForm(task);
    renderTasks();
    renderRules();
    return;
  }
  if (button.dataset.action === "enable-task" || button.dataset.action === "disable-task") {
    const action = button.dataset.action === "enable-task" ? "enable" : "disable";
    await api(`/api/tasks/${taskId}/${action}`, jsonRequest("POST", {}));
    flash(`任务 ${taskId} 已${action === "enable" ? "启用" : "停用"}`);
    await loadTasks();
    await loadRuns();
  }
}

async function handleRuleListClick(event) {
  const button = event.target.closest("button[data-action]");
  if (!button) {
    return;
  }
  const task = currentTask();
  if (!task) {
    return;
  }
  const rule = task.rules.find((item) => item.id === Number(button.dataset.id));
  if (!rule) {
    return;
  }
  if (button.dataset.action === "edit-rule") {
    state.editingRuleId = rule.id;
    fillForm(dom.ruleForm, {
      rule_name: rule.rule_name,
      rule_type: rule.rule_type,
      source_field: rule.source_field,
      priority: rule.priority,
      target_mobile_field: rule.target_mobile_field,
      fixed_receivers: (rule.fixed_receivers || []).join("\n"),
      filter_json: JSON.stringify(rule.filter_json || {}, null, 2),
    });
    dom.ruleForm.elements.target_match_field.value = rule.target_match_field;
    dom.ruleForm.elements.enabled.checked = rule.enabled;
    dom.ruleForm.elements.include_self.checked = rule.include_self;
    dom.ruleForm.elements.include_county.checked = rule.include_county;
    dom.ruleForm.elements.include_city.checked = rule.include_city;
    renderRules();
    return;
  }
  if (button.dataset.action === "delete-rule") {
    await api(`/api/rules/${rule.id}`, { method: "DELETE" });
    flash(`规则 ${rule.id} 已删除`);
    await loadTasks();
    resetRuleForm();
  }
}

async function handleRunListClick(event) {
  const button = event.target.closest("button[data-action='view-run']");
  if (!button) {
    return;
  }
  try {
    const detail = await api(`/api/task-runs/${button.dataset.id}`);
    flash(JSON.stringify(detail, null, 2));
  } catch (error) {
    flash(error.message, true);
  }
}

function fillTaskForm(task) {
  fillForm(dom.taskForm, {
    task_name: task.task_name,
    dedup_window_minutes: task.dedup_window_minutes,
    runtime_config: JSON.stringify(task.runtime_config || {}, null, 2),
  });
  dom.taskForm.elements.enabled.checked = task.enabled;
  dom.scriptSelect.value = String(task.script_id);
  updateVersionSelect();
  dom.scriptVersionSelect.value = String(task.script_version_id);
  dom.templateSelect.value = task.message_template_id ? String(task.message_template_id) : "";
  const schedule = task.schedules[0];
  if (schedule) {
    dom.taskForm.elements.schedule_interval_value.value = schedule.interval_value;
    dom.taskForm.elements.schedule_interval_unit.value = schedule.interval_unit;
  }
}

function fillForm(form, values) {
  Object.entries(values).forEach(([key, value]) => {
    if (form.elements[key]) {
      form.elements[key].value = value ?? "";
    }
  });
}

function resetTemplateForm() {
  state.editingTemplateId = null;
  dom.templateForm.reset();
  dom.templateForm.elements.enabled.checked = true;
  renderTemplates();
}

function resetTaskForm() {
  state.editingTaskId = null;
  dom.taskForm.reset();
  dom.taskForm.elements.dedup_window_minutes.value = 720;
  dom.taskForm.elements.schedule_interval_value.value = 20;
  dom.taskForm.elements.schedule_interval_unit.value = "minute";
  dom.taskForm.elements.runtime_config.value = "{}";
  dom.taskForm.elements.enabled.checked = true;
  updateScriptSelects();
  updateTemplateSelect();
  renderTasks();
}

function resetRuleForm() {
  state.editingRuleId = null;
  dom.ruleForm.reset();
  dom.ruleForm.elements.priority.value = 100;
  dom.ruleForm.elements.target_mobile_field.value = "mobile";
  dom.ruleForm.elements.filter_json.value = "{}";
  dom.ruleForm.elements.enabled.checked = true;
  dom.ruleForm.elements.include_self.checked = true;
  renderRules();
}

function flash(message, isError = false) {
  dom.flash.textContent = message;
  dom.flash.style.borderColor = isError ? "rgba(167, 60, 44, 0.32)" : "rgba(13, 107, 87, 0.12)";
  dom.flash.style.background = isError ? "#f7ebe8" : "#ecf4f1";
}

function emptyHtml(text) {
  return `<article class="list-item"><div class="item-meta">${escapeHtml(text)}</div></article>`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function parseJson(value, fallback) {
  try {
    return JSON.parse(String(value || "").trim() || JSON.stringify(fallback));
  } catch (error) {
    throw new Error(`JSON 解析失败: ${error.message}`);
  }
}

function splitLines(value) {
  return String(value || "")
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function formatTime(value) {
  return value ? value.replace("T", " ").slice(0, 19) : "-";
}

function jsonRequest(method, payload) {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  };
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (response.status === 204) {
    return null;
  }
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new Error(data && data.detail ? data.detail : `请求失败: ${response.status}`);
  }
  return data;
}
